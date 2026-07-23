// Live-editor bridge — injected into the PREVIEW render only (page_preview
// view, mode='edit'); published pages never include it. The preview iframe is
// sandboxed into an opaque origin, so parent and frame talk exclusively via
// postMessage, discriminated by a `source` marker rather than origin:
//
//   editor → preview:  apply-content {fields:[{id, field_type, value}]}
//                      highlight-field {id}
//   preview → editor:  ready {}
//                      focus-field {id}
//
// Apply logic mirrors the server render engine (apps/pages/render.py) for the
// editable field types; the server stays the source of truth on every real load.
(function () {
  "use strict";

  var PARENT = window.parent;
  if (!PARENT || PARENT === window) return;

  var style = document.createElement("style");
  style.textContent =
    "[data-editable-id]{cursor:pointer;outline:2px solid transparent;outline-offset:2px;" +
    "transition:outline-color 120ms ease;}" +
    "[data-editable-id]:hover{outline-color:rgba(22,101,52,0.45);}" +
    ".cms-flash{outline-color:#166534 !important;}";
  document.head.appendChild(style);

  function nodeFor(id) {
    var esc = window.CSS && CSS.escape ? CSS.escape(id) : id.replace(/"/g, '\\"');
    return document.querySelector('[data-editable-id="' + esc + '"]');
  }

  function setText(node, value) {
    node.textContent = value == null ? "" : String(value);
  }

  function apply(field) {
    var node = nodeFor(field.id);
    if (!node) return;
    var v = field.value;
    switch (field.field_type) {
      case "text":
      case "link_text":
        setText(node, v);
        break;
      case "richtext":
        // Scripts inserted via innerHTML never execute; the server re-sanitizes on save.
        node.innerHTML = v == null ? "" : String(v);
        break;
      case "image":
        v = v || {};
        if (v.src) {
          node.setAttribute("src", v.src);
          node.removeAttribute("srcset");
        }
        if (v.alt != null) node.setAttribute("alt", v.alt);
        break;
      case "background_image":
        var src = v && (typeof v === "object" ? v.src : v);
        if (src) {
          var s = node.getAttribute("style") || "";
          if (/url\(/i.test(s)) {
            s = s.replace(/url\(\s*['"]?[^'")]+['"]?\s*\)/i, 'url("' + src + '")');
          } else {
            s = (s.trim() ? s.replace(/;?\s*$/, "; ") : "") + 'background-image: url("' + src + '")';
          }
          node.setAttribute("style", s);
        }
        break;
      case "link_url":
        if (v) node.setAttribute("href", String(v));
        break;
      case "cta":
        v = v || {};
        if (v.url) node.setAttribute("href", v.url);
        if (v.text != null) setText(node, v.text);
        break;
    }
  }

  var flashed = null;
  var flashTimer = null;
  function highlight(id) {
    var node = nodeFor(id);
    if (!node) return;
    if (flashed) flashed.classList.remove("cms-flash");
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("cms-flash");
    flashed = node;
    if (flashTimer) clearTimeout(flashTimer);
    flashTimer = setTimeout(function () {
      node.classList.remove("cms-flash");
    }, 1600);
  }

  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.source !== "cms-editor") return;
    if (msg.type === "apply-content") {
      (msg.fields || []).forEach(apply);
    } else if (msg.type === "highlight-field") {
      highlight(msg.id);
    }
  });

  // Click any annotated element → its field focuses in the editor panel.
  // Capture phase + preventDefault so CTA links don't navigate the preview.
  document.addEventListener(
    "click",
    function (event) {
      var node = event.target && event.target.closest
        ? event.target.closest("[data-editable-id]")
        : null;
      if (!node) return;
      event.preventDefault();
      var id = node.getAttribute("data-editable-id");
      highlight(id);
      PARENT.postMessage({ source: "cms-preview", type: "focus-field", id: id }, "*");
    },
    true
  );

  PARENT.postMessage({ source: "cms-preview", type: "ready" }, "*");
})();
