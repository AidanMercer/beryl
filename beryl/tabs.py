from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, Qt,
                            Signal, Slot)
from PySide6.QtGui import QGuiApplication


class TabModel(QAbstractListModel):
    """Source of truth for tabs. QML mounts one WebEngineView per row (behind a
    Loader gated on `live`, so restored rows cost nothing until activated) and
    reports state back through viewState(). Never reset the model — that would
    tear down live pages; rows only move through begin/end Insert/Remove."""

    UidRole = Qt.ItemDataRole.UserRole + 1
    UrlRole = Qt.ItemDataRole.UserRole + 2
    TitleRole = Qt.ItemDataRole.UserRole + 3
    IconRole = Qt.ItemDataRole.UserRole + 4
    LiveRole = Qt.ItemDataRole.UserRole + 5
    LoadingRole = Qt.ItemDataRole.UserRole + 6
    ProgressRole = Qt.ItemDataRole.UserRole + 7

    _ROLES = {
        UidRole: b"uid", UrlRole: b"url", TitleRole: b"title",
        IconRole: b"icon", LiveRole: b"live", LoadingRole: b"loading",
        ProgressRole: b"progress",
    }
    _KEYS = {"url": UrlRole, "title": TitleRole, "icon": IconRole,
             "loading": LoadingRole, "progress": ProgressRole}

    currentIndexChanged = Signal()
    currentInfoChanged = Signal()
    countChanged = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._tabs = []          # list of dicts, one per row
        self._closed = []        # (url, index) stack for X / undo-close
        self._next_uid = 1
        self._current = -1

    # ---- model plumbing ------------------------------------------------------
    def roleNames(self):
        return dict(self._ROLES)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tabs)

    def data(self, index, role):
        if not index.isValid() or not (0 <= index.row() < len(self._tabs)):
            return None
        t = self._tabs[index.row()]
        key = self._ROLES.get(role)
        return t.get(key.decode()) if key else None

    def _row_changed(self, row, roles):
        ix = self.index(row)
        self.dataChanged.emit(ix, ix, roles)

    # ---- properties ----------------------------------------------------------
    @Property(int, notify=currentIndexChanged)
    def currentIndex(self):
        return self._current

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._tabs)

    @Property(int, notify=currentInfoChanged)
    def currentUid(self):
        return self._tabs[self._current]["uid"] if 0 <= self._current < len(self._tabs) else -1

    @Property(str, notify=currentInfoChanged)
    def currentUrl(self):
        return self._tabs[self._current]["url"] if 0 <= self._current < len(self._tabs) else ""

    @Property(str, notify=currentInfoChanged)
    def currentTitle(self):
        return self._tabs[self._current]["title"] if 0 <= self._current < len(self._tabs) else ""

    # ---- tab operations ------------------------------------------------------
    @Slot(str)
    @Slot(str, bool)
    def newTab(self, url, background=False):
        row = len(self._tabs)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tabs.append({
            "uid": self._next_uid, "url": url, "title": "", "icon": "",
            "live": True, "loading": False, "progress": 0,
        })
        self._next_uid += 1
        self.endInsertRows()
        self.countChanged.emit()
        if not background or self._current < 0:
            self.activate(row)

    @Slot(int)
    def closeTab(self, i):
        if not (0 <= i < len(self._tabs)):
            return
        if len(self._tabs) == 1:
            QGuiApplication.quit()   # closing the last tab closes beryl, vim-style
            return
        self._closed.append((self._tabs[i]["url"], i))
        del self._closed[:-30]
        self.beginRemoveRows(QModelIndex(), i, i)
        del self._tabs[i]
        self.endRemoveRows()
        self.countChanged.emit()
        if self._current > i:
            self._current -= 1                            # keep following the same tab
        elif self._current == i:
            self._current = min(i, len(self._tabs) - 1)   # fall onto the right neighbour
        # emit unconditionally: even when the number didn't change, the tab at
        # this index did, and the QML refocus hangs off this signal
        self.currentIndexChanged.emit()
        self.currentInfoChanged.emit()

    @Slot()
    def undoClose(self):
        if not self._closed:
            return
        url, i = self._closed.pop()
        i = min(i, len(self._tabs))
        self.beginInsertRows(QModelIndex(), i, i)
        self._tabs.insert(i, {
            "uid": self._next_uid, "url": url, "title": "", "icon": "",
            "live": True, "loading": False, "progress": 0,
        })
        self._next_uid += 1
        self.endInsertRows()
        self.countChanged.emit()
        self.activate(i)

    @Slot(int)
    def activate(self, i):
        if not (0 <= i < len(self._tabs)):
            return
        if not self._tabs[i]["live"]:
            self._tabs[i]["live"] = True   # lazy-restored row wakes up here
            self._row_changed(i, [self.LiveRole])
        self._set_current(i)

    @Slot()
    def nextTab(self):
        if self._tabs:
            self.activate((self._current + 1) % len(self._tabs))

    @Slot()
    def prevTab(self):
        if self._tabs:
            self.activate((self._current - 1) % len(self._tabs))

    def _set_current(self, i):
        if i != self._current:
            self._current = i
            self.currentIndexChanged.emit()
        self.currentInfoChanged.emit()

    # ---- session support -------------------------------------------------------
    def snapshot(self):
        return [(t["url"], t["title"]) for t in self._tabs]

    def restoreRows(self, rows, active):
        """Bulk-insert dead rows (live=False) at startup; activate() wakes only
        the current one. Call before any newTab."""
        if not rows:
            return
        first = len(self._tabs)
        self.beginInsertRows(QModelIndex(), first, first + len(rows) - 1)
        for url, title in rows:
            self._tabs.append({
                "uid": self._next_uid, "url": url, "title": title, "icon": "",
                "live": False, "loading": False, "progress": 0,
            })
            self._next_uid += 1
        self.endInsertRows()
        self.countChanged.emit()
        self.activate(first + max(0, min(active, len(rows) - 1)))

    # ---- feedback from the QML views ----------------------------------------
    @Slot(int, str, "QVariant")
    def viewState(self, uid, key, value):
        role = self._KEYS.get(key)
        if role is None:
            return
        for row, t in enumerate(self._tabs):
            if t["uid"] == uid:
                if t.get(key) == value:
                    return
                t[key] = value
                self._row_changed(row, [role])
                if row == self._current and key in ("url", "title"):
                    self.currentInfoChanged.emit()
                return
