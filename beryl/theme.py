import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from PySide6.QtCore import (Property, QFileSystemWatcher, QObject, QTimer,
                            Signal)

THEMES_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "themes"
_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
_AWWW_CACHE = _CACHE / "awww"
_LAST_WALLPAPER = _CACHE / "world80" / "last-wallpaper"

# Frosted-dark defaults (tokyo-night-ish), used verbatim when no rice theme
# resolves. When one does, _build_theme() re-derives everything from the theme's
# config.toml tokens so beryl follows the rest of the rice, light themes and
# all. Colors are #AARRGGBB — the chrome stays translucent so Hyprland's blur
# shows through it; the page itself sits on the opaque viewBg.
_BASE = {
    "bg":        "#66161a24",   # window glass
    "card":      "#ee161a24",   # near-opaque overlays (completion, cheat sheet)
    "glassSoft": "#14ffffff",   # hover wash
    "border":    "#30ffffff",
    "divider":   "#1affffff",

    "text":      "#ffc8ccd8",
    "subtext":   "#ff7e87b0",

    "sel":       "#4d7aa2f7",   # active tab / completion selection wash
    "selText":   "#ffc8ccd8",

    "accent":    "#ff7aa2f7",
    "accent2":   "#ff7dcfff",
    "accentSoft":"#337aa2f7",
    "warn":      "#ffe0af68",
    "onAccent":  "#ff11121a",   # glyphs on accent fills (mode pill)

    "viewBg":    "#ff11121a",   # opaque page background (kills white flash)

    "radius":   16,
    "radiusSm": 10,
    "pad":      12,
    "font":     "monospace",
}

# mirrors themes/default/config.toml — the fallback when even the default toml
# is missing, so keys always resolve.
_TOKEN_FALLBACK = {
    "accent":      "#7aa2f7",
    "accent2":     "#7dcfff",
    "accent3":     "#bb9af7",
    "accent_warn": "#e0af68",
    "accent_dim":  "#3b3f51",
    "hue_green":   "#9ece6a",
    "hue_blue":    "#7aa2f7",
    "fg":          "#c8ccd8",
    "bg":          "#11121a",
    "font_mono":   "monospace",
}


def _rgba(hex_color, alpha="ff"):
    """Theme tomls store opaque "#rrggbb"; QML wants "#aarrggbb". Prefix the
    alpha, pass 8-digit through, expand #rgb. None for anything unrecognised so
    the caller keeps its default."""
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return "#" + h
    if len(h) == 6:
        return "#" + alpha + h
    if len(h) == 3:
        return "#" + alpha + "".join(c * 2 for c in h)
    return None


def _luminance(hex_color):
    """Rough perceptual luminance 0..1 of an opaque colour, for light/dark
    decisions."""
    h = (hex_color or "").lstrip("#")
    if len(h) == 8:
        h = h[2:]
    if len(h) != 6:
        return 0.0
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 0.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rel_lum(rgb):
    """WCAG relative luminance of (r, g, b) in 0..1 — gamma-corrected, unlike
    _luminance, so yellow reads as bright and blue as dark."""
    def lin(u):
        return u / 12.92 if u <= 0.03928 else ((u + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _legible(hex_color, dark):
    """Themes tune their accents for wallpaper art, not for text on frost:
    a mid-luminance accent (nature's honey gold, fuel's neon orange) melts
    into the glass wherever the wallpaper behind it fights it. Walk the
    colour toward the legible pole — white on dark themes, black on light —
    until it clears a luminance bar; hue survives, already-legible accents
    (moon's yellow, vinland's ice) pass through untouched."""
    h = (hex_color or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:
        h = h[2:]
    if len(h) != 6:
        return hex_color
    try:
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return hex_color
    pole = 1.0 if dark else 0.0
    ok = (lambda c: _rel_lum(c) >= 0.5) if dark else (lambda c: _rel_lum(c) <= 0.3)
    for _ in range(30):
        if ok(rgb):
            break
        rgb = [c + (pole - c) * 0.1 for c in rgb]
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def _focused_monitor():
    """Name of the focused Hyprland monitor ("" if unknowable). Monitors can
    show different themes; beryl should match the one being looked at."""
    try:
        out = subprocess.run(["hyprctl", "monitors", "-j"],
                             capture_output=True, text=True, timeout=2).stdout
        for m in json.loads(out):
            if m.get("focused"):
                return m.get("name", "")
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return ""


def _active_theme_dir():
    """Folder of the wallpaper awww shows on the focused monitor — the same
    resolution the quickshell loaders, frostify, mica and vellum use.
    BERYL_THEME (a name or a path) overrides it for headless testing. None if
    nothing resolves."""
    override = os.environ.get("BERYL_THEME", "").strip()
    if override:
        p = Path(override).expanduser() if "/" in override else THEMES_DIR / override
        return p if p.is_dir() else None
    try:
        out = subprocess.run(["awww", "query"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    mon = _focused_monitor()
    lines = out.splitlines()
    picked = next((l for l in lines if mon and f"{mon}:" in l), None)
    m = re.search(r"image:\s*(.+)", picked if picked is not None else out)
    if not m:
        return None
    d = Path(m.group(1).strip()).parent
    return d if d.is_dir() else None


def _read_tokens(theme_dir):
    """Theme config.toml layered over default/config.toml layered over the
    builtin fallback — flat keys, last write wins (same as the shell)."""
    tokens = dict(_TOKEN_FALLBACK)
    layers = [THEMES_DIR / "default" / "config.toml"]
    if theme_dir is not None:
        layers.append(theme_dir / "config.toml")
    for f in layers:
        try:
            tokens.update(tomllib.loads(f.read_text()))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return tokens


def _build_theme(tokens):
    """Re-derive beryl's palette from the rice tokens. Chrome hairlines follow
    `fg` rather than white so light themes (shiro) stay legible. Accents get
    a legibility clamp (_legible) — they're used as TEXT here (statusbar url,
    tab titles, page links), a harsher job than the shell's fills and lines."""
    theme = dict(_BASE)

    def col(key):
        v = tokens.get(key)
        return v if isinstance(v, str) and v.startswith("#") and _rgba(v) else None

    dark = _luminance(col("bg") or _TOKEN_FALLBACK["bg"]) < 0.5

    accent = col("accent")
    if accent:
        accent = _legible(accent, dark)
        theme["accent"]     = _rgba(accent)
        theme["sel"]        = _rgba(accent, "4d")
        theme["accentSoft"] = _rgba(accent, "33")

    accent2 = col("accent2")
    if accent2:
        theme["accent2"] = _rgba(_legible(accent2, dark))

    warn = col("accent_warn")
    if warn:
        theme["warn"] = _rgba(_legible(warn, dark))

    fg = col("fg") or col("text")
    if fg:
        theme["text"]      = _rgba(fg)
        theme["selText"]   = _rgba(fg)
        theme["subtext"]   = _rgba(fg, "aa")
        theme["border"]    = _rgba(fg, "30")
        theme["divider"]   = _rgba(fg, "1a")
        theme["glassSoft"] = _rgba(fg, "12")

    bg = col("bg")
    if bg:
        theme["bg"]       = _rgba(bg, "66")
        theme["card"]     = _rgba(bg, "ee")
        theme["viewBg"]   = _rgba(bg)
        theme["onAccent"] = _rgba(bg)

    font = tokens.get("font_mono")
    if isinstance(font, str) and font:
        theme["font"] = font

    return theme


class ThemeManager(QObject):
    """Follows the active rice theme (~/.config/themes/<x>) live. Watches
    ~/.cache/awww (touched on every wallpaper switch) plus the active theme's
    config.toml, so switching themes or editing one re-skins beryl while it
    runs. themeChanged fires after each rebuild; main.py re-sets the Theme
    context property, which re-evaluates every Theme.* binding in the QML."""
    themeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir = None
        self._theme = dict(_BASE)
        self._tokens = dict(_TOKEN_FALLBACK)
        self._snapshot = None

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._poke)
        self._watcher.fileChanged.connect(self._poke)
        # a theme switch touches several files in a burst — coalesce them
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._refresh)

        self._refresh(first=True)

    @Property(str, notify=themeChanged)
    def name(self):
        return self._dir.name if self._dir else ""

    @Property(str, notify=themeChanged)
    def themeDir(self):
        return str(self._dir) if self._dir else ""

    def theme_dict(self):
        return self._theme

    def is_dark(self):
        return _luminance(self._tokens.get("bg", "#11121a")) < 0.5

    def _poke(self, _path):
        self._debounce.start()

    def _refresh(self, first=False):
        d = _active_theme_dir()
        tokens = _read_tokens(d)
        snapshot = (str(d) if d else "",
                    tuple(sorted((k, str(v)) for k, v in tokens.items())))
        self._rewatch(d)
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot

        self._dir = d
        self._tokens = tokens
        self._theme = _build_theme(tokens)
        print(f"[theme] {self._dir.name if self._dir else '(defaults)'}", flush=True)
        if not first:
            self.themeChanged.emit()

    def _rewatch(self, d):
        """(Re-)arm the watcher. Dir watches catch atomic-replace saves and new
        files; file watches catch in-place edits. Stale paths are pruned by
        QFileSystemWatcher itself when they vanish; re-adding dupes is a no-op.

        The live theme-switch signal is the per-monitor cache FILES awww keeps
        under ~/.cache/awww/<ver>/<monitor>: awww rewrites them *in place* (same
        inode, bumped mtime) on every wallpaper/theme change, which fires inotify
        IN_MODIFY on the file but leaves the parent dir unchanged — so watching
        only the dir (as this used to) never noticed a switch. Watch the files
        directly, plus world80's last-wallpaper marker as a second signal."""
        want = [_AWWW_CACHE] + [p for p in _AWWW_CACHE.glob("*") if p.is_dir()]
        want += [f for sub in _AWWW_CACHE.glob("*") if sub.is_dir()
                 for f in sub.iterdir() if f.is_file()]
        want += [_LAST_WALLPAPER]
        want += [THEMES_DIR / "default" / "config.toml"]
        if d is not None:
            want += [d, d / "config.toml"]
        have = set(self._watcher.directories()) | set(self._watcher.files())
        missing = [str(p) for p in want if p.exists() and str(p) not in have]
        if missing:
            self._watcher.addPaths(missing)
