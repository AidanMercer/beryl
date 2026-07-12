import QtQuick

// Recent downloads — opened with gd. Same modal shape as BookmarksList: the
// KeyController is in "downloads" mode and forwards every key via Vim.listKey.
//   j / k / arrows   move      Enter / o   open the file
//   f       open its folder       y   yank path
//   x       cancel / drop entry   type to filter · Esc close
Item {
    id: root

    property var rows: []          // filtered Dl.items
    property int sel: 0
    property string filter: ""

    function refresh() {
        var all = Dl.items
        if (filter === "") {
            rows = all
        } else {
            var f = filter.toLowerCase(), out = []
            for (var i = 0; i < all.length; i++)
                if (all[i].name.toLowerCase().indexOf(f) >= 0 ||
                    all[i].dir.toLowerCase().indexOf(f) >= 0)
                    out.push(all[i])
            rows = out
        }
        if (sel >= rows.length) sel = Math.max(0, rows.length - 1)
    }

    function start() {
        filter = ""; sel = 0
        refresh()
    }

    function close() {
        Vim.setMode("normal")
    }

    function human(n) {
        if (n <= 0) return ""
        var u = ["B", "KB", "MB", "GB"], i = 0
        while (n >= 1024 && i < 3) { n /= 1024; i++ }
        return (n >= 10 || i === 0 ? Math.round(n) : n.toFixed(1)) + " " + u[i]
    }
    function ago(ts) {
        if (!ts) return ""
        var s = Date.now() / 1000 - ts
        if (s < 60) return "just now"
        if (s < 3600) return Math.floor(s / 60) + "m ago"
        if (s < 86400) return Math.floor(s / 3600) + "h ago"
        return Math.floor(s / 86400) + "d ago"
    }
    function detail(r) {
        if (r.state === "downloading")
            return r.percent >= 0
                ? r.percent + "% · " + human(r.got) + " / " + human(r.size)
                : human(r.got)
        if (r.state === "missing") return "missing"
        var size = human(r.size)
        return size !== "" ? size + " · " + ago(r.ts) : ago(r.ts)
    }

    Connections {
        target: Vim
        function onListKey(k) { root.handleKey(k) }
    }
    // running rows tick along while the list is up
    Connections {
        target: Dl
        function onChanged() { root.refresh() }
    }

    function handleKey(k) {
        if (k === "<Esc>") { close(); return }
        if (k === "<CR>") {
            if (rows.length && rows[sel].state !== "missing") {
                Dl.openPath(rows[sel].path); close()
            }
            return
        }
        // arrows work even mid-filter (j/k type into the filter there)
        if (k === "<Down>" || (k === "j" && filter === "")) { sel = Math.min(sel + 1, rows.length - 1); return }
        if (k === "<Up>" || (k === "k" && filter === "")) { sel = Math.max(sel - 1, 0); return }
        if (k === "o" && filter === "") {
            if (rows.length && rows[sel].state !== "missing") {
                Dl.openPath(rows[sel].path); close()
            }
            return
        }
        if (k === "f" && filter === "") {
            if (rows.length) { Dl.openDir(rows[sel].path); close() }
            return
        }
        if (k === "y" && filter === "") {
            if (rows.length) { Dl.yank(rows[sel].path); close() }
            return
        }
        if (k === "x" && filter === "") {
            if (rows.length) { Dl.remove(rows[sel].path); refresh() }
            return
        }
        if (k === "<BS>") { filter = filter.slice(0, -1); refresh(); return }
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
                    text: "downloads"
                    color: Theme.accent
                    font.pixelSize: 15; font.bold: true; font.family: Theme.font
                }
                Item { width: parent.width - 400; height: 1 }
                Text {
                    text: root.filter !== "" ? "/" + root.filter
                          : "j/k move · enter open · f folder · y yank · x remove · esc"
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
                        onClicked: {
                            if (modelData.state !== "missing") {
                                Dl.openPath(modelData.path); root.close()
                            }
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: stateText.left
                        anchors.rightMargin: 10
                        spacing: 1
                        Text {
                            text: "↓ " + modelData.name
                            color: modelData.state === "missing" ? Theme.subtext
                                 : index === root.sel ? Theme.selText : Theme.text
                            font.pixelSize: 13; font.family: Theme.font
                            font.strikeout: modelData.state === "missing"
                            elide: Text.ElideRight
                            width: parent.width
                        }
                        Text {
                            text: modelData.dir
                            color: Theme.subtext
                            font.pixelSize: 11; font.family: Theme.font
                            elide: Text.ElideMiddle
                            width: parent.width
                        }
                    }
                    Text {
                        id: stateText
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.detail(modelData)
                        color: modelData.state === "downloading" ? Theme.accent2 : Theme.subtext
                        font.pixelSize: 11; font.family: Theme.font
                    }
                }
            }
        }
    }
}
