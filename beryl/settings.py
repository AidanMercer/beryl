import re

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import config

ENGINES = [
    ("duckduckgo", "https://duckduckgo.com/?q={}"),
    ("google", "https://www.google.com/search?q={}"),
    ("bing", "https://www.bing.com/search?q={}"),
    ("brave", "https://search.brave.com/search?q={}"),
    ("startpage", "https://www.startpage.com/sp/search?query={}"),
]


class Settings(QObject):
    """The s overlay: app settings that apply live and write back into
    config.toml (surgical single-line edits — the file stays the user's,
    comments and all)."""
    changed = Signal()
    applied = Signal()   # main refreshes the QML Config property on this —
                         # synchronously, so a follow-up reload sees the change
                         # (the file watcher's debounced reload is too late)

    def __init__(self, cfg, api=None, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._api = api

    def _engine_index(self):
        cur = self._cfg.get("search", "")
        return next((i for i, (_, u) in enumerate(ENGINES) if u == cur), -1)

    @Property("QVariantList", notify=changed)
    def items(self):
        i = self._engine_index()
        return [
            {
                "key": "search",
                "label": "search engine",
                "value": ENGINES[i][0] if i >= 0 else "custom",
                "detail": self._cfg.get("search", ""),
            },
            {
                "key": "transparent",
                "label": "transparent pages",
                "value": "on" if self._cfg.get("transparent_pages") else "off",
                "detail": "strip page backgrounds — the frost shows through",
            },
            {
                "key": "colors",
                "label": "page colors",
                "value": self._cfg.get("page_colors", "auto"),
                "detail": "palette on transparent pages — auto follows the theme",
            },
            {
                "key": "passwords",
                "label": "save passwords",
                "value": "on" if self._cfg.get("passwords", True) else "off",
                "detail": "offer to save & autofill logins (gp lists them)",
            },
        ]

    @Slot(str, int)
    def cycle(self, key, direction):
        if key == "search":
            i = self._engine_index()
            if i < 0:
                # a hand-edited custom url: cycling steps onto the preset ring
                i = 0 if direction > 0 else len(ENGINES) - 1
            else:
                i = (i + direction) % len(ENGINES)
            self._cfg["search"] = ENGINES[i][1]   # applies immediately
            self._persist("search", ENGINES[i][1])
        elif key == "transparent":
            on = not self._cfg.get("transparent_pages", False)
            self._cfg["transparent_pages"] = on
            self.applied.emit()
            self._persist("transparent_pages", on)
            # the current page shows the change right away; others follow on
            # their next load (user scripts apply per navigation)
            if self._api is not None:
                self._api.reloadRequested.emit(False)
        elif key == "colors":
            ring = ["auto", "dark", "light"]
            cur = self._cfg.get("page_colors", "auto")
            i = ring.index(cur) if cur in ring else 0
            self._cfg["page_colors"] = ring[(i + direction) % len(ring)]
            self.applied.emit()
            self._persist("page_colors", self._cfg["page_colors"])
            if self._api is not None:
                self._api.reloadRequested.emit(False)
        elif key == "passwords":
            on = not self._cfg.get("passwords", True)
            self._cfg["passwords"] = on
            self.applied.emit()
            self._persist("passwords", on)
            # creds.js is registered per-navigation, so autofill/capture starts
            # or stops on the next load; the toggle takes effect from there
            if self._api is not None:
                self._api.reloadRequested.emit(False)
        else:
            return
        self.changed.emit()

    def _persist(self, key, value):
        """Rewrite just this key's value in config.toml; everything else —
        indentation and comments included, even on the edited line — stays
        untouched. The config watcher reloads after our write, but it reloads
        exactly what we already set, so no self-write suppression is needed."""
        try:
            text = config.CONFIG_FILE.read_text()
        except OSError:
            if config.CONFIG_FILE.exists():
                # unreadable but present: writing would replace the user's
                # whole file with one line — the live cfg change still applies
                print("[settings] config.toml unreadable — not persisting",
                      flush=True)
                return
            text = ""
        if isinstance(value, bool):
            val = "true" if value else "false"
        else:
            val = f'"{value}"'
        # tolerate indentation, preserve an inline comment on the line
        pat = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*[^#\n]*(#.*)?$", re.M)

        def repl(m):
            comment = (m.group(2) or "").rstrip()
            return f"{m.group(1)}{key} = {val}" + (f"   {comment}" if comment else "")

        if pat.search(text):
            text = pat.sub(repl, text, count=1)
        else:
            text = f"{key} = {val}\n" + text
        try:
            config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = config.CONFIG_FILE.with_suffix(".toml.tmp")
            tmp.write_text(text)
            tmp.replace(config.CONFIG_FILE)
        except OSError as e:
            print(f"[settings] config write failed: {e}", flush=True)
