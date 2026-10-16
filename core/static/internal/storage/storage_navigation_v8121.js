/*
 * B3 LIMS V8.12.1
 *
 * Consolidate the existing Storage Designer navigation.
 *
 * No inventory modifications, form submissions or
 * authorization changes are performed here.
 */
(() => {
  "use strict";

  const byId = id => document.getElementById(id);

  const normalize = text =>
    String(text || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  function findButton(toolbar, label) {
    return Array.from(
      toolbar.querySelectorAll("button")
    ).find(button =>
      normalize(button.textContent) ===
      normalize(label)
    ) || null;
  }

  function installStyles() {
    if (byId("b3-storage-navigation-v8121-style")) {
      return;
    }

    const style = document.createElement("style");
    style.id = "b3-storage-navigation-v8121-style";

    style.textContent = `
      #storage-spatial-viewer {
        background: #ffffff;
      }

      #storage-spatial-viewer
      .b3-cutaway-toolbar {
        display: none !important;
      }

      #storage-3d-example-notice {
        display: none !important;
      }

      #b3-shell-v812 .b3-shell-v812-note {
        display: none !important;
      }

      #b3-shell-v812
      .b3-nav-v8121-proxy {
        display: none !important;
      }

      #storage-spatial-viewer
      .b3-designer-tabs {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }

      #storage-spatial-viewer
      .b3-designer-tabs .btn {
        width: 100%;
        min-height: 36px;
      }

      #storage-spatial-viewer
      .b3-cutaway-side {
        background: #ffffff;
      }

      #b3-shell-v812
      .b3-shell-v812-toolbar {
        background: #ffffff;
        gap: 7px;
      }

      #b3-shell-v812
      .b3-shell-v812-extras {
        background: #ffffff;
      }

      .b3-webgl-v8121-warning {
        padding: 9px 12px;
        background: #fff8e9;
        color: #77551f;
        border: 1px solid #ead5a9;
        border-radius: 7px;
        margin: 9px;
        font-size: .83rem;
      }
    `;

    document.head.append(style);
  }

  function webglAvailable() {
    const canvas = document.createElement("canvas");

    let context = null;

    try {
      context =
        canvas.getContext("webgl2") ||
        canvas.getContext("webgl");
    } catch (_) {
      return false;
    }

    if (!context) return false;

    const extension = context.getExtension(
      "WEBGL_lose_context"
    );

    if (extension) {
      extension.loseContext();
    }

    return true;
  }

  function initialize() {
    if (byId("b3-navigation-v8121-ready")) {
      return;
    }

    const shell = byId("b3-shell-v812");

    const browse = byId("storage-designer-browse");
    const build = byId("storage-designer-build");

    const browsePanel = byId(
      "storage-designer-browse-panel"
    );

    const buildPanel = byId(
      "storage-designer-build-panel"
    );

    const live = byId("storage-3d-real");
    const example = byId("storage-3d-example");

    const toolbar = shell?.querySelector(
      ".b3-shell-v812-toolbar"
    );

    if (
      !shell ||
      !browse ||
      !build ||
      !browsePanel ||
      !buildPanel ||
      !toolbar ||
      !live ||
      !example
    ) {
      console.error(
        "B3 V8.12.1: required navigation components unavailable"
      );
      return;
    }

    const inventoryButton = findButton(
      toolbar, "Inventory"
    );

    const workspacesButton = findButton(
      toolbar, "Workspaces"
    );

    const viewerButton = findButton(
      toolbar, "Viewer"
    );

    if (
      !inventoryButton ||
      !workspacesButton ||
      !viewerButton
    ) {
      console.error(
        "B3 V8.12.1: existing workspace actions missing"
      );
      return;
    }

    installStyles();

    const ready = document.createElement("span");
    ready.id = "b3-navigation-v8121-ready";
    ready.hidden = true;
    shell.append(ready);

    // Keep the existing registered inventory source.
    // The demonstration source is no longer selectable.
    if (
      example.getAttribute("aria-pressed") === "true"
    ) {
      live.click();
    }

    browse.textContent = "Inventory";
    browse.setAttribute(
      "aria-label",
      "Browse registered and historical storage"
    );

    build.setAttribute(
      "aria-label",
      "Manage workspaces and create physical locations"
    );

    // Keep existing proxy buttons in the DOM because
    // the V8.12 shell owns their panel switching.
    inventoryButton.classList.add(
      "b3-nav-v8121-proxy"
    );

    workspacesButton.classList.add(
      "b3-nav-v8121-proxy"
    );

    inventoryButton.setAttribute("tabindex", "-1");
    workspacesButton.setAttribute("tabindex", "-1");

    // Creation shortcuts logically belong to Build location.
    // Moving them preserves their existing event listeners.
    const shortcuts = browsePanel.querySelector(
      ".b3-designer-shortcuts"
    );

    if (shortcuts) {
      buildPanel.append(shortcuts);
    }

    // The Inventory entry point now opens the existing
    // Django inventory explorer with search, details and
    // Sample occupancy.
    browse.addEventListener("click", () => {
      if (
        live.getAttribute("aria-pressed") !== "true"
      ) {
        live.click();
      }

      inventoryButton.click();
    });

    // Build location now exposes the existing workspace
    // creation and physical infrastructure forms.
    build.addEventListener("click", () => {
      workspacesButton.click();
    });

    // Preserve all server-side permissions and original
    // Django form action URLs.
    const forms = shell.querySelectorAll("form");

    for (const form of forms) {
      form.setAttribute(
        "data-b3-original-form",
        "preserved"
      );
    }

    // An unavailable WebGL context is a browser limitation,
    // not a Django server failure. Use 2D instead of
    // leaving an empty 3D viewport.
    if (!window.B3StorageSVGV813?.ready && !webglAvailable()) {
      const controls = document.querySelector(
        ".b3-v5-controls"
      );

      const mode3D = controls?.querySelector(
        '[data-v5-view="3d"]'
      );

      const modeSplit = controls?.querySelector(
        '[data-v5-view="split"]'
      );

      const mode2D = controls?.querySelector(
        '[data-v5-view="2d"]'
      );

      for (const button of [mode3D, modeSplit]) {
        if (!button) continue;

        button.disabled = true;

        button.setAttribute(
          "title",
          "WebGL is unavailable in this browser"
        );

        button.setAttribute(
          "aria-disabled",
          "true"
        );
      }

      if (controls) {
        const notice = document.createElement("div");

        notice.className =
          "b3-webgl-v8121-warning";

        notice.setAttribute("role", "status");

        notice.textContent =
          "3D visualization requires WebGL. " +
          "The 2D and Hierarchy views remain available.";

        controls.insertAdjacentElement(
          "afterend", notice
        );
      }

      if (mode2D) {
        mode2D.click();
      }

      console.warn(
        "B3 V8.12.1: WebGL unavailable; 2D selected."
      );
    }

    console.info(
      "B3 V8.12.1: navigation consolidated."
    );
  }

  // The existing V8.12 controller initializes on load.
  // Run after it, without reparenting the 3D canvas.
  window.addEventListener("load", () => {
    window.requestAnimationFrame(initialize);
  }, {once: true});
})();
