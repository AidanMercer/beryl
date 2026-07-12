import QtQuick

// Thin bar under the tab strip: "host wants clipboard  [y] allow  [n] deny".
// Answered with y/n from normal mode (the KeyController forwards them while
// the bar is up) or by clicking; Esc just dismisses — deny persists to disk
// (StoreOnDisk), so it must be a deliberate keypress, never a reflex Esc.
// The answer path is window-local: `hot` = visible AND in the active window,
// so a keystroke can never answer a prompt sitting in another window, and
// the global flag can't stick when a prompt-bearing window closes.
Rectangle {
    id: root
    property var queue: []
    readonly property var cur: queue.length > 0 ? queue[0] : null
    readonly property bool hot: cur !== null && Window.active

    visible: cur !== null
    onHotChanged: Vim.setPromptActive(hot)
    Component.onDestruction: if (hot) Vim.setPromptActive(false)

    radius: Theme.radiusSm
    color: Theme.card
    border.color: Theme.border
    border.width: 1
    height: 30

    function ask(permission) {
        queue = queue.concat([permission])
    }

    function answer(allow) {
        if (cur === null)
            return
        if (allow)
            cur.grant()
        else
            cur.deny()
        queue = queue.slice(1)
    }

    function dismiss() {
        // drop the request unanswered: the site can re-ask, nothing persists
        if (cur !== null)
            queue = queue.slice(1)
    }

    Connections {
        target: Vim
        function onPromptAnswer(k) {
            if (!root.hot)
                return
            if (k === "y")
                root.answer(true)
            else if (k === "n")
                root.answer(false)
            else
                root.dismiss()
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
                  ? root.cur.origin.toString().replace(/^https?:\/\//, "")
                    + " wants " + api.permName(root.cur.permissionType)
                  : ""
            color: Theme.text
            font.pixelSize: 12
            font.family: Theme.font
            elide: Text.ElideMiddle
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: allowLabel.implicitWidth + 14; height: 18; radius: 4
            color: Theme.accentSoft
            Text {
                id: allowLabel
                anchors.centerIn: parent
                text: "y allow"
                color: Theme.accent
                font.pixelSize: 11; font.bold: true; font.family: Theme.font
            }
            MouseArea { anchors.fill: parent; onClicked: root.answer(true) }
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: denyLabel.implicitWidth + 14; height: 18; radius: 4
            color: Theme.glassSoft
            Text {
                id: denyLabel
                anchors.centerIn: parent
                text: "n deny"
                color: Theme.subtext
                font.pixelSize: 11; font.bold: true; font.family: Theme.font
            }
            MouseArea { anchors.fill: parent; onClicked: root.answer(false) }
        }
    }
}
