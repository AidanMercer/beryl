import os
import tomllib
from pathlib import Path

CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "beryl"
LOG_FILE = CACHE_HOME / "beryl.log"

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "beryl"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "beryl"
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
