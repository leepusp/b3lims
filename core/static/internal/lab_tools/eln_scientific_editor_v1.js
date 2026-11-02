/*
 * B3 ELN scientific document editor v1.
 * Self-hosted SunEditor 3.4.1; no CDN or external upload.
 */
(function () {
  "use strict";

  function plainTextToHtml(source) {
    const container = document.createElement("div");

    source.split(/\r?\n/).forEach(function (line) {
      const paragraph = document.createElement("p");

      if (line.length) {
        paragraph.textContent = line;
      } else {
        paragraph.appendChild(
          document.createElement("br")
        );
      }

      container.appendChild(paragraph);
    });

    return container.innerHTML;
  }

  function initialize() {
    const form = document.getElementById("eln-editor-form");
    const textarea = document.getElementById("eln-content");

    if (!form || !textarea) return;

    const format = form.querySelector(
      'input[name="content_format"]'
    );

    if (!format) return;

    if (
      !window.SUNEDITOR ||
      typeof window.SUNEDITOR.create !== "function"
    ) {
      console.error(
        "B3 ELN: local editor could not be loaded."
      );
      return;
    }

    const initial = (
      format.value === "rich_html_v1"
        ? textarea.value
        : plainTextToHtml(textarea.value)
    );

    let editor;

    try {
      editor = window.SUNEDITOR.create(textarea, {
        plugins: window.SUNEDITOR.plugins,
        value: initial,
        mode: "classic",
        width: "100%",
        minHeight: "420px",
        placeholder: (
          "Document objectives, methods, observations, " +
          "tables, references and conclusions."
        ),
        buttonList: [
          ["undo", "redo"],
          ["blockStyle"],
          ["bold", "italic", "underline",
           "strike", "subscript", "superscript"],
          ["removeFormat"],
          ["list", "table", "link"],
          ["codeView", "fullScreen"]
        ]
      });
    } catch (error) {
      console.error("B3 ELN editor initialization failed.", error);
      return;
    }

    if (
      !editor ||
      !editor.$ ||
      !editor.$.html ||
      typeof editor.$.html.get !== "function"
    ) {
      console.error(
        "B3 ELN: incompatible editor interface."
      );
      return;
    }

    form.addEventListener("submit", function (event) {
      const html = editor.$.html.get();

      const length = new TextEncoder()
        .encode(html).length;

      if (length > 512000) {
        event.preventDefault();
        window.alert(
          "Main Text exceeds the 500 KiB limit. " +
          "Reduce its size before saving."
        );
        return;
      }

      // Update the original Django form field.
      textarea.value = html;
      format.value = "rich_html_v1";
    });

    form.dataset.richEditorReady = "true";
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded", initialize,
      { once: true }
    );
  } else {
    initialize();
  }
})();
