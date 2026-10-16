(() => {
  "use strict";

  if (typeof document === "undefined") return;

  const normalize = value =>
    (value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  const make = (tag, klass, text) => {
    const el = document.createElement(tag);
    if (klass) el.className = klass;
    if (text !== undefined) el.textContent = text;
    return el;
  };

  const allTextMatches = (selectors, label) => {
    const wanted = normalize(label);
    return Array.from(document.querySelectorAll(selectors))
      .filter(node => normalize(node.textContent) === wanted);
  };

  const firstTextMatch = (selectors, label) =>
    allTextMatches(selectors, label)[0] || null;

  function hideExactText(label) {
    const matches = allTextMatches(
      "button, a, span, summary, [role='button'], .badge, .btn, .nav-link",
      label
    );

    for (const node of matches) {
      const target =
        node.closest("button, a, summary, .btn, .badge") || node;

      target.hidden = true;
      target.setAttribute("aria-hidden", "true");
      target.classList.add("b3-shell-v812-hidden-source");
    }
  }

  function hideContainerIfEmpty(node) {
    if (!node) return;

    const parent = node.parentElement;
    if (!parent) return;

    const visibleChildren = Array.from(parent.children).filter(
      child => !child.hidden && child.offsetParent !== null
    );

    if (!visibleChildren.length) {
      parent.hidden = true;
      parent.classList.add("b3-shell-v812-hidden-source");
    }
  }

  function findSectionByHeading(label) {
    const wanted = normalize(label);

    const headings = document.querySelectorAll(
      "summary,h1,h2,h3,h4,h5,h6,button,[role='button'],legend"
    );

    for (const heading of headings) {
      if (!normalize(heading.textContent).includes(wanted)) {
        continue;
      }

      const block = heading.closest(
        "details,section,article,.accordion-item,.card,.border,.rounded,.shadow-sm,div"
      );

      if (block && block !== document.body && block !== document.documentElement) {
        return block;
      }
    }

    return null;
  }

  function installStyle() {
    if (document.getElementById("b3-v812-shell-style")) return;

    const style = document.createElement("style");
    style.id = "b3-v812-shell-style";

    style.textContent = `
      .b3-shell-v812 {
        margin-top: 14px;
        border: 1px solid #d8e3ea;
        border-radius: 12px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(16,42,67,.05);
        overflow: hidden;
      }
      .b3-shell-v812-toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 12px;
        border-bottom: 1px solid #e5edf2;
        background: #ffffff;
        align-items: center;
      }
      .b3-shell-v812-toolbar .btn {
        border-radius: 10px;
      }
      .b3-shell-v812-main {
        background: #ffffff;
      }
      .b3-shell-v812-panel {
        display: none;
      }
      .b3-shell-v812-panel.active {
        display: block;
      }
      .b3-shell-v812-extras {
        border-top: 1px solid #e5edf2;
        background: #fbfdff;
        padding: 12px;
      }
      .b3-shell-v812-extra {
        display: none;
      }
      .b3-shell-v812-extra.active {
        display: block;
      }
      .b3-shell-v812-note {
        padding: 10px 12px;
        border-bottom: 1px solid #e5edf2;
        color: #5a7180;
        background: #f9fcfe;
        font-size: .86rem;
      }
      .b3-shell-v812-lifted {
        margin: 0 !important;
        border: 0 !important;
        box-shadow: none !important;
        background: transparent !important;
      }
      .b3-shell-v812-hidden-source {
        display: none !important;
      }
      .b3-shell-v812-title {
        font-weight: 600;
        color: #16384b;
        margin-right: 8px;
        align-self: center;
      }
    `;

    document.head.append(style);
  }

  function triggerViewerRefresh() {
    const fire = () => {
      window.dispatchEvent(new Event("resize"));

      const activeMode =
        document.querySelector(
          'button[data-v5-view].active, button[data-v5-view][aria-pressed="true"]'
        ) ||
        firstTextMatch("button", "3D + 2D") ||
        firstTextMatch("button", "3D");

      if (activeMode) {
        activeMode.click();
      }

      window.dispatchEvent(new Event("resize"));
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(fire);
    });
  }

  function init() {
    if (document.getElementById("b3-shell-v812")) return;

    installStyle();

    const hierarchyHost = document.getElementById("b3-v810-hierarchy-view");
    if (!hierarchyHost) return;

    const spatialTab = firstTextMatch("button, a", "Spatial viewer");
    const samplesTab = firstTextMatch("button, a", "Samples");
    const transfersTab = firstTextMatch("button, a", "Transfers");
    const historyTab = firstTextMatch("button, a", "History");

    const sourceTabs = {
      spatial: spatialTab,
      samples: samplesTab,
      transfers: transfersTab,
      history: historyTab,
    };

    const tabBar = spatialTab?.parentElement;
    if (tabBar) {
      tabBar.classList.add("b3-shell-v812-hidden-source");
      tabBar.setAttribute("aria-hidden", "true");
    }

    hideExactText("Explore example");
    hideExactText("Audited inventory");
    hideExactText("Back");
    hideExactText("Overview");
    hideExactText("Rotate");
    hideExactText("Cutaway walls");

    hideContainerIfEmpty(firstTextMatch("button, a", "Explore example"));
    hideContainerIfEmpty(firstTextMatch("span, a, button", "Audited inventory"));

    const inventoryBlock = findSectionByHeading("Detailed inventory");
    const workspacesBlock = findSectionByHeading("My physical storage workspaces");
    const configureBlock = findSectionByHeading("Configure spatial view");

    const currentMain =
      hierarchyHost.closest("section,article,div")?.parentElement ||
      hierarchyHost.parentElement;

    if (!currentMain || !currentMain.parentElement) return;

    const shell = make("section", "b3-shell-v812");
    shell.id = "b3-shell-v812";

    const toolbar = make("div", "b3-shell-v812-toolbar");
    const note = make(
      "div",
      "b3-shell-v812-note",
      "Workspace navigation and inventory tools are consolidated in a single main panel."
    );
    const title = make("span", "b3-shell-v812-title", "Workspace panel");

    const mainRegion = make("div", "b3-shell-v812-main");
    const viewerPanel = make("div", "b3-shell-v812-panel");
    viewerPanel.dataset.panel = "viewer";
    viewerPanel.classList.add("active");

    const extras = make("div", "b3-shell-v812-extras");
    const extraPanels = new Map();
    const buttons = new Map();

    function setActiveButton(key) {
      for (const [name, btn] of buttons.entries()) {
        btn.classList.remove("btn-primary");
        btn.classList.remove("btn-outline-primary");
        btn.classList.add("btn-outline-secondary");

        if (name === key) {
          btn.classList.remove("btn-outline-secondary");
          btn.classList.add("btn-primary");
        }
      }
    }

    function setActivePanel(key) {
      viewerPanel.classList.toggle("active", key === "viewer");

      for (const [name, panel] of extraPanels.entries()) {
        panel.classList.toggle("active", name === key);
      }

      setActiveButton(key);

      if (key === "viewer") {
        triggerViewerRefresh();
      }
    }

    function registerButton(key, label, callback) {
      const btn = make("button", "btn btn-sm btn-outline-secondary", label);
      btn.type = "button";
      btn.addEventListener("click", callback);
      buttons.set(key, btn);
      toolbar.append(btn);
      return btn;
    }

    function registerExtra(key, node) {
      if (!node) return;

      const wrapper = make("div", "b3-shell-v812-extra");
      wrapper.dataset.shellExtra = key;

      node.classList.add("b3-shell-v812-lifted");
      wrapper.append(node);
      extraPanels.set(key, wrapper);
      extras.append(wrapper);
    }

    registerExtra("inventory", inventoryBlock);
    registerExtra("workspaces", workspacesBlock);
    registerExtra("configure", configureBlock);

    const parent = currentMain.parentElement;
    parent.insertBefore(shell, currentMain);
    shell.append(toolbar, note, mainRegion);

    viewerPanel.append(currentMain);
    mainRegion.append(viewerPanel);

    if (extraPanels.size) {
      mainRegion.append(extras);
    }

    toolbar.append(title);

    registerButton("viewer", "Viewer", () => {
      if (sourceTabs.spatial) {
        sourceTabs.spatial.click();
      }
      setActivePanel("viewer");
    });

    if (extraPanels.has("inventory")) {
      registerButton("inventory", "Inventory", () => {
        setActivePanel("inventory");
      });
    }

    if (sourceTabs.samples) {
      registerButton("samples", "Samples", () => {
        sourceTabs.samples.click();
        setActivePanel("viewer");
      });
    }

    if (sourceTabs.transfers) {
      registerButton("transfers", "Transfers", () => {
        sourceTabs.transfers.click();
        setActivePanel("viewer");
      });
    }

    if (sourceTabs.history) {
      registerButton("history", "History", () => {
        sourceTabs.history.click();
        setActivePanel("viewer");
      });
    }

    if (extraPanels.has("workspaces")) {
      registerButton("workspaces", "Workspaces", () => {
        setActivePanel("workspaces");
      });
    }

    if (extraPanels.has("configure")) {
      registerButton("configure", "Configure", () => {
        setActivePanel("configure");
      });
    }

    const syncFromExternal = () => {
      const activeTop =
        [
          sourceTabs.spatial,
          sourceTabs.samples,
          sourceTabs.transfers,
          sourceTabs.history
        ].find(node =>
          node?.classList.contains("active") ||
          node?.getAttribute("aria-selected") === "true"
        );

      if (activeTop === sourceTabs.samples) {
        setActiveButton("samples");
      } else if (activeTop === sourceTabs.transfers) {
        setActiveButton("transfers");
      } else if (activeTop === sourceTabs.history) {
        setActiveButton("history");
      } else {
        setActiveButton("viewer");
      }
    };

    const observer = new MutationObserver(() => {
      syncFromExternal();
      hideExactText("Explore example");
      hideExactText("Audited inventory");
      hideExactText("Back");
      hideExactText("Overview");
      hideExactText("Rotate");
      hideExactText("Cutaway walls");
    });

    for (const node of Object.values(sourceTabs)) {
      if (!node) continue;
      observer.observe(node, {
        attributes: true,
        attributeFilter: ["class", "aria-selected"]
      });
    }

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    setActivePanel("viewer");
    syncFromExternal();
    triggerViewerRefresh();
  }

  window.addEventListener("load", () => {
    init();
  }, {once: true});
})();
