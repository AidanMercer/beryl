import QtQuick

// App settings — opened with s. Same modal shape as the other lists: the
// KeyController is in "settings" mode and forwards every key via Vim.listKey.
// Changes apply live and are written back into config.toml.
//   j / k / arrows   move       Enter / l / → next value
//   h / ←            previous   Esc close
Item {
    id: root

    property var rows: []
    property int sel: 0

    function refresh() {
        rows = Prefs.items
        if (sel >= rows.length) sel = Math.max(0, rows.length - 1)
    }
    function start() { sel = 0; refresh() }
    function close() { Vim.setMode("normal") }

    Connections {
        target: Vim
        function onListKey(k) { root.handleKey(k) }
    }
    Connections {
        target: Prefs
        function onChanged() { root.refresh() }
    }

    function handleKey(k) {
        if (k === "<Esc>") { close(); return }
        if (k === "j" || k === "<Down>") { sel = Math.min(sel + 1, rows.length - 1); return }
        if (k === "k" || k === "<Up>") { sel = Math.max(sel - 1, 0); return }
        if (k === "<CR>" || k === "l" || k === "<Right>" || k === "<Space>") {
            if (rows.length) Prefs.cycle(rows[sel].key, 1)
            return
        }
        if (k === "h" || k === "<Left>") {
            if (rows.length) Prefs.cycle(rows[sel].key, -1)
        }
    }

    MouseArea { anchors.fill: parent; onClicked: root.close() }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 100, 620)
        height: Math.min(parent.height - 100, 84 + root.rows.length * 48)
        radius: Theme.radius
        color: Theme.card
        border.color: Theme.border
        border.width: 1

        Column {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            Row {
                width: parent.width
                Text {
                    text: "settings"
                    color: Theme.accent
                    font.pixelSize: 15; font.bold: true; font.family: Theme.font
                }
                Item { width: parent.width - 330; height: 1 }
                Text {
                    text: "j/k move · enter/l/h change · esc"
                    color: Theme.subtext
                    font.pixelSize: 11; font.family: Theme.font
                }
            }

            ListView {
                id: list
                width: parent.width
                height: parent.height - 40
                model: root.rows
                clip: true
                currentIndex: root.sel

                delegate: Rectangle {
                    required property int index
                    required property var modelData
                    width: list.width
                    height: 44
                    radius: 8
                    color: index === root.sel ? Theme.sel
                         : hov.hovered ? Theme.glassSoft : "transparent"

                    HoverHandler { id: hov }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            root.sel = index
                            Prefs.cycle(modelData.key, 1)
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: value.left
                        anchors.rightMargin: 10
                        spacing: 1
                        Text {
                            text: modelData.label
                            color: index === root.sel ? Theme.selText : Theme.text
                            font.pixelSize: 13; font.family: Theme.font
                        }
                        Text {
                            text: modelData.detail
                            color: Theme.subtext
                            font.pixelSize: 11; font.family: Theme.font
                            elide: Text.ElideMiddle
                            width: parent.width
                        }
                    }
                    Text {
                        id: value
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: "‹ " + modelData.value + " ›"
                        color: Theme.accent2
                        font.pixelSize: 12; font.family: Theme.font
                    }
                }
            }
        }
    }
}
