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
    function openUrl(u) {
        var v = currentView()
        if (v) v.url = u
    }

    property string msg: ""
    property bool msgError: false
    function toast(t, err) { msg = t; msgError = err === true; msgTimer.restart() }
    Timer { id: msgTimer; interval: 2600; onTriggered: win.msg = "" }

    // page fullscreen (avd, video): chrome melts away, page gets every pixel
    readonly property bool fs: visibility === Window.FullScreen

    function askPermission(permission) { permPrompt.ask(permission) }

    // ---- frosted glass ---------------------------------------------------------
    Rectangle {
        visible: !win.fs
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.bg
        border.color: Theme.border
        border.width: 1
    }

    TabStrip {
        id: tabstrip
        visible: !win.fs
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: Theme.pad }
        height: 28
    }

    PermissionPrompt {
        id: permPrompt
        anchors { top: tabstrip.bottom; left: parent.left; right: parent.right }
        anchors.topMargin: 2
        anchors.leftMargin: Theme.pad
        anchors.rightMargin: Theme.pad
        z: 5
    }

    // ---- pages -------------------------------------------------------------------
    // One live WebEngineView per tab behind a Loader; hidden tabs don't render,
    // dead (lazy-restored) tabs don't even exist yet. The page stays rectangular
    // inside the rounded frame on purpose — corner-masking it would force a
    // full-page FBO every frame.
    Item {
        id: viewport
        anchors {
            top: win.fs ? parent.top : tabstrip.bottom
            topMargin: win.fs ? 0 : 6
            left: parent.left; leftMargin: win.fs ? 0 : Theme.pad
            right: parent.right; rightMargin: win.fs ? 0 : Theme.pad
            bottom: win.fs ? parent.bottom : footer.top
            bottomMargin: win.fs ? 0 : 6
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
        visible: !win.fs
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

    Loader {
        id: help
        anchors.fill: parent
        active: false
        z: 10
        sourceComponent: CheatSheet {}
    }

    Loader {
        id: bookmarksList
        anchors.fill: parent
        active: false
        z: 11
        sourceComponent: BookmarksList {
            onOpenHere: function (url) { win.openUrl(url) }
            onOpenTab: function (url) { Tabs.newTab(url, false) }
        }
        onLoaded: item.start()
    }
    // overlays are mode-driven: they vanish the moment we leave their mode
    Connections {
        target: Vim
        function onModeChanged() {
            if (Vim.mode !== "bookmarks" && bookmarksList.active)
                bookmarksList.active = false
            if (Vim.mode !== "help" && help.active)
                help.active = false
        }
    }

    // ---- python → view dispatch -----------------------------------------------
    Connections {
        target: api

        function onJsRequested(script, world, rid) {
            var v = win.currentView()
            if (!v) {
                if (rid > 0) api.jsDone(rid, null)
                return
            }
            if (rid > 0)
                v.runJavaScript(script, world, function (res) { api.jsDone(rid, res) })
            else
                v.runJavaScript(script, world)
        }
        function onZoomRequested(step) {
            var v = win.currentView()
            if (!v) return
            v.zoomFactor = step === 0 ? 1.0
                : Math.max(0.3, Math.min(4.0, v.zoomFactor + step))
        }
        function onHelpRequested() { help.active = true }
        function onBookmarksRequested() { bookmarksList.active = true }
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
        function onFindCount(c) { footer.findCount = c }
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
