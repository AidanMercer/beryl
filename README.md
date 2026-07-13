# beryl

**a vim browser that wears your system theme**

beryl is a small, fast, private web browser you drive entirely from the
keyboard — full vim / Vimium muscle memory, a top tab strip, and frosted-glass
chrome that follows your rice (or a tokyo-night-ish default on its own). it's
the browser in world80, next to mica (files), vellum (editor), and pulse
(system monitor).

under the hood it's qtwebengine — de-googled blink, so no google api keys, no
telemetry, no crash reporting, no privacy sandbox — with a privacy hardening
layer on top and zero heavy ui. page speed is blink; the yazi feel is minimal
keyboard-driven chrome. qutebrowser proves the combo works; beryl is that idea,
themed and trimmed to the essentials.

> it's a personal thing i daily-drive, not a hardened product. no warranty,
> expect the odd sharp edge. developed on hyprland/wayland.

## install

runtime deps: PySide6 (≥6.8) built with qtwebengine, and python-adblock (Brave's
adblock-rust bindings — optional; without it the blocker just stays off).

```sh
# arch
sudo pacman -S pyside6 qt6-webengine python-adblock

# elsewhere: install your distro's qtwebengine + PySide6, then
pip install --user "PySide6>=6.8" "adblock>=0.6"
```

then:

```sh
git clone https://github.com/AidanMercer/beryl
./beryl/beryl.sh https://example.com
```

`beryl.sh` is single-instance — a second launch hands its urls to the running
one and exits, so it's safe to spam from a keybind (bind it in your wm; i use
super+b). drop `beryl.desktop` in `~/.local/share/applications/` to register it
as a browser / link handler.

## keys

normal mode is the default. `i` types into the page (insert), `Esc` comes back —
and focusing a text field flips you to insert on its own. everything below is
rebindable (see [config](#config)).

| | |
|---|---|
| **move** | `j`/`k` scroll · `d`/`u` half-page · `gg`/`G` top/bottom · `H`/`L` back/forward · `/ n N` find · `m`/`'` set/jump mark |
| **links** | `f`/`F` hint (this / new tab) · `gi` focus first input |
| **tabs** | `o`/`O` open (here / current url) · `t` new-tab open · `T` switch tab · `J`/`K` prev/next · `x`/`X` close/reopen |
| **windows** | `W` new window · `gw` detach tab · `ZZ` close window · `:qa` quit all |
| **page** | `r`/`R` reload / hard reload · `gu`/`gU` url up/root · `zi`/`zo`/`zz` zoom · `yy` yank url · `p`/`P` paste-and-go |
| **stuff** | `*` bookmark · `b` bookmarks · `gd` downloads · `gp` passwords · `s` settings · `h`/`?` this help |
| **ex** | `:` command line · `:open`/`:tabopen` url-or-search · `:tab <q>` switch tab |
| **passthrough** | `S-Esc` hand the whole keyboard to the page (remote desktops); `S-Esc` or `C-A-Esc` to leave |

## google sign-in

google blocks account sign-in from embedded engines like beryl on purpose — it's
an anti-token-theft measure (BotGuard/WAA), and it detects the kind of identity
spoofing you'd need to sneak past, so faking it only makes things worse. beryl
doesn't fight it. `:google-signin` signs you in through a real browser google
already trusts and carries the session back into beryl:

- **`:google-signin`** — already logged into google in firefox / zen / librewolf
  / waterfox? it grabs that session instantly, no window.
- **`:google-signin login`** — opens a real firefox-family browser for a fresh
  login, then pulls the cookies back the moment you're signed in.

re-run it any time to refresh an expired session. needs a firefox-family browser
installed (chromium-family isn't supported yet). the one thing no browser can
work around: a google workspace org that *enforces* context-aware session
binding will hard-block anything that isn't chrome.

## privacy

local data persists so logins and completion work, but nothing phones home and
pages get curbed on the wire:

- third-party cookies blocked (with an allowlist for sso login iframes)
- easylist + easyprivacy ad/tracker blocking
- `Sec-GPC: 1` + `DNT: 1` on every request
- webrtc restricted to public interfaces — no local-ip leak
- no dns-prefetch, no hyperlink-auditing beacons
- omnibar completion is local-only — your keystrokes never hit a search-suggest
  endpoint; the search engine only ever sees what you actually submit
- **`:clear`** — one-shot nuke of cookies, http cache, history, and session

canvas/font anti-fingerprinting is tor-browser territory; beryl doesn't pretend
to do it.

## importing from firefox / zen

carry your cookies (logins), history, bookmarks, and saved passwords over from a
firefox-family profile (zen by default):

```sh
./beryl/beryl.sh --import-zen             # everything
./beryl/beryl.sh --import-zen-passwords   # just the passwords
```

quit beryl first — the import needs the profile to itself.

## config

`~/.config/beryl/config.toml` is written on first run and live-reloaded when you
save it. a few of the knobs:

```toml
search = "https://duckduckgo.com/?q={}"
homepage = "about:blank"
adblock = true
restore_session = true
transparent_pages = false            # strip page backgrounds, let the frost show through
google_signin_domains = ["google.com", "youtube.com"]

[binds.normal]
# "gg" = "scroll-top"                # override any default; "" unbinds a key
```

## theming

running the world80 rice? beryl follows your live theme — wallpaper accent and
palette, light themes and all — and re-colors on the fly when you switch. on its
own it ships a frosted dark (tokyo-night-ish) default. pin a specific one with
`BERYL_THEME=<name> ./beryl/beryl.sh`.

## files

- data — `~/.local/share/beryl/` (profile, session, bookmarks, history, encrypted password vault)
- cache — `~/.cache/beryl/` (log, web cache, adblock lists)
- config — `~/.config/beryl/config.toml`
