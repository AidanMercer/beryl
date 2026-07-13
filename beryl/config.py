import os
import tomllib
from pathlib import Path

# `or` not a get() default: an empty (set-but-blank) XDG var must not yield
# relative paths in whatever directory beryl was launched from
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "beryl"
LOG_FILE = CACHE_HOME / "beryl.log"

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "beryl"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "beryl"
CONFIG_FILE = CONFIG_DIR / "config.toml"

_DEFAULTS = {
    "homepage": "about:blank",
    "search": "https://duckduckgo.com/?q={}",
    "download_dir": "~/Downloads",
    "scroll_step": 80,          # px per j/k (multiplied by counts)
    "hint_chars": "asdfghjkl",
    "seq_timeout_ms": 800,      # how long a pending multi-key sequence waits
    "adblock": True,
    "adblock_update_days": 7,
    "history_days": 180,
    "restore_session": True,
    "tab_freeze_minutes": 5,
    # offer to save logins and autofill them (encrypted at rest); gp lists them
    "passwords": True,
    # zen-style transparency: strip page backgrounds so the frosted window
    # shows through the site itself
    "transparent_pages": False,
    # palette forced onto transparent pages: "auto" follows the rice theme,
    # "dark"/"light" pin it
    "page_colors": "auto",
    # third-party cookies are blocked EXCEPT cookies belonging to these
    # domains — microsoft sso silently refreshes tokens through
    # login.microsoftonline.com iframes and breaks without them
    "cookie_allow_3p": [
        "login.microsoftonline.com", "login.live.com",
        "login.windows.net", "login.microsoft.com",
        # google sign-in runs a cross-domain cookie check ("we've detected a
        # problem with your cookie settings" / CookieMismatch) that spans the
        # apex — the subdomain alone isn't enough (google's own advice is to
        # allow www.google.com). endswith covers accounts./www.google.com.
        "google.com",
    ],
    # hosts that get a Firefox UA instead of the Chrome masquerade: google's
    # oauth "this browser may not be secure" gate blocks chromium-embedded
    # engines but allows firefox. Sign-in only — the rest of google keeps the
    # Chrome UA. Add a host here if its sign-in claims the browser's insecure.
    "firefox_ua_hosts": ["accounts.google.com"],
    # sites that get the whole keyboard automatically (remote desktops etc);
    # fnmatch patterns against the host. S-Esc still toggles manually.
    "passthrough_sites": [
        "*.wvd.microsoft.com", "windows.cloud.microsoft",
        "*.cloudpc.microsoft.com",
    ],
}

# written to ~/.config/beryl/config.toml on first run so there's something to edit
_TEMPLATE = """\
# beryl config — everything here is optional; delete a line to use the default.
# edits apply live (beryl watches this file).

homepage = "about:blank"
search = "https://duckduckgo.com/?q={}"
download_dir = "~/Downloads"

scroll_step = 80           # px per j/k, multiplied by counts (5j)
hint_chars = "asdfghjkl"   # link-hint label alphabet (home row)
seq_timeout_ms = 800       # multi-key sequences (gg) give up after this

adblock = true
adblock_update_days = 7    # refresh easylist/easyprivacy this often
history_days = 180         # visits older than this are purged at startup
restore_session = true     # reopen last session's tabs (lazily) on launch
tab_freeze_minutes = 5     # freeze background tabs after this long hidden
passwords = true           # offer to save & autofill logins (gp lists them)
transparent_pages = false  # zen-style: strip page backgrounds, frost shows through
page_colors = "auto"       # transparent-page palette: auto (follow theme) / dark / light

# third-party cookies are blocked except cookies belonging to these domains
# (microsoft sso needs its login iframes; add your idp here if sso loops)
cookie_allow_3p = [
  "login.microsoftonline.com", "login.live.com",
  "login.windows.net", "login.microsoft.com",
  "google.com",   # google sign-in cookie check spans the apex (accounts./www.google.com)
]

# hosts that automatically get the whole keyboard (remote desktops like avd);
# fnmatch patterns. shift+esc enters passthrough manually anywhere; while in
# passthrough, ctrl+alt+esc (or shift+esc) hands the keyboard back to beryl.
passthrough_sites = [
  "*.wvd.microsoft.com", "windows.cloud.microsoft", "*.cloudpc.microsoft.com",
]

# key overrides merge over the defaults per key; "" unbinds a default.
# sequences use single chars and <angle> notation: "gg", "<C-d>", "<Esc>".
[binds.normal]
# "gg" = "scroll-top"

[binds.insert]
# "<Esc>" = "mode-normal"
"""


def ensure():
    """Drop a commented default config on first run so the knobs are
    discoverable. Best-effort — never blocks startup."""
    try:
        if not CONFIG_FILE.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(_TEMPLATE)
    except OSError:
        pass


def load():
    cfg = {k: (v.copy() if isinstance(v, (dict, list)) else v)
           for k, v in _DEFAULTS.items()}
    cfg["binds"] = {}
    try:
        data = tomllib.loads(CONFIG_FILE.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return cfg
    for key in _DEFAULTS:
        if key in data:
            cfg[key] = data[key]
    if isinstance(data.get("binds"), dict):
        cfg["binds"] = data["binds"]
    return cfg


def load_or_none():
    """Live-reload variant: None on a parse error, so a half-saved edit keeps
    the running config instead of silently resetting everything to defaults
    until the file is fixed."""
    try:
        tomllib.loads(CONFIG_FILE.read_text())
    except tomllib.TOMLDecodeError as e:
        print(f"[config] parse error, keeping running config: {e}", flush=True)
        return None
    except OSError:
        pass   # missing file is a valid state (defaults)
    return load()
