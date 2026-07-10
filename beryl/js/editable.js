// beryl: auto-insert detection. Runs in the MAIN world (the webchannel
// transport only exists there) at DocumentReady, after qwebchannel.js.
// Reports "an editable element has focus" over the channel; the Python side
// flips normal/insert off it. Zero globals leaked.
(function () {
    "use strict";

    function editable(el) {
        if (!el) return false;
        if (el.isContentEditable) return true;
        var t = el.tagName;
        if (t === "TEXTAREA" || t === "SELECT") return true;
        if (t === "INPUT")
            return !/^(button|checkbox|radio|submit|reset|file|image|range|color|hidden)$/
                .test((el.type || "text").toLowerCase());
        return false;
    }

    if (typeof qt === "undefined" || !qt.webChannelTransport || typeof QWebChannel === "undefined")
        return;

    new QWebChannel(qt.webChannelTransport, function (ch) {
        var bridge = ch.objects.bridge;
        if (!bridge) return;
        document.addEventListener("focusin", function (e) {
            if (editable(e.target)) bridge.editableFocused(true);
        }, true);
        document.addEventListener("focusout", function () {
            bridge.editableFocused(false);
        }, true);
        if (editable(document.activeElement)) bridge.editableFocused(true);
    });
})();
