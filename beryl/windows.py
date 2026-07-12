from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from . import commands

_MAIN_QML = QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml"))


class WindowHandle(QObject):
    """A window's identity, handed to Main.qml as an initial property. uid =
    which tab the window is showing; the viewport placement, strip highlight
    and window title all hang off it."""

    uidChanged = Signal()
    titleChanged = Signal()
    currentChanged = Signal()

    def __init__(self, mgr):
        super().__init__(mgr)
        self._mgr = mgr
        self._uid = -1
        self._title = ""
        self._current = False
        self.win = None    # root ApplicationWindow, set after load
        self.stack = []    # previously shown uids, newest last (steal fallback)

    @Property(int, notify=uidChanged)
    def uid(self):
        return self._uid

    @Property(str, notify=titleChanged)
    def title(self):
        return self._title

    @Property(bool, notify=currentChanged)
    def current(self):
        """Exactly one window is 'current' at any time — the last active one.
        Api signals route here, NOT to whichever window has compositor focus:
        commands must still land when beryl itself isn't focused."""
        return self._current

    def set_current(self, on):
        if on != self._current:
            self._current = on
            self.currentChanged.emit()

    def set_uid(self, uid):
        if uid != self._uid:
            self._uid = uid
            self.uidChanged.emit()

    def set_title(self, t):
        if t != self._title:
            self._title = t
            self.titleChanged.emit()

    # ---- reported by Main.qml -------------------------------------------------
    @Slot()
    def notifyActive(self):
        self._mgr.window_activated(self)

    @Slot()
    def notifyClosing(self):
        self._mgr.window_closing(self)


class WindowManager(QObject):
    """One engine, many windows, one shared tab pool — zen-style. Every
    window's strip shows every tab; a tab's live view renders in whichever
    window claims it (vault-parented otherwise), so activating a tab another
    window is showing steals it, and that window falls back to what it showed
    before. A window that ends up with nothing to show closes itself."""

    def __init__(self, engine, cfg, tabs, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = cfg
        self.tabs = tabs
        self.session = None      # set right after construction (mutual ref)
        self.handles = []
        self._active = None
        self._filter = None
        self._guard = False      # direct assignments skip the steal logic

        tabs.currentInfoChanged.connect(self._sync_current)
        tabs.dataChanged.connect(self._titles_changed)
        tabs.rowsRemoved.connect(self._rows_removed)
        tabs.lastTabClosed.connect(QGuiApplication.quit)

    def set_session(self, session):
        self.session = session

    def set_key_filter(self, f):
        self._filter = f

    # ---- opening ----------------------------------------------------------------
    def open_window(self, urls=None, bare=False):
        """New window. With urls they become its tabs; bare skips the homepage
        fallback because the caller is about to assign a tab itself."""
        h = WindowHandle(self)
        before = len(self.engine.rootObjects())
        self.engine.setInitialProperties({"winctl": h})
        self.engine.load(_MAIN_QML)
        roots = self.engine.rootObjects()
        if len(roots) <= before:
            print("[win] open failed: Main.qml did not load", flush=True)
            h.deleteLater()
            return None
        h.win = roots[-1]
        if self._filter is not None:
            h.win.installEventFilter(self._filter)
        self.handles.append(h)
        self._active = h     # the compositor is about to focus it anyway
        self._mark_current(h)
        for u in urls or []:
            self.tabs.newTab(commands.to_url(u, self.cfg))
        if h.uid < 0 and not bare:
            self.tabs.newTab(self.cfg["homepage"])
        if self.session is not None:
            self.session.poke()
        return h

    def restore(self, rows, shown, active_row, awin):
        """Startup: dead rows into the shared pool, then one window per saved
        entry, each woken onto its own tab. Runs before any window exists."""
        self.tabs.restoreRows(rows, active_row)
        used = set()
        for srow in shown[:self.tabs.count]:
            uid = self.tabs.uid_at(srow)
            if uid < 0 or uid in used:
                uid = next((self.tabs.uid_at(i) for i in range(self.tabs.count)
                            if self.tabs.uid_at(i) not in used), -1)
            if uid < 0:
                break
            h = self.open_window(bare=True)
            if h is None:
                continue
            self._guard = True
            self.tabs.wake(self.tabs.index_of(uid))
            self._assign(h, uid)
            self._guard = False
            used.add(uid)
        if self.handles:
            h = self.handles[awin] if 0 <= awin < len(self.handles) else self.handles[0]
            self._active = h
            if h.uid >= 0:
                self.tabs.activate(self.tabs.index_of(h.uid))

    # ---- window ops (commands land here) ----------------------------------------
    def active_window(self):
        if self._active in self.handles:
            return self._active
        return self.handles[-1] if self.handles else None

    def close_active(self):
        h = self.active_window()
        if h is not None:
            self.close_window(h)

    def close_window(self, h):
        if len(self.handles) <= 1:
            QGuiApplication.quit()   # last window → quit; session flushes on aboutToQuit
        else:
            self._teardown(h)

    def detach_current(self):
        """Move the focused tab into its own window — the live view moves with
        it, no reload; the old window falls back to its previous tab."""
        uid = self.tabs.currentUid
        if uid < 0:
            return
        if self.open_window(bare=True) is None:
            return
        # re-activating the same tab runs the steal logic with the new window
        # active: it claims the tab, the old window falls back
        self.tabs.activate(self.tabs.index_of(uid))

    def _mark_current(self, h):
        for x in self.handles:
            x.set_current(x is h)

    def window_activated(self, h):
        if h not in self.handles:
            return
        self._active = h
        self._mark_current(h)
        # global current follows the focused window, so commands/statusbar/url
        # ops always mean the tab you're looking at
        if h.uid >= 0 and self.tabs.currentUid != h.uid:
            i = self.tabs.index_of(h.uid)
            if i >= 0:
                self.tabs.activate(i)

    def window_closing(self, h):
        # last window closing = quitting via quitOnLastWindowClosed; keep it in
        # the list so the aboutToQuit session flush still sees a window
        if len(self.handles) <= 1 or h not in self.handles:
            return
        QTimer.singleShot(0, lambda: self._teardown(h))

    def _teardown(self, h):
        if h not in self.handles:
            return
        self.handles.remove(h)
        if self._active is h:
            self._active = self.handles[-1] if self.handles else None
            if self._active is not None:
                self._mark_current(self._active)
        h.set_current(False)
        h.set_uid(-1)        # Main.qml stashes its view back into the vault
        if h.win is not None:
            h.win.close()
            h.win.deleteLater()
        h.deleteLater()
        if self.session is not None:
            self.session.poke()

    # ---- the shared-pool state machine --------------------------------------
    def _sync_current(self):
        """Global current changed (activate/newTab/close fixup): the focused
        window claims that tab; whoever was showing it falls back — unless the
        change is closeTab's neighbour fixup, which must never steal a tab out
        of another window (closing your own tab shouldn't teleport pages)."""
        if self._guard:
            return
        uid = self.tabs.currentUid
        w = self.active_window()
        if uid < 0 or w is None or w.uid == uid:
            return
        holder = next((h for h in self.handles if h is not w and h.uid == uid), None)
        if holder is not None and self.tabs.in_fixup:
            # the neighbour belongs to another window: give w its own fallback
            # and quietly point the model at it instead
            alt = self._fallback_uid(w)
            if alt is None:
                self.close_window(w)
                return
            i = self.tabs.index_of(alt)
            self.tabs.wake(i)
            self._assign(w, alt)
            self._guard = True
            self.tabs.activate(i)
            self._guard = False
            return
        self.tabs.wake(self.tabs.index_of(uid))   # fixup rows may be dead
        self._assign(w, uid)
        if holder is not None:
            self._fall_back(holder)

    def _rows_removed(self, _parent, _first, _last):
        # a closed tab may have been some other window's shown tab; the active
        # window's own fallback comes from the model's neighbour fixup instead.
        # Deferred: this fires mid-rowsRemoved delivery, before the QML delegate
        # models have applied the removal — waking rows here would land the
        # LiveRole dataChanged on stale indices and brick the fallback tab.
        QTimer.singleShot(0, self._refit_orphans)

    def _refit_orphans(self):
        for h in list(self.handles):
            if h is not self.active_window() and h.uid >= 0 \
                    and self.tabs.index_of(h.uid) < 0:
                self._fall_back(h)

    def _fall_back(self, h):
        alt = self._fallback_uid(h)
        if alt is None:
            self.close_window(h)   # nothing left for this window to show
            return
        self.tabs.wake(self.tabs.index_of(alt))
        self._assign(h, alt)

    def _fallback_uid(self, h):
        """Most recently shown tab that still exists and isn't on screen in
        another window; else any unshown row, live ones first."""
        taken = {x.uid for x in self.handles if x is not h}
        for uid in reversed(h.stack):
            if uid not in taken and self.tabs.index_of(uid) >= 0:
                return uid
        best = None
        for i in range(self.tabs.count):
            uid = self.tabs.uid_at(i)
            if uid in taken:
                continue
            if self.tabs.live_at(i):
                return uid
            if best is None:
                best = uid
        return best

    def _assign(self, h, uid):
        if h.uid == uid:
            return
        if h.uid >= 0:
            h.stack.append(h.uid)
            del h.stack[:-20]
        h.set_uid(uid)
        h.set_title(self.tabs.title_at(self.tabs.index_of(uid)))
        if self.session is not None:
            self.session.poke()

    def _titles_changed(self, tl, br, roles):
        if roles and self.tabs.TitleRole not in roles:
            return
        for row in range(tl.row(), br.row() + 1):
            uid = self.tabs.uid_at(row)
            for h in self.handles:
                if h.uid == uid:
                    h.set_title(self.tabs.title_at(row))

    # ---- session support --------------------------------------------------------
    def snapshot(self):
        rows, idx_map = [], {}
        for i, (u, t) in enumerate(self.tabs.snapshot()):
            if u:
                idx_map[i] = len(rows)
                rows.append({"url": u, "title": t})
        active = self.active_window()
        return {
            "tabs": rows,
            "active": idx_map.get(self.tabs.currentIndex, 0),
            "awin": self.handles.index(active) if active in self.handles else 0,
            "windows": [{"shown": idx_map.get(self.tabs.index_of(h.uid), 0)}
                        for h in self.handles],
        }
