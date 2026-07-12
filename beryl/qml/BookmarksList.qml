import QtQuick

// The bookmarks list — opened with b. Its own little modal: the KeyController
// is in "bookmarks" mode and forwards every key here via Vim.listKey.
//   j / k / arrows   move      Enter   open here
//   o / t   open in a new tab  x       remove
//   type    filter             Esc     close
Item {
    id: root
    signal openHere(string url)
    signal openTab(string url)

    property var rows: []          // filtered [{url,title}]
    property int sel: 0
    property string filter: ""

    function refresh() {
        var all = Bookmarks.items
        if (filter === "") {
            rows = all
        } else {
            var f = filter.toLowerCase(), out = []
            for (var i = 0; i < all.length; i++)
                if (all[i].url.toLowerCase().indexOf(f) >= 0 ||
                    all[i].title.toLowerCase().indexOf(f) >= 0)
                    out.push(all[i])
            rows = out
        }
        sel = Math.max(0, Math.min(sel, rows.length - 1))   // clamp both ends
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
        if (k === "<CR>") {
            if (rows.length) { root.openHere(rows[sel].url); close() }
            return
        }
        // arrows work even mid-filter (j/k type into the filter there)
        if (k === "<Down>" || (k === "j" && filter === "")) { if (rows.length) sel = Math.min(sel + 1, rows.length - 1); return }
        if (k === "<Up>" || (k === "k" && filter === "")) { sel = Math.max(sel - 1, 0); return }
        if ((k === "o" || k === "t") && filter === "") {
            if (rows.length) { root.openTab(rows[sel].url); close() }
            return
        }
        if (k === "x" && filter === "") {
            if (rows.length) { Bookmarks.removeUrl(rows[sel].url); refresh() }
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
                    text: "bookmarks"
                    color: Theme.accent
                    font.pixelSize: 15; font.bold: true; font.family: Theme.font
                }
                Item { width: parent.width - 340; height: 1 }
                Text {
                    text: root.filter !== "" ? "/" + root.filter
                          : "j/k move · enter open · o new tab · x remove · esc"
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
                        onClicked: { root.openHere(modelData.url); root.close() }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        spacing: 1
                        Text {
                            text: "★ " + (modelData.title !== "" ? modelData.title : modelData.url)
                            color: index === root.sel ? Theme.selText : Theme.text
                            font.pixelSize: 13; font.family: Theme.font
                            elide: Text.ElideRight
                            width: parent.width
                        }
                        Text {
                            text: modelData.url
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
