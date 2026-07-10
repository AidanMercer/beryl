import QtQuick
import QtQuick.Controls.Basic
import QtWebEngine

ApplicationWindow {
    id: win
    visible: true
    width: 1380
    height: 860
    minimumWidth: 640
    minimumHeight: 400
    color: "transparent"
    title: (Tabs.currentTitle !== "" ? Tabs.currentTitle + " — " : "") + "beryl"

    function currentView() {
        var ld = viewRepeater.itemAt(Tabs.currentIndex)
        return (ld && ld.item) ? ld.item : null
    }
    function refocusView() {
        if (cmdline.active)
            return
        var v = currentView()
        if (v)
            v.forceActiveFocus()
    }

    property string msg: ""
    property bool msgError: false
    function toast(t, err) { msg = t; msgError = err === true; msgTimer.restart() }
    Timer { id: msgTimer; interval: 2600; onTriggered: win.msg = "" }

    // ---- frosted glass ---------------------------------------------------------
    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.bg
        border.color: Theme.border
        border.width: 1
    }

    TabStrip {
        id: tabstrip
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.pad }
        height: 28
    }

    // ---- pages -------------------------------------------------------------------
    // One live WebEngineView per tab behind a Loader; hidden tabs don't render,
    // dead (lazy-restored) tabs don't even exist yet. The page stays rectangular
    // inside the rounded frame on purpose — corner-masking it would force a
    // full-page FBO every frame.
    Item {
        id: viewport
        anchors {
            top: tabstrip.bottom; topMargin: 6
            left: parent.left; leftMargin: Theme.pad
            right: parent.right; rightMargin: Theme.pad
            bottom: footer.top; bottomMargin: 6
        }

        Repeater {
            id: viewRepeater
            model: Tabs

            Loader {
                id: ld
                required property int index
                required property int uid
                required property string url
                required property bool live

                anchors.fill: parent
                active: live
                visible: index === Tabs.currentIndex

                sourceComponent: WebView {
                    tabUid: ld.uid
                    initialUrl: ld.url
                }
                onLoaded: {
                    if (index === Tabs.currentIndex)
                        item.forceActiveFocus()
                }
            }
        }
    }

    StatusBar {
        id: footer
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right; margins: Theme.pad }
        height: 24
        message: win.msg
        messageError: win.msgError
    }

    CmdLine {
        id: cmdline
        anchors.fill: footer
        onClosed: win.refocusView()
    }

    // ---- python → view dispatch -----------------------------------------------
    Connections {
        target: api

        function onJsRequested(script, rid) {
            var v = win.currentView()
            if (!v) {
                if (rid > 0) api.jsDone(rid, null)
                return
            }
            if (rid > 0)
                v.runJavaScript(script, function (res) { api.jsDone(rid, res) })
            else
                v.runJavaScript(script)
        }
        function onNavRequested(url) {
            var v = win.currentView()
            if (v) v.url = url
        }
        function onHistRequested(d) {
            var v = win.currentView()
            if (!v) return
            for (var i = 0; i < Math.abs(d); i++)
                d < 0 ? v.goBack() : v.goForward()
        }
        function onReloadRequested(bypass) {
            var v = win.currentView()
            if (!v) return
            bypass ? v.reloadAndBypassCache() : v.reload()
        }
        function onFindRequested(term, backwards) {
            var v = win.currentView()
            if (!v) return
            if (backwards)
                v.findText(term, WebEngineView.FindBackward)
            else
                v.findText(term)
        }
        function onCmdlineOpenRequested(prefix, prefill) {
            cmdline.open(prefix, prefill)
        }
        function onToast(t, e) { win.toast(t, e) }
    }

    Connections {
        target: Dl
        function onToast(t, e) { win.toast(t, e) }
    }

    Connections {
        target: Tabs
        function onCurrentIndexChanged() { win.refocusView() }
    }

    // after exposure, so this wins over Qt's initial-focus assignment
    Component.onCompleted: Qt.callLater(win.refocusView)
}
