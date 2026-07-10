import json

from PySide6.QtCore import QObject, QTimer, Slot

from . import config

_PATH = config.DATA_HOME / "session.json"


class Session(QObject):
    """Debounced tab-set persistence. Restore builds dead rows (live=false) so
    a 20-tab session costs one renderer at startup, not twenty."""

    def __init__(self, cfg, tabs, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._tabs = tabs
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.save)

    def wire(self):
        """Connect after restore so restoring doesn't immediately re-save."""
        self._tabs.countChanged.connect(self.poke)
        self._tabs.currentIndexChanged.connect(self.poke)
        self._tabs.currentInfoChanged.connect(self.poke)

    @Slot()
    def poke(self):
        self._timer.start()

    @Slot()
    def save(self):
        data = {"v": 1, "active": self._tabs.currentIndex,
                "tabs": [{"url": u, "title": t} for u, t in self._tabs.snapshot() if u]}
        try:
            config.DATA_HOME.mkdir(parents=True, exist_ok=True)
            tmp = _PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(_PATH)
        except OSError as e:
            print(f"[session] save failed: {e}", flush=True)

    def flush(self):
        self._timer.stop()
        self.save()

    def restore(self):
        """True if any tabs were restored."""
        if not self._cfg.get("restore_session", True):
            return False
        try:
            data = json.loads(_PATH.read_text())
        except (OSError, ValueError):
            return False
        rows = [(t.get("url", ""), t.get("title", ""))
                for t in data.get("tabs", []) if t.get("url")]
        if not rows:
            return False
        self._tabs.restoreRows(rows, int(data.get("active", 0)))
        return True

    def clear(self):
        try:
            _PATH.unlink(missing_ok=True)
        except OSError:
            pass
