import QtQuick

// Thin bar under the tab strip: "save password for github.com?  [y] save
// [n] never  esc later". Fed by Vault.askSave (app-global — only the current
// window shows it); answered with y/n from normal mode via Vim.saveAnswer, or
// by clicking. Esc = not now (the site can re-offer); n = never for this
// origin (persists). Same window-local `hot` guard as PermissionPrompt so a
// keystroke can't answer a prompt sitting in another window.
Rectangle {
    id: root
    // set by Main from win.isCurrent — only the current (last-active) window
    // queues the global askSave, so exactly one bar shows across all windows
    property bool isCurrent: false
    property var queue: []          // [{pid, host, username, isUpdate}]
    readonly property var cur: queue.length > 0 ? queue[0] : null
    readonly property bool hot: cur !== null && Window.active

    visible: cur !== null
    onHotChanged: Vim.setSaveActive(hot)
    Component.onDestruction: if (hot) Vim.setSaveActive(false)

    radius: Theme.radiusSm
    color: Theme.card
    border.color: Theme.border
    border.width: 1
    height: 30

    Connections {
        target: Vault
        function onAskSave(pid, host, username, isUpdate) {
            // only the current window queues it — others ignore the global
            // signal, so exactly one bar shows
            if (root.isCurrent)
                root.queue = root.queue.concat([{
                    "pid": pid, "host": host,
                    "username": username, "isUpdate": isUpdate
                }])
        }
    }

    function answer(verdict) {
        if (cur === null)
            return
        Vault.answer(cur.pid, verdict)   // "save" / "never" / "later"
        queue = queue.slice(1)
    }

    Connections {
        target: Vim
        function onSaveAnswer(k) {
            if (!root.hot)
                return
            if (k === "y")
                root.answer("save")
            else if (k === "n")
                root.answer("never")
            else
                root.answer("later")
        }
    }

    Row {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: 10
        spacing: 14

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.cur !== null
                  ? (root.cur.isUpdate ? "update password for " : "save password for ")
                    + root.cur.host
                    + (root.cur.username !== "" ? "  (" + root.cur.username + ")" : "")
                  : ""
            color: Theme.text
            font.pixelSize: 12
            font.family: Theme.font
            elide: Text.ElideMiddle
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: saveLabel.implicitWidth + 14; height: 18; radius: 4
            color: Theme.accentSoft
            Text {
                id: saveLabel
                anchors.centerIn: parent
                text: root.cur !== null && root.cur.isUpdate ? "y update" : "y save"
                color: Theme.accent
                font.pixelSize: 11; font.bold: true; font.family: Theme.font
            }
            MouseArea { anchors.fill: parent; onClicked: root.answer("save") }
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: neverLabel.implicitWidth + 14; height: 18; radius: 4
            color: Theme.glassSoft
            Text {
                id: neverLabel
                anchors.centerIn: parent
                text: "n never"
                color: Theme.subtext
                font.pixelSize: 11; font.bold: true; font.family: Theme.font
            }
            MouseArea { anchors.fill: parent; onClicked: root.answer("never") }
        }
    }
}
