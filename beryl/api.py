from PySide6.QtCore import QObject, Signal, Slot


class Api(QObject):
    """The seam between Python commands and the QML-owned WebEngineViews.
    PySide can't call runJavaScript with a callback on the Quick view type, so
    the flow is inverted: Python emits a request, Main.qml executes it on the
    current view and answers back with the request id. Keeps every command
    testable against a mock."""

    jsRequested = Signal(str, int)            # script, requestId (0 = fire-and-forget)
    navRequested = Signal(str)                # url → current view
    histRequested = Signal(int)               # -1 back / +1 forward
    reloadRequested = Signal(bool)            # bypass cache?
    findRequested = Signal(str, bool)         # term ("" clears), backwards
    cmdlineOpenRequested = Signal(str, str)   # prefix (":" or "/"), prefill
    toast = Signal(str, bool)                 # message, isError

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cbs = {}
        self._rid = 0
        self._ex = None
        self.last_find = ""

    def set_ex_handler(self, fn):
        self._ex = fn

    # ---- python side ---------------------------------------------------------
    def js(self, script, cb=None):
        rid = 0
        if cb is not None:
            self._rid += 1
            rid = self._rid
            self._cbs[rid] = cb
        self.jsRequested.emit(script, rid)

    def find(self, term, backwards=False):
        if term:
            self.last_find = term
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
