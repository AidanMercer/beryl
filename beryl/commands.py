import re
from urllib.parse import quote, urlsplit, urlunsplit

from PySide6.QtGui import QGuiApplication

# One registry backs both the key binds and the ex command line. Bind values
# are full command lines ("cmdline-open :open "), so binds are just canned ex
# invocations — qutebrowser's trick.

_ALIASES = {
    "q": "quit",
    "o": "open",
    "t": "tabopen",
    "tc": "tab-close",
    "w": "session-save",
    "nohl": "search-stop",
    "bm": "bookmark-add",
    "bookmark": "bookmark-add",
    "clear": "clear",
}

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


class Command:
    __slots__ = ("name", "fn", "takes_key")

    def __init__(self, name, fn, takes_key=False):
        self.name = name
        self.fn = fn
        self.takes_key = takes_key


def to_url(text, cfg):
    """The :open heuristic — scheme passes through, bare hosts get https,
    anything else becomes a search."""
    t = text.strip()
    if not t:
        return cfg["homepage"]
    if _SCHEME.match(t):
        return t
    host = t.split("/", 1)[0]
    if " " not in t and ("." in host or host.startswith("localhost")):
        return "https://" + t
    return cfg["search"].format(quote(t))


def build(api, tabs, keys, cfg, profile=None, history=None, session=None,
          hints=None, bookmarks=None):
    reg = {}
    marks = {}   # per-url scroll marks: {char: (url, x, y)} — session-lived

    def command(name, takes_key=False):
        def deco(fn):
            reg[name] = Command(name, fn, takes_key)
            return fn
        return deco

    # ---- scrolling (all JS: 'instant' beats page smooth-scroll CSS) ----------
    @command("scroll-down")
    def scroll_down(count=1, arg=""):
        api.js(f"window.scrollBy({{top:{cfg['scroll_step'] * count},left:0,behavior:'instant'}})")

    @command("scroll-up")
    def scroll_up(count=1, arg=""):
        api.js(f"window.scrollBy({{top:{-cfg['scroll_step'] * count},left:0,behavior:'instant'}})")

    @command("scroll-half-down")
    def scroll_half_down(count=1, arg=""):
        api.js(f"window.scrollBy({{top:window.innerHeight/2*{count},left:0,behavior:'instant'}})")

    @command("scroll-half-up")
    def scroll_half_up(count=1, arg=""):
        api.js(f"window.scrollBy({{top:-window.innerHeight/2*{count},left:0,behavior:'instant'}})")

    @command("scroll-top")
    def scroll_top(count=1, arg=""):
        api.js("window.scrollTo({top:0,left:0,behavior:'instant'})")

    @command("scroll-bottom")
    def scroll_bottom(count=1, arg=""):
        api.js("window.scrollTo({top:document.documentElement.scrollHeight,left:0,behavior:'instant'})")

    # ---- navigation ------------------------------------------------------------
    @command("open")
    def open_(count=1, arg=""):
        api.navRequested.emit(to_url(arg, cfg))

    @command("tabopen")
    def tabopen(count=1, arg=""):
        tabs.newTab(to_url(arg, cfg))

    @command("back")
    def back(count=1, arg=""):
        api.histRequested.emit(-count)

    @command("forward")
    def forward(count=1, arg=""):
        api.histRequested.emit(count)

    @command("reload")
    def reload(count=1, arg=""):
        api.reloadRequested.emit(False)

    @command("reload-bypass")
    def reload_bypass(count=1, arg=""):
        api.reloadRequested.emit(True)

    # ---- tabs --------------------------------------------------------------------
    @command("tab-close")
    def tab_close(count=1, arg=""):
        tabs.closeTab(tabs.currentIndex)

    @command("tab-undo-close")
    def tab_undo_close(count=1, arg=""):
        tabs.undoClose()

    @command("tab-next")
    def tab_next(count=1, arg=""):
        for _ in range(count):
            tabs.nextTab()

    @command("tab-prev")
    def tab_prev(count=1, arg=""):
        for _ in range(count):
            tabs.prevTab()

    # ---- modes / cmdline -----------------------------------------------------
    @command("mode-insert")
    def mode_insert(count=1, arg=""):
        keys.set_mode("insert")

    @command("mode-normal")
    def mode_normal(count=1, arg=""):
        keys.set_mode("normal")

    @command("mode-passthrough")
    def mode_passthrough(count=1, arg=""):
        keys.set_mode("passthrough")

    # ---- hints / gi ----------------------------------------------------------
    @command("hint")
    def hint(count=1, arg=""):
        if hints is not None:
            hints.start(new_tab=False)

    @command("hint-tab")
    def hint_tab(count=1, arg=""):
        if hints is not None:
            hints.start(new_tab=True)

    @command("focus-input")
    def focus_input(count=1, arg=""):
        api.js("__beryl.hints.firstInput()", None, world=1)

    # ---- url surgery / zoom --------------------------------------------------
    @command("url-up")
    def url_up(count=1, arg=""):
        parts = urlsplit(tabs.currentUrl)
        path = parts.path.rstrip("/")
        up = path.rsplit("/", 1)[0] if "/" in path else ""
        api.navRequested.emit(urlunsplit((parts.scheme, parts.netloc, up + "/", "", "")))

    @command("url-root")
    def url_root(count=1, arg=""):
        parts = urlsplit(tabs.currentUrl)
        if parts.netloc:
            api.navRequested.emit(f"{parts.scheme}://{parts.netloc}/")

    @command("zoom-in")
    def zoom_in(count=1, arg=""):
        api.zoomRequested.emit(0.1 * count)

    @command("zoom-out")
    def zoom_out(count=1, arg=""):
        api.zoomRequested.emit(-0.1 * count)

    @command("zoom-reset")
    def zoom_reset(count=1, arg=""):
        api.zoomRequested.emit(0.0)

    # ---- marks (per-url scroll position) -------------------------------------
    @command("mark-set", takes_key=True)
    def mark_set(count=1, arg=""):
        url = tabs.currentUrl
        def store(pos):
            if isinstance(pos, list) and len(pos) == 2:
                marks[arg] = (url, pos[0], pos[1])
        api.js("[window.scrollX, window.scrollY]", store)

    @command("mark-jump", takes_key=True)
    def mark_jump(count=1, arg=""):
        m = marks.get(arg)
        if not m:
            api.toast.emit(f"no mark {arg}", True)
            return
        url, x, y = m
        if url == tabs.currentUrl:
            api.js(f"window.scrollTo({{top:{y},left:{x},behavior:'instant'}})")
        else:
            api.navRequested.emit(url)   # cross-page jump just navigates for now

    # ---- bookmarks -----------------------------------------------------------
    @command("bookmark-toggle")
    def bookmark_toggle(count=1, arg=""):
        if bookmarks is None:
            return
        url, title = tabs.currentUrl, tabs.currentTitle
        if bookmarks.contains(url):
            bookmarks.remove(url)
            api.toast.emit("bookmark removed", False)
        else:
            bookmarks.add(url, title)
            api.toast.emit("bookmarked", False)

    @command("bookmark-add")
    def bookmark_add(count=1, arg=""):
        if bookmarks is not None:
            bookmarks.add(tabs.currentUrl, tabs.currentTitle)
            api.toast.emit("bookmarked", False)

    @command("bookmarks-open")
    def bookmarks_open(count=1, arg=""):
        if bookmarks is None or not bookmarks.all():
            api.toast.emit("no bookmarks yet — press * to add this page", False)
            return
        keys.set_mode("bookmarks")
        api.bookmarksRequested.emit()

    @command("help")
    def help_(count=1, arg=""):
        if keys.mode == "help":
            keys.set_mode("normal")
        else:
            keys.set_mode("help")
            api.helpRequested.emit()

    @command("tab")
    def tab(count=1, arg=""):
        """:tab <query> — switch to the first tab whose url/title matches."""
        q = arg.lower()
        for i, (url, title) in enumerate(tabs.snapshot()):
            if q in url.lower() or q in title.lower():
                tabs.activate(i)
                return

    @command("cmdline-open")
    def cmdline_open(count=1, arg=""):
        prefix, prefill = (arg[0], arg[1:]) if arg else (":", "")
        keys.set_mode("command")
        api.cmdlineOpenRequested.emit(prefix, prefill)

    @command("cmdline-open-url")
    def cmdline_open_url(count=1, arg=""):
        keys.set_mode("command")
        api.cmdlineOpenRequested.emit(":", f"open {tabs.currentUrl}")

    # ---- find / misc ------------------------------------------------------------
    @command("search-next")
    def search_next(count=1, arg=""):
        api.find_again(False)

    @command("search-prev")
    def search_prev(count=1, arg=""):
        api.find_again(True)

    @command("search-stop")
    def search_stop(count=1, arg=""):
        api.findRequested.emit("", False)

    @command("yank-url")
    def yank_url(count=1, arg=""):
        url = tabs.currentUrl
        if url:
            QGuiApplication.clipboard().setText(url)
            api.toast.emit(f"yanked {url}", False)

    @command("paste-go")
    def paste_go(count=1, arg=""):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            api.navRequested.emit(to_url(text, cfg))

    @command("paste-go-tab")
    def paste_go_tab(count=1, arg=""):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            tabs.newTab(to_url(text, cfg))

    @command("session-save")
    def session_save(count=1, arg=""):
        if session is not None:
            session.save()
            api.toast.emit("session saved", False)

    @command("clear")
    def clear(count=1, arg=""):
        """The quick nuke: cookies, http cache, history, session — persist by
        default, wipe on demand."""
        if profile is not None:
            profile.cookieStore().deleteAllCookies()
            profile.clearHttpCache()
        if history is not None:
            history.clear()
        if session is not None:
            session.clear()
        api.toast.emit("cleared cookies, cache, history", False)

    @command("quit")
    def quit_(count=1, arg=""):
        QGuiApplication.quit()

    return reg


def run_ex(line, registry, api):
    """The ':' line — same registry, table-driven."""
    line = line.strip()
    if not line:
        return
    name, _, arg = line.partition(" ")
    name = _ALIASES.get(name, name)
    cmd = registry.get(name)
    if cmd is None:
        api.toast.emit(f"not a command: {name}", True)
        return
    cmd.fn(count=1, arg=arg.strip())
