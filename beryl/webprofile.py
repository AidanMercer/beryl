from PySide6.QtWebEngineQuick import QQuickWebEngineProfile

from . import config


def build(cfg, downloads, parent=None):
    """The one persistent Chromium profile. Built in Python (not QML) because
    the pieces that hang off it — download adoption, and later the adblock
    interceptor and cookie filter — all live on this side. QML views bind it
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
    return profile
