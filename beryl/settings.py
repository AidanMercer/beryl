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
    comments and all). One entry so far: the default search engine."""
    changed = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg

    def _engine_index(self):
        cur = self._cfg.get("search", "")
        return next((i for i, (_, u) in enumerate(ENGINES) if u == cur), -1)

    @Property("QVariantList", notify=changed)
    def items(self):
        i = self._engine_index()
        return [{
            "key": "search",
            "label": "search engine",
            "value": ENGINES[i][0] if i >= 0 else "custom",
            "detail": self._cfg.get("search", ""),
        }]

    @Slot(str, int)
    def cycle(self, key, direction):
        if key != "search":
            return
        i = self._engine_index()
        if i < 0:
            # a hand-edited custom url: cycling steps onto the preset ring
            i = 0 if direction > 0 else len(ENGINES) - 1
        else:
            i = (i + direction) % len(ENGINES)
        self._cfg["search"] = ENGINES[i][1]   # applies immediately
        self._persist("search", ENGINES[i][1])
        self.changed.emit()

    def _persist(self, key, value):
        """Rewrite just this key's line in config.toml; everything else —
        comments included — stays untouched. The config watcher reloads after
        our write, but it reloads exactly what we already set, so no self-write
        suppression is needed."""
        try:
            text = config.CONFIG_FILE.read_text()
        except OSError:
            text = ""
        line = f'{key} = "{value}"'
        pat = re.compile(rf"^{key}\s*=.*$", re.M)
        text = pat.sub(line, text, count=1) if pat.search(text) else line + "\n" + text
        try:
            config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = config.CONFIG_FILE.with_suffix(".toml.tmp")
            tmp.write_text(text)
            tmp.replace(config.CONFIG_FILE)
        except OSError as e:
            print(f"[settings] config write failed: {e}", flush=True)
