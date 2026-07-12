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
                sourceUrl: Qt.resolvedUrl("../js/transparent.js"),
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
