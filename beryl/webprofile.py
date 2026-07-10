from PySide6.QtWebEngineQuick import QQuickWebEngineProfile

from . import config


def build(cfg, downloads, blocker, parent=None):
    """The one persistent Chromium profile. Built in Python (not QML) because
    the pieces that hang off it — download adoption, the adblock/privacy
    interceptor, the cookie filter — all live on this side. QML views bind it
    via the WebProfile context property."""
    profile = QQuickWebEngineProfile(parent)
    profile.setStorageName("beryl")
    profile.setPersistentStoragePath(str(config.DATA_HOME / "profile"))
    profile.setCachePath(str(config.CACHE_HOME / "webcache"))
    profile.setHttpCacheType(QQuickWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentCookiesPolicy(
        QQuickWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
    # Qt persists per-site permission grants itself — no custom store needed
    profile.setPersistentPermissionsPolicy(
        QQuickWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk)

    profile.downloadRequested.connect(downloads.adopt)

    # every request passes the blocker: privacy headers always, filter-list
    # matching once the engine is compiled (daemon thread)
    profile.setUrlRequestInterceptor(blocker)
    blocker.start()

    # third-party cookie blocking; runs on the IO thread, keep it pure
    profile.cookieStore().setCookieFilter(lambda request: not request.thirdParty)

    return profile
