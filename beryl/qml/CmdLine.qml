import QtQuick
import QtQuick.Controls.Basic

// The ex/search line — sits exactly over the statusbar while open (vellum's
// footer pattern). ':' runs through the command registry, '/' drives findText.
// The popup above it is the local-only completion: commands, open tabs,
// history frecency. Tab / C-n / C-p cycle; Enter takes the highlighted row.
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
        Completion.update(p, prefill)
        field.forceActiveFocus()
        field.cursorPosition = field.length
    }

    function close() {
        prefix = ""
        field.text = ""
        Completion.reset()
        Vim.cmdlineClosed()
        root.closed()
    }

    function cycle(d) {
        Completion.cycle(d)
        var t = Completion.currentInsert()
        if (t !== "") {
            field.text = t
            field.cursorPosition = field.length
        }
    }

    // ---- completion popup -------------------------------------------------
    Rectangle {
        id: popup
        visible: root.active && root.prefix === ":" && Completion.count > 0
        anchors { left: parent.left; right: parent.right; bottom: parent.top; bottomMargin: 6 }
        height: Math.min(Completion.count, 12) * 26 + 10
        radius: Theme.radiusSm
        color: Theme.card
        border.color: Theme.border
        border.width: 1

        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 5
            model: Completion
            clip: true
            currentIndex: Completion.sel
            onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)

            delegate: Rectangle {
                required property int index
                required property string label
                required property string detail

                width: list.width
                height: 26
                radius: 6
                color: index === Completion.sel ? Theme.sel
                     : rowHover.hovered ? Theme.glassSoft : "transparent"

                HoverHandler { id: rowHover }
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    spacing: 10
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: label
                        color: index === Completion.sel ? Theme.selText : Theme.text
                        font.pixelSize: 12
                        font.family: Theme.font
                        elide: Text.ElideRight
                        width: Math.min(implicitWidth, list.width * 0.45)
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: detail
                        color: Theme.subtext
                        font.pixelSize: 11
                        font.family: Theme.font
                        elide: Text.ElideMiddle
                        width: Math.min(implicitWidth, list.width * 0.5)
                    }
                }
            }
        }
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

            onTextEdited: Completion.update(root.prefix, text)

            onAccepted: {
                var t = Completion.currentInsert() !== "" ? Completion.currentInsert()
                                                          : field.text
                var p = root.prefix
                root.close()
                if (p === ":")
                    api.runEx(t)
                else if (p === "/")
                    api.runFind(t)
            }

            Keys.onEscapePressed: root.close()
            Keys.onPressed: function (e) {
                var ctrl = e.modifiers & Qt.ControlModifier
                if (e.key === Qt.Key_Down || e.key === Qt.Key_Tab || (ctrl && e.key === Qt.Key_N)) {
                    root.cycle(1)
                    e.accepted = true
                } else if (e.key === Qt.Key_Up || e.key === Qt.Key_Backtab || (ctrl && e.key === Qt.Key_P)) {
                    root.cycle(-1)
                    e.accepted = true
                }
            }
        }
    }
}
