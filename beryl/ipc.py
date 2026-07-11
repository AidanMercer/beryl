import hashlib
import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import config

# One beryl per profile: a Chromium profile dir can't be shared between
# processes, so a second launch hands its urls to the first over this socket
# and exits. Scoped to the data dir, not just the uid, so a sandboxed beryl
# (custom XDG dirs) doesn't forward into the real one.
_SOCKET = (f"beryl-{os.getuid()}-"
           + hashlib.sha1(str(config.DATA_HOME).encode()).hexdigest()[:8])


def try_forward(urls, new_window=False):
    """If another instance is listening, send it our urls (and whether they
    want their own window) and return True (the caller should exit). False
    means we're first — go ahead and own the profile."""
    sock = QLocalSocket()
    sock.connectToServer(_SOCKET)
    if not sock.waitForConnected(300):
        return False
    payload = {"urls": urls, "window": bool(new_window)}
    sock.write((json.dumps(payload) + "\n").encode())
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """The first instance's end of the socket. Emits received for every launch
    that got forwarded here: {"urls": [...], "window": bool}."""
    received = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        QLocalServer.removeServer(_SOCKET)   # clear a stale socket after a crash
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        if not self._server.listen(_SOCKET):
            print(f"[ipc] listen failed: {self._server.errorString()}", flush=True)

    def _accept(self):
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        sock.readyRead.connect(lambda: self._read(sock))
        sock.disconnected.connect(sock.deleteLater)

    def _read(self, sock):
        while sock.canReadLine():
            try:
                obj = json.loads(bytes(sock.readLine()).decode())
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(obj, list):   # pre-multiwindow client
                obj = {"urls": obj, "window": False}
            if isinstance(obj, dict) and isinstance(obj.get("urls"), list):
                self.received.emit(obj)
