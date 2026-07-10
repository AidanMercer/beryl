import time

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, Qt,
                            Signal, Slot)

# Everything here is local: command names, open tabs, history. Keystrokes in
# the cmdline never touch the network — that's a feature, not a gap.

_ARG_COMMANDS = ("open", "tabopen", "o", "t", "tab", "T")


def _fuzzy(query, text):
    """Subsequence match with a crude gap penalty. None = no match; higher is
    better. Cheap on ≤200 candidates."""
    if not query:
        return 0.0
    q = query.lower()
    t = text.lower()
    score, ti, streak = 0.0, 0, 0.0
    for ch in q:
        i = t.find(ch, ti)
        if i < 0:
            return None
        streak = streak + 1.0 if i == ti else 1.0
        score += streak - (i - ti) * 0.05
        ti = i + 1
    return score


class Completion(QAbstractListModel):
    LabelRole = Qt.ItemDataRole.UserRole + 1
    DetailRole = Qt.ItemDataRole.UserRole + 2

    selChanged = Signal()
    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []      # dicts: label, detail, insert
        self._sel = -1
        self._registry = {}
        self._tabs = None
        self._history = None
        self._bookmarks = None

    def set_sources(self, registry, tabs, history, bookmarks=None):
        self._registry = registry
        self._tabs = tabs
        self._history = history
        self._bookmarks = bookmarks

    # ---- model -------------------------------------------------------------
    def roleNames(self):
        return {self.LabelRole: b"label", self.DetailRole: b"detail"}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        r = self._rows[index.row()]
        if role == self.LabelRole:
            return r["label"]
        if role == self.DetailRole:
            return r["detail"]
        return None

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._rows)

    @Property(int, notify=selChanged)
    def sel(self):
        return self._sel

    # ---- driven by the cmdline ------------------------------------------------
    @Slot(str, str)
    def update(self, prefix, text):
        rows = []
        if prefix == ":":
            head, _, arg = text.partition(" ")
            rows = self._complete(head, arg, has_space=(" " in text))
        self._replace(rows)

    def _complete(self, head, arg, has_space):
        if not has_space:
            # command-name completion
            out = []
            for name in sorted(self._registry):
                s = _fuzzy(head, name)
                if s is not None:
                    out.append((s, {"label": name, "detail": "", "insert": name + " "}))
            out.sort(key=lambda p: -p[0])
            return [r for _, r in out[:20]]
        if head not in _ARG_COMMANDS:
            return []
        # url arg completion: open tabs first, then history by fuzzy × frecency
        out = []
        now = time.time()
        if self._tabs is not None:
            for url, title in self._tabs.snapshot():
                s = _fuzzy(arg, url + " " + title)
                if s is not None and url:
                    out.append((s + 5.0, {"label": title or url, "detail": url,
                                          "insert": f"{head} {url}"}))
        if self._bookmarks is not None:
            for url, title in self._bookmarks.all():
                s = _fuzzy(arg, url + " " + title)
                if s is not None:
                    out.append((s + 3.0, {"label": ("★ " + (title or url)),
                                          "detail": url, "insert": f"{head} {url}"}))
        if self._history is not None:
            for url, title, visits, last_ts in self._history.search(arg):
                s = _fuzzy(arg, url + " " + (title or ""))
                if s is None:
                    continue
                age_days = max(0.0, (now - last_ts) / 86400)
                frecency = visits / (1.0 + age_days / 7.0)
                out.append((s + min(frecency, 4.0),
                            {"label": title or url, "detail": url,
                             "insert": f"{head} {url}"}))
        out.sort(key=lambda p: -p[0])
        seen, rows = set(), []
        for _, r in out:
            if r["detail"] in seen:
                continue
            seen.add(r["detail"])
            rows.append(r)
            if len(rows) >= 15:
                break
        return rows

    def _replace(self, rows):
        self.beginResetModel()
        self._rows = rows
        self._sel = -1
        self.endResetModel()
        self.countChanged.emit()
        self.selChanged.emit()

    @Slot(int)
    def cycle(self, d):
        if not self._rows:
            return
        n = len(self._rows)
        self._sel = ((self._sel + 1 + d) % (n + 1)) - 1   # …→ -1 → 0 → … → n-1 → -1
        self.selChanged.emit()

    @Slot(result=str)
    def currentInsert(self):
        if 0 <= self._sel < len(self._rows):
            return self._rows[self._sel]["insert"]
        return ""

    @Slot()
    def reset(self):
        self._replace([])
