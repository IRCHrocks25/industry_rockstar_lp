// Editor panel (architecture.md §7 "Editing loop"): edits apply to the preview
// instantly over the postMessage bridge (static/js/preview-bridge.js) and
// persist to the draft via the debounced save endpoint. Focus syncs both ways:
// clicking a panel field highlights the element in the preview, clicking an
// element in the preview scrolls to and focuses its panel field. The sandboxed
// iframe is an opaque origin, so postMessage is the only channel — no reloads.
(function () {
  "use strict";

  var cfg = window.EDITOR;
  if (!cfg) return;

  var form = document.getElementById("fields-form");
  var frame = document.getElementById("preview-frame");
  var state = document.getElementById("save-state");
  if (!form) return;

  var timer = null;

  function post(msg) {
    if (frame && frame.contentWindow) {
      msg.source = "cms-editor";
      frame.contentWindow.postMessage(msg, "*");
    }
  }

  function escapeSelector(id) {
    return window.CSS && CSS.escape ? CSS.escape(id) : id.replace(/"/g, '\\"');
  }

  function controlsFor(id) {
    return form.querySelectorAll('[data-field-id="' + escapeSelector(id) + '"]');
  }

  function fieldPayload(id) {
    var controls = controlsFor(id);
    if (!controls.length) return null;
    var fieldType = controls[0].dataset.fieldType;
    var value = null;
    controls.forEach(function (el) {
      if (el.dataset.part) {
        if (value === null || typeof value !== "object") value = {};
        value[el.dataset.part] = el.value;
      } else {
        value = el.value;
      }
    });
    return { id: id, field_type: fieldType, value: value };
  }

  function collectValues() {
    var values = {};
    form.querySelectorAll("[data-field-id]").forEach(function (el) {
      var id = el.dataset.fieldId;
      if (el.dataset.part) {
        if (typeof values[id] !== "object" || values[id] === null) values[id] = {};
        values[id][el.dataset.part] = el.value;
      } else {
        values[id] = el.value;
      }
    });
    return values;
  }

  function allPayloads() {
    var seen = {};
    var fields = [];
    form.querySelectorAll("[data-field-id]").forEach(function (el) {
      var id = el.dataset.fieldId;
      if (seen[id]) return;
      seen[id] = true;
      var payload = fieldPayload(id);
      if (payload) fields.push(payload);
    });
    return fields;
  }

  function setState(text) {
    if (state) state.textContent = text;
  }

  function save() {
    setState("Saving…");
    fetch(cfg.saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ values: collectValues() }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("save failed");
        setState("Saved");
      })
      .catch(function () {
        setState("Couldn’t save — retrying on next edit");
      });
  }

  // Typing: instant preview update, debounced persist.
  form.addEventListener("input", function (event) {
    var el = event.target;
    if (el && el.dataset && el.dataset.fieldId) {
      var payload = fieldPayload(el.dataset.fieldId);
      if (payload) post({ type: "apply-content", fields: [payload] });
    }
    setState("Editing…");
    if (timer) clearTimeout(timer);
    timer = setTimeout(save, 600);
  });

  // Panel → preview: focusing a field highlights and scrolls to its element.
  form.addEventListener("focusin", function (event) {
    var el = event.target;
    if (el && el.dataset && el.dataset.fieldId) {
      post({ type: "highlight-field", id: el.dataset.fieldId });
    }
  });

  // Preview → panel: clicking an element focuses its field.
  var flashTimer = null;
  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.source !== "cms-preview") return;
    if (msg.type === "ready") {
      // Frame (re)loaded: push current panel state so in-flight edits show.
      var fields = allPayloads();
      if (fields.length) post({ type: "apply-content", fields: fields });
    } else if (msg.type === "focus-field") {
      var control = form.querySelector('[data-field-id="' + escapeSelector(msg.id) + '"]');
      var anchor = control
        ? control.closest(".field")
        : form.querySelector('[data-field-anchor="' + escapeSelector(msg.id) + '"]');
      if (!anchor && !control) return;
      (anchor || control).scrollIntoView({ behavior: "smooth", block: "center" });
      if (control) control.focus({ preventScroll: true });
      if (anchor) {
        anchor.classList.remove("field-flash");
        void anchor.offsetWidth; // restart the animation
        anchor.classList.add("field-flash");
        if (flashTimer) clearTimeout(flashTimer);
        flashTimer = setTimeout(function () {
          anchor.classList.remove("field-flash");
        }, 1300);
      }
    }
  });
})();
