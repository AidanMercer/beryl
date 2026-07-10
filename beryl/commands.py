import re
from urllib.parse import quote

from PySide6.QtGui import QGuiApplication

# One registry backs both the key binds and the ex command line. Bind values
# are full command lines ("cmdline-open :open "), so binds are just canned ex
# invocations — qutebrowser's trick.

_ALIASES = {
    "q": "quit",
    "o": "open",
    "tc": "tab-close",
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


def build(api, tabs, keys, cfg):
    reg = {}

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
