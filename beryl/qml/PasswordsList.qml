import QtQuick

// The saved-passwords list — opened with gp. Its own little modal: the
// KeyController is in "passwords" mode and forwards every key here via
// Vim.listKey. Passwords are NEVER shown or put in the model — y copies the
// password to the clipboard straight from python, u copies the username.
//   j / k / arrows   move        y       copy password
//   u   copy username            x       delete login
//   type   filter                Esc     close
Item {
    id: root

    property var rows: []          // filtered [{origin,host,username}]
    property int sel: 0
    property string filter: ""

    function refresh() {
        var all = Vault.items
        if (filter === "") {
            rows = all
        } else {
            var f = filter.toLowerCase(), out = []
            for (var i = 0; i < all.length; i++)
                if (all[i].host.toLowerCase().indexOf(f) >= 0 ||
                    all[i].username.toLowerCase().indexOf(f) >= 0)
                    out.push(all[i])
            rows = out
        }
        sel = Math.max(0, Math.min(sel, rows.length - 1))
    }

    function start() {
        filter = ""; sel = 0
        refresh()
    }

    function close() {
        Vim.setMode("normal")
    }

    Connections {
        target: Vim
        function onListKey(k) { root.handleKey(k) }
    }

    function handleKey(k) {
        if (k === "<Esc>") { close(); return }
        if (k === "<Down>" || (k === "j" && filter === "")) { if (rows.length) sel = Math.min(sel + 1, rows.length - 1); return }
        if (k === "<Up>" || (k === "k" && filter === "")) { sel = Math.max(sel - 1, 0); return }
        if ((k === "y" || k === "<CR>") && filter === "") {
            if (rows.length) { Vault.yankPassword(rows[sel].origin, rows[sel].username); close() }
            return
        }
        if (k === "u" && filter === "") {
            if (rows.length) Vault.yankUsername(rows[sel].origin, rows[sel].username)
            return
        }
        if (k === "x" && filter === "") {
            if (rows.length) { Vault.removeLogin(rows[sel].origin, rows[sel].username); refresh() }
            return
        }
        if (k === "<BS>") { filter = filter.slice(0, -1); refresh(); return }
        if (k === "<Space>") { filter += " "; refresh(); return }
        if (k.length === 1 && k >= " ") { filter += k; refresh() }
    }

    MouseArea { anchors.fill: parent; onClicked: root.close() }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 100, 760)
        height: Math.min(parent.height - 100, 520)
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
                    text: "passwords"
                    color: Theme.accent
                    font.pixelSize: 15; font.bold: true; font.family: Theme.font
                }
                Item { width: parent.width - 380; height: 1 }
                Text {
                    text: root.filter !== "" ? "/" + root.filter
                          : "j/k move · y copy password · u username · x delete · esc"
                    color: root.filter !== "" ? Theme.accent2 : Theme.subtext
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
                onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)

                delegate: Rectangle {
                    required property int index
                    required property var modelData
                    width: list.width
                    height: 40
                    radius: 8
                    color: index === root.sel ? Theme.sel
                         : hov.hovered ? Theme.glassSoft : "transparent"

                    HoverHandler { id: hov }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: { Vault.yankPassword(modelData.origin, modelData.username); root.close() }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        spacing: 1
                        Text {
                            text: "🔑 " + modelData.host
                            color: index === root.sel ? Theme.selText : Theme.text
                            font.pixelSize: 13; font.family: Theme.font
                            elide: Text.ElideRight
                            width: parent.width
                        }
                        Text {
                            text: modelData.username !== "" ? modelData.username : "— no username —"
                            color: Theme.subtext
                            font.pixelSize: 11; font.family: Theme.font
                            elide: Text.ElideMiddle
                            width: parent.width
                        }
                    }
                }
            }
        }
    }
}
