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
    function transparentCss() {
        function rgba(c, a) {
            var k = Qt.color(c)
            return "rgba(" + Math.round(k.r * 255) + "," + Math.round(k.g * 255) + ","
                 + Math.round(k.b * 255) + "," + (a !== undefined ? a : k.a).toFixed(2) + ")"
        }
        // page_colors: auto rides the rice theme; dark/light pin the palette
        // (links keep the theme accent either way — it's tuned for the frost)
        var mode = Config.page_colors || "auto"
        var dark = mode === "auto" ? Qt.color(Theme.bg).hslLightness < 0.5
                                   : mode === "dark"
        var auto = mode === "auto"
        var text = auto ? rgba(Theme.text, 1)
                        : (dark ? "rgba(236,239,244,1.00)" : "rgba(26,27,34,1.00)")
        var sub = auto ? rgba(Theme.subtext, 1)
                       : (dark ? "rgba(178,184,200,1.00)" : "rgba(92,94,110,1.00)")
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
        var shadow = dark ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.65)"
        return "html,body{background:transparent !important;}"
             + "*{background-color:transparent !important;"
             + "color:" + text + " !important;"
             + "border-color:" + border + " !important;"
             + "text-shadow:0 1px 3px " + shadow + " !important;"
             + "box-shadow:none !important;}"   // shadows draw ghost boxes on frost
             + "a,a *{color:" + rgba(Theme.accent, 1) + " !important;}"
             + "input,textarea,select{background-color:" + field
             + " !important;text-shadow:none !important;}"
             + "button{text-shadow:none !important;}"
             + "img,picture,video,canvas,svg,iframe,embed,object{text-shadow:none !important;}"
             + "::placeholder{color:" + sub + " !important;}"
             + ":root{color-scheme:" + (dark ? "dark" : "light") + " !important;}"
             + "[data-beryl-ng-b]::before{background-image:none !important;}"
             + "[data-beryl-ng-a]::after{background-image:none !important;}"
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
        return `
(function () {
    if (window.__berylTransparent) return;
    window.__berylTransparent = true;
    var css = ${JSON.stringify(transparentCss())};
    try {
        var s = new CSSStyleSheet();
        s.replaceSync(css);
        document.adoptedStyleSheets = document.adoptedStyleSheets.concat(s);
        window.__berylSheet = s;
    } catch (e) {
        var t = document.createElement("style");
        t.id = "__beryl_style";
        t.textContent = css;
        (document.head || document.documentElement).appendChild(t);
    }
    function gradOnly(bi) {
        return bi && bi.indexOf("gradient(") >= 0 && bi.indexOf("url(") < 0;
    }
    function strip(el) {
        var cs = getComputedStyle(el);
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
        if (bc && bc !== "rgba(0, 0, 0, 0)" && bc !== "transparent"
                && !/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)
                && el.style.getPropertyValue("background-color") !== "transparent")
            el.style.setProperty("background-color", "transparent", "important");
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
            if (r.width >= innerWidth * 0.9 && r.height >= innerHeight * 0.85)
                el.style.setProperty("background-image", "none", "important");
        }
        if (gradOnly(getComputedStyle(el, "::before").backgroundImage))
            el.setAttribute("data-beryl-ng-b", "");
        if (gradOnly(getComputedStyle(el, "::after").backgroundImage))
            el.setAttribute("data-beryl-ng-a", "");
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
        scheduled = false;
        sweeps.forEach(sweep);
        strips.forEach(function (el) { if (el.isConnected) strip(el); });
        sweeps.clear();
        strips.clear();
    }
    function queue(set, n) {
        set.add(n);
        if (!scheduled) { scheduled = true; setTimeout(flush, 120); }
    }
    function init() {
        sweep(document);
        new MutationObserver(function (muts) {
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
        }).observe(document.documentElement, {
            childList: true, subtree: true, attributes: true,
            attributeFilter: ["class", "style",
                              "data-theme", "data-color-mode", "data-bs-theme"]
        });
        // late stylesheets finish after DOMContentLoaded — sweep again once
        // everything has painted
        window.addEventListener("load",
            function () { queue(sweeps, document); }, { once: true });
        document.documentElement.dataset.berylTransparent = "1";
    }
    if (document.documentElement)
        init();
    else
        document.addEventListener("DOMContentLoaded", init);
})();`
    }
    // theme switches / page-color changes rewrite the injected sheet in place
    // on live pages (the vault calls this on every view) — no reload needed
    function applyTransparentTheme() {
        if (!Config.transparent_pages)
            return
        var css = JSON.stringify(transparentCss())
        runJavaScript("if(window.__berylSheet){window.__berylSheet.replaceSync(" + css + ");}"
                      + "else{var t=document.getElementById('__beryl_style');"
                      + "if(t)t.textContent=" + css + ";}")
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
