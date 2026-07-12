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
        self._items = []   # running downloads: (seq, item) — python refs keep
                           # the Qt wrappers alive; pruned once finished/logged
        self._seq = 0
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
        self._seq += 1
        self._items.append((self._seq, item))
        item.accept()
        self.changed.emit()

    def _dedupe(self, target, name):
        # in-flight names count as taken too — two simultaneous "report.pdf"
        # downloads would otherwise both stream into the same file
        inflight = {it.downloadFileName() for _, it in self._items
                    if not it.isFinished()}
        def taken(n):
            return (target / n).exists() or n in inflight
        if not taken(name):
            return name
        p = Path(name)
        for n in range(2, 1000):
            fresh = f"{p.stem} ({n}){p.suffix}"
            if not taken(fresh):
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
        # finished either way: the wrapper has nothing left to say (the log has
        # the record) — drop the ref so it doesn't accumulate for the lifetime
        self._items = [(s, it) for s, it in self._items if it is not item]
        self.changed.emit()

    # ---- statusbar glance -------------------------------------------------------
    @Property(int, notify=changed)
    def activeCount(self):
        return sum(1 for _, it in self._items if not it.isFinished())

    @Property(int, notify=changed)
    def percent(self):
        """Aggregate progress across running downloads, -1 when idle/unknown.
        Unknown-size downloads are left out entirely — counting their bytes
        against a zero total pushed the aggregate past 100%."""
        got = total = 0
        for _, it in self._items:
            if it.isFinished() or it.totalBytes() <= 0:
                continue
            got += max(0, it.receivedBytes())
            total += it.totalBytes()
        if total <= 0:
            return -1
        return min(100, int(got * 100 / total))

    # ---- the gd overlay ---------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def items(self):
        """Running downloads first (live progress), then the finished log,
        newest first. Each row carries a stable `key` so the overlay's
        selection and actions survive live reordering."""
        rows = []
        for seq, it in reversed(self._items):
            if it.isFinished():
                continue
            total = max(0, it.totalBytes())
            got = max(0, it.receivedBytes())
            rows.append({
                "key": f"run:{seq}",
                "name": it.downloadFileName(), "dir": it.downloadDirectory(),
                "path": str(Path(it.downloadDirectory()) / it.downloadFileName()),
                "size": total, "got": got,
                "percent": int(got * 100 / total) if total > 0 else -1,
                "ts": 0, "state": "downloading",
            })
        for e in reversed(self._log):
            rows.append({
                "key": f"log:{e.get('ts', 0)}:{e['path']}",
                "name": e.get("name", ""), "dir": e.get("dir", ""),
                "path": e["path"], "size": e.get("size", 0), "got": 0,
                "percent": -1, "ts": e.get("ts", 0),
                "state": "done" if Path(e["path"]).exists() else "missing",
            })
        return rows

    def has_any(self):
        return bool(self._log) or any(not it.isFinished() for _, it in self._items)

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
    def remove(self, key):
        """x in the overlay: cancel THE running download the row points at
        (matched by its stable key, never by path — a stale log row must not
        cancel an active re-download of the same file), or drop a finished
        entry from the log. The file on disk is never touched."""
        if key.startswith("run:"):
            seq = int(key[4:])
            for s, it in self._items:
                if s == seq and not it.isFinished():
                    it.cancel()
                    return
            return
        if not key.startswith("log:"):
            return
        ts_s, _, path = key[4:].partition(":")
        n = len(self._log)
        self._log = [e for e in self._log
                     if not (e.get("path") == path and str(e.get("ts", 0)) == ts_s)]
        if len(self._log) != n:
            self._write_log()
            self.changed.emit()
