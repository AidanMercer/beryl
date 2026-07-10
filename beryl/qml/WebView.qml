import QtQuick
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

    Component.onCompleted: {
        if (initialUrl !== "")
            url = initialUrl
    }

    onUrlChanged: Tabs.viewState(tabUid, "url", url.toString())
    onTitleChanged: Tabs.viewState(tabUid, "title", title)
    onIconChanged: Tabs.viewState(tabUid, "icon", icon.toString())
    onLoadingChanged: Tabs.viewState(tabUid, "loading", loading)
    onLoadProgressChanged: Tabs.viewState(tabUid, "progress", loadProgress)

    // M1 placeholder: target=_blank and window.open land in a fresh tab.
    // (M3 switches to request.openIn so POST/background hints survive.)
    onNewWindowRequested: function (request) {
        Tabs.newTab(request.requestedUrl.toString(), false)
    }
}
