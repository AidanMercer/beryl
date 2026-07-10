import QtQuick

// Thin bar under the tab strip: "host wants clipboard  [y] allow  [n] deny".
// Answered with y/n/Esc from normal mode (the KeyController forwards them
// while the bar is up) or by clicking. Grants persist via the profile
// (StoreOnDisk); some permission types re-ask each session by design.
Rectangle {
    id: root
    property var queue: []
    readonly property var cur: queue.length > 0 ? queue[0] : null

    visible: cur !== null
    onVisibleChanged: Vim.setPromptActive(visible)

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

    Connections {
        target: Vim
        function onPromptAnswer(k) { root.answer(k === "y") }
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
