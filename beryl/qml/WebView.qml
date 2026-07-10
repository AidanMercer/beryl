import QtQuick
import QtWebChannel
import QtWebEngine

// One live page. All per-view signal wiring lives here; state flows into the
// TabModel via viewState() so the strip and statusbar stay model-driven.
WebEngineView {
    id: view
    required property int tabUid
    property string initialUrl: ""

    profile: WebProfile
    backgroundColor: Theme.viewBg              // kills the white flash

    settings.focusOnNavigationEnabled: false   // pages don't get to grab the keyboard
    settings.dnsPrefetchEnabled: false         // no speculative traffic
    settings.hyperlinkAuditingEnabled: false   // no a[ping] beacons
    settings.webRTCPublicInterfacesOnly: true  // no local-IP leak

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
            if (view.visible)              // background tabs don't get a vote
                Vim.pageEditable(on === true)
        }
    }
    userScripts.collection: [
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
        }
    ]

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
        if (view.visible)
            api.findResult(result.numberOfMatches, result.activeMatch)
    }

    // M1 placeholder: target=_blank and window.open land in a fresh tab.
    // (M3 switches to request.openIn so POST/background hints survive.)
    onNewWindowRequested: function (request) {
        Tabs.newTab(request.requestedUrl.toString(), false)
    }
}
