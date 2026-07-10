import json
import time

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import config

_PATH = config.DATA_HOME / "bookmarks.json"


class Bookmarks(QObject):
    """Flat bookmark list, JSON on disk (app-written data is JSON; TOML is for
    human config). Fed into the cmdline completion alongside history."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []      # [{url, title, added}]
        self._urls = set()
        self._load()

    def _load(self):
        try:
            data = json.loads(_PATH.read_text())
        except (OSError, ValueError):
            return
        if isinstance(data, list):
            self._items = [b for b in data if isinstance(b, dict) and b.get("url")]
            self._urls = {b["url"] for b in self._items}

    def _save(self):
        try:
            config.DATA_HOME.mkdir(parents=True, exist_ok=True)
            tmp = _PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._items, indent=1))
            tmp.replace(_PATH)
        except OSError as e:
            print(f"[bookmarks] save failed: {e}", flush=True)

    @Property("QVariantList", notify=changed)
    def items(self):
        # newest first, so a fresh bookmark lands at the top of the list
        return [{"url": b["url"], "title": b["title"]}
                for b in reversed(self._items)]

    @Slot(str, result=bool)
    def contains(self, url):
        return url in self._urls

    @Slot(str)
    def removeUrl(self, url):
        self.remove(url)

    def add(self, url, title):
        if not url or url in self._urls:
            return
        self._items.append({"url": url, "title": title or "", "added": int(time.time())})
        self._urls.add(url)
        self._save()
        self.changed.emit()

    def remove(self, url):
        if url not in self._urls:
            return
        self._items = [b for b in self._items if b["url"] != url]
        self._urls.discard(url)
        self._save()
        self.changed.emit()

    def all(self):
        return [(b["url"], b["title"]) for b in self._items]
