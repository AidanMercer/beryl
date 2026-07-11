import json
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

from . import config

_LOG_PATH = config.DATA_HOME / "downloads.json"
_LOG_CAP = 100


class Downloads(QObject):
    """Bare downloads: everything auto-saves into download_dir (deduped names),
    the status bar shows an aggregate glance while anything is running, and a
    toast announces where each file landed. Finished downloads land in a small
    json log so the gd overlay can show recent ones across restarts."""
    changed = Signal()
    toast = Signal(str, bool)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._items = []   # python refs keep the Qt wrappers alive
        self._log = []     # [{name, dir, path, size, ts}] oldest first
        try:
            data = json.loads(_LOG_PATH.read_text())
            if isinstance(data, list):
                self._log = [e for e in data if isinstance(e, dict) and e.get("path")]
        except (OSError, ValueError):
            pass

    def adopt(self, item):
        target = Path(self._cfg["download_dir"]).expanduser()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        item.setDownloadDirectory(str(target))
        item.setDownloadFileName(self._dedupe(target, item.downloadFileName()))

        item.receivedBytesChanged.connect(self.changed)
        item.totalBytesChanged.connect(self.changed)
        item.isFinishedChanged.connect(lambda it=item: self._finished(it))
        self._items.append(item)
        item.accept()
        self.changed.emit()

    @staticmethod
    def _dedupe(target, name):
        if not (target / name).exists():
            return name
        p = Path(name)
        for n in range(2, 1000):
            fresh = f"{p.stem} ({n}){p.suffix}"
            if not (target / fresh).exists():
                return fresh
        return name

    def _write_log(self):
        try:
            config.DATA_HOME.mkdir(parents=True, exist_ok=True)
            tmp = _LOG_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._log))
            tmp.replace(_LOG_PATH)
        except OSError as e:
            print(f"[downloads] log save failed: {e}", flush=True)

    def _finished(self, item):
        state = item.state()
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self._log.append({
                "name": item.downloadFileName(),
                "dir": item.downloadDirectory(),
                "path": str(Path(item.downloadDirectory()) / item.downloadFileName()),
                "size": max(item.receivedBytes(), item.totalBytes(), 0),
                "ts": int(time.time()),
            })
            del self._log[:-_LOG_CAP]
            self._write_log()
            self.toast.emit(f"↓ {item.downloadFileName()}", False)
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            self.toast.emit(f"download failed: {item.downloadFileName()}", True)
        # cancelled: silent — the user did it
        self.changed.emit()

    # ---- statusbar glance -------------------------------------------------------
    @Property(int, notify=changed)
    def activeCount(self):
        return sum(1 for it in self._items if not it.isFinished())

    @Property(int, notify=changed)
    def percent(self):
        """Aggregate progress across running downloads, -1 when idle/unknown."""
        got = total = 0
        for it in self._items:
            if it.isFinished():
                continue
            got += max(0, it.receivedBytes())
            total += max(0, it.totalBytes())
        if total <= 0:
            return -1
        return int(got * 100 / total)

    # ---- the gd overlay ---------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def items(self):
        """Running downloads first (live progress), then the finished log,
        newest first."""
        rows = []
        for it in reversed(self._items):
            if it.isFinished():
                continue
            total = max(0, it.totalBytes())
            got = max(0, it.receivedBytes())
            rows.append({
                "name": it.downloadFileName(), "dir": it.downloadDirectory(),
                "path": str(Path(it.downloadDirectory()) / it.downloadFileName()),
                "size": total, "got": got,
                "percent": int(got * 100 / total) if total > 0 else -1,
                "ts": 0, "state": "downloading",
            })
        for e in reversed(self._log):
            rows.append({
                "name": e.get("name", ""), "dir": e.get("dir", ""),
                "path": e["path"], "size": e.get("size", 0), "got": 0,
                "percent": -1, "ts": e.get("ts", 0),
                "state": "done" if Path(e["path"]).exists() else "missing",
            })
        return rows

    def has_any(self):
        return bool(self._log) or any(not it.isFinished() for it in self._items)

    @Slot(str)
    def openPath(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot(str)
    def openDir(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    @Slot(str)
    def yank(self, path):
        QGuiApplication.clipboard().setText(path)
        self.toast.emit(f"yanked {path}", False)

    @Slot(str)
    def remove(self, path):
        """x in the overlay: cancel a running download, or drop a finished one
        from the log — the file on disk is never touched."""
        for it in self._items:
            if not it.isFinished() and \
                    str(Path(it.downloadDirectory()) / it.downloadFileName()) == path:
                it.cancel()
                return
        n = len(self._log)
        self._log = [e for e in self._log if e.get("path") != path]
        if len(self._log) != n:
            self._write_log()
            self.changed.emit()
