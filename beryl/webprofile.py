import subprocess

from PySide6.QtWebEngineCore import qWebEngineChromiumVersion
from PySide6.QtWebEngineQuick import QQuickWebEngineProfile

from . import config


def _chrome_ua():
    """A plain Chrome-on-Linux UA with the real engine version. The stock
    string advertises QtWebEngine, which microsoft's login flows treat as an
    unsupported browser — and blending in is the better fingerprint anyway."""
    v = qWebEngineChromiumVersion()
    if isinstance(v, (bytes, bytearray, memoryview)):
        v = bytes(v).decode()
    major = str(v).split(".")[0]
    return ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36")


def _cookie_filter(cfg):
    allow = tuple(cfg.get("cookie_allow_3p", []))

    def accept(request):
        if not request.thirdParty:
            return True
        host = request.origin.host()
        return any(host == d or host.endswith("." + d) for d in allow)
    return accept


def _notify(notification):
    """Web Notifications → the desktop, so outlook can tap the shoulder."""
    try:
        subprocess.Popen(["notify-send", "-a", "beryl", "-i", "web-browser",
                          notification.title() or "beryl",
                          notification.message() or ""])
    except OSError:
        pass
    notification.show()


def build(cfg, downloads, blocker, parent=None):
    """The one persistent Chromium profile. Built in Python (not QML) because
    the pieces that hang off it — download adoption, the adblock/privacy
    interceptor, the cookie filter — all live on this side. QML views bind it
    via the WebProfile context property."""
    # the storage name MUST be a constructor arg — a default-constructed
    # profile is off-the-record (in-memory) forever, and setStorageName after
    # the fact does NOT switch it to persistent. Passing it here is what makes
    # cookies/logins/cache survive a restart at all.
    profile = QQuickWebEngineProfile(
        "beryl", parent,
        persistentStoragePath=str(config.DATA_HOME / "profile"),
        cachePath=str(config.CACHE_HOME / "webcache"),
        httpCacheType=QQuickWebEngineProfile.HttpCacheType.DiskHttpCache,
        persistentCookiesPolicy=QQuickWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies,
        persistentPermissionsPolicy=QQuickWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk,
        httpUserAgent=_chrome_ua())

    profile.downloadRequested.connect(downloads.adopt)
    profile.presentNotification.connect(_notify)

    # every request passes the blocker: privacy headers always, filter-list
    # matching once the engine is compiled (daemon thread)
    profile.setUrlRequestInterceptor(blocker)
    blocker.start()

    # third-party cookie blocking (with the sso exception list); IO thread —
    # keep the callback pure
    profile.cookieStore().setCookieFilter(_cookie_filter(cfg))

    return profile
