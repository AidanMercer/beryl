import QtQuick
import QtWebEngine

// Minimal scene for `beryl --import-zen`: a single WebEngineView on the real
// profile so the cookie store actually connects (setCookie is a no-op until a
// view spins up the network context). Python injects once onLoad fires.
Window {
    id: win
    width: 400
    height: 200
    visible: true
    title: "beryl — importing…"
    color: "#11121a"

    Text {
        anchors.centerIn: parent
        text: "importing from zen…"
        color: "#c8ccd8"
        font.pixelSize: 16
    }

    WebEngineView {
        id: view
        visible: false
        width: 1; height: 1
        profile: WebProfile
        url: "about:blank"
        onLoadingChanged: function (info) {
            if (info.status === WebEngineLoadingInfo.LoadSucceededStatus)
                importer.injectCookies()
        }
    }
}
