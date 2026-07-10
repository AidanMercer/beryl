// beryl: link hints. Runs in an ISOLATED world (ApplicationWorld) — the page
// can't see or clobber __beryl, and no webchannel is needed because Python
// drives every exchange through runJavaScript round-trips. Labels are
// fixed-position divs inside a closed shadow root, so page CSS can't touch
// them and `* { all: unset }` pages can't break them.
var __beryl = __beryl || {};
__beryl.hints = (function () {
    "use strict";
    var host = null, items = [];

    function clickables() {
        var sel = 'a[href], button, input:not([type=hidden]), textarea, select,' +
                  ' summary, [onclick], [role=link], [role=button], [role=tab],' +
                  ' [role=menuitem], [role=checkbox], [contenteditable=""],' +
                  ' [contenteditable=true], [tabindex]:not([tabindex="-1"])';
        var seen = new Set(), out = [];
        document.querySelectorAll(sel).forEach(function (el) {
            if (seen.has(el)) return;
            seen.add(el);
            var r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return;
            if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return;
            var cs = getComputedStyle(el);
            if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") return;
            out.push({ el: el, rect: r });
        });
        return out;
    }

    // uniform-length base-k labels — prefix-free by construction
    function labels(n, alphabet) {
        var k = alphabet.length;
        var len = Math.max(1, Math.ceil(Math.log(n) / Math.log(k)));
        var out = [];
        for (var i = 0; i < n; i++) {
            var s = "", x = i;
            for (var j = 0; j < len; j++) { s = alphabet[x % k] + s; x = (x / k) | 0; }
            out.push(s);
        }
        return out;
    }

    function editable(el) {
        if (el.isContentEditable) return true;
        var t = el.tagName;
        if (t === "TEXTAREA" || t === "SELECT") return true;
        if (t === "INPUT")
            return !/^(button|checkbox|radio|submit|reset|file|image|range|color|hidden)$/
                .test((el.type || "text").toLowerCase());
        return false;
    }

    function show(alphabet) {
        clear();
        var els = clickables();
        if (els.length === 0) return 0;
        host = document.createElement("beryl-hints");
        var root = host.attachShadow({ mode: "closed" });
        var box = document.createElement("div");
        box.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none;";
        var labs = labels(els.length, alphabet);
        els.forEach(function (c, i) {
            var d = document.createElement("div");
            d.textContent = labs[i];
            d.style.cssText =
                "position:fixed;left:" + Math.max(0, c.rect.left - 2) + "px;top:" +
                Math.max(0, c.rect.top - 2) + "px;background:#f8e08e;color:#1a1a1a;" +
                "font:bold 11px monospace;padding:1px 4px;border-radius:3px;" +
                "box-shadow:0 1px 3px rgba(0,0,0,.55);";
            box.appendChild(d);
            items.push({ el: c.el, label: labs[i], div: d });
        });
        root.appendChild(box);
        document.documentElement.appendChild(host);
        return els.length;
    }

    function filter(typed) {
        var live = 0;
        items.forEach(function (it) {
            var m = it.label.indexOf(typed) === 0;
            it.div.style.display = m ? "" : "none";
            if (m) live++;
        });
        return live;
    }

    function activate(typed, newTab) {
        var it = null;
        for (var i = 0; i < items.length; i++)
            if (items[i].label === typed) { it = items[i]; break; }
        clear();
        if (!it) return { miss: true };
        var el = it.el;
        if (newTab && el.href) return { open: el.href };
        if (editable(el)) {
            el.focus();                     // editable.js flips us to insert
            return { focused: true };
        }
        el.focus();
        el.click();                         // full synthetic sequence, works on js-only buttons
        return { clicked: true };
    }

    function firstInput() {                 // gi
        var els = clickables();
        for (var i = 0; i < els.length; i++)
            if (editable(els[i].el)) { els[i].el.focus(); return true; }
        return false;
    }

    function clear() {
        if (host) host.remove();
        host = null;
        items = [];
    }

    return { show: show, filter: filter, activate: activate,
             firstInput: firstInput, clear: clear };
})();
