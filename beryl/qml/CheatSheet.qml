import QtQuick

// A quick key reference — toggled with ? (help command). Behind a Loader so it
// costs nothing until first opened.
Item {
    id: root
    property bool shown: false
    function toggle() { shown = !shown }
    visible: shown

    readonly property var sections: [
        { title: "move", keys: [
            ["j / k", "scroll down / up"], ["d / u", "half page"],
            ["gg / G", "top / bottom"], ["H / L", "back / forward"],
            ["/ n N", "find, next, prev"], ["m / '", "set / jump mark"]] },
        { title: "links & tabs", keys: [
            ["f / F", "hint (this / new tab)"], ["gi", "focus first input"],
            ["o / t", "open (here / new tab)"], ["T", "switch tab"],
            ["J / K", "prev / next tab"], ["x / X", "close / reopen tab"]] },
        { title: "page & url", keys: [
            ["r / R", "reload / hard reload"], ["gu / gU", "url up / root"],
            ["zi / zo / zz", "zoom in / out / reset"], ["yy", "yank url"],
            ["p / P", "paste-go (here / tab)"]] },
        { title: "bookmarks & help", keys: [
            ["*", "bookmark this page (★)"], ["b", "open bookmarks list"],
            ["h / ?", "this help"], [":clear", "wipe cookies+history"],
            [":w", "save session"], ["ZZ", "quit"]] },
        { title: "modes & ex", keys: [
            ["i / Esc", "insert / normal"], ["S-Esc", "passthrough (avd)"],
            [":", "command line"], [":open / :tabopen", "url or search"],
            [":tab <q>", "switch to a tab"], [":bm", "bookmark this page"]] }
    ]

    MouseArea { anchors.fill: parent; onClicked: root.shown = false }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 720)
        height: Math.min(parent.height - 80, grid.implicitHeight + 60)
        radius: Theme.radius
        color: Theme.card
        border.color: Theme.border
        border.width: 1

        Text {
            id: heading
            anchors { top: parent.top; left: parent.left; margins: 20 }
            text: "beryl — keys"
            color: Theme.accent
            font.pixelSize: 15
            font.bold: true
            font.family: Theme.font
        }
        Text {
            anchors { top: parent.top; right: parent.right; margins: 20 }
            text: "? or click to close"
            color: Theme.subtext
            font.pixelSize: 11
            font.family: Theme.font
        }

        Grid {
            id: grid
            anchors { top: heading.bottom; left: parent.left; right: parent.right
                      topMargin: 14; leftMargin: 20; rightMargin: 20 }
            columns: 2
            columnSpacing: 30
            rowSpacing: 16

            Repeater {
                model: root.sections
                Column {
                    required property var modelData
                    width: (grid.width - 30) / 2
                    spacing: 5
                    Text {
                        text: modelData.title
                        color: Theme.accent2
                        font.pixelSize: 12
                        font.bold: true
                        font.family: Theme.font
                    }
                    Repeater {
                        model: modelData.keys
                        Row {
                            required property var modelData
                            spacing: 10
                            Text {
                                width: 90
                                text: modelData[0]
                                color: Theme.text
                                font.pixelSize: 12
                                font.family: Theme.font
                            }
                            Text {
                                text: modelData[1]
                                color: Theme.subtext
                                font.pixelSize: 12
                                font.family: Theme.font
                            }
                        }
                    }
                }
            }
        }
    }
}
