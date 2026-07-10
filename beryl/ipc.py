import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# One beryl per user: a Chromium profile dir can't be shared between processes,
# so a second launch hands its urls to the first over this socket and exits.
_SOCKET = f"beryl-{os.getuid()}"


def try_forward(urls):
    """If another instance is listening, send it our urls and return True (the
    caller should exit). False means we're first — go ahead and own the
    profile."""
    sock = QLocalSocket()
    sock.connectToServer(_SOCKET)
    if not sock.waitForConnected(300):
        return False
    sock.write((json.dumps(urls) + "\n").encode())
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """The first instance's end of the socket. Emits urlsReceived for every
    launch that got forwarded here."""
    urlsReceived = Signal(list)

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
                urls = json.loads(bytes(sock.readLine()).decode())
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(urls, list):
                self.urlsReceived.emit(urls)
