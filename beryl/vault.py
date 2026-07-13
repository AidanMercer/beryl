import json
import os
import secrets
import subprocess
import time
from urllib.parse import urlsplit

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import config

# Saved logins, encrypted at rest. QtWebEngine ships no password manager (the
# Chromium component isn't built), so this is beryl's own save/fill layer.
# Crypto: AES256 via `gpg --symmetric` with a random keyfile beside the store —
# silent by design (no master password, no keyring daemon). The threat model
# matches the cookie jar: the user account is the boundary; the encryption
# keeps the passwords out of casual file greps and backups of the store alone.

_STORE = config.DATA_HOME / "vault.gpg"
_KEY = config.DATA_HOME / "vault.key"


def _gpg(extra, **kw):
    cmd = ["gpg", "--batch", "--yes", "--quiet",
           "--pinentry-mode", "loopback", "--passphrase-file", str(_KEY)]
    return subprocess.run(cmd + extra, capture_output=True, **kw)


def _ensure_key():
    if _KEY.exists():
        return True
    try:
        config.DATA_HOME.mkdir(parents=True, exist_ok=True)
        fd = os.open(_KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, secrets.token_hex(32).encode())
        os.close(fd)
        return True
    except OSError as e:
        print(f"[vault] key create failed: {e}", flush=True)
        return False


class Vault(QObject):
    """The password store + the save-prompt state machine. Fill/capture happen
    in creds.js; the QML bridge routes them here, and the current window's
    prompt bar answers pending saves via answer(). Constructable without an
    event loop so the importer can write logins headless."""
    changed = Signal()
    # pid, host, username, isUpdate — Main.qml shows this in the prompt bar
    askSave = Signal(int, str, str, bool)

    def __init__(self, cfg=None, api=None, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._api = api
        self._logins = []     # [{origin, username, password, created}]
        self._never = []      # origins the user said never to save for
        self._pending = {}    # pid → candidate login awaiting y/n
        self._pid = 0
        self._load()

    # ---- disk ------------------------------------------------------------------
    def _load(self):
        if not _STORE.exists() or not _KEY.exists():
            return
        r = _gpg(["--decrypt", str(_STORE)])
        if r.returncode != 0:
            print(f"[vault] decrypt failed: {r.stderr.decode(errors='replace').strip()}",
                  flush=True)
            return
        try:
            data = json.loads(r.stdout)
        except ValueError:
            print("[vault] store unreadable — starting empty", flush=True)
            return
        self._logins = [l for l in data.get("logins", [])
                        if isinstance(l, dict) and l.get("origin")]
        self._never = [n for n in data.get("never", []) if isinstance(n, str)]

    def flush(self):
        if not _ensure_key():
            return
        blob = json.dumps({"logins": self._logins, "never": self._never})
        tmp = _STORE.with_suffix(".gpg.tmp")
        r = _gpg(["--symmetric", "--cipher-algo", "AES256", "-o", str(tmp), "-"],
                 input=blob.encode())
        if r.returncode != 0:
            print(f"[vault] encrypt failed: {r.stderr.decode(errors='replace').strip()}",
                  flush=True)
            return
        try:
            tmp.replace(_STORE)
        except OSError as e:
            print(f"[vault] store write failed: {e}", flush=True)

    # ---- helpers ---------------------------------------------------------------
    def _enabled(self):
        return self._cfg is None or bool(self._cfg.get("passwords", True))

    def _toast(self, msg, err=False):
        if self._api is not None:
            self._api.toast.emit(msg, err)

    @staticmethod
    def _host(origin):
        return urlsplit(origin).netloc or origin

    def _find(self, origin, username):
        for l in self._logins:
            if l["origin"] == origin and l["username"] == username:
                return l
        return None

    def upsert(self, origin, username, password):
        """Add or update without persisting — callers batch then flush()."""
        l = self._find(origin, username)
        if l is None:
            self._logins.append({"origin": origin, "username": username,
                                 "password": password, "created": int(time.time())})
        else:
            l["password"] = password

    def count(self):
        return len(self._logins)

    # ---- page bridge (via WebView.qml, origin already validated there) ----------
    @Slot(str, result="QVariantList")
    def credsFor(self, origin):
        if not self._enabled():
            return []
        return [{"username": l["username"], "password": l["password"]}
                for l in self._logins if l["origin"] == origin]

    @Slot(str, str, str)
    def submitted(self, origin, username, password):
        """A login form went off. Prompt unless we know this exact login, the
        site is on the never list, or an identical offer is already pending."""
        if not self._enabled() or not password or origin in self._never:
            return
        known = self._find(origin, username)
        if known is not None and known["password"] == password:
            return
        for p in self._pending.values():
            if (p["origin"] == origin and p["username"] == username
                    and p["password"] == password):
                return
        self._pid += 1
        self._pending[self._pid] = {"origin": origin, "username": username,
                                    "password": password}
        self.askSave.emit(self._pid, self._host(origin), username,
                          known is not None)

    @Slot(int, str)
    def answer(self, pid, verdict):
        """The prompt bar's verdict: save / never / dismiss (esc = not now)."""
        p = self._pending.pop(pid, None)
        if p is None:
            return
        if verdict == "save":
            self.upsert(p["origin"], p["username"], p["password"])
            self.flush()
            self.changed.emit()
            self._toast(f"password saved for {self._host(p['origin'])}")
        elif verdict == "never":
            if p["origin"] not in self._never:
                self._never.append(p["origin"])
                self.flush()
            self._toast(f"never saving for {self._host(p['origin'])}")

    # ---- the gp overlay ---------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def items(self):
        # newest first; passwords stay python-side — yank slots hand them to
        # the clipboard without ever entering a QML model
        return [{"origin": l["origin"], "host": self._host(l["origin"]),
                 "username": l["username"]}
                for l in reversed(self._logins)]

    @Slot(str, str)
    def yankPassword(self, origin, username):
        l = self._find(origin, username)
        if l is not None:
            QGuiApplication.clipboard().setText(l["password"])
            self._toast(f"password copied — {self._host(origin)}")

    @Slot(str, str)
    def yankUsername(self, origin, username):
        if username:
            QGuiApplication.clipboard().setText(username)
            self._toast("username copied")

    @Slot(str, str)
    def removeLogin(self, origin, username):
        before = len(self._logins)
        self._logins = [l for l in self._logins
                        if not (l["origin"] == origin and l["username"] == username)]
        if len(self._logins) != before:
            self.flush()
            self.changed.emit()
            self._toast("login removed")
