from PySide6.QtCore import QObject, Signal, Slot


class Api(QObject):
    """The seam between Python commands and the QML-owned WebEngineViews.
    PySide can't call runJavaScript with a callback on the Quick view type, so
    the flow is inverted: Python emits a request, Main.qml executes it on the
    current view and answers back with the request id. Keeps every command
    testable against a mock."""

    jsRequested = Signal(str, int, int)       # script, worldId, requestId (0 = fire-and-forget)
    zoomRequested = Signal(float)             # step; 0 = reset
    helpRequested = Signal()                  # toggle the cheat sheet
    bookmarksRequested = Signal()             # open the bookmarks list overlay
    downloadsRequested = Signal()             # open the downloads list overlay
    navRequested = Signal(str)                # url → current view
    histRequested = Signal(int)               # -1 back / +1 forward
    reloadRequested = Signal(bool)            # bypass cache?
    findRequested = Signal(str, bool)         # term ("" clears), backwards
    cmdlineOpenRequested = Signal(str, str)   # prefix (":" or "/"), prefill
    toast = Signal(str, bool)                 # message, isError
    findCount = Signal(str)                   # "3/17" for the statusbar, "" = hidden

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cbs = {}
        self._rid = 0
        self._ex = None
        self.last_find = ""
        self._find_active = False

    def set_ex_handler(self, fn):
        self._ex = fn

    # ---- python side ---------------------------------------------------------
    # worlds: 0 = MainWorld (the page's JS), 1 = ApplicationWorld (isolated —
    # where hints.js lives, out of the page's reach)
    def js(self, script, cb=None, world=0):
        rid = 0
        if cb is not None:
            self._rid += 1
            rid = self._rid
            self._cbs[rid] = cb
        self.jsRequested.emit(script, world, rid)

    def find(self, term, backwards=False):
        if term:
            self.last_find = term
        self._find_active = bool(term)
        if not term:
            self.findCount.emit("")
        self.findRequested.emit(term, backwards)

    def find_again(self, backwards):
        if self.last_find:
            self.findRequested.emit(self.last_find, backwards)
        else:
            self.toast.emit("no search", True)

    # ---- called from QML -----------------------------------------------------
    @Slot(int, "QVariant")
    def jsDone(self, rid, result):
        cb = self._cbs.pop(rid, None)
        if cb is not None:
            cb(result)

    @Slot(str)
    def runEx(self, text):
        if self._ex is not None:
            self._ex(text)

    @Slot(str)
    def runFind(self, text):
        self.find(text)

    @Slot(int, result=str)
    def permName(self, value):
        """Human label for QWebEnginePermission.PermissionType (values pinned
        against the 6.11 enum)."""
        return {1: "microphone", 2: "camera", 3: "camera + microphone",
                4: "screen capture", 5: "screen capture + audio",
                6: "mouse lock", 7: "notifications", 8: "location",
                9: "clipboard", 10: "local fonts"}.get(int(value), "a permission")

    @Slot(int, int)
    def findResult(self, matches, active):
        """WebEngine reports 0/0 both for 'no matches' and 'search cleared' —
        _find_active disambiguates."""
        if self._find_active:
            self.findCount.emit(f"{active}/{matches}")
