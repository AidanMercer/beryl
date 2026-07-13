import json
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtWebEngineCore import (QWebEngineUrlRequestInfo,
                                     QWebEngineUrlRequestInterceptor)

from . import config

# The interceptor runs on Chromium's IO thread: keep interceptRequest lean,
# guard the engine handoff with a lock, and pass everything through while the
# engine is still compiling on the daemon thread.

_LISTS = {
    "easylist.txt": "https://easylist.to/easylist/easylist.txt",
    "easyprivacy.txt": "https://easylist.to/easylist/easyprivacy.txt",
}

_DIR = config.CACHE_HOME / "adblock"

# Google's OAuth "secure browser" gate blocks Chromium-embedded engines
# (QtWebEngine) even behind our Chrome UA, but lets Firefox through — Firefox
# doesn't send Sec-CH-UA client hints, so there's no UA-vs-hints mismatch for
# Google to catch. We present Firefox to the google sign-in hosts ONLY (the
# Chrome UA stays everywhere else, which the microsoft/AVD stack depends on).
# Same workaround qutebrowser ships. Applied per-request in the interceptor.
_FIREFOX_UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) "
               "Gecko/20100101 Firefox/140.0")
# the low-entropy client hints Chromium sends by default — blanked for the
# Firefox-UA hosts so the headers don't contradict the spoofed UA
_CH_HEADERS = (b"Sec-CH-UA", b"Sec-CH-UA-Mobile", b"Sec-CH-UA-Platform",
               b"Sec-CH-UA-Full-Version", b"Sec-CH-UA-Full-Version-List",
               b"Sec-CH-UA-Platform-Version", b"Sec-CH-UA-Arch",
               b"Sec-CH-UA-Model", b"Sec-CH-UA-Bitness")


def _firefox_ua_host(host, cfg):
    hosts = cfg.get("firefox_ua_hosts", [])
    return any(host == d or host.endswith("." + d) for d in hosts)

_R = QWebEngineUrlRequestInfo.ResourceType
_RTYPE = {
    _R.ResourceTypeMainFrame: "document",
    _R.ResourceTypeSubFrame: "subdocument",
    _R.ResourceTypeStylesheet: "stylesheet",
    _R.ResourceTypeScript: "script",
    _R.ResourceTypeImage: "image",
    _R.ResourceTypeFontResource: "font",
    _R.ResourceTypeObject: "object",
    _R.ResourceTypeMedia: "media",
    _R.ResourceTypeXhr: "xhr",
    _R.ResourceTypeJson: "xhr",
    _R.ResourceTypePing: "ping",
    _R.ResourceTypeCspReport: "csp_report",
    _R.ResourceTypeWebSocket: "websocket",
    _R.ResourceTypePrefetch: "other",
    _R.ResourceTypeFavicon: "image",
}


class Blocker(QWebEngineUrlRequestInterceptor):
    """easylist + easyprivacy via Brave's adblock-rust. Also stamps the
    privacy headers on every request — the interceptor sees them all anyway."""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._lock = threading.Lock()
        self._engine = None
        self._building = False
        self.blocked = 0

    # ---- IO thread ---------------------------------------------------------
    def interceptRequest(self, info):
        info.setHttpHeader(b"DNT", b"1")
        info.setHttpHeader(b"Sec-GPC", b"1")

        # present Firefox to google's sign-in gate (see _FIREFOX_UA); blank the
        # Chromium client hints so they don't give the game away
        if _firefox_ua_host(info.requestUrl().host(), self._cfg):
            info.setHttpHeader(b"User-Agent", _FIREFOX_UA)
            for h in _CH_HEADERS:
                info.setHttpHeader(h, b"")

        # checked per-request so the config toggle applies live (dict reads
        # are GIL-atomic; worst case one request uses the old value)
        if not self._cfg.get("adblock", True):
            return
        rtype = info.resourceType()
        if rtype == _R.ResourceTypeMainFrame:
            return                       # never block navigation itself
        with self._lock:
            engine = self._engine
        if engine is None:
            return
        try:
            result = engine.check_network_urls(
                info.requestUrl().toString(),
                info.firstPartyUrl().toString(),
                _RTYPE.get(rtype, "other"))
        except Exception:
            return
        if result.matched:
            info.block(True)
            self.blocked += 1

    # ---- daemon thread -----------------------------------------------------
    def start(self):
        """Idempotent: also called on config reload, so flipping adblock on
        after booting with it off compiles the engine then."""
        if self._cfg.get("adblock", True) and self._engine is None \
                and not self._building:
            self._building = True
            threading.Thread(target=self._build, daemon=True, name="adblock").start()

    def _build(self):
        try:
            self._build_inner()
        finally:
            self._building = False

    def _build_inner(self):
        try:
            import adblock
        except ImportError:
            print("[adblock] python-adblock missing — blocker off", flush=True)
            return
        _DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()

        cached = _DIR / "engine.bin"
        lists_fresh = self._refresh_lists()

        engine = None
        if cached.exists() and not lists_fresh:
            try:
                engine = adblock.Engine.deserialize_from_file(str(cached))
            except Exception:
                engine = None
        if engine is None:
            fs = adblock.FilterSet()
            got_any = False
            for name in _LISTS:
                try:
                    fs.add_filter_list((_DIR / name).read_text(errors="replace"))
                    got_any = True
                except OSError:
                    pass
            if not got_any:
                print("[adblock] no lists available — blocker off", flush=True)
                return
            engine = adblock.Engine(filter_set=fs)
            try:
                engine.serialize_to_file(str(cached))
            except Exception:
                pass

        with self._lock:
            self._engine = engine
        print(f"[adblock] engine ready in {time.monotonic() - t0:.2f}s", flush=True)

    def _refresh_lists(self):
        """Download lists that are missing or older than adblock_update_days.
        Returns True if anything changed (forces a recompile)."""
        meta_path = _DIR / "meta.json"
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            meta = {}
        max_age = float(self._cfg.get("adblock_update_days", 7)) * 86400
        changed = False
        for name, url in _LISTS.items():
            path = _DIR / name
            if path.exists() and time.time() - meta.get(name, 0) < max_age:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "beryl"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    path.write_bytes(resp.read())
                meta[name] = time.time()
                changed = True
                print(f"[adblock] fetched {name}", flush=True)
            except OSError as e:
                print(f"[adblock] fetch {name} failed: {e}", flush=True)
        try:
            meta_path.write_text(json.dumps(meta))
        except OSError:
            pass
        return changed
