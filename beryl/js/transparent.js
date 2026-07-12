// transparent pages (zen-style): strip the page's own background so the
// frosted window shows through the site. A constructed stylesheet is used
// because strict-CSP sites block injected <style> elements; adoptedStyleSheets
// are CSP-immune. The data marker is what beryl (and the tests) can probe.
(function () {
    var css = "html, body { background: transparent !important; }";
    function mark() {
        if (document.documentElement)
            document.documentElement.dataset.berylTransparent = "1";
    }
    try {
        var sheet = new CSSStyleSheet();
        sheet.replaceSync(css);
        document.adoptedStyleSheets = document.adoptedStyleSheets.concat(sheet);
    } catch (e) {
        var s = document.createElement("style");
        s.textContent = css;
        (document.head || document.documentElement).appendChild(s);
    }
    if (document.documentElement)
        mark();
    else
        document.addEventListener("DOMContentLoaded", mark);
})();
