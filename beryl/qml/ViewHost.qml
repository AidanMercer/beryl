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

    // a lazily-woken row instantiates its view after windows already asked
    // for it — they listen for this and refit
    signal woke(int uid)

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

    // workspace switches occlude windows and Chromium evicts their composited
    // frames — on return the page area is black until a new frame arrives
    // (static pages never send one). Blinking visibility delivers
    // wasHidden/wasShown and forces a recomposite; windows call this when
    // they regain activation.
    function repaintAll() {
        for (var i = 0; i < rep.count; i++) {
            var it = rep.itemAt(i)
            if (it && it.item && it.item.shown) {
                it.item.visible = false
                it.item.visible = true
            }
        }
    }

    // live pages keep the rice's palette: theme switches and page-color
    // changes rewrite the injected stylesheet in place, no reload needed
    function rethemeAll() {
        for (var i = 0; i < rep.count; i++) {
            var it = rep.itemAt(i)
            if (it && it.item)
                it.item.applyTransparentTheme()
        }
    }
    Connections {
        target: Rice
        function onThemeChanged() { vault.rethemeAll() }
    }
    Connections {
        target: Prefs
        function onApplied() { vault.rethemeAll() }
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
                onLoaded: vault.woke(ld.uid)
            }
        }
    }
}
