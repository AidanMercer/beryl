from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot


class Downloads(QObject):
    """Bare downloads: everything auto-saves into download_dir (deduped names),
    the status bar shows an aggregate glance while anything is running, and a
    toast announces where each file landed. No panel — that's the point."""
    changed = Signal()
    toast = Signal(str, bool)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._items = []   # python refs keep the Qt wrappers alive

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

    def _finished(self, item):
        self.toast.emit(f"↓ {item.downloadFileName()}", False)
        self.changed.emit()

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
