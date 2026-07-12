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
        var card = auto ? rgba(Theme.card)
                        : (dark ? "rgba(18,20,28,0.55)" : "rgba(255,255,255,0.60)")
        var shadow = dark ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.65)"
        return "html,body{background:transparent !important;}"
             + "*{background-color:transparent !important;"
             + "color:" + text + " !important;"
             + "border-color:" + border + " !important;"
             + "text-shadow:0 1px 3px " + shadow + " !important;}"
             + "a,a *{color:" + rgba(Theme.accent, 1) + " !important;}"
             + "input,textarea,select,button{background-color:" + card
             + " !important;text-shadow:none !important;}"
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
        // and keep watching: those fades are inserted dynamically.
        return `
(function () {
    var css = ${JSON.stringify(transparentCss())};
    try {
        var s = new CSSStyleSheet();
        s.replaceSync(css);
        document.adoptedStyleSheets = document.adoptedStyleSheets.concat(s);
    } catch (e) {
        var t = document.createElement("style");
        t.textContent = css;
        (document.head || document.documentElement).appendChild(t);
    }
    function gradOnly(bi) {
        return bi && bi.indexOf("gradient(") >= 0 && bi.indexOf("url(") < 0;
    }
    function strip(el) {
        if (gradOnly(getComputedStyle(el).backgroundImage))
            el.style.setProperty("background-image", "none", "important");
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
    var pending = new Set(), scheduled = false;
    function flush() {
        scheduled = false;
        pending.forEach(sweep);
        pending.clear();
    }
    function queue(n) {
        pending.add(n);
        if (!scheduled) { scheduled = true; setTimeout(flush, 120); }
    }
    sweep(document);
    new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
            var m = muts[i];
            if (m.type === "attributes") { queue(m.target); continue; }
            for (var j = 0; j < m.addedNodes.length; j++)
                if (m.addedNodes[j].nodeType === 1) queue(m.addedNodes[j]);
        }
    }).observe(document.documentElement, {
        childList: true, subtree: true,
        attributes: true, attributeFilter: ["class", "style"]
    });
    document.documentElement.dataset.berylTransparent = "1";
})();`
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
        // DocumentReady, not DocumentCreation: creation-time scripts can lose
        // the registration race against a fresh renderer's first navigation
        if (Config.transparent_pages)
            scripts.push({
                name: "transparent",
                sourceCode: transparentScript(),
                injectionPoint: WebEngineScript.DocumentReady,
                worldId: WebEngineScript.MainWorld
            })
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
