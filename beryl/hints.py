import json

from PySide6.QtCore import QObject

# Hint-mode session state. The KeyController consumes every key while in hint
# mode and feeds it here; each keystroke round-trips to hints.js in the
# isolated world (~1-2ms). Uniform-length prefix-free labels mean a unique
# prefix identifies its target — we activate as soon as exactly one remains.


class Hints(QObject):
    def __init__(self, cfg, api, tabs, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._api = api
        self._tabs = tabs
        self._keys = None       # set late (keys needs hints, hints needs keys)
        self._typed = ""
        self._new_tab = False

    def set_keys(self, keys):
        self._keys = keys

    def start(self, new_tab):
        self._typed = ""
        self._new_tab = new_tab
        alphabet = json.dumps(self._cfg.get("hint_chars", "asdfghjkl"))
        self._api.js(f"__beryl.hints.show({alphabet})", self._shown, world=1)

    def _shown(self, n):
        if not n:
            self._api.toast.emit("no hints", True)
            return
        self._keys.set_mode("hint")

    def key(self, ks):
        """Called for every key while in hint mode; everything is consumed."""
        if ks == "<Esc>":
            self.cancel()
        elif ks == "<BS>":
            self._typed = self._typed[:-1]
            self._filter()
        elif len(ks) == 1 and ks in self._cfg.get("hint_chars", "asdfghjkl"):
            self._typed += ks
            self._filter()
        # anything else: swallowed silently (scrolling etc cancels via Esc)

    def _filter(self):
        typed = json.dumps(self._typed)
        self._api.js(f"__beryl.hints.filter({typed})", self._filtered, world=1)

    def _filtered(self, live):
        if live == 0 and self._typed:
            self._typed = self._typed[:-1]     # dead key — pretend it didn't happen
            self._filter()
        elif live == 1:
            typed = json.dumps(self._typed)
            new_tab = "true" if self._new_tab else "false"
            self._api.js(f"__beryl.hints.activate({typed}, {new_tab})",
                         self._activated, world=1)

    def _activated(self, res):
        self._keys.set_mode("normal")
        if not isinstance(res, dict):
            return
        if res.get("open"):
            self._tabs.newTab(res["open"], True)   # F = background tab, vimium-style
        # focused → editable.js flips to insert on its own; clicked → done

    def cancel(self):
        self._api.js("__beryl.hints.clear()", world=1)
        self._keys.set_mode("normal")
