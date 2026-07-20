import base64
import ctypes
import json
import shutil
import sqlite3
import tempfile
import time
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_void_p
from pathlib import Path

from PySide6.QtCore import (QDateTime, QObject, QTimer, QUrl, Signal, Slot)
from PySide6.QtNetwork import QNetworkCookie

from . import bookmarks as bookmarks_mod
from . import config
from .vault import Vault

# Best-effort import from a Firefox-family profile (Zen). Cookies carry the
# logins over; history + bookmarks feed the cmdline completion. We never touch
# the source profile — everything is copied to a temp file first (the live DB
# is WAL-locked while the other browser runs).

_ZEN_DIR = Path.home() / ".config" / "zen"


def _find_profile():
    if not _ZEN_DIR.is_dir():
        return None
    # prefer the default-release profile; else the newest with cookies
    candidates = sorted(_ZEN_DIR.glob("*/cookies.sqlite"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for c in candidates:
        if "Default" in c.parent.name:
            return c.parent
    return candidates[0].parent if candidates else None


def _copy(src):
    """Copy a possibly-WAL-locked sqlite (plus -wal) to a temp file we can read
    without fighting the running browser."""
    tmp = Path(tempfile.mkdtemp(prefix="beryl-import-")) / src.name
    shutil.copy(src, tmp)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy(side, tmp.with_name(tmp.name + suffix))
    return tmp


def read_cookie_rows(cookies_sqlite):
    """Read Firefox moz_cookies from a (possibly WAL-locked) cookies.sqlite off
    a throwaway copy, so a running browser isn't disturbed. Cleans up after
    itself and never raises — a bad/locked db just yields []. Shared by the
    full --import-zen path and the live :google-signin harvest."""
    src = Path(cookies_sqlite)
    if not src.exists():
        return []
    tmpdir = Path(tempfile.mkdtemp(prefix="beryl-cookies-"))
    try:
        dst = tmpdir / "cookies.sqlite"
        shutil.copy(src, dst)
        for suffix in ("-wal", "-shm"):
            side = src.with_name(src.name + suffix)
            if side.exists():
                shutil.copy(side, dst.with_name(dst.name + suffix))
        db = sqlite3.connect(dst)
        try:
            return db.execute(
                "SELECT name, value, host, path, expiry, isSecure, isHttpOnly,"
                " sameSite FROM moz_cookies").fetchall()
        finally:
            db.close()
    except (OSError, sqlite3.Error) as e:
        print(f"[import] cookie read failed: {e}", flush=True)
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def host_matches(host, suffixes):
    """A cookie host (with or without firefox's leading dot) belongs to one of
    the domain suffixes — exact or a dotted subdomain, so "google.com" matches
    accounts.google.com but not evil-google.com."""
    h = str(host).lstrip(".")
    return any(h == s or h.endswith("." + s) for s in suffixes)


def _queue_cookie(cookie_store, row):
    name, value, host, path, expiry, secure, http_only, same_site = row
    c = QNetworkCookie(str(name).encode(), str(value).encode())
    # firefox stores host-only cookies without a leading dot. Only dotted
    # hosts get a Domain attribute — stamping it on host-only cookies broadens
    # their scope, and __Host-* cookies (github's user_session_same_site among
    # them) are outright REJECTED by Chromium if Domain is present, which
    # silently broke every imported github POST (422 "What?"). Host-only
    # cookies take their host from the origin url instead.
    if host.startswith("."):
        c.setDomain(host)
    c.setPath(path or "/")
    c.setSecure(bool(secure))
    c.setHttpOnly(bool(http_only))
    if expiry and expiry > time.time():
        c.setExpirationDate(QDateTime.fromSecsSinceEpoch(int(expiry)))
    # origin url: leading-dot domains are host-suffix cookies
    h = host.lstrip(".")
    origin = QUrl(f"{'https' if secure else 'http'}://{h}{path or '/'}")
    cookie_store.setCookie(c, origin)


def inject_cookies(cookie_store, rows, host_suffixes=None):
    """Queue Firefox cookie rows into a live QtWebEngine cookie store. With
    host_suffixes, only cookies for those domains go in (additive — every other
    login in the store is untouched, and setCookie overwrites by name+host+path
    so a re-harvest refreshes a rotated session). Must run with the Qt event
    loop alive so the async store can flush."""
    cookie_store.loadAllCookies()   # wake the store or setCookie is a no-op
    n = 0
    for row in rows:
        if host_suffixes and not host_matches(row[2], host_suffixes):
            continue
        _queue_cookie(cookie_store, row)
        n += 1
    return n


def has_session(rows, host_suffixes, names):
    """True if the rows hold a plausible live session cookie — one of `names`
    with a non-trivial value on one of the host_suffixes. Cheap presence check;
    can't tell a server-expired session from a live one (only a real load can),
    so a stale hit just gets re-injected and the user re-runs with `login`."""
    for name, value, host, *_ in rows:
        if name in names and value and len(str(value)) > 20 \
                and host_matches(host, host_suffixes):
            return True
    return False


def import_cookies(cookie_store, profile_dir):
    """The full --import-zen cookie carry: every cookie in the profile."""
    n = inject_cookies(cookie_store, read_cookie_rows(profile_dir / "cookies.sqlite"))
    print(f"[import] queued {n} cookies", flush=True)
    return n


def import_history(profile_dir):
    src = profile_dir / "places.sqlite"
    if not src.exists():
        return 0
    tmp = _copy(src)
    n = 0
    try:
        fdb = sqlite3.connect(tmp)
        rows = fdb.execute(
            "SELECT p.url, p.title, h.visit_date"
            " FROM moz_places p JOIN moz_historyvisits h ON h.place_id = p.id"
            " WHERE p.url LIKE 'http%'").fetchall()
        fdb.close()
    except sqlite3.Error as e:
        print(f"[import] history read failed: {e}", flush=True)
        return 0

    config.DATA_HOME.mkdir(parents=True, exist_ok=True)
    hdb = sqlite3.connect(config.DATA_HOME / "history.db")
    hdb.executescript(
        "CREATE TABLE IF NOT EXISTS visits("
        "  id INTEGER PRIMARY KEY, url TEXT NOT NULL,"
        "  title TEXT DEFAULT '', ts INTEGER NOT NULL);")
    existing = {r[0] for r in hdb.execute("SELECT DISTINCT url || '@' || ts FROM visits")}
    for url, title, visit_date in rows:
        ts = int((visit_date or 0) / 1_000_000)   # firefox stores microseconds
        if ts <= 0 or f"{url}@{ts}" in existing:
            continue                              # re-import is a no-op
        hdb.execute("INSERT INTO visits(url, title, ts) VALUES(?,?,?)",
                    (url, title or "", ts))
        existing.add(f"{url}@{ts}")
        n += 1
    hdb.commit()
    hdb.close()
    print(f"[import] {n} history visits", flush=True)
    return n


def import_bookmarks(profile_dir):
    src = profile_dir / "places.sqlite"
    if not src.exists():
        return 0
    tmp = _copy(src)
    try:
        db = sqlite3.connect(tmp)
        rows = db.execute(
            "SELECT b.title, p.url, b.dateAdded FROM moz_bookmarks b"
            " JOIN moz_places p ON p.id = b.fk"
            " WHERE b.type = 1 AND p.url LIKE 'http%'").fetchall()
        db.close()
    except sqlite3.Error as e:
        print(f"[import] bookmarks read failed: {e}", flush=True)
        return 0

    bm = bookmarks_mod.Bookmarks()
    n = 0
    for title, url, date_added in rows:
        if not bm.contains(url):
            bm.add(url, title or "")
            n += 1
    print(f"[import] {n} bookmarks", flush=True)
    return n


class _SECItem(Structure):
    _fields_ = [("type", c_int), ("data", c_void_p), ("len", c_int)]


def import_passwords(profile_dir):
    """Decrypt Firefox/Zen saved logins (NSS SDR) and fold them into beryl's
    vault. QtWebEngine has no password manager, so these would otherwise be
    lost across the switch. Works on a COPY of the key/cert DBs so a running
    Zen isn't disturbed; only handles the no-primary-password case (encrypted
    logins with a master password would need an interactive prompt we don't
    have). Best-effort — any failure just imports zero."""
    src = profile_dir / "logins.json"
    if not src.exists():
        return 0
    try:
        logins = json.loads(src.read_text()).get("logins", [])
    except (OSError, ValueError):
        return 0
    if not logins:
        return 0

    # NSS wants a profile dir it can open; copy just the key material so we
    # never touch (or lock) the live one
    tmp = Path(tempfile.mkdtemp(prefix="beryl-nss-"))
    for name in ("key4.db", "cert9.db", "pkcs11.txt"):
        s = profile_dir / name
        if s.exists():
            shutil.copy(s, tmp / name)

    try:
        nss = ctypes.CDLL("libnss3.so")
    except OSError as e:
        print(f"[import] libnss3 unavailable, skipping passwords: {e}", flush=True)
        return 0
    nss.NSS_Init.argtypes = [c_char_p]
    nss.PK11_GetInternalKeySlot.restype = c_void_p
    nss.PK11_Authenticate.argtypes = [c_void_p, c_int, c_void_p]
    nss.PK11SDR_Decrypt.argtypes = [POINTER(_SECItem), POINTER(_SECItem), c_void_p]
    nss.PK11_FreeSlot.argtypes = [c_void_p]

    if nss.NSS_Init(str(tmp).encode()) != 0:
        print("[import] NSS_Init failed, skipping passwords", flush=True)
        return 0

    def decrypt(b64):
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError):
            return None
        buf = ctypes.create_string_buffer(raw, len(raw))
        inp = _SECItem(0, ctypes.cast(buf, c_void_p), len(raw))
        out = _SECItem(0, None, 0)
        if nss.PK11SDR_Decrypt(byref(inp), byref(out), None) != 0:
            return None
        return ctypes.string_at(out.data, out.len).decode("utf-8", "replace")

    n = 0
    try:
        slot = nss.PK11_GetInternalKeySlot()
        # empty primary password: a set master password returns nonzero and we
        # bail (no interactive prompt to offer)
        if nss.PK11_Authenticate(slot, True, None) != 0:
            print("[import] zen profile has a primary password — passwords "
                  "not imported", flush=True)
            nss.PK11_FreeSlot(slot)
            return 0
        nss.PK11_FreeSlot(slot)

        vault = Vault()
        for l in logins:
            origin = l.get("hostname") or ""     # zen stores scheme://host[:port]
            if not origin.startswith(("http://", "https://")):
                continue
            user = decrypt(l.get("encryptedUsername", ""))
            pw = decrypt(l.get("encryptedPassword", ""))
            if pw is None:
                continue
            vault.upsert(origin, user or "", pw)
            n += 1
        if n and not vault.flush():
            print("[import] existing vault unreadable — nothing imported",
                  flush=True)
            n = 0
    finally:
        try:
            nss.NSS_Shutdown()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"[import] {n} passwords", flush=True)
    return n


class Importer(QObject):
    """Driver for `beryl --import-zen`. history/bookmarks import immediately;
    cookies wait for the QML WebEngineView to connect the store (injectCookies
    is called from Import.qml on first load), then we flush and quit."""
    def __init__(self, profile, app):
        super().__init__(app)
        self._profile = profile
        self._app = app
        self._dir = _find_profile()

    def start(self):
        """False when there's nothing to import — the caller must exit itself:
        quit() before the event loop runs is silently lost, so calling it here
        used to leave `--import-zen` hanging forever."""
        if self._dir is None:
            print("[import] no zen profile found under ~/.config/zen", flush=True)
            return False
        print(f"[import] from {self._dir.name}", flush=True)
        import_history(self._dir)
        import_bookmarks(self._dir)
        # passwords before any WebEngineView loads: NSS is a process-global, so
        # decrypt while we're sure Chromium hasn't claimed it
        import_passwords(self._dir)
        return True

    @Slot()
    def injectCookies(self):
        if self._dir is None:
            return
        n = import_cookies(self._profile.cookieStore(), self._dir)
        # cookies write asynchronously; give Chromium time to flush, then quit
        QTimer.singleShot(4000 + n, self._done)

    def _done(self):
        print("[import] done — launch beryl normally to use your imported data",
              flush=True)
        self._app.quit()
