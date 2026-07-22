import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal, Slot


class FilePicker(QObject):
    """Runs mica as the file chooser for page uploads (<input type=file>).

    QtWebEngine only draws its own bare QtQuick dialog when nobody claims
    fileDialogRequested, and Qt's native path is dead here anyway
    (QT_QPA_PLATFORMTHEME=qt6ct exposes no native file dialog, so the
    xdg-desktop-portal → mica chain never gets asked). So we claim the signal
    and drive `mica --pick` ourselves — the same picker the portal runs, minus
    the portal.

    mica writes the selection to an --out file and quits; we read it when the
    process exits and answer the waiting request over picked(). One picker at a
    time: a second request while mica is up is refused, and QML rejects it.
    """

    picked = Signal(int, "QStringList")   # request id, chosen paths ([] = cancelled)
    toast = Signal(str, bool)             # message, isError

    def __init__(self, mica_dir=None, parent=None):
        super().__init__(parent)
        d = mica_dir or os.environ.get("BERYL_MICA_DIR") or "~/dev/mica"
        self._dir = Path(d).expanduser()
        self._proc = None
        self._out = ""
        self._id = 0
        self._pending = 0        # id of the request mica is currently answering
        self._last_dir = str(Path.home())   # picks resume where the last one left off

    # ---- QML side ------------------------------------------------------------
    @Slot(str, str, result=int)
    def pick(self, mode, name=""):
        """mode: file | files | dir | save. Returns the request id to match
        against picked(), or -1 if no picker could be opened (QML then rejects
        the page's request rather than leaving it hanging)."""
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self.toast.emit("a file picker is already open", True)
            return -1

        # always the repo, never a `mica` off PATH: ~/.local/bin/mica is the
        # retired Rust TUI, which has no --pick and would hang the page waiting
        # for an out file that never appears
        if not (self._dir / "mica" / "__main__.py").exists():
            self.toast.emit(f"mica not found at {self._dir}", True)
            return -1
        prog, args, cwd = sys.executable, ["-m", "mica"], str(self._dir)

        fd, self._out = tempfile.mkstemp(prefix="beryl-pick-", suffix=".txt")
        os.close(fd)
        args += ["--pick", "--out", self._out]
        if mode == "files":
            args.append("--multiple")
        elif mode == "dir":
            args.append("--directory")
        elif mode == "save":
            args.append("--save")
            if name:
                args += ["--name", name]
        args.append(self._last_dir)

        self._id += 1
        rid = self._pending = self._id
        self._proc = QProcess(self)
        self._proc.setProgram(prog)
        self._proc.setArguments(args)
        self._proc.setWorkingDirectory(cwd)
        self._proc.finished.connect(lambda _c, _s, r=rid: self._done(r))
        self._proc.errorOccurred.connect(lambda _e, r=rid: self._failed(r))
        self._proc.start()
        return rid

    # ---- process -------------------------------------------------------------
    def _read(self):
        paths = []
        try:
            paths = [l for l in Path(self._out).read_text().splitlines() if l.strip()]
        except OSError:
            pass
        try:
            os.unlink(self._out)
        except OSError:
            pass
        self._out = ""
        if self._proc is not None:
            self._proc.deleteLater()   # else one dead QProcess piles up per pick
            self._proc = None
        return paths

    def _done(self, rid):
        if self._pending != rid:
            return              # a crash fires errorOccurred AND finished; first one wins
        self._pending = 0
        paths = self._read()
        if paths:
            d = Path(paths[0])
            self._last_dir = str(d if d.is_dir() else d.parent)
        self.picked.emit(rid, paths)

    def _failed(self, rid):
        if self._pending != rid:
            return
        self._pending = 0
        self._read()
        self.toast.emit("couldn't launch mica", True)
        self.picked.emit(rid, [])
