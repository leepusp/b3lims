(() => {
  "use strict";

  function buildModel(rows) {
    const nodes = new Map();

    for (const row of rows) {
      const id = String(row.id || "");
      if (!id || nodes.has(id)) continue;

      nodes.set(id, {
        ...row,
        id,
        parent: String(row.parent || ""),
        workspace: String(row.workspace || "")
      });
    }

    function safe(node) {
      const visited = new Set();
      let current = node;

      while (current) {
        if (visited.has(current.id)) return false;
        visited.add(current.id);

        if (!current.parent) return true;

        const parent = nodes.get(current.parent);
        if (!parent) return false;

        if (parent.workspace !== node.workspace) {
          return false;
        }

        current = parent;
      }

      return true;
    }

    return [...nodes.values()].filter(safe);
  }

  if (typeof window !== "undefined") {
    window.B3StorageV814 = {buildModel};
  }

  if (typeof document === "undefined") return;

  function initialize() {
    const root = document.getElementById("b3-storage-v814");
    if (!root) return;

    const find = id => document.getElementById(id);
    const locSource = find("b3s-location-data");
    const sampleSource = find("b3s-sample-data");

    if (!locSource?.content || !sampleSource?.content) {
      return;
    }

    // The Django projection contains only visible historical
    // records. Never create physical StorageLocations from it.
    const legacySource = find("b3s-legacy-data");
    let legacyProjection = {nodes: [], samples: []};

    if (legacySource) {
      try {
        const parsed = JSON.parse(legacySource.textContent);

        if (
          !Array.isArray(parsed.nodes) ||
          !Array.isArray(parsed.samples)
        ) {
          throw new Error("Invalid historical projection");
        }

        legacyProjection = parsed;
      } catch (error) {
        console.error(
          "Historical storage projection unavailable",
          error
        );
      }
    }

    const physicalNodes = [
      ...locSource.content.querySelectorAll("[data-id]")
    ].map(el => ({...el.dataset}));

    const historicalNodes = legacyProjection.nodes
      .filter(row => row && row.id != null)
      .map(row => ({
        id: "h:" + String(row.id),
        parent: row.parent == null || row.parent === ""
          ? ""
          : "h:" + String(row.parent),
        workspace: "",
        name: String(row.name || "Historical location"),
        type: String(row.kind || row.type || "historical"),
        path: String(row.path || row.name || ""),
        active: "0",
        historical: true
      }));

    const nodes = buildModel([
      ...physicalNodes,
      ...historicalNodes
    ]);

    const samples = [
      ...sampleSource.content.querySelectorAll("[data-id]")
    ].map(el => ({...el.dataset}));

    const legacySamples = legacyProjection.samples.map(row => ({
      location: "h:" + String(
        row.box || row.location || ""
      ),
      sample: String(row.code || "Sample"),
      position: String(row.position || ""),
      url: String(row.url || "")
    }));

    const historicalIds = new Set(
      nodes.filter(node => node.historical).map(node => node.id)
    );

    const visibleLegacySamples = legacySamples.filter(
      row => historicalIds.has(row.location)
    );

    const byId = new Map(
      nodes.map(node => [node.id, node])
    );

    const children = new Map();

    for (const node of nodes) {
      const parent = node.parent || "";

      if (!children.has(parent)) {
        children.set(parent, []);
      }

      children.get(parent).push(node);
    }

    const compare = (a, b) =>
      a.name.localeCompare(b.name, undefined, {
        numeric: true,
        sensitivity: "base"
      });

    for (const list of children.values()) {
      list.sort(compare);
    }

    const mk = (tag, value, className) => {
      const el = document.createElement(tag);
      if (value != null) el.textContent = value;
      if (className) el.className = className;
      return el;
    };

    let selected = "";
    let workspace = "";
    let query = "";

    function pathFor(node) {
      const parts = [];
      const seen = new Set();

      while (node && !seen.has(node.id)) {
        seen.add(node.id);
        parts.unshift(node.name);
        node = byId.get(node.parent);
      }

      return parts.join(" › ");
    }

    function matches(node) {
      if (workspace && node.workspace !== workspace) {
        return false;
      }

      if (!query) return true;

      const text = [
        node.name,
        node.type,
        node.path,
        ...samples
          .filter(item => item.location === node.id)
          .map(item => item.sample),
        ...visibleLegacySamples
          .filter(item => item.location === node.id)
          .map(item => item.sample)
      ].join(" ").toLowerCase();

      return text.includes(query);
    }

    function visibleNodes() {
      if (!query) {
        return nodes.filter(node =>
          !workspace || node.workspace === workspace
        );
      }

      const accepted = new Set();

      for (const node of nodes.filter(matches)) {
        let current = node;
        const visited = new Set();

        while (current && !visited.has(current.id)) {
          visited.add(current.id);
          accepted.add(current.id);
          current = byId.get(current.parent);
        }
      }

      return nodes.filter(node =>
        accepted.has(node.id) &&
        (!workspace || node.workspace === workspace)
      );
    }

    function choose(id) {
      selected = id;
      render();
    }

    function renderTree() {
      const container = find("b3s-tree");
      container.replaceChildren();

      const visible = visibleNodes();
      const visibleIds = new Set(visible.map(n => n.id));

      const walk = (parentId, depth) => {
        for (const node of children.get(parentId) || []) {
          if (!visibleIds.has(node.id)) continue;

          const button = mk(
            "button",
            node.name,
            "b3s-node"
          );

          button.type = "button";
          button.style.paddingLeft =
            `${9 + depth * 15}px`;

          if (node.id === selected) {
            button.classList.add("is-selected");
          }

          if (node.historical) {
            button.classList.add("is-historical");
          }

          button.addEventListener(
            "click",
            () => choose(node.id)
          );

          container.append(button);
          walk(node.id, depth + 1);
        }
      };

      walk("", 0);
      find("b3s-count").textContent =
        String(visible.length);
    }

    function renderContents() {
      const node = byId.get(selected);
      const direct = samples.filter(sample =>
        node
          ? sample.location === node.id
          : !workspace ||
            byId.get(sample.location)?.workspace === workspace
      );

      find("b3s-title").textContent = node
        ? node.name
        : "All storage locations";

      find("b3s-type").textContent = node
        ? node.type.toUpperCase()
        : "OVERVIEW";

      find("b3s-breadcrumb").textContent = node
        ? pathFor(node)
        : "All authorized locations";

      find("b3s-metadata").textContent = node
        ? node.historical
          ? "Historical registration · Read-only"
          : `${node.active === "1" ? "Active" : "Inactive"} · ` +
            `${node.workspace ? "Registered workspace" : "Unscoped"}`
        : `${nodes.length} visible location records`;

      const descendants = node
        ? children.get(node.id) || []
        : children.get("") || [];

      const host = find("b3s-children");
      host.replaceChildren();

      for (const child of descendants) {
        if (workspace && child.workspace !== workspace) {
          continue;
        }

        const button = mk(
          "button", null, "b3s-child"
        );

        button.type = "button";
        button.append(
          mk("strong", child.name),
          mk("div", child.type)
        );

        button.addEventListener(
          "click", () => choose(child.id)
        );

        host.append(button);
      }

      if (!host.children.length) {
        host.append(
          mk("p", "No child locations.", "b3s-note")
        );
      }

      const records = find("b3s-assignments");
      records.replaceChildren();

      for (const item of direct) {
        const line = mk("div", null, "b3s-record");
        const link = mk("a", item.sample);

        link.href = item.url;

        line.append(
          link,
          mk(
            "span",
            item.position
              ? `Position: ${item.position}`
              : "Position not recorded"
          )
        );

        records.append(line);
      }

      if (!records.children.length) {
        records.append(
          mk(
            "p",
            "No recorded Samples at this level.",
            "b3s-note"
          )
        );
      }
    }

    function renderGraph() {
      const target = find("b3s-graph");
      target.replaceChildren();

      const visible = visibleNodes().slice(0, 120);
      const ids = new Set(visible.map(n => n.id));

      const positioned = [];
      const seen = new Set();

      function walk(parent, depth) {
        for (const node of children.get(parent) || []) {
          if (!ids.has(node.id) || seen.has(node.id)) {
            continue;
          }

          seen.add(node.id);

          positioned.push({
            node,
            depth,
            row: positioned.length
          });

          walk(node.id, depth + 1);
        }
      }

      walk("", 0);

      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");

      const width = Math.max(
        650,
        ...positioned.map(p => p.depth * 205 + 205)
      );

      const height = Math.max(
        240,
        positioned.length * 66 + 25
      );

      svg.setAttribute(
        "viewBox", `0 0 ${width} ${height}`
      );

      svg.setAttribute("width", width);
      svg.setAttribute("height", height);
      svg.setAttribute(
        "aria-label", "Storage path tree"
      );

      const sv = (name, attrs) => {
        const el = document.createElementNS(ns, name);

        for (const [key, value] of Object.entries(attrs)) {
          el.setAttribute(key, String(value));
        }

        return el;
      };

      const layout = new Map(
        positioned.map(p => [p.node.id, p])
      );

      for (const p of positioned) {
        const parent = layout.get(p.node.parent);
        if (!parent) continue;

        const x1 = parent.depth * 205 + 190;
        const y1 = parent.row * 66 + 42;
        const x2 = p.depth * 205 + 10;
        const y2 = p.row * 66 + 42;

        const mid = (x1 + x2) / 2;

        svg.append(
          sv("path", {
            d: `M${x1} ${y1} H${mid} V${y2} H${x2}`,
            fill: "none",
            stroke: "#a9bfd2",
            "stroke-width": "1.5"
          })
        );
      }

      for (const p of positioned) {
        const g = sv("g", {
          tabindex: "0",
          role: "button"
        });

        const x = p.depth * 205 + 10;
        const y = p.row * 66 + 12;

        g.append(
          sv("rect", {
            x, y, width: 180, height: 50,
            rx: 6,
            fill: selected === p.node.id
              ? "#eaf2ff"
              : "#ffffff",
            stroke: selected === p.node.id
              ? "#146cff"
              : "#c9d8e3"
          })
        );

        const label = sv("text", {
          x: x + 9,
          y: y + 29,
          "font-size": 11,
          fill: "#243747"
        });

        label.textContent =
          p.node.name.length > 23
            ? p.node.name.slice(0, 22) + "…"
            : p.node.name;

        const title = sv("title");
        title.textContent = pathFor(p.node);

        g.append(label, title);

        g.addEventListener(
          "click", () => choose(p.node.id)
        );

        g.addEventListener("keydown", event => {
          if (
            event.key === "Enter" ||
            event.key === " "
          ) {
            event.preventDefault();
            choose(p.node.id);
          }
        });

        svg.append(g);
      }

      target.append(svg);
    }

    function renderLegacy() {
      const host = find("b3s-legacy");
      host.replaceChildren();

      const node = byId.get(selected);

      const rows = visibleLegacySamples.filter(row =>
        node
          ? row.location === node.id
          : !workspace
      );

      if (!rows.length) {
        host.append(mk(
          "p",
          "No historical registrations at this level.",
          "b3s-note"
        ));
        return;
      }

      host.append(mk(
        "p",
        `${rows.length} historical Sample registrations. ` +
        "These records cannot be used as movement destinations.",
        "b3s-note"
      ));

      for (const row of rows.slice(0, 150)) {
        const line = mk("div", null, "b3s-record");

        line.append(
          mk("strong", row.sample),
          mk(
            "span",
            row.position
              ? `Recorded position: ${row.position}`
              : "Position not recorded"
          )
        );

        host.append(line);
      }

      if (rows.length > 150) {
        host.append(mk(
          "p",
          "Additional historical records are not shown here.",
          "b3s-note"
        ));
      }
    }

    function render() {
      renderTree();
      renderContents();
      renderLegacy();
      renderGraph();
    }

    for (const button of root.querySelectorAll(
      "[data-b3s-tab]"
    )) {
      button.addEventListener("click", () => {
        const tab = button.dataset.b3sTab;

        for (const other of root.querySelectorAll(
          "[data-b3s-tab]"
        )) {
          other.setAttribute(
            "aria-selected",
            String(other === button)
          );
        }

        for (const [name, id] of [
          ["contents", "b3s-contents"],
          ["tree", "b3s-path-tree"],
          ["movements", "b3s-movements"],
          ["manage", "b3s-manage"]
        ]) {
          const section = find(id);
          if (section) {
            section.hidden = name !== tab;
          }
        }
      });
    }

    find("b3s-search").addEventListener(
      "input", event => {
        query = event.target.value.trim().toLowerCase();
        render();
      }
    );

    find("b3s-workspace-filter").addEventListener(
      "change", event => {
        workspace = event.target.value;
        selected = "";
        render();
      }
    );

    const newLocation = find("b3s-new-location");

    if (newLocation) {
      newLocation.addEventListener("click", () => {
        root.querySelector(
          '[data-b3s-tab="manage"]'
        )?.click();

        const node = byId.get(selected);
        const workspaceSelect =
          find("b3s-create-workspace");
        const parentSelect =
          find("b3s-create-parent");

        if (node && node.workspace) {
          workspaceSelect.value = node.workspace;
        }

        workspaceSelect.dispatchEvent(
          new Event("change")
        );

        if (node && node.active === "1") {
          parentSelect.value = node.id;
        }
      });
    }

    const createWorkspace = find("b3s-create-workspace");
    const createParent = find("b3s-create-parent");

    if (createWorkspace && createParent) {
      createWorkspace.addEventListener(
        "change", () => {
          const selectedWorkspace = createWorkspace.value;

          for (const option of createParent.options) {
            if (!option.value) {
              option.hidden = false;
              continue;
            }

            option.hidden =
              option.dataset.workspace !== selectedWorkspace;
          }

          createParent.value = "";
        }
      );

      createWorkspace.dispatchEvent(
        new Event("change")
      );
    }

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded", initialize, {once: true}
    );
  } else {
    initialize();
  }
})();
