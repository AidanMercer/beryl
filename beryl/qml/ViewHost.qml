import QtQuick

// Never shown. Owns one (lazy) WebView loader per tab so live pages belong to
// the app, not to any window: a window shows a tab by reparenting the loader's
// ITEM (never the loader — the Repeater stacks its delegates and warns if one
// left) into its viewport, and stash() returns it here — page state survives
// window closes and moves between windows without a reload. Views carry their
// own `anchors.fill: parent`, so reparenting alone re-fits them.
Window {
    id: vault
    visible: false
    width: 1280
    height: 800

    function get(uid) {
        for (var i = 0; i < rep.count; i++) {
            var it = rep.itemAt(i)
            if (it && it.uid === uid)
                return it
        }
        return null
    }
    function stash(item) {
        if (item)
            item.parent = pool
    }

    Item {
        id: pool
        anchors.fill: parent

        Repeater {
            id: rep
            model: Tabs

            Loader {
                id: ld
                required property int uid
                required property string url
                required property bool live

                anchors.fill: parent
                active: live
                sourceComponent: WebView {
                    tabUid: ld.uid
                    initialUrl: ld.url
                }
            }
        }
    }
}
