import json

from PySide6.QtCore import QObject, QTimer, Slot

from . import config

_PATH = config.DATA_HOME / "session.json"


class Session(QObject):
    """Debounced persistence of the shared tab pool plus which tab each window
    was showing. Restore builds dead rows (live=false) so a 20-tab session
    costs one renderer per window at startup, not twenty. Saves are disarmed
    until arm() so restoring doesn't immediately re-save."""

    def __init__(self, cfg, manager, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._mgr = manager
        self._armed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.save)

    def arm(self):
        """Enable saves once startup restore/argv tabs are in place."""
        self._armed = True

    def watch(self, tabs):
        tabs.countChanged.connect(self.poke)
        tabs.currentIndexChanged.connect(self.poke)
        tabs.currentInfoChanged.connect(self.poke)

    @Slot()
    def poke(self):
        if self._armed:
            self._timer.start()

    @Slot()
    def save(self):
        snap = self._mgr.snapshot()
        if not snap["tabs"] or not snap["windows"]:
            return   # mid-quit race — never overwrite the session with nothing
        data = {"v": 3, **snap}
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
        """Rebuild the pool and one window per saved entry; True if anything
        was restored. Understands v3 (shared pool), v2 (tabs-per-window) and
        the original v1 single-window shape."""
        if not self._cfg.get("restore_session", True):
            return False
        try:
            data = json.loads(_PATH.read_text())
        except (OSError, ValueError):
            return False

        v = data.get("v", 1)
        if v >= 3:
            tabs = data.get("tabs", [])
            shown = [w.get("shown", 0) for w in data.get("windows", [])]
            active = int(data.get("active", 0))
            awin = int(data.get("awin", 0))
        elif v == 2:
            # flatten each window's tab list into one pool, keep each window
            # pointed at what was its active tab
            tabs, shown, active, awin = [], [], 0, 0
            for wi, w in enumerate(data.get("windows", [])):
                if not isinstance(w, dict):
                    continue
                base = len(tabs)
                wtabs = [t for t in w.get("tabs", []) if t.get("url")]
                if not wtabs:
                    continue
                tabs.extend(wtabs)
                shown.append(base + max(0, min(int(w.get("active", 0)),
                                               len(wtabs) - 1)))
                if wi == 0:
                    active = shown[-1]
        else:
            tabs = data.get("tabs", [])
            shown = [int(data.get("active", 0))]
            active = shown[0]
            awin = 0

        rows = [(t.get("url", ""), t.get("title", ""))
                for t in tabs if isinstance(t, dict) and t.get("url")]
        if not rows or not shown:
            return False
        self._mgr.restore(rows, shown, active, awin)
        return bool(self._mgr.handles)

    def clear(self):
        try:
            _PATH.unlink(missing_ok=True)
        except OSError:
            pass
