(() => {
  "use strict";

  function initialize() {
    const button = document.getElementById(
      "b3-v810-hierarchy-button"
    );
    const treeView = document.getElementById(
      "b3-v810-hierarchy-view"
    );
    const viewer = document.getElementById("b3-v5-views");
    const relationship = document.getElementById(
      "storage-relationship-v89"
    );
    const controls = document.querySelector(".b3-v5-controls");

    if (![button, treeView, viewer, relationship, controls]
        .every(Boolean)) {
      return;
    }

    const modes = Array.from(
      controls.querySelectorAll("[data-v5-view]")
    );

    if (modes.length !== 3) return;

    // Reuse the existing authorized hierarchy controller.
    treeView.appendChild(relationship);

    treeView.hidden = true;
    treeView.style.display = "none";

    function activate(selected) {
      for (const item of [...modes, button]) {
        const active = item === selected;

        item.classList.toggle("btn-primary", active);
        item.classList.toggle(
          "btn-outline-secondary", !active
        );
        item.setAttribute("aria-pressed", String(active));
      }
    }

    button.addEventListener("click", () => {
      viewer.hidden = true;
      viewer.style.display = "none";

      treeView.hidden = false;
      treeView.style.display = "";

      if (relationship.tagName === "DETAILS") {
        relationship.open = true;
      }

      activate(button);
    });

    for (const mode of modes) {
      mode.addEventListener("click", () => {
        treeView.hidden = true;
        treeView.style.display = "none";

        viewer.hidden = false;
        viewer.style.display = "";

        // The existing controller manages the 3D/2D scene.
        activate(mode);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded", initialize, { once: true }
    );
  } else {
    initialize();
  }
})();
