import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import (QObject, QProcess, QProcessEnvironment, QTimer,
                            Slot)

from . import importer

# Why beryl doesn't just sign into Google in-app: Google blocks interactive
# account sign-in from embedded engines (QtWebEngine) with its BotGuard/WAA
# attestation. That block is BY DESIGN (an anti-token-theft measure every SSO
# vendor documents), and it detects the navigator tampering a spoof would
# need — so faking a Chrome/Firefox identity only makes detection MORE certain.
# That whole arms race was tried and reverted (see beryl-browser memory).
#
# The winning move is to never type the password inside beryl. Complete the
# login once in a real browser Google trusts — any Firefox/Gecko build, the
# same reason Zen works — then carry the resulting session cookies into beryl's
# cookie jar. Transplanting a Google session still works on Linux in 2026:
# DBSC (device-bound cookies) is Chrome/Windows-only, per-site opt-in, with
# graceful fallback to ordinary long-lived cookies for non-DBSC browsers — and
# it has no Linux support, so a session minted by Firefox on this machine is
# freely portable. This module automates the carry two ways:
#   1. harvest the session straight from an existing Firefox/Zen profile that's
#      already logged into Google (the common case — instant, no window), or
#   2. open a throwaway real-browser window for a one-shot login, then grab the
#      cookies back the moment they appear.
# Re-runnable anytime: Google rotates session cookies, so :google-signin again
# re-harvests a fresh set. The one thing no client can fix: a Google Workspace
# org whose admin enforces Context-Aware "session binding" hard-blocks
# non-DBSC browsers from the protected apps.

# real Gecko browsers, in preference order (vanilla firefox has the most
# predictable flags; any firefox fork works — they all pass Google's gate and
# store cookies in the same plaintext cookies.sqlite we read back)
_GECKO = ["firefox", "firefox-esr", "librewolf", "waterfox", "icecat",
          "zen", "zen-browser"]

# firefox-family profile roots to scan for an already-logged-in Google session
_PROFILE_ROOTS = [
    Path.home() / ".config" / "zen",
    Path.home() / ".mozilla" / "firefox",
    Path.home() / ".mozilla" / "icecat",
    Path.home() / ".librewolf",
    Path.home() / ".waterfox",
]

# any one of these on a google host means "there's a live session in here"
_SESSION_NAMES = {"SID", "__Secure-1PSID", "__Secure-3PSID", "SSID", "HSID"}

_LOGIN_URL = "https://accounts.google.com/"
_POLL_MS = 2000
_DEADLINE_MS = 6 * 60 * 1000
# arg words that force a fresh interactive login instead of harvesting an
# existing (possibly stale) session
_FORCE_WORDS = {"login", "new", "fresh", "reauth", "relogin"}


def _gecko_profile_dirs():
    """Every firefox-family profile dir with a cookies.sqlite, freshest first —
    candidate sources for an existing Google session."""
    found = []
    for root in _PROFILE_ROOTS:
        if root.is_dir():
            found += list(root.glob("*/cookies.sqlite"))
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.parent for p in found]


def _find_browser():
    for name in _GECKO:
        path = shutil.which(name)
        if path:
            return path
    return None


class GoogleSignIn(QObject):
    """Drives :google-signin. Owns at most one helper browser + temp profile at
    a time; cleans both up on completion, timeout, or app quit."""

    def __init__(self, profile, api, tabs, cfg, parent=None):
        super().__init__(parent)
        self._profile = profile
        self._api = api
        self._tabs = tabs
        self._cfg = cfg
        self._proc = None
        self._tmp = None
        self._harvested = False
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._check)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._give_up)

    def _domains(self):
        d = self._cfg.get("google_signin_domains") or ["google.com", "youtube.com"]
        return [str(x) for x in d]

    def _toast(self, msg, warn=False):
        self._api.toast.emit(msg, warn)

    def _cookie_store(self):
        return self._profile.cookieStore()

    # ---- entry point ---------------------------------------------------------
    @Slot(str)
    def start(self, arg=""):
        force = arg.strip().lower() in _FORCE_WORDS
        domains = self._domains()
        if not force:
            src = self._existing_session(domains)
            if src is not None:
                where, rows = src
                n = importer.inject_cookies(self._cookie_store(), rows, domains)
                self._toast(f"imported google session from {where} ({n} cookies)"
                            " — reloading", False)
                self._api.reloadRequested.emit(False)
                return
        self._launch(domains)

    def _existing_session(self, domains):
        """First firefox-family profile already logged into Google → (label,
        google-scoped rows). None if nothing's signed in."""
        for d in _gecko_profile_dirs():
            rows = importer.read_cookie_rows(d / "cookies.sqlite")
            if rows and importer.has_session(rows, domains, _SESSION_NAMES):
                google = [r for r in rows if importer.host_matches(r[2], domains)]
                # label like "zen" / "firefox" from the profile root
                return d.parent.name.lstrip("."), google
        return None

    # ---- interactive fallback ------------------------------------------------
    def _launch(self, domains):
        browser = _find_browser()
        if browser is None:
            self._toast("no firefox-family browser found — install firefox "
                        "(or librewolf/waterfox/zen) to sign in, then "
                        ":google-signin", True)
            return
        # a re-run supersedes any prior helper — kill it and its temp profile
        # so the fresh launch gets a clean, unlocked profile dir
        self._finish()
        self._tmp = Path(tempfile.mkdtemp(prefix="beryl-signin-"))
        self._harvested = False
        env = QProcessEnvironment.systemEnvironment()
        env.insert("MOZ_NO_REMOTE", "1")   # force a separate instance instead
                                           # of a tab in the running firefox/zen
        self._proc = QProcess(self)
        self._proc.setProcessEnvironment(env)
        self._proc.finished.connect(self._on_finished)
        self._proc.start(browser,
                         ["-no-remote", "-profile", str(self._tmp), _LOGIN_URL])
        self._toast(f"opening {Path(browser).name} — sign in to google, beryl "
                    "will grab the session automatically", False)
        self._poll.start()
        self._deadline.start(_DEADLINE_MS)

    def _check(self):
        if self._harvested or self._tmp is None:
            return
        rows = importer.read_cookie_rows(self._tmp / "cookies.sqlite")
        domains = self._domains()
        if rows and importer.has_session(rows, domains, _SESSION_NAMES):
            self._harvest(rows, domains)

    def _harvest(self, rows, domains):
        google = [r for r in rows if importer.host_matches(r[2], domains)]
        n = importer.inject_cookies(self._cookie_store(), google, domains)
        self._harvested = True
        self._poll.stop()
        self._deadline.stop()
        self._toast(f"google session imported ({n} cookies) — reloading; you "
                    "can close the sign-in window", False)
        self._api.reloadRequested.emit(False)

    def _on_finished(self, exit_code=0, exit_status=None):
        # window closed BY THE USER (deliberate termination disconnects this
        # first, so we don't fire on our own re-run/quit): last chance to catch
        # a session that landed between polls
        if not self._harvested and self._tmp is not None:
            rows = importer.read_cookie_rows(self._tmp / "cookies.sqlite")
            domains = self._domains()
            if rows and importer.has_session(rows, domains, _SESSION_NAMES):
                self._harvest(rows, domains)
            else:
                self._toast("sign-in window closed before completing — "
                            ":google-signin login to retry", True)
        self._poll.stop()
        self._deadline.stop()
        self._cleanup_tmp()

    def _give_up(self):
        self._poll.stop()
        if not self._harvested:
            self._toast("sign-in timed out — :google-signin login to retry", True)
        self._finish()

    # ---- lifecycle -----------------------------------------------------------
    def _finish(self):
        self._terminate_proc()
        self._cleanup_tmp()

    def _terminate_proc(self):
        p = self._proc
        self._proc = None
        if p is None:
            return
        # deliberate kill — don't let finished() run the user-close handler
        try:
            p.finished.disconnect(self._on_finished)
        except (RuntimeError, TypeError):
            pass
        try:
            if p.state() != QProcess.ProcessState.NotRunning:
                p.terminate()
                if not p.waitForFinished(2000):
                    p.kill()
                    p.waitForFinished(1000)
            p.deleteLater()
        except RuntimeError:
            pass   # C++ side already gone

    def _cleanup_tmp(self):
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def stop(self):
        """aboutToQuit: never leave a helper browser or temp profile behind."""
        self._poll.stop()
        self._deadline.stop()
        self._finish()
