import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import (QDateTime, QObject, QTimer, QUrl, Signal, Slot)
from PySide6.QtNetwork import QNetworkCookie

from . import bookmarks as bookmarks_mod
from . import config

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


def import_cookies(cookie_store, profile_dir):
    """Inject Firefox cookies into the QtWebEngine cookie store. Must run with
    the Qt event loop alive so the async store can flush."""
    src = profile_dir / "cookies.sqlite"
    if not src.exists():
        return 0
    tmp = _copy(src)
    n = 0
    cookie_store.loadAllCookies()   # wake the store or setCookie is a no-op
    try:
        db = sqlite3.connect(tmp)
        rows = db.execute(
            "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite"
            " FROM moz_cookies").fetchall()
        db.close()
    except sqlite3.Error as e:
        print(f"[import] cookies read failed: {e}", flush=True)
        return 0

    for name, value, host, path, expiry, secure, http_only, same_site in rows:
        c = QNetworkCookie(str(name).encode(), str(value).encode())
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
        n += 1
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
