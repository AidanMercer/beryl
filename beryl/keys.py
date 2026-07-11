from fnmatch import fnmatch
from urllib.parse import urlsplit

from PySide6.QtCore import Property, QEvent, QObject, Qt, QTimer, Signal, Slot

# The vim layer's entry point: every key in the app passes through KeyFilter
# (installed on the root window) before the focused item — the WebEngineView —
# ever sees it. Consuming = the page never knows; passing = zero added latency.
# QML Keys handlers can't do this job: WebEngineView swallows keys without
# re-propagating, and moving focus off the view would break IME.

DEFAULT_BINDS = {
    "normal": {
        "j": "scroll-down", "k": "scroll-up",
        "d": "scroll-half-down", "u": "scroll-half-up",
        "gg": "scroll-top", "G": "scroll-bottom",
        "H": "back", "L": "forward",
        "r": "reload", "R": "reload-bypass",
        "o": "cmdline-open :open ", "O": "cmdline-open-url",
        "t": "cmdline-open :tabopen ",
        "T": "cmdline-open :tab ",
        "W": "cmdline-open :winopen ",
        "gw": "detach",
        "b": "bookmarks-open",
        "h": "help",
        "f": "hint", "F": "hint-tab",
        "gi": "focus-input",
        "i": "mode-insert",
        "x": "tab-close", "X": "tab-undo-close",
        "J": "tab-prev", "K": "tab-next",
        "gu": "url-up", "gU": "url-root",
        "zi": "zoom-in", "zo": "zoom-out", "zz": "zoom-reset",
        "m": "mark-set", "'": "mark-jump",
        "yy": "yank-url",
        "p": "paste-go", "P": "paste-go-tab",
        "*": "bookmark-toggle",
        ":": "cmdline-open :", "/": "cmdline-open /",
        "n": "search-next", "N": "search-prev",
        "?": "help",
        "<Esc>": "search-stop",
        "<S-Esc>": "mode-passthrough",
        "ZZ": "quit",
    },
    "insert": {
        "<Esc>": "mode-normal",
    },
    "passthrough": {
        # plain Esc has to reach the remote desktop, so the way out is a chord
        # the remote won't use. both of these exit passthrough:
        "<S-Esc>": "mode-normal",       # shift+esc
        "<C-A-Esc>": "mode-normal",     # ctrl+alt+esc
    },
}

# shown in the status bar so the escape hatch is never a secret
PASSTHROUGH_HINT = "ctrl+alt+esc to exit"

_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock,
    Qt.Key.Key_ScrollLock, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
}

_SPECIAL = {
    Qt.Key.Key_Escape: "Esc", Qt.Key.Key_Return: "CR", Qt.Key.Key_Enter: "CR",
    Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backtab: "Tab",
    Qt.Key.Key_Backspace: "BS", Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_PageUp: "PgUp", Qt.Key.Key_PageDown: "PgDn",
    Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
    Qt.Key.Key_Insert: "Ins", Qt.Key.Key_Delete: "Del",
}


def keystr(ev):
    """One string vocabulary for keys, shared with the binds TOML: printables
    are themselves ("j", "G", ":"), everything else is angle notation
    ("<Esc>", "<C-d>", "<S-Esc>"). None for bare modifiers, "DEAD" for dead
    keys (consumed but never fed to the sequence matcher)."""
    key = ev.key()
    if key in _MODIFIER_KEYS:
        return None
    if Qt.Key.Key_Dead_Grave <= key <= Qt.Key.Key_Dead_Longsolidusoverlay:
        return "DEAD"

    mods = ev.modifiers()
    ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    meta = bool(mods & Qt.KeyboardModifier.MetaModifier)
    shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

    text = ev.text()
    if not ctrl and not alt and not meta and key != Qt.Key.Key_Space \
            and text and text.isprintable():
        return text   # shift is already baked into the char ("G", ":")

    name = _SPECIAL.get(key)
    if name is None:
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
            name = f"F{key - Qt.Key.Key_F1 + 1}"
        elif 0x20 <= key <= 0x7E:
            name = chr(key).lower()
        else:
            return None
    prefix = ("C-" if ctrl else "") + ("A-" if alt else "") + ("M-" if meta else "")
    if shift:
        prefix += "S-"
    if prefix or len(name) > 1:
        return f"<{prefix}{name}>"
    return name


class KeyController(QObject):
    """The modal state machine. Lives in Python so it's testable headless and
    the binds come straight from the TOML; QML only renders mode + pending."""
    modeChanged = Signal()
    pendingChanged = Signal()
    promptAnswer = Signal(str)   # "y" / "n" / "<Esc>" while a prompt bar is up
    listKey = Signal(str)        # every key while a list overlay (bookmarks) is up

    def __init__(self, cfg, api, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._api = api
        self._hints = None
        self._registry = {}
        self._mode = "normal"
        self._binds = {}
        self._count = ""
        self._seq = ""
        self._capture = None       # (command, count) waiting for one raw key
        self._pressed = {}         # key code → did we consume its press?
        self._mode_reason = "manual"
        self._prompt_active = False
        # passthrough intent is per-tab, not per-host: switching tabs must not
        # forget what you chose. _pt_override[uid] = {"host": h, "on": bool}
        # records a manual on/off; absent = decide automatically by site.
        self._cur_uid = -1
        self._cur_host = ""
        self._pt_override = {}

        self._seq_timer = QTimer(self)
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(self._seq_timeout)

        self.reload_binds()

    def set_registry(self, registry):
        self._registry = registry

    def set_hints(self, hints):
        self._hints = hints

    def reload_binds(self):
        """DEFAULT_BINDS with the config's [binds.*] merged over it per key;
        an empty string unbinds a default."""
        merged = {}
        user = self._cfg.get("binds", {})
        for mode, table in DEFAULT_BINDS.items():
            m = dict(table)
            over = user.get(mode)
            if isinstance(over, dict):
                for k, v in over.items():
                    if isinstance(v, str):
                        m[k] = v
            merged[mode] = {k: v for k, v in m.items() if v}
        self._binds = merged

    # ---- state shown in the statusbar ---------------------------------------
    @Property(str, notify=modeChanged)
    def mode(self):
        return self._mode

    @Property(str, notify=pendingChanged)
    def pending(self):
        return self._count + self._seq

    @Property(str, notify=modeChanged)
    def modeHint(self):
        return PASSTHROUGH_HINT if self._mode == "passthrough" else ""

    def set_mode(self, mode, reason="manual"):
        if mode == self._mode:
            return
        old = self._mode
        self._mode = mode
        self._mode_reason = reason
        # remember a manual passthrough choice against the current tab, so it
        # survives tab switches and only the same tab navigating elsewhere
        # forgets it
        if reason == "manual" and self._cur_uid >= 0:
            if mode == "passthrough":
                self._pt_override[self._cur_uid] = {"host": self._cur_host, "on": True}
            elif mode == "normal" and old == "passthrough":
                self._pt_override[self._cur_uid] = {"host": self._cur_host, "on": False}
        self._reset_pending()
        self.modeChanged.emit()
        # leaving insert/passthrough: blur the page's editable so stray input
        # (and IME composition) has nowhere to land in normal mode
        if mode == "normal" and old in ("insert", "passthrough"):
            self._api.js("if(document.activeElement)document.activeElement.blur()")

    @Slot(bool)
    def pageEditable(self, on):
        """editable.js reports page focus moving in/out of a text field (only
        the visible tab's bridge forwards). Auto-entered insert drops on blur;
        a manual `i` doesn't get cancelled by page focus noise."""
        if on and self._mode == "normal":
            self.set_mode("insert", reason="page")
        elif not on and self._mode == "insert" and self._mode_reason == "page":
            self.set_mode("normal")

    def tab_context(self, uid, url):
        """Called when the current tab or its url changes. Decides passthrough
        from the tab's manual override if it has one (surviving tab switches),
        otherwise automatically by site. Only an auto-entered passthrough is
        auto-exited — a manual choice is never overridden by a title ping."""
        host = urlsplit(url).hostname or ""
        self._cur_uid = uid
        self._cur_host = host

        # a tab that navigated to a genuinely different host forgets its
        # manual override (the choice was about the old page); a stale manual
        # passthrough then becomes fair game to auto-manage again
        ov = self._pt_override.get(uid)
        dropped = ov is not None and ov["host"] != host
        if dropped:
            del self._pt_override[uid]
            ov = None

        if ov is not None:
            want = ov["on"]
        else:
            want = any(fnmatch(host, pat)
                       for pat in self._cfg.get("passthrough_sites", []))

        if want and self._mode in ("normal", "insert"):
            self.set_mode("passthrough", reason="site")
        elif not want and self._mode == "passthrough" \
                and (self._mode_reason == "site" or dropped):
            self.set_mode("normal")

    @Slot(bool)
    def setPromptActive(self, on):
        """The permission bar is up: y/n/Esc answer it from normal mode."""
        self._prompt_active = bool(on)

    @Slot()
    def cmdlineClosed(self):
        """The cmdline TextField calls this when it closes (esc or accept)."""
        if self._mode == "command":
            self.set_mode("normal")

    @Slot(str)
    def setMode(self, mode):
        """QML-callable (overlays hand focus back with setMode('normal'))."""
        self.set_mode(mode)

    # ---- the filter feeds these ----------------------------------------------
    def press(self, ev):
        """Record the decision per key code so the paired release is always
        consumed (or passed) identically — even when this press switches
        modes. Orphan keyups confuse pages that track keydown/keyup."""
        consumed = self._press(ev)
        self._pressed[ev.key()] = consumed
        return consumed

    def release(self, ev):
        return self._pressed.pop(ev.key(), False)

    def _press(self, ev):
        if self._mode == "command":
            return False          # the cmdline TextField owns its own keys
        if self._mode == "hint":
            ks = keystr(ev)
            if ks and ks not in ("DEAD",) and self._hints is not None:
                self._hints.key(ks)
            return True           # hint mode owns every key
        if self._mode == "bookmarks":
            ks = keystr(ev)
            if ks and ks != "DEAD":
                self.listKey.emit(ks)
            return True           # the overlay owns every key
        if self._mode == "help":
            ks = keystr(ev)
            if ks in ("<Esc>", "h", "?", "q"):
                self.set_mode("normal")
            return True           # help swallows everything (page can't scroll under it)
        if self._mode in ("insert", "passthrough"):
            ks = keystr(ev)
            cmdline = self._binds[self._mode].get(ks) if ks else None
            if cmdline:
                self._dispatch(cmdline, 1)
                return True
            return False          # everything else reaches the page natively

        # ---- normal mode ----
        ks = keystr(ev)
        if ks is None:
            return False          # bare modifier — page may track it
        if ks == "DEAD":
            return True           # never let composition start in normal mode

        if self._prompt_active and ks in ("y", "n", "<Esc>"):
            self.promptAnswer.emit(ks)
            return True

        if self._capture is not None:
            cmdline, count = self._capture
            self._capture = None
            self._update_pending()
            if len(ks) == 1:
                self._dispatch(f"{cmdline} {ks}", count)
            return True

        if ks.isdigit() and not self._seq and (self._count or ks != "0"):
            self._count += ks
            self._update_pending()
            return True

        binds = self._binds["normal"]
        seq = self._seq + ks
        is_prefix = any(k != seq and k.startswith(seq) for k in binds)
        if seq in binds and not is_prefix:
            self._fire(binds[seq])
            return True
        if seq in binds or is_prefix:
            self._seq = seq
            self._update_pending()
            self._seq_timer.start(int(self._cfg.get("seq_timeout_ms", 800)))
            return True

        # dead end: drop the pending sequence, retry this key on its own
        had_pending = bool(self._seq)
        self._reset_pending()
        if had_pending and ks in binds \
                and not any(k != ks and k.startswith(ks) for k in binds):
            self._fire(binds[ks])
            return True
        if len(ks) == 1:
            return True           # unbound printable — never leak typing into the page
        return False              # unbound special/modifier combo — page's problem

    # ---- internals -------------------------------------------------------------
    def _fire(self, cmdline):
        try:
            count = max(1, int(self._count)) if self._count else 1
        except ValueError:
            count = 1
        self._reset_pending()
        self._dispatch(cmdline, count)

    def _dispatch(self, cmdline, count):
        name, _, arg = cmdline.partition(" ")
        cmd = self._registry.get(name)
        if cmd is None:
            self._api.toast.emit(f"unknown command: {name}", True)
            return
        if getattr(cmd, "takes_key", False) and not arg:
            self._capture = (name, count)
            self._update_pending()
            return
        cmd.fn(count=count, arg=arg)

    def _seq_timeout(self):
        seq = self._seq
        binds = self._binds["normal"]
        if seq and seq in binds:
            self._fire(binds[seq])   # e.g. a bind that's also a longer bind's prefix
        else:
            self._reset_pending()

    def _reset_pending(self):
        self._seq_timer.stop()
        self._count = ""
        self._seq = ""
        self._capture = None
        self._update_pending()

    def _update_pending(self):
        self.pendingChanged.emit()


class KeyFilter(QObject):
    """Installed on the root QQuickWindow — sees every key event before the
    delivery agent hands it to the focused item."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._c = controller

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.KeyPress:
            return self._c.press(ev)
        if t == QEvent.Type.KeyRelease:
            return self._c.release(ev)
        return False
