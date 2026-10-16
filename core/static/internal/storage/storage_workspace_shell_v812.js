(() => {
  "use strict";

  if (typeof document === "undefined") return;

  const normalize = value =>
    (value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  const byText = (selectors, label) => {
    const wanted = normalize(label);

    for (const node of document.querySelectorAll(selectors)) {
      if (normalize(node.textContent) === wanted) {
        return node;
      }
    }
    return null;
  };

  const hideByText = label => {
    const node = byText("button, a, summary, [role='button']", label);
    if (node) {
      node.hidden = true;
      node.setAttribute("aria-hidden", "true");
    }
    return node;
  };

  const findSectionByHeading = label => {
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
  };

  const make = (tag, klass, text) => {
    const el = document.createElement(tag);
    if (klass) el.className = klass;
    if (text !== undefined) el.textContent = text;
    return el;
  };

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
      }
      .b3-shell-v812-toolbar .btn {
        border-radius: 10px;
      }
      .b3-shell-v812-toolbar .btn-primary {
        box-shadow: none;
      }
      .b3-shell-v812-main {
        padding: 0;
        background: #ffffff;
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
      .b3-shell-v812-lifted > summary,
      .b3-shell-v812-lifted .accordion-button {
        background: #ffffff !important;
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

  function init() {
    installStyle();

    const hierarchyHost = document.getElementById("b3-v810-hierarchy-view");
    if (!hierarchyHost) return;

    const spatialTab = byText("button, a", "Spatial viewer");
    const locationsTab = byText("button, a", "Locations");
    const samplesTab = byText("button, a", "Samples");
    const transfersTab = byText("button, a", "Transfers");
    const historyTab = byText("button, a", "History");

    const sourceTabs = {
      spatial: spatialTab,
      locations: locationsTab,
      samples: samplesTab,
      transfers: transfersTab,
      history: historyTab,
    };

    const tabBar = spatialTab?.parentElement;

    if (tabBar) {
      tabBar.classList.add("b3-shell-v812-hidden-source");
      tabBar.setAttribute("aria-hidden", "true");
    }

    hideByText("Audited inventory");
    hideByText("Back");
    hideByText("Overview");
    hideByText("Rotate");
    hideByText("Cutaway walls");

    const inventoryBlock = findSectionByHeading("Detailed inventory");
    const workspacesBlock = findSectionByHeading("My physical storage workspaces");
    const configureBlock = findSectionByHeading("Configure spatial view");

    const mainAnchor =
      hierarchyHost.closest("section,article,div")?.parentElement ||
      hierarchyHost.parentElement;

    if (!mainAnchor) return;

    if (document.getElementById("b3-shell-v812")) return;

    const shell = make("section", "b3-shell-v812");
    shell.id = "b3-shell-v812";

    const toolbar = make("div", "b3-shell-v812-toolbar");
    const note = make(
      "div",
      "b3-shell-v812-note",
      "Single workspace panel: view switching, inventory and configuration are consolidated here."
    );

    const title = make("span", "b3-shell-v812-title", "Workspace panel");

    toolbar.append(title);

    const internalButtons = [];

    const makeButton = (label, onClick) => {
      const btn = make("button", "btn btn-sm btn-outline-secondary", label);
      btn.type = "button";
      btn.addEventListener("click", onClick);
      internalButtons.push(btn);
      return btn;
    };

    const setActive = activeButton => {
      for (const btn of internalButtons) {
        btn.classList.remove("btn-primary");
        btn.classList.remove("btn-outline-primary");
        btn.classList.add("btn-outline-secondary");
      }

      if (activeButton) {
        activeButton.classList.remove("btn-outline-secondary");
        activeButton.classList.add("btn-primary");
      }
    };

    const extras = make("div", "b3-shell-v812-extras");
    const extraPanels = new Map();

    const registerExtra = (key, label, node) => {
      if (!node) return null;

      const wrapper = make("div", "b3-shell-v812-extra");
      wrapper.dataset.shellExtra = key;

      node.classList.add("b3-shell-v812-lifted");
      wrapper.append(node);
      extraPanels.set(key, wrapper);
      extras.append(wrapper);

      const btn = makeButton(label, () => {
        showExtra(key);
      });

      return btn;
    };

    const showExtra = key => {
      for (const [name, panel] of extraPanels.entries()) {
        panel.classList.toggle("active", name === key);
      }

      const btn = internalButtons.find(
        node => node.dataset.extraKey === key
      );

      if (btn) setActive(btn);
    };

    const proxyTab = (label, sourceButton) => {
      if (!sourceButton) return null;

      return makeButton(label, () => {
        sourceButton.click();
        for (const panel of extraPanels.values()) {
          panel.classList.remove("active");
        }
      });
    };

    const spatialBtn = proxyTab("Spatial", sourceTabs.spatial);
    const locationsBtn = proxyTab("Locations", sourceTabs.locations);
    const samplesBtn = proxyTab("Samples", sourceTabs.samples);
    const transfersBtn = proxyTab("Transfers", sourceTabs.transfers);
    const historyBtn = proxyTab("History", sourceTabs.history);

    for (const btn of [
      spatialBtn,
      locationsBtn,
      samplesBtn,
      transfersBtn,
      historyBtn
    ]) {
      if (btn) toolbar.append(btn);
    }

    const inventoryBtn = registerExtra("inventory", "Inventory", inventoryBlock);
    const workspacesBtn = registerExtra("workspaces", "Workspaces", workspacesBlock);
    const configureBtn = registerExtra("configure", "Configure", configureBlock);

    if (inventoryBtn) {
      inventoryBtn.dataset.extraKey = "inventory";
      toolbar.append(inventoryBtn);
    }

    if (workspacesBtn) {
      workspacesBtn.dataset.extraKey = "workspaces";
      toolbar.append(workspacesBtn);
    }

    if (configureBtn) {
      configureBtn.dataset.extraKey = "configure";
      toolbar.append(configureBtn);
    }

    const currentMain = hierarchyHost.parentElement;
    if (!currentMain) return;

    shell.append(toolbar, note);
    currentMain.parentElement.insertBefore(shell, currentMain);
    shell.append(currentMain);

    const mainRegion = make("div", "b3-shell-v812-main");
    shell.append(mainRegion);
    mainRegion.append(currentMain);

    if (extraPanels.size) {
      shell.append(extras);
      showExtra("inventory");
      if (inventoryBtn) setActive(inventoryBtn);
    } else if (spatialBtn) {
      setActive(spatialBtn);
    }

    const syncFromExternal = () => {
      const activeTop =
        [sourceTabs.spatial, sourceTabs.locations, sourceTabs.samples, sourceTabs.transfers, sourceTabs.history]
          .find(node =>
            node?.classList.contains("active") ||
            node?.getAttribute("aria-selected") === "true"
          );

      const mapping = new Map([
        [sourceTabs.spatial, spatialBtn],
        [sourceTabs.locations, locationsBtn],
        [sourceTabs.samples, samplesBtn],
        [sourceTabs.transfers, transfersBtn],
        [sourceTabs.history, historyBtn],
      ]);

      if (activeTop && mapping.get(activeTop)) {
        setActive(mapping.get(activeTop));
      }
    };

    const observer = new MutationObserver(syncFromExternal);

    for (const node of Object.values(sourceTabs)) {
      if (!node) continue;
      observer.observe(node, {
        attributes: true,
        attributeFilter: ["class", "aria-selected"]
      });
    }

    syncFromExternal();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, {once: true});
  } else {
    init();
  }
})();
