import QtQuick
import QtWebChannel
import QtWebEngine

// One live page. All per-view signal wiring lives here; state flows into the
// TabModel via viewState() so the strip and statusbar stay model-driven.
WebEngineView {
    id: view
    required property int tabUid
    property string initialUrl: ""

    // "on screen" = parented into a real window, not the hidden ViewHost
    // vault (item visibility can't tell those apart — the vault's items are
    // visible inside an unshown window)
    readonly property bool shown: Window.window !== null && Window.window.visible

    // a fullscreen view stashed into the vault (tab switch) must unwind
    // Chromium's fullscreen state, or the page believes it's still fullscreen
    // and its own exit event later gets rejected by the !shown branch
    onShownChanged: {
        if (!shown && isFullScreen)
            fullScreenCancelled()
    }

    anchors.fill: parent   // fits the vault slot or a window's viewport alike

    profile: WebProfile
    // opaque theme bg kills the white flash; transparent mode lets the frost
    // show through pages instead (transparent.js strips their backgrounds)
    backgroundColor: Config.transparent_pages ? "transparent" : Theme.viewBg

    settings.focusOnNavigationEnabled: false   // pages don't get to grab the keyboard
    settings.dnsPrefetchEnabled: false         // no speculative traffic
    settings.hyperlinkAuditingEnabled: false   // no a[ping] beacons
    settings.webRTCPublicInterfacesOnly: true  // no local-IP leak
    settings.fullScreenSupportEnabled: true    // avd / video fullscreen

    Component.onCompleted: {
        if (initialUrl !== "")
            url = initialUrl
    }

    // ---- auto-insert: editable.js posts page focus over the webchannel ------
    webChannel: WebChannel {
        registeredObjects: [pageBridge]
    }
    readonly property QtObject pageBridge: QtObject {
        WebChannel.id: "bridge"
        function editableFocused(on) {
            if (view.shown)                // background tabs don't get a vote
                Vim.pageEditable(on === true)
        }
        // creds.js claims an origin; never trust it — a login only counts for
        // the page actually loaded here (the main frame's origin). A cross-
        // origin iframe can't phish another site's saved password this way.
        function pageOrigin() {
            var u = view.url.toString()
            var m = u.match(/^(https?:\/\/[^\/]+)/)
            return m ? m[1] : ""
        }
        // QWebChannel delivers this return value to creds.js's trailing
        // callback — the JS-side cb arg never reaches here
        function credsFor(origin) {
            var o = pageOrigin()
            return (o !== "" && origin === o) ? Vault.credsFor(o) : []
        }
        function credsSubmitted(origin, username, password) {
            var o = pageOrigin()
            if (o !== "" && origin === o && view.shown)
                Vault.submitted(o, username, password)
        }
    }
    // transparent mode strips page backgrounds AND repaints their text in the
    // rice's palette — without the repaint, a site's white-background colors
    // (near-black text, dark links) sit invisible on a dark frost. Only
    // background-color is cleared, so sprites/hero images survive; hint labels
    // live in a closed shadow root the * selector can't reach.
    // returns {css, pal}: the stylesheet plus the palette in computed-style
    // form ("rgb(r, g, b)") — strip() compares getComputedStyle().color
    // against pal to spot text the sheet failed to repaint (sites pinning
    // colors with their own !important on class selectors beat our
    // element-selector rules; GitHub's Link--muted/Link--primary do exactly
    // this and sat unreadable in whatever palette the site chose)
    function transparentTheme() {
        function rgba(c, a) {
            var k = Qt.color(c)
            return "rgba(" + Math.round(k.r * 255) + "," + Math.round(k.g * 255) + ","
                 + Math.round(k.b * 255) + "," + (a !== undefined ? a : k.a).toFixed(2) + ")"
        }
        function cssRgb(c) {
            var k = Qt.color(c)
            return "rgb(" + Math.round(k.r * 255) + ", " + Math.round(k.g * 255) + ", "
                 + Math.round(k.b * 255) + ")"
        }
        function cssRgba(c, a) {
            var k = Qt.color(c)
            return "rgba(" + Math.round(k.r * 255) + ", " + Math.round(k.g * 255) + ", "
                 + Math.round(k.b * 255) + ", " + a + ")"
        }
        // theme colors are clamped for the CHROME's side of the glass
        // (theme.py); pinned page_colors can put the page on the opposite
        // side — re-clamp against the page's own dark/light so a light rice
        // accent doesn't paint invisible links on a pinned-dark page
        function relLum(c) {
            function lin(u) { return u <= 0.03928 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4) }
            var k = Qt.color(c)
            return 0.2126 * lin(k.r) + 0.7152 * lin(k.g) + 0.0722 * lin(k.b)
        }
        function legible(c, wantDark) {
            var k = Qt.color(c)
            var p = wantDark ? 1 : 0
            for (var i = 0; i < 30; i++) {
                if (wantDark ? relLum(k) >= 0.5 : relLum(k) <= 0.3)
                    break
                k = Qt.rgba(k.r + (p - k.r) * 0.1, k.g + (p - k.g) * 0.1,
                            k.b + (p - k.b) * 0.1, 1)
            }
            return k
        }
        // page_colors: auto rides the rice theme; dark/light pin the palette
        // (links keep the theme accent either way — it's tuned for the frost)
        var mode = Config.page_colors || "auto"
        var dark = mode === "auto" ? Qt.color(Theme.bg).hslLightness < 0.5
                                   : mode === "dark"
        var auto = mode === "auto"
        var textC = auto ? legible(Theme.text, dark) : (dark ? "#eceff4" : "#1a1b22")
        var subC  = auto ? legible(Theme.subtext, dark) : (dark ? "#b2b8c8" : "#5c5e6e")
        var linkC = legible(Theme.accent, dark)
        var text = rgba(textC, 1)
        var sub = rgba(subC, 1)
        var border = auto ? rgba(Theme.border)
                          : (dark ? "rgba(255,255,255,0.14)" : "rgba(0,0,0,0.15)")
        // text fields get a whisper of frost so they read as fields, capped
        // low — full-strength theme cards turned search bars into slabs.
        // buttons stay fully transparent (card-colored circles read as blobs).
        function capped(c, cap) {
            var k = Qt.color(c)
            return "rgba(" + Math.round(k.r * 255) + "," + Math.round(k.g * 255) + ","
                 + Math.round(k.b * 255) + "," + Math.min(k.a, cap).toFixed(2) + ")"
        }
        var field = auto ? capped(Theme.card, 0.35)
                         : (dark ? "rgba(16,18,26,0.35)" : "rgba(255,255,255,0.40)")
        // floating UI (popups, menus, tooltips) sits on TOP of other page
        // content — see-through, it's unreadable. strip() paints detected
        // surfaces with this card; alpha high so the text underneath loses.
        var cardC = auto ? Theme.card : (dark ? "#10121a" : "#ffffff")
        // layered halo, not a single drop shadow: a tight edge plus a soft
        // glow gives every glyph its own local scrim, so text survives even
        // where a bright wallpaper region bleeds through the frost
        var halo = dark ? "0 0 2px rgba(0,0,0,0.85),0 1px 6px rgba(0,0,0,0.55)"
                        : "0 0 2px rgba(255,255,255,0.90),0 1px 6px rgba(255,255,255,0.65)"
        // -webkit-text-fill-color: a transparent fill (gradient-text effects)
        // outlives the bg-gradient strip and leaves invisible headings —
        // currentcolor folds it back into the repainted color
        var css = "html,body{background:transparent !important;}"
             + "*{background-color:transparent !important;"
             + "color:" + text + " !important;"
             + "-webkit-text-fill-color:currentcolor !important;"
             + "border-color:" + border + " !important;"
             + "text-shadow:" + halo + " !important;"
             + "box-shadow:none !important;"    // shadows draw ghost boxes on frost
             // any scrollbar-color/width in page CSS switches the element to
             // standard scrollbars and our ::-webkit-scrollbar rules go dead —
             // reset to auto so the pill below wins everywhere
             + "scrollbar-color:auto !important;scrollbar-width:auto !important;}"
             + "a,a *{color:" + rgba(linkC, 1) + " !important;}"
             // Chromium's default scrollbar paints an opaque track slab down
             // the frost: bare the track, slim the gutter, and roll the thumb
             // into an inset accent pill (transparent border + padding-box
             // clip keeps it off the window edge)
             + "::-webkit-scrollbar{width:10px;height:10px;background:transparent !important;}"
             + "::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:transparent !important;}"
             + "::-webkit-scrollbar-thumb{background-color:" + rgba(linkC, 0.40)
             + " !important;border-radius:5px;border:2px solid transparent !important;"
             + "background-clip:padding-box !important;}"
             + "::-webkit-scrollbar-thumb:hover,::-webkit-scrollbar-thumb:active{background-color:"
             + rgba(linkC, 0.70) + " !important;}"
             + "::-webkit-scrollbar-button{display:none !important;}"
             + "input,textarea,select{background-color:" + field
             + " !important;text-shadow:none !important;}"
             + "button{text-shadow:none !important;}"
             + "img,picture,video,canvas,svg,iframe,embed,object{text-shadow:none !important;}"
             + "::placeholder{color:" + sub + " !important;}"
             + ":root{color-scheme:" + (dark ? "dark" : "light") + " !important;}"
             + "[data-beryl-ng-b]::before{background-image:none !important;}"
             + "[data-beryl-ng-a]::after{background-image:none !important;}"
        return { css: css,
                 pal: { text: cssRgb(textC), link: cssRgb(linkC), sub: cssRgb(subC),
                        card: cssRgba(cardC, 0.85),
                        shadow: dark ? "0 8px 24px rgba(0,0,0,0.45)"
                                     : "0 8px 24px rgba(0,0,0,0.20)" } }
    }
    function transparentScript() {
        // adoptedStyleSheets, not a <style> tag — strict-CSP sites block
        // inline styles; the dataset marker is what beryl/tests can probe.
        // gradients are background-IMAGES, so the color rules miss them
        // (google's white "show more" fade) — strip pure-gradient backgrounds
        // (url() sprites/heroes survive), pseudo-elements via marker attrs,
        // and keep watching: those fades are inserted dynamically, late
        // stylesheets/theme flips activate new ones, and CSS-in-JS mutates
        // nothing observable — hence the extra load-time re-sweeps.
        // Attribute churn re-strips only the TARGET element (a full subtree
        // sweep per class flip melted busy SPAs — and our own inline-style
        // writes would re-trigger it). Injected at BOTH DocumentCreation and
        // DocumentReady (creation can lose the registration race on a fresh
        // renderer; ready is the reliable one) — the window guard keeps the
        // second run a no-op.
        var t = transparentTheme()
        return `
(function () {
    if (window.__berylTransparent) return;
    window.__berylTransparent = true;
    var css = ${JSON.stringify(t.css)};
    window.__berylPal = ${JSON.stringify(t.pal)};
    window.__berylCss = css;
    window.__berylSheets = [];        // every adopted sheet — retheme hits all
    window.__berylRoots = [document]; // every themed tree — resweep hits all
    try {
        var s = new CSSStyleSheet();
        s.replaceSync(css);
        document.adoptedStyleSheets = document.adoptedStyleSheets.concat(s);
        window.__berylSheet = s;
        window.__berylSheets.push(s);
    } catch (e) {
        var t = document.createElement("style");
        t.id = "__beryl_style";
        t.textContent = css;
        (document.head || document.documentElement).appendChild(t);
    }
    function gradOnly(bi) {
        return bi && bi.indexOf("gradient(") >= 0 && bi.indexOf("url(") < 0;
    }
    var OBS = { childList: true, subtree: true, attributes: true,
                attributeFilter: ["class", "style", "open",
                                  "data-theme", "data-color-mode", "data-bs-theme"] };
    var observer = null;   // one observer watches the main doc, reached-into
                           // frames, and shadow roots alike
    function adoptInto(target, realmWin) {
        // constructable sheets are realm-bound: adopting a sheet built in
        // another document's realm throws — build it over there
        try {
            var sh = new realmWin.CSSStyleSheet();
            sh.replaceSync(window.__berylCss);
            target.adoptedStyleSheets = target.adoptedStyleSheets.concat(sh);
            window.__berylSheets.push(sh);
            return true;
        } catch (e) { return false; }
    }
    function themeFrame(fr) {
        // chromium never injects user scripts into about:blank/srcdoc frames
        // (azure's portal builds whole blades that way — they sat bone-white
        // in the frost) — theme any same-origin document from the parent;
        // cross-origin frames run their own copy of this script instead
        var doc;
        try { doc = fr.contentDocument; } catch (e) { return; }
        if (!doc || !doc.documentElement
                || doc.documentElement.dataset.berylTransparent) return;
        doc.documentElement.dataset.berylTransparent = "1";
        // real-url same-origin frames also get their own injected copy —
        // no-op it, this document is parent-managed now
        try { if (fr.contentWindow) fr.contentWindow.__berylTransparent = true; }
        catch (e) {}
        if (!adoptInto(doc, doc.defaultView)) {
            var st = doc.createElement("style");
            st.textContent = window.__berylCss;
            (doc.head || doc.documentElement).appendChild(st);
        }
        window.__berylRoots.push(doc);
        if (observer) observer.observe(doc.documentElement, OBS);
        queue(sweeps, doc.documentElement);
    }
    function hookFrame(fr) {
        themeFrame(fr);
        if (!fr.__berylHook) {
            fr.__berylHook = 1;   // the element survives navigations; its doc doesn't
            fr.addEventListener("load", function () { themeFrame(fr); });
        }
    }
    function adoptShadow(sr) {
        // document sheets don't cascade into shadow trees — every open root
        // (fluent/lit web components) needs its own adoption and observation
        if (sr.__beryl) return;
        sr.__beryl = 1;
        adoptInto(sr, window);
        window.__berylRoots.push(sr);
        if (observer) observer.observe(sr, OBS);
        queue(sweeps, sr);
    }
    var ROLES = /^(dialog|alertdialog|menu|listbox|tooltip)$/;
    function surface(el, cs, win) {
        // floating UI: popups, menus, dropdowns, tooltips. Out of flow and
        // self-declared (role / dialog / popover), or out of flow with an
        // elevated z-index (portal'd popups from popper/fluent/friends).
        var out = cs.position === "fixed" || cs.position === "absolute";
        var tagged = ROLES.test((el.getAttribute && el.getAttribute("role")) || "")
                  || (el.matches && el.matches("dialog,[popover]"));
        if (!(tagged ? out : (out && (parseInt(cs.zIndex, 10) || 0) >= 100)))
            return null;
        if (cs.pointerEvents === "none" || cs.visibility === "hidden")
            return null;               // positioning wrappers, hidden shells
        var r = el.getBoundingClientRect();
        if (r.width < 40 || r.height < 16)
            return null;               // badges, beaks, decor
        if (r.width >= win.innerWidth * 0.95 && r.height >= win.innerHeight * 0.95)
            return null;               // full-viewport wrapper/backdrop
        if (r.height > win.innerHeight * 1.2)
            return null;               // virtualized scroller body, not a popup
        return r;
    }
    function strip(el) {
        // styles resolve in the element's OWN realm — el may live in a
        // same-origin child frame themed from out here
        var win = (el.ownerDocument && el.ownerDocument.defaultView) || window;
        var cs = win.getComputedStyle(el);
        var pal = window.__berylPal || {};
        // floating surfaces sit on TOP of other page content — transparent,
        // they're unreadable (outlook's editor card over the compose text).
        // They get a frost card INSTEAD of a strip: card + shadow inline
        // (inline !important outranks the sheet), gated on a dataset marker
        // (not in the observer's attributeFilter) so re-strips can't loop,
        // holding the painted value so a theme switch repaints it.
        var surf = pal.card ? surface(el, cs, win) : null;
        if (surf) {
            if (el.dataset.berylCard !== pal.card) {
                el.dataset.berylCard = pal.card;
                el.style.setProperty("background-color", pal.card, "important");
                el.style.setProperty("box-shadow", pal.shadow, "important");
                // real frost — blur what's underneath. Never on full-width
                // bars: a backdrop-filter makes the element the containing
                // block for fixed descendants, re-anchoring nested dropdowns
                if (surf.width < win.innerWidth * 0.9)
                    el.style.setProperty("backdrop-filter", "blur(16px)", "important");
            }
        } else if (el.dataset.berylCard) {
            // stopped being a surface (class flip): undo the card and fall
            // through — a survivor background still gets neutralised below
            delete el.dataset.berylCard;
            el.style.removeProperty("background-color");
            el.style.removeProperty("box-shadow");
            el.style.removeProperty("backdrop-filter");
        }
        // a background-color that survived the sheet's "*{...!important}" —
        // the site pinned it with its OWN !important on a higher-specificity
        // selector (a class beats the universal), so the frost can't show
        // through (e.g. ai.azure.com's white hero arc, #f5f5f5). An inline
        // !important outranks any author rule, so neutralise it directly.
        // The transparent-check skips the elements the sheet already won (the
        // overwhelming majority) — only genuine survivors get an inline write,
        // and it's idempotent (a re-strip sees transparent and stops), so the
        // style-attr MutationObserver can't loop on it.
        // form fields are the ONE thing the sheet intentionally keeps a
        // (capped-alpha) background on, so they read as fields — never strip
        // those, or search bars melt into the frost again
        var bc = cs.backgroundColor;
        if (!surf && bc && bc !== "rgba(0, 0, 0, 0)" && bc !== "transparent"
                && !/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)
                && el.style.getPropertyValue("background-color") !== "transparent")
            el.style.setProperty("background-color", "transparent", "important");
        // same story for text COLOR: a class-selector !important beats the
        // sheet's element selectors, leaving text in the site's palette —
        // unreadable on frost (github's Link--muted file list). Anything not
        // wearing our palette gets repainted inline; links to the accent.
        // Idempotent: the repaint makes the computed color match pal, so the
        // attribute observer's re-strip is a no-op. Alpha-0 colors are left
        // alone — sites hide text that way on purpose.
        var col = cs.color;
        if (pal.text && col && !/,\\s*0\\)$/.test(col)
                && col !== pal.text && col !== pal.link && col !== pal.sub) {
            var want = (el.closest && el.closest("a")) ? pal.link : pal.text;
            el.style.setProperty("color", want, "important");
        }
        if (gradOnly(cs.backgroundImage))
            el.style.setProperty("background-image", "none", "important");
        // full-viewport BACKDROP images (url too, not just gradients): a
        // decorative image covering the whole viewport washes the page out and
        // buries the repainted text (microsoft's login uses a fixed 100%x100%
        // petals backdrop). Strip it so the frost shows through — same result
        // as zen. Small/banner images (heroes, logos, thumbnails) never match
        // the size gate, so real content survives. getBoundingClientRect only
        // runs for the rare element that actually has a url() background.
        if (cs.backgroundImage.indexOf("url(") >= 0) {
            var r = el.getBoundingClientRect();
            if (r.width >= win.innerWidth * 0.9 && r.height >= win.innerHeight * 0.85)
                el.style.setProperty("background-image", "none", "important");
        }
        if (gradOnly(win.getComputedStyle(el, "::before").backgroundImage))
            el.setAttribute("data-beryl-ng-b", "");
        if (gradOnly(win.getComputedStyle(el, "::after").backgroundImage))
            el.setAttribute("data-beryl-ng-a", "");
        // trees the sheet can't reach get themed as they're discovered
        if (el.tagName === "IFRAME" || el.tagName === "FRAME")
            hookFrame(el);
        if (el.shadowRoot)
            adoptShadow(el.shadowRoot);
    }
    function sweep(root) {
        if (root.nodeType === 1) {
            if (!root.isConnected) return;
            strip(root);
        }
        var els = root.querySelectorAll ? root.querySelectorAll("*") : [];
        for (var i = 0; i < els.length; i++) strip(els[i]);
    }
    var sweeps = new Set(), strips = new Set(), scheduled = false;
    function flush() {
        // swap the queues out BEFORE walking them: a strip can discover work
        // (a shell opening, a shadow root, a frame) and queue a sweep for it,
        // and clearing afterwards would drop exactly those late additions on
        // the floor — the modal that opens by a class flip never gets carded.
        scheduled = false;
        var sw = sweeps, st = strips;
        sweeps = new Set();
        strips = new Set();
        sw.forEach(sweep);
        st.forEach(function (el) { if (el.isConnected) strip(el); });
    }
    function queue(set, n) {
        set.add(n);
        if (!scheduled) { scheduled = true; setTimeout(flush, 120); }
    }
    function init() {
        // observer first: the initial sweep already discovers frames and
        // shadow roots, and they attach themselves to it
        observer = new MutationObserver(function (muts) {
            for (var i = 0; i < muts.length; i++) {
                var m = muts[i];
                if (m.type === "attributes") { queue(strips, m.target); continue; }
                for (var j = 0; j < m.addedNodes.length; j++) {
                    var n = m.addedNodes[j];
                    if (n.nodeType !== 1) continue;
                    queue(sweeps, n);
                    if (n.tagName === "LINK" || n.tagName === "STYLE")
                        n.addEventListener("load",
                            function () { queue(sweeps, document); }, { once: true });
                }
            }
        });
        observer.observe(document.documentElement, OBS);
        sweep(document);
        // late stylesheets finish after DOMContentLoaded — sweep again once
        // everything has painted
        window.addEventListener("load",
            function () { queue(sweeps, document); }, { once: true });
        // theme switches need a full re-pass over EVERY themed tree: inline
        // colors written for the OLD palette must be repainted. Trees whose
        // frame navigated away or whose host left the DOM are dropped.
        window.__berylResweep = function () {
            window.__berylRoots = window.__berylRoots.filter(function (r) {
                return r.nodeType === 9 ? r.defaultView
                                        : r.host && r.host.isConnected;
            });
            window.__berylRoots.forEach(function (r) { queue(sweeps, r); });
        };
        document.documentElement.dataset.berylTransparent = "1";
    }
    if (document.documentElement)
        init();
    else
        document.addEventListener("DOMContentLoaded", init);
})();`
    }
    // theme switches / page-color changes rewrite the injected sheets in
    // place on live pages (the vault calls this on every view) — no reload
    // needed. The palette + resweep keep the inline survivor repaints
    // current too. Known gap: runJavaScript only reaches the MAIN frame, so
    // cross-origin iframes (which run their own script copy) keep the old
    // palette until they next navigate.
    function applyTransparentTheme() {
        if (!Config.transparent_pages)
            return
        var t = transparentTheme()
        var css = JSON.stringify(t.css)
        runJavaScript("window.__berylPal=" + JSON.stringify(t.pal) + ";"
                      + "window.__berylCss=" + css + ";"
                      + "if(window.__berylSheets){window.__berylSheets.forEach("
                      + "function(s){try{s.replaceSync(" + css + ")}catch(e){}});}"
                      + "else if(window.__berylSheet){window.__berylSheet.replaceSync(" + css + ");}"
                      + "var t=document.getElementById('__beryl_style');"
                      + "if(t)t.textContent=" + css + ";"
                      + "if(window.__berylResweep)window.__berylResweep();")
    }

    userScripts.collection: {
        var scripts = [
            {
                name: "qwebchannel",
                sourceUrl: Qt.resolvedUrl("../js/qwebchannel.js"),
                injectionPoint: WebEngineScript.DocumentCreation,
                worldId: WebEngineScript.MainWorld
            },
            {
                name: "editable",
                sourceUrl: Qt.resolvedUrl("../js/editable.js"),
                injectionPoint: WebEngineScript.DocumentReady,
                worldId: WebEngineScript.MainWorld
            },
            {
                name: "hints",
                sourceUrl: Qt.resolvedUrl("../js/hints.js"),
                injectionPoint: WebEngineScript.DocumentReady,
                worldId: WebEngineScript.ApplicationWorld
            }
        ]
        // password autofill/capture: main world (needs the webchannel and the
        // fills must read as real input to the page); only when enabled
        if (Config.passwords) {
            scripts.push({
                name: "creds",
                sourceUrl: Qt.resolvedUrl("../js/creds.js"),
                injectionPoint: WebEngineScript.DocumentReady,
                worldId: WebEngineScript.MainWorld
            })
        }
        // injected twice: DocumentCreation kills the unthemed first paint on
        // every navigation after the first (creation-time scripts can lose the
        // registration race on a fresh renderer), DocumentReady is the one
        // that's guaranteed to run — the script's window guard dedupes.
        // runs in subframes too — embedded iframes otherwise keep their own
        // opaque backgrounds and punch white holes in the frost.
        if (Config.transparent_pages) {
            var src = transparentScript()
            scripts.push({
                name: "transparent-early",
                sourceCode: src,
                injectionPoint: WebEngineScript.DocumentCreation,
                worldId: WebEngineScript.MainWorld,
                runsOnSubFrames: true
            })
            scripts.push({
                name: "transparent",
                sourceCode: src,
                injectionPoint: WebEngineScript.DocumentReady,
                worldId: WebEngineScript.MainWorld,
                runsOnSubFrames: true
            })
        }
        return scripts
    }

    // ---- state → model / history ---------------------------------------------
    onUrlChanged: Tabs.viewState(tabUid, "url", url.toString())
    onTitleChanged: {
        Tabs.viewState(tabUid, "title", title)
        History.retitle(url.toString(), title)
    }
    onIconChanged: Tabs.viewState(tabUid, "icon", icon.toString())
    onLoadProgressChanged: Tabs.viewState(tabUid, "progress", loadProgress)
    onLoadingChanged: function (loadingInfo) {
        Tabs.viewState(tabUid, "loading", loading)
        if (loadingInfo.status === WebEngineLoadingInfo.LoadSucceededStatus)
            History.record(loadingInfo.url.toString(), view.title)
    }

    onFindTextFinished: function (result) {
        if (view.shown)
            api.findResult(result.numberOfMatches, result.activeMatch)
    }

    // M1 placeholder: target=_blank and window.open land in a fresh tab.
    // (M3 switches to request.openIn so POST/background hints survive.)
    onNewWindowRequested: function (request) {
        Tabs.newTab(request.requestedUrl.toString(), false)
    }

    onFullScreenRequested: function (request) {
        if (!view.shown) {
            request.reject()
            return
        }
        request.accept()
        Window.window.visibility = request.toggleOn ? Window.FullScreen
                                                    : Window.Windowed
    }

    onPermissionRequested: function (permission) {
        if (view.shown)
            Window.window.askPermission(permission)
        else
            permission.deny()   // background tabs don't get to nag
    }
}
