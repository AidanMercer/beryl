import QtQuick

// The tab strip: mica's pill row, model-driven. Click activates, middle-click
// closes, the 2px underline is the load progress. The pool is shared across
// windows, so the highlight follows what THIS window shows, not the global
// current tab. A ListView, not a Row: with enough tabs the strip scrolls
// (wheel/drag) instead of pushing pills invisibly past the window edge, and
// it keeps this window's shown tab scrolled into view.
Item {
    id: root
    property int shownUid: -1

    onShownUidChanged: {
        var i = Tabs.indexOfUid(shownUid)
        if (i >= 0)
            strip.positionViewAtIndex(i, ListView.Contain)
    }

    ListView {
        id: strip
        anchors.fill: parent
        anchors.leftMargin: 4
        orientation: ListView.Horizontal
        spacing: 4
        clip: true
        model: Tabs
        boundsBehavior: Flickable.StopAtBounds

        delegate: Rectangle {
            required property int index
            required property int uid
            required property string title
            required property string url
            required property bool loading
            required property int progress
            readonly property bool active: uid === root.shownUid

            y: Math.max(0, (strip.height - height) / 2)
            height: 24
            width: Math.min(content.implicitWidth + 18, 220)
            radius: Theme.radiusSm
            color: active ? Theme.sel : (hover.hovered ? Theme.glassSoft : "transparent")
            clip: true

            HoverHandler { id: hover }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                cursorShape: Qt.PointingHandCursor
                onClicked: function (mouse) {
                    if (mouse.button === Qt.MiddleButton)
                        Tabs.closeTab(index)
                    else
                        Tabs.activate(index)
                }
            }

            Row {
                id: content
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 9
                spacing: 6
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: index + 1
                    color: active ? Theme.accent : Theme.subtext
                    font.pixelSize: 11
                    font.family: Theme.font
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: title !== "" ? title : (url !== "" ? url : "new tab")
                    color: active ? Theme.selText : Theme.text
                    font.pixelSize: 12
                    font.family: Theme.font
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, 180)
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                height: 2
                radius: 1
                visible: loading
                width: parent.width * progress / 100
                color: Theme.accent2
            }
        }
    }
}
