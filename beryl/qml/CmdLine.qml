import QtQuick
import QtQuick.Controls.Basic

// The ex/search line — sits exactly over the statusbar while open (vellum's
// footer pattern). ':' runs through the command registry, '/' drives findText.
Rectangle {
    id: root
    property string prefix: ""            // "" closed | ":" | "/"
    readonly property bool active: prefix !== ""
    signal closed()

    visible: active
    radius: Theme.radiusSm
    color: Theme.card
    border.color: Theme.border
    border.width: 1

    function open(p, prefill) {
        prefix = p
        field.text = prefill
        field.forceActiveFocus()
        field.cursorPosition = field.length
    }

    function close() {
        prefix = ""
        field.text = ""
        Vim.cmdlineClosed()
        root.closed()
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 6

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.prefix
            color: Theme.accent
            font.pixelSize: 13
            font.bold: true
            font.family: Theme.font
        }

        TextField {
            id: field
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 24
            background: null
            color: Theme.text
            font.pixelSize: 13
            font.family: Theme.font
            selectionColor: Theme.sel
            selectedTextColor: Theme.selText
            cursorDelegate: Rectangle {
                width: 2
                color: Theme.accent2
            }

            onAccepted: {
                var text = field.text
                var p = root.prefix
                root.close()
                if (p === ":")
                    api.runEx(text)
                else if (p === "/")
                    api.runFind(text)
            }
            Keys.onEscapePressed: root.close()
        }
    }
}
