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

    // per-window identity from the window manager (initial property): which
    // tab of the shared pool this window is showing
    property QtObject winctl
    readonly property int shownUid: winctl ? winctl.uid : -1

    title: (winctl && winctl.title !== ""
            ? winctl.title.substring(0, 200) + " — " : "") + "beryl"

    // the manager tracks focus (commands/urls target the focused window) and
    // closes (a WM-close tears the window down like ZZ would)
    onActiveChanged: if (active && winctl) winctl.notifyActive()
    onClosing: if (winctl) winctl.notifyClosing()

    function currentView() {
        var ld = Views.get(win.shownUid)
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
        shownUid: win.shownUid
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

    // ---- page --------------------------------------------------------------------
    // The views live in the ViewHost vault; this window borrows the loader of
    // the tab it's showing by reparenting it here. The loader keeps its own
    // anchors.fill binding, so a reparent is all it takes. Never stash a view
    // another window has already claimed from us mid-steal.
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

        property Item held: null
        function refit() {
            var ld = Views.get(win.shownUid)
            var v = (ld && ld.item) ? ld.item : null
            if (held && held !== v && held.parent === viewport)
                Views.stash(held)
            held = v
            if (v) {
                if (v.parent !== viewport) {
                    v.parent = viewport
                    // a reparented view keeps its last Chromium frame (stale
                    // size — static pages never repaint on their own); blink
                    // visibility to force a fresh composite in this window
                    v.visible = false
                    v.visible = true
                }
                if (win.active)
                    v.forceActiveFocus()
            }
        }
        Connections {
            target: win.winctl
            function onUidChanged() { viewport.refit() }
        }
        Component.onCompleted: refit()
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

    Loader {
        id: downloadsList
        anchors.fill: parent
        active: false
        z: 11
        sourceComponent: DownloadsList {}
        onLoaded: item.start()
    }

    Loader {
        id: settingsList
        anchors.fill: parent
        active: false
        z: 11
        sourceComponent: SettingsList {}
        onLoaded: item.start()
    }
    // overlays are mode-driven: they vanish the moment we leave their mode
    Connections {
        target: Vim
        function onModeChanged() {
            if (Vim.mode !== "bookmarks" && bookmarksList.active)
                bookmarksList.active = false
            if (Vim.mode !== "downloads" && downloadsList.active)
                downloadsList.active = false
            if (Vim.mode !== "settings" && settingsList.active)
                settingsList.active = false
            if (Vim.mode !== "help" && help.active)
                help.active = false
        }
    }

    // ---- python → view dispatch -----------------------------------------------
    // api is app-global and every window hears it; only the focused window
    // acts, so commands always mean the tab you're looking at.
    Connections {
        target: api

        function onJsRequested(script, world, rid) {
            if (!win.active)
                return
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
            if (!win.active) return
            var v = win.currentView()
            if (!v) return
            v.zoomFactor = step === 0 ? 1.0
                : Math.max(0.3, Math.min(4.0, v.zoomFactor + step))
        }
        function onHelpRequested() { if (win.active) help.active = true }
        function onBookmarksRequested() { if (win.active) bookmarksList.active = true }
        function onDownloadsRequested() { if (win.active) downloadsList.active = true }
        function onSettingsRequested() { if (win.active) settingsList.active = true }
        function onNavRequested(url) {
            if (!win.active) return
            var v = win.currentView()
            if (v) v.url = url
        }
        function onHistRequested(d) {
            if (!win.active) return
            var v = win.currentView()
            if (!v) return
            for (var i = 0; i < Math.abs(d); i++)
                d < 0 ? v.goBack() : v.goForward()
        }
        function onReloadRequested(bypass) {
            if (!win.active) return
            var v = win.currentView()
            if (!v) return
            bypass ? v.reloadAndBypassCache() : v.reload()
        }
        function onFindRequested(term, backwards) {
            if (!win.active) return
            var v = win.currentView()
            if (!v) return
            if (backwards)
                v.findText(term, WebEngineView.FindBackward)
            else
                v.findText(term)
        }
        function onCmdlineOpenRequested(prefix, prefill) {
            if (win.active)
                cmdline.open(prefix, prefill)
        }
        function onToast(t, e) { if (win.active) win.toast(t, e) }
        function onFindCount(c) { if (win.active) footer.findCount = c }
    }

    Connections {
        target: Dl
        function onToast(t, e) { win.toast(t, e) }
    }

    Connections {
        target: Tabs
        function onCurrentIndexChanged() { if (win.active) win.refocusView() }
    }

    // after exposure, so this wins over Qt's initial-focus assignment
    Component.onCompleted: Qt.callLater(win.refocusView)
}
