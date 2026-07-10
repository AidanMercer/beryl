import QtQuick

// The status line: mode pill + pending keys + url (or a transient message) on
// the left; downloads glance · tab position · theme wordmark on the right.
Item {
    id: root
    property string message: ""
    property bool messageError: false
    property string findCount: ""

    readonly property color _modeColor: Vim.mode === "insert" ? Theme.accent2
        : Vim.mode === "command" ? Theme.accent2
        : Vim.mode === "passthrough" ? Theme.warn
        : Theme.accent

    Row {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: 6
        anchors.right: rightRow.left
        anchors.rightMargin: 12
        spacing: 10

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: modeLabel.implicitWidth + 16
            height: 18
            radius: 4
            color: root._modeColor
            Text {
                id: modeLabel
                anchors.centerIn: parent
                text: Vim.mode.toUpperCase()
                color: Theme.onAccent
                font.pixelSize: 11
                font.bold: true
                font.family: Theme.font
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: Vim.pending !== ""
            text: Vim.pending
            color: Theme.accent2
            font.pixelSize: 12
            font.family: Theme.font
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.message !== "" ? root.message : Tabs.currentUrl
            color: root.message !== "" ? (root.messageError ? Theme.warn : Theme.accent2)
                                       : Theme.subtext
            font.pixelSize: 12
            font.family: Theme.font
            elide: Text.ElideMiddle
            width: Math.min(implicitWidth, parent.width - 140)
        }
    }

    Row {
        id: rightRow
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: 6
        spacing: 12

        Text {
            visible: root.findCount !== ""
            text: root.findCount
            color: Theme.accent2
            font.pixelSize: 12
            font.family: Theme.font
        }
        Text {
            visible: Dl.activeCount > 0
            text: "↓" + Dl.activeCount + (Dl.percent >= 0 ? "  " + Dl.percent + "%" : "")
            color: Theme.accent2
            font.pixelSize: 12
            font.family: Theme.font
        }
        Text {
            text: (Tabs.currentIndex + 1) + "/" + Tabs.count
            color: Theme.subtext
            font.pixelSize: 12
            font.family: Theme.font
        }
        Text {
            text: Rice.name !== "" ? Rice.name : "—"
            color: Theme.accent
            font.pixelSize: 12
            font.family: Theme.font
        }
    }
}
