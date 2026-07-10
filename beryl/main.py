import sys
import time
from pathlib import Path

from PySide6.QtCore import (QFileSystemWatcher, Qt, QTimer, QUrl,
                            qInstallMessageHandler)
from PySide6.QtGui import QFont, QGuiApplication, QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick

from . import commands, config, ipc, webprofile
from .adblock import Blocker
from .api import Api
from .completion import Completion
from .downloads import Downloads
from .history import History
from .keys import KeyController, KeyFilter
from .session import Session
from .tabs import TabModel
from .theme import ThemeManager

_LOG_CAP = 1024 * 1024


class _Tee:
    """Fan writes to several streams so everything lands in the log even when
    the launcher sends stdout to /dev/null."""
    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self._streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self._streams:
            try:
                st.flush()
            except Exception:
                pass


def _start_logging():
    try:
        config.CACHE_HOME.mkdir(parents=True, exist_ok=True)
        mode = "w" if (config.LOG_FILE.exists()
                       and config.LOG_FILE.stat().st_size > _LOG_CAP) else "a"
        logf = open(config.LOG_FILE, mode, buffering=1)
    except Exception:
        return
    sys.stdout = _Tee(sys.__stdout__, logf)
    sys.stderr = _Tee(sys.__stderr__, logf)
    print(f"\n==== beryl session {time.strftime('%Y-%m-%d %H:%M:%S')} ====", flush=True)


def _qt_message_handler(mode, ctx, msg):
    # page JS console output arrives here too (ctx.file = the page's script
    # url) — that's the site's noise, not ours; keep it out of the log
    if ctx.file and ctx.file.startswith(("http:", "https:")):
        return
    loc = f" ({ctx.file}:{ctx.line})" if ctx.file else ""
    print(f"[qml] {msg}{loc}", file=sys.stderr, flush=True)


def _url_args(argv):
    return [a for a in argv[1:] if not a.startswith("-")]


def main():
    t0 = time.monotonic()
    _start_logging()

    # let the chrome be translucent so Hyprland blurs behind it. Both of these
    # have to happen before the QGuiApplication exists — the WebEngine one is a
    # hard Chromium requirement, not a nicety.
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    qInstallMessageHandler(_qt_message_handler)
    QtWebEngineQuick.initialize()

    app = QGuiApplication(sys.argv)
    app.setApplicationName("beryl")
    app.setDesktopFileName("beryl")   # Wayland app_id Hyprland matches

    # single instance: a Chromium profile can't be shared, so a second launch
    # hands its urls over the local socket and exits before touching anything.
    args = _url_args(sys.argv)
    if ipc.try_forward(args):
        print("[ipc] forwarded to running instance", flush=True)
        return
    server = ipc.InstanceServer(app)

    config.ensure()
    cfg = config.load()

    theme = ThemeManager(app)
    downloads = Downloads(cfg, app)
    blocker = Blocker(cfg, app)
    profile = webprofile.build(cfg, downloads, blocker, app)
    tabs = TabModel(cfg, app)
    api = Api(app)
    keys = KeyController(cfg, api, app)
    history = History(cfg, app)
    session = Session(cfg, tabs, app)
    registry = commands.build(api, tabs, keys, cfg,
                              profile=profile, history=history, session=session)
    keys.set_registry(registry)
    api.set_ex_handler(lambda line: commands.run_ex(line, registry, api))
    completion = Completion(app)
    completion.set_sources(registry, tabs, history)

    def apply_font():
        app.setFont(QFont(theme.theme_dict()["font"]))
    apply_font()

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("Theme", theme.theme_dict())
    ctx.setContextProperty("Rice", theme)
    ctx.setContextProperty("Config", cfg)
    ctx.setContextProperty("Tabs", tabs)
    ctx.setContextProperty("Vim", keys)   # "Keys" would collide with QML's attached Keys
    ctx.setContextProperty("api", api)
    ctx.setContextProperty("WebProfile", profile)
    ctx.setContextProperty("Dl", downloads)
    ctx.setContextProperty("History", history)
    ctx.setContextProperty("Completion", completion)

    def retheme():
        ctx.setContextProperty("Theme", theme.theme_dict())
        apply_font()
    theme.themeChanged.connect(retheme)

    # live config reload — watch the file (and its dir, since editors replace
    # it). cfg is mutated in place so everything holding the dict sees fresh
    # values; the binds table is rebuilt explicitly.
    watcher = QFileSystemWatcher(app)
    debounce = QTimer(app)
    debounce.setSingleShot(True)
    debounce.setInterval(250)

    def reload_config():
        fresh = config.load()
        cfg.clear()
        cfg.update(fresh)
        keys.reload_binds()
        ctx.setContextProperty("Config", cfg)
        if config.CONFIG_FILE.exists() and str(config.CONFIG_FILE) not in watcher.files():
            watcher.addPath(str(config.CONFIG_FILE))

    debounce.timeout.connect(reload_config)
    watcher.fileChanged.connect(lambda _p: debounce.start())
    watcher.directoryChanged.connect(lambda _p: debounce.start())
    watcher.addPath(str(config.CONFIG_DIR))
    if config.CONFIG_FILE.exists():
        watcher.addPath(str(config.CONFIG_FILE))

    # first tabs: last session (lazily), then argv urls, else the homepage
    session.restore()
    for a in args:
        tabs.newTab(commands.to_url(a, cfg))
    if tabs.count == 0:
        tabs.newTab(cfg["homepage"])
    session.wire()
    app.aboutToQuit.connect(session.flush)

    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    win = engine.rootObjects()[0]

    # every key in the app passes through here before the focused item (the
    # WebEngineView) sees it — this is the whole vim layer's entry point.
    key_filter = KeyFilter(keys, app)
    win.installEventFilter(key_filter)

    def on_urls(urls):
        for u in urls:
            tabs.newTab(commands.to_url(u, cfg))
        win.requestActivate()
    server.urlsReceived.connect(on_urls)

    # permanent startup instrumentation — keep an eye on the "lightning fast"
    def on_frame():
        print(f"[startup] first frame in {time.monotonic() - t0:.3f}s", flush=True)
    win.frameSwapped.connect(on_frame, Qt.ConnectionType.SingleShotConnection)

    sys.exit(app.exec())
