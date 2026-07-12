import sqlite3
import time

from PySide6.QtCore import QObject, QTimer, Slot

from . import config

_SKIP = ("about:", "data:", "view-source:", "chrome:", "qrc:")


class History(QObject):
    """Local visit log — sqlite, WAL, single main-thread connection. Feeds the
    cmdline completion; never leaves the machine."""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        config.DATA_HOME.mkdir(parents=True, exist_ok=True)
        path = config.DATA_HOME / "history.db"
        try:
            self._db = self._open(path)
        except sqlite3.DatabaseError as e:
            # a corrupt db must not brick startup: set it aside, start fresh
            print(f"[history] corrupt history.db ({e}) — starting a new one",
                  flush=True)
            try:
                path.replace(path.with_suffix(".db.corrupt"))
            except OSError:
                pass
            self._db = self._open(path)
        QTimer.singleShot(5000, self._purge)

    @staticmethod
    def _open(path):
        db = sqlite3.connect(path)
        db.executescript(
            "PRAGMA journal_mode=WAL;"
            "PRAGMA synchronous=NORMAL;"
            "CREATE TABLE IF NOT EXISTS visits("
            "  id INTEGER PRIMARY KEY, url TEXT NOT NULL,"
            "  title TEXT DEFAULT '', ts INTEGER NOT NULL);"
            "CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts);"
            "CREATE INDEX IF NOT EXISTS idx_visits_url ON visits(url);")
        return db

    @Slot(str, str)
    def record(self, url, title):
        if not url or url.startswith(_SKIP):
            return
        self._db.execute("INSERT INTO visits(url, title, ts) VALUES(?,?,?)",
                         (url, title or "", int(time.time())))
        self._db.commit()

    @Slot(str, str)
    def retitle(self, url, title):
        """Titles often arrive after the load-success we recorded."""
        if not url or not title or url.startswith(_SKIP):
            return
        self._db.execute(
            "UPDATE visits SET title=? WHERE id="
            "(SELECT id FROM visits WHERE url=? ORDER BY ts DESC LIMIT 1)",
            (title, url))
        self._db.commit()

    def search(self, q, limit=200):
        """Grouped-by-url candidates for completion: (url, title, visits,
        last_ts). Prefiltered per whitespace token (each must appear in
        url+title, any order) so multi-word queries still reach the fuzzy
        pass in completion.py — one LIKE over the raw string matched nothing
        for 'git hub'."""
        where, params = [], []
        for tok in (q or "").split():
            where.append("(url || ' ' || title) LIKE ?")
            params.append(f"%{tok}%")
        sql = ("SELECT url, MAX(title), COUNT(*), MAX(ts) FROM visits"
               + (" WHERE " + " AND ".join(where) if where else "")
               + " GROUP BY url ORDER BY MAX(ts) DESC LIMIT ?")
        return self._db.execute(sql, (*params, limit)).fetchall()

    def clear(self):
        self._db.execute("DELETE FROM visits")
        self._db.commit()

    def _purge(self):
        cutoff = int(time.time()) - int(self._cfg.get("history_days", 180)) * 86400
        self._db.execute("DELETE FROM visits WHERE ts < ?", (cutoff,))
        self._db.commit()
