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

  // Canonical slot name ("A1") when `position` is a cell of a
  // rows x columns grid, otherwise "". Same naming as the position map.
  function gridSlot(position, rows, columns) {
    const match = /^([A-Z])0*([1-9][0-9]*)$/.exec(
      String(position || "").trim().toUpperCase()
    );
    if (!match) return "";
    const row = match[1].charCodeAt(0) - 65;
    const column = Number(match[2]) - 1;
    if (row >= rows || column >= columns) return "";
    return match[1] + (column + 1);
  }

  // Occupancy of one location from its own assignments.
  // used: distinct grid cells recorded; offGrid: samples of a grid
  // location whose position is blank or not a cell of that grid.
  function gridUsage(rows, columns, positions) {
    const cells = new Set();
    let offGrid = 0;
    for (const position of positions) {
      const slot = gridSlot(position, rows, columns);
      if (slot) cells.add(slot);
      else offGrid += 1;
    }
    return {used: cells.size, offGrid};
  }

  if (typeof window !== "undefined") {
    window.B3StorageV814 = {buildModel, gridSlot, gridUsage};
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {buildModel, gridSlot, gridUsage};
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
    let workspace =
      find("b3s-workspace-filter")?.value || "";
    let query = "";
    const collapsedLocations = new Set();

    function displayName(node) {
      const name = String(node.name || "");

      return node.historical
        ? name.replace(/\s*[·-]\s*historical\s*$/i, "")
        : name;
    }

    function pathFor(node) {
      const parts = [];
      const seen = new Set();

      while (node && !seen.has(node.id)) {
        seen.add(node.id);
        parts.unshift(displayName(node));
        node = byId.get(node.parent);
      }

      return parts.join(" › ");
    }

    // V8.14.7 — summaries used by cards, tree and move mode.
    const TYPE_LABELS = {
      room: "Room",
      freezer: "Freezer",
      shelf: "Shelf",
      rack: "Rack",
      box: "Box",
      position: "Position",
      other: "Other",
      historical: "Historical"
    };

    function typeLabel(node) {
      if (!node) return "";
      return node.c3Type ||
        TYPE_LABELS[node.type] ||
        String(node.type || "");
    }

    function ancestorsOf(node) {
      const result = [];
      const seen = new Set();
      let current = node ? byId.get(node.parent) : null;

      while (current && !seen.has(current.id)) {
        seen.add(current.id);
        result.unshift(current);
        current = byId.get(current.parent);
      }

      return result;
    }

    function subtreeIds(node) {
      const found = new Set();
      const stack = node ? [node.id] : [];

      while (stack.length) {
        const id = stack.pop();
        if (found.has(id)) continue;
        found.add(id);

        for (const child of children.get(id) || []) {
          stack.push(child.id);
        }
      }

      return found;
    }

    const directSampleCount = new Map();

    for (const item of [...samples, ...visibleLegacySamples]) {
      directSampleCount.set(
        item.location,
        (directSampleCount.get(item.location) || 0) + 1
      );
    }

    // Named compartments (doors, drawers, shelves) of a location.
    function slotLabels(node) {
      if (!node || node.c3Organization !== "slots") return [];

      try {
        const labels = JSON.parse(node.c3Slots || "[]");
        return Array.isArray(labels) ? labels.map(String) : [];
      } catch (error) {
        return [];
      }
    }

    function slotName(node, position) {
      const text = String(position || "").trim().toLowerCase();
      return slotLabels(node).find(name => name.toLowerCase() === text) || "";
    }

    function gridCapacity(node) {
      if (node && node.c3Organization === "slots") {
        return slotLabels(node).length;
      }

      if (!node || node.c3Organization !== "grid") return 0;

      const rows = Number(node.c3Rows);
      const columns = Number(node.c3Columns);

      return Number.isInteger(rows) && Number.isInteger(columns)
        ? rows * columns
        : 0;
    }

    function gridRows(node) {
      return Number(node.c3Rows);
    }

    function gridColumns(node) {
      return Number(node.c3Columns);
    }

    function usageOf(node) {
      const positions = [];

      for (const item of samples) {
        if (item.location === node.id) positions.push(item.position);
      }

      if (node.c3Organization === "slots") {
        const used = new Set();
        let offGrid = 0;

        for (const position of positions) {
          const name = slotName(node, position);
          if (name) used.add(name);
          else offGrid += 1;
        }

        return {used: used.size, offGrid};
      }

      return window.B3StorageV814.gridUsage(
        gridRows(node),
        gridColumns(node),
        positions
      );
    }

    const summaryCache = new Map();

    // One occupancy rule for the tree, cards and stats:
    // capacity/used only count grid locations (capacity = cells, used =
    // distinct valid cells recorded). Samples in locations without a grid
    // are counted as samples only (untracked), samples of a grid location
    // that are not on the grid are offGrid.
    function summary(node) {
      if (!node) {
        return {
          samples: 0, locations: 0, capacity: 0, used: 0,
          offGrid: 0, untracked: 0
        };
      }
      if (summaryCache.has(node.id)) return summaryCache.get(node.id);

      const result = {
        samples: 0, locations: -1, capacity: 0, used: 0,
        offGrid: 0, untracked: 0
      };

      for (const id of subtreeIds(node)) {
        const item = byId.get(id);
        const direct = directSampleCount.get(id) || 0;
        result.locations += 1;
        result.samples += direct;

        const capacity = gridCapacity(item);

        if (capacity) {
          const usage = usageOf(item);
          result.capacity += capacity;
          result.used += usage.used;
          result.offGrid += usage.offGrid;
        } else {
          result.untracked += direct;
        }
      }

      summaryCache.set(node.id, result);
      return result;
    }

    function plural(count, word) {
      return `${count} ${word}${count === 1 ? "" : "s"}`;
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
      const ids = new Set(visible.map(item => item.id));

      const roots = visible.filter(item =>
        !item.parent || !ids.has(item.parent)
      );

      function branch(node, visited) {
        if (visited.has(node.id)) return null;

        const nextVisited = new Set(visited);
        nextVisited.add(node.id);

        const li = mk("li", null, "b3s-branch");
        const line = mk("div", null, "b3s-tree-line");

        const descendants = (
          children.get(node.id) || []
        ).filter(item => ids.has(item.id));

        const hasChildren = descendants.length > 0;

        const expanded =
          hasChildren && (
            query || !collapsedLocations.has(node.id)
          );

        if (hasChildren) {
          const toggle = mk(
            "button",
            expanded ? "▾" : "▸",
            "b3s-tree-toggle"
          );

          toggle.type = "button";
          toggle.setAttribute(
            "aria-label",
            (expanded ? "Collapse " : "Expand ") +
              displayName(node)
          );
          toggle.setAttribute(
            "aria-expanded",
            String(Boolean(expanded))
          );

          toggle.addEventListener("click", () => {
            if (collapsedLocations.has(node.id)) {
              collapsedLocations.delete(node.id);
            } else {
              collapsedLocations.add(node.id);
            }
            renderTree();
          });

          line.append(toggle);
        } else {
          line.append(mk(
            "span", "", "b3s-tree-toggle-placeholder"
          ));
        }

        const button = mk(
          "button",
          null,
          "b3s-node"
        );

        button.type = "button";
        button.title = pathFor(node);

        if (node.id === selected) {
          button.classList.add("is-selected");
        }

        if (node.historical) {
          button.classList.add("is-historical");
        }

        button.append(
          mk("span", displayName(node), "b3s-node-label")
        );

        if (node.historical) {
          button.append(
            mk("small", "Historical", "b3s-node-status")
          );
        }

        const treeCount = summary(node).samples;

        if (treeCount) {
          const badge = mk("small", String(treeCount), "b3s-node-count");
          badge.title = plural(treeCount, "Sample") + " inside";
          button.append(badge);
        }

        // Selecting a location always reveals its children.
        // Collapsing is done only with the arrow toggle.
        button.addEventListener("click", () => {
          collapsedLocations.delete(node.id);
          choose(node.id);
        });

        line.append(button);
        li.append(line);

        if (hasChildren && expanded) {
          const nested = mk(
            "ul", null, "b3s-branches"
          );

          for (const child of descendants) {
            const element = branch(child, nextVisited);
            if (element) nested.append(element);
          }

          li.append(nested);
        }

        return li;
      }

      const list = mk(
        "ul", null, "b3s-branches b3s-tree-root"
      );

      for (const node of roots) {
        const element = branch(node, new Set());
        if (element) list.append(element);
      }

      container.append(list);

      find("b3s-count").textContent =
        String(visible.length);
    }

    function renderContents() {
      const node = byId.get(selected);

      // Notify optional, read-only position visualizations.
      // The microtask runs after synchronous content rendering.
      queueMicrotask(() => {
        document.dispatchEvent(
          new CustomEvent(
            "b3:storage-v814-contents-rendered",
            {
              detail: {
                locationId: node ? node.id : ""
              }
            }
          )
        );
      });
      const direct = samples.filter(sample =>
        node
          ? sample.location === node.id
          : !workspace ||
            byId.get(sample.location)?.workspace === workspace
      );

      find("b3s-title").textContent = node
        ? displayName(node)
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

      if (node && node.c3Type) {
        find("b3s-type").textContent =
          `${node.type.toUpperCase()} · ${node.c3Type}`;
      }

      renderStats(node);
      renderHeadActions(node);

      const descendants = node
        ? children.get(node.id) || []
        : children.get("") || [];

      const host = find("b3s-children");
      host.replaceChildren();

      for (const child of descendants) {
        if (workspace && child.workspace !== workspace) {
          continue;
        }

        host.append(childCard(child));
      }

      if (!host.children.length) {
        host.append(
          mk("p", "No child locations.", "b3s-note")
        );
      }

      const records = find("b3s-assignments");
      records.replaceChildren();

      // In a configured grid the position map is the main view;
      // the full list stays available but collapsed.
      let listHost = records;

      if (node && gridCapacity(node) && direct.length) {
        const details = mk("details", null, "b3s-record-list");
        details.append(
          mk(
            "summary",
            `Show the list of ${plural(direct.length, "recorded Sample")}`
          )
        );
        records.append(details);
        listHost = details;
      }

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

        listHost.append(line);
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


    // Small tiles for what a location holds (shelves in a freezer,
    // boxes in a rack...), coloured by how full each one is, so a level
    // is seen as a picture and not only as a number.
    const TILE_LIMIT = 16;

    function tileState(node) {
      const info = summary(node);
      if (!info.samples) return "is-empty";
      if (info.capacity && info.untracked === 0) {
        return info.used / info.capacity >= 0.9 ? "is-full" : "is-partial";
      }
      return "is-partial";
    }

    function childTiles(child) {
      const kids = (children.get(child.id) || []).filter(
        item => !item.historical
      );
      if (!kids.length) return null;

      const row = mk("div", null, "b3s-tiles");
      row.setAttribute("aria-hidden", "true");

      for (const kid of kids.slice(0, TILE_LIMIT)) {
        const info = summary(kid);
        const tile = mk("i", null, `b3s-tile ${tileState(kid)}`);
        tile.title = `${displayName(kid)} · ${plural(info.samples, "Sample")}`;
        row.append(tile);
      }

      if (kids.length > TILE_LIMIT) {
        row.append(mk("em", `+${kids.length - TILE_LIMIT}`, "b3s-tile-more"));
      }

      return row;
    }

    function childCard(child) {
      const info = summary(child);
      const button = mk("button", null, "b3s-child");

      button.type = "button";
      button.title = pathFor(child);

      if (child.historical) button.classList.add("is-historical");
      if (child.active === "0" && !child.historical) {
        button.classList.add("is-inactive");
      }

      const top = mk("div", null, "b3s-child-top");
      top.append(
        mk("span", typeLabel(child), "b3s-chip"),
        child.c3Temperature
          ? mk("span", child.c3Temperature, "b3s-temp")
          : mk("span", "")
      );

      button.append(top, mk("strong", displayName(child)));

      if (info.capacity) {
        const bar = mk("div", null, "b3s-bar");
        const fill = mk("i");
        const ratio = info.used / info.capacity;

        fill.style.width = `${Math.round(ratio * 100)}%`;
        if (ratio >= 0.9) bar.classList.add("is-full");
        bar.append(fill);
        bar.setAttribute("role", "img");
        bar.setAttribute(
          "aria-label",
          `${info.used} of ${info.capacity} grid positions recorded as occupied`
        );

        const parts = [
          `${info.used}/${info.capacity} grid positions`,
          plural(info.samples, "Sample")
        ];
        if (info.untracked) parts.push(`${info.untracked} outside a grid`);
        if (info.offGrid) parts.push(`${info.offGrid} off the grid`);

        button.append(
          bar,
          mk("small", parts.join(" · "), "b3s-child-meta")
        );
      } else {
        const parts = [plural(info.samples, "Sample")];
        if (info.locations > 0) {
          parts.push(plural(info.locations, "location") + " inside");
        }
        button.append(mk("small", parts.join(" · "), "b3s-child-meta"));
      }

      const tiles = childTiles(child);
      if (tiles) button.append(tiles);

      button.addEventListener("click", () => choose(child.id));
      return button;
    }

    function renderStats(node) {
      const host = find("b3s-stats");
      if (!host) return;
      host.replaceChildren();

      const add = (label, value) => {
        const item = mk("div", null, "b3s-stat");
        item.append(mk("dt", label), mk("dd", value));
        host.append(item);
      };

      if (!node) {
        const roots = (children.get("") || []).filter(item =>
          !workspace || item.workspace === workspace
        );
        let total = 0;
        for (const item of roots) total += summary(item).samples;
        add("Root locations", String(roots.length));
        add("Samples recorded", String(total));
        return;
      }

      const info = summary(node);
      add("Samples inside", String(info.samples));
      add("Locations inside", String(Math.max(0, info.locations)));

      if (gridCapacity(node)) {
        add("Grid", `${node.c3Rows} × ${node.c3Columns}`);
      }

      if (info.capacity) {
        add(
          "Grid occupancy",
          `${Math.round((info.used / info.capacity) * 100)}%`
        );
      }

      if (info.capacity && info.untracked) {
        add("Outside a grid", String(info.untracked));
      }

      if (info.offGrid) add("Off the grid", String(info.offGrid));

      if (node.c3Temperature) add("Temperature", node.c3Temperature);
      add("Path depth", String(ancestorsOf(node).length + 1));
    }

    function renderHeadActions(node) {
      const host = find("b3s-head-actions");
      if (!host) return;
      host.replaceChildren();

      if (!node) return;

      const tree = mk(
        "button",
        "Show in path tree",
        "btn btn-sm btn-outline-secondary"
      );
      tree.type = "button";
      tree.addEventListener("click", () => showTab("tree"));
      host.append(tree);

      if (movable(node)) {
        const move = mk(
          "button",
          "Move this location",
          "btn btn-sm btn-outline-primary"
        );
        move.type = "button";
        move.addEventListener("click", () => beginMove(node));
        host.append(move);
      }
    }

    // ---------------------------------------------------------
    // V8.14.7 — Path tree drawn by level, with move selection.
    // The browser only proposes a destination. The server
    // preview (?preview_container=1) validates, authorizes and
    // renders the confirmation form.
    // ---------------------------------------------------------

    let moveState = null;

    function movable(node) {
      return Boolean(
        node &&
        manageable(node) &&
        node.active === "1" &&
        node.type !== "room" &&
        node.type !== "position"
      );
    }

    function destinationProblem(container, target) {
      if (!target) return "Choose a location.";
      if (target.historical) return "Historical records are read-only.";
      if (target.active !== "1") return "Inactive location.";
      if (!manageable(target)) return "You cannot manage this location.";
      if (target.type === "position") {
        return "A position cannot hold a container.";
      }
      if (subtreeIds(container).has(target.id)) {
        return "Cannot move inside itself.";
      }
      if (target.id === container.parent) {
        return "Already here.";
      }

      const lowered = String(container.name).toLowerCase();
      const clash = (children.get(target.id) || []).some(item =>
        item.id !== container.id &&
        String(item.name).toLowerCase() === lowered
      );

      return clash ? "A location with this name already exists there." : "";
    }

    function pickUrl(params, hash) {
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = hash;
      for (const [key, value] of params) url.searchParams.append(key, value);
      return url.toString();
    }

    // Move a location, with everything inside it, to a place chosen on
    // the drawing. The server preview checks it again before any change.
    function beginMove(node) {
      if (!movable(node)) return;

      if (window.B3StoragePicker) {
        const inside = summary(node).samples;
        window.B3StoragePicker.open({
          title: `Move ${displayName(node)}`,
          mode: "node",
          workspaceRoots: true,
          exclude: node.id,
          confirmLabel: "Preview move",
          onPick: result => {
            window.location.href = previewUrl(node.id, result.id);
          }
        });
        return;
      }

      moveState = {id: node.id, destination: ""};
      selected = node.id;
      showTab("tree");
      render();
    }

    function cancelMove() {
      moveState = null;
      render();
    }

    function previewUrl(containerId, destinationId) {
      const url = new URL(window.location.href);
      url.search = "";
      url.hash = "storage-container-preview";
      url.searchParams.set("preview_container", "1");
      url.searchParams.set("container_id", containerId);
      url.searchParams.set("destination_id", destinationId);
      return url.toString();
    }

    function renderLegend() {
      const host = find("b3s-tree-legend");
      if (!host) return;
      host.replaceChildren();

      const items = moveState
        ? [
            ["is-moving", "Moves together"],
            ["is-destination", "Destination"],
            ["is-blocked", "Cannot receive"]
          ]
        : [
            ["is-path", "Path to selected location"],
            ["", "Other locations"],
            ["is-historical", "Historical (read-only)"]
          ];

      for (const [className, label] of items) {
        const item = mk("span", null, "b3s-legend-item");
        item.append(mk("i", null, "b3s-swatch " + className), label);
        host.append(item);
      }
    }

    function renderPathPanel() {
      const host = find("b3s-path-panel");
      if (!host) return;
      host.replaceChildren();

      if (moveState) {
        const container = byId.get(moveState.id);

        if (!container) {
          moveState = null;
          return renderPathPanel();
        }

        const info = summary(container);

        host.append(
          mk("h4", "Moving " + typeLabel(container).toLowerCase()),
          mk("p", displayName(container), "b3s-panel-title"),
          mk(
            "p",
            `Carries ${plural(Math.max(0, info.locations), "location")} ` +
              `and ${plural(info.samples, "Sample")} with it.`,
            "b3s-note"
          )
        );

        const before = mk("div", null, "b3s-compare is-before");
        before.append(mk("b", "Before"), mk("span", pathFor(container)));
        host.append(before);

        const target = byId.get(moveState.destination);

        if (!target) {
          host.append(
            mk(
              "p",
              "Click the new parent in the tree. Faded locations " +
                "cannot receive this item.",
              "b3s-note"
            )
          );
        } else {
          const after = mk("div", null, "b3s-compare is-after");
          after.append(
            mk("b", "After"),
            mk("span", `${pathFor(target)} › ${displayName(container)}`)
          );
          host.append(
            after,
            mk(
              "p",
              "The server checks this move again and asks for a " +
                "reason before anything changes.",
              "b3s-note"
            )
          );

          const go = mk(
            "a",
            "Review and confirm",
            "btn btn-sm btn-primary"
          );
          go.href = previewUrl(container.id, target.id);
          host.append(go);
        }

        const cancel = mk(
          "button",
          "Cancel move",
          "btn btn-sm btn-outline-secondary"
        );
        cancel.type = "button";
        cancel.addEventListener("click", cancelMove);
        host.append(cancel);
        return;
      }

      const node = byId.get(selected);

      if (!node) {
        host.append(
          mk("h4", "Path to the root"),
          mk(
            "p",
            "Select any location to see its full path and " +
              "everything that depends on it.",
            "b3s-note"
          )
        );
        return;
      }

      host.append(mk("h4", "Path to the root"));

      const list = mk("ol", null, "b3s-levels");
      const chain = [...ancestorsOf(node), node];

      chain.forEach((item, index) => {
        const li = mk("li", null, item.id === node.id ? "is-current" : "");
        const link = mk("button", displayName(item), "b3s-level-link");
        link.type = "button";
        link.addEventListener("click", () => choose(item.id));
        li.append(mk("span", typeLabel(item) || `Level ${index + 1}`, "b3s-level-no"), link);
        list.append(li);
      });

      host.append(list);

      const info = summary(node);
      host.append(
        mk(
          "p",
          `${plural(Math.max(0, info.locations), "location")} and ` +
            `${plural(info.samples, "Sample")} depend on this level. ` +
            "Moving it updates all of their addresses at once.",
          "b3s-note"
        )
      );

      const actions = mk("div", null, "b3s-manage-actions");
      const open = mk("button", "Open contents", "btn btn-sm btn-outline-secondary");
      open.type = "button";
      open.addEventListener("click", () => showTab("contents"));
      actions.append(open);

      if (movable(node)) {
        const move = mk("button", "Move this location", "btn btn-sm btn-primary");
        move.type = "button";
        move.addEventListener("click", () => beginMove(node));
        actions.append(move);
      }

      host.append(actions);
    }

    const SVG_NS = "http://www.w3.org/2000/svg";

    function svg(tag, attributes, text) {
      const el = document.createElementNS(SVG_NS, tag);
      for (const [key, value] of Object.entries(attributes || {})) {
        el.setAttribute(key, String(value));
      }
      if (text != null) el.textContent = text;
      return el;
    }

    function clip(text, size) {
      const value = String(text || "");
      return value.length > size ? value.slice(0, size - 1) + "…" : value;
    }

    const GRAPH_LIMIT = 400;

    function renderGraph() {
      const target = find("b3s-graph");
      target.replaceChildren();
      target.scrollLeft = 0;
      renderLegend();
      renderPathPanel();

      const visible = visibleNodes();

      if (!visible.length) {
        target.append(
          mk("p", "No locations available for this view.", "b3s-note")
        );
        return;
      }

      if (visible.length > GRAPH_LIMIT) {
        target.append(
          mk(
            "p",
            `${visible.length} locations: showing the list view. ` +
              "Filter by workspace or search to see the diagram.",
            "b3s-note"
          )
        );
        renderGraphList(target, visible);
        return;
      }

      const ids = new Set(visible.map(item => item.id));
      const ROOT = "__root__";
      const H = 52;
      const ROW = 64;
      const PAD_X = 14;
      const PAD_Y = 34;
      let W = 184;
      let COLUMN = 226;

      const kidsOf = id => (
        id === ROOT
          ? visible.filter(item => !item.parent || !ids.has(item.parent))
          : (children.get(id) || []).filter(item => ids.has(item.id))
      );

      const place = new Map();
      let leaf = 0;
      let depthMax = 0;

      (function walk(id, depth, seen) {
        if (seen.has(id)) return 0;
        const nextSeen = new Set(seen).add(id);
        const kids = kidsOf(id);
        let y;

        if (!kids.length) {
          y = leaf++;
        } else {
          const ys = kids.map(child => walk(child.id, depth + 1, nextSeen));
          y = (ys[0] + ys[ys.length - 1]) / 2;
        }

        place.set(id, {x: depth * COLUMN + PAD_X, y: y * ROW + PAD_Y, depth});
        depthMax = Math.max(depthMax, depth);
        return y;
      })(ROOT, 0, new Set());

      // Fit all levels in the frame when they can be made narrower
      // (down to ~60%); beyond that the diagram scrolls.
      const available = (target.clientWidth || 880) - 44;
      const natural = depthMax * COLUMN + W + PAD_X * 2;
      if (natural > available) {
        const scale = Math.max(available / natural, 0.6);
        W = Math.round(W * scale);
        COLUMN = Math.round(COLUMN * scale);
        for (const point of place.values()) {
          point.x = point.depth * COLUMN + PAD_X;
        }
      }

      const width = depthMax * COLUMN + W + PAD_X * 2;
      const height = Math.max(leaf, 1) * ROW + PAD_Y + 6;

      const selectedNode = byId.get(selected);
      const pathIds = new Set([ROOT]);
      if (selectedNode) {
        for (const item of [...ancestorsOf(selectedNode), selectedNode]) {
          pathIds.add(item.id);
        }
      }

      const container = moveState ? byId.get(moveState.id) : null;
      const moving = container ? subtreeIds(container) : new Set();
      const destinationIds = new Set();

      if (container && moveState.destination) {
        const destination = byId.get(moveState.destination);
        if (destination) {
          destinationIds.add(ROOT);
          for (const item of [...ancestorsOf(destination), destination]) {
            destinationIds.add(item.id);
          }
        }
      }

      const drawing = svg("svg", {
        width,
        height,
        viewBox: `0 0 ${width} ${height}`,
        role: "group",
        "aria-label": "Storage path tree by level",
        class: "b3s-svg-tree"
      });

      // Column title: the most common location type at that depth
      // (Freezer, Shelf, Box...), so a level reads as what it holds.
      const typesAt = new Map();
      for (const [id, point] of place) {
        if (id === ROOT) continue;
        const counts = typesAt.get(point.depth) || new Map();
        const label = typeLabel(byId.get(id));
        counts.set(label, (counts.get(label) || 0) + 1);
        typesAt.set(point.depth, counts);
      }

      const levelTitle = depth => {
        const counts = typesAt.get(depth);
        if (!counts) return `Level ${depth}`;
        const [top] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
        return `${top}${counts.size > 1 ? " and others" : ""}`;
      };

      for (let depth = 0; depth <= depthMax; depth++) {
        drawing.append(
          svg(
            "text",
            {x: depth * COLUMN + PAD_X, y: 18, class: "b3s-level-label"},
            depth === 0 ? "Storage" : levelTitle(depth)
          )
        );
      }

      const edges = svg("g", {class: "b3s-edges"});
      const shapes = svg("g", {class: "b3s-nodes"});
      drawing.append(edges, shapes);

      for (const [id, point] of place) {
        if (id === ROOT) continue;
        const node = byId.get(id);
        const parentId = node.parent && ids.has(node.parent) ? node.parent : ROOT;
        const from = place.get(parentId);
        if (!from) continue;

        let className = "b3s-edge";
        if (moving.has(id) && id !== moveState?.id) className += " is-moving";
        else if (!moveState && pathIds.has(id) && pathIds.has(parentId)) {
          className += " is-path";
        } else if (destinationIds.has(id) && destinationIds.has(parentId)) {
          className += " is-destination";
        }

        const x1 = from.x + W;
        const y1 = from.y + H / 2;
        const x2 = point.x;
        const y2 = point.y + H / 2;
        const mid = (x1 + x2) / 2;

        edges.append(
          svg("path", {
            class: className,
            d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`
          })
        );
      }

      const drawNode = (id, name, subtitle, info, node) => {
        const point = place.get(id);
        let className = "b3s-path-card b3s-svg-node";
        let blocked = false;

        if (moveState && container) {
          if (moving.has(id)) className += " is-moving";
          if (id === moveState.destination) className += " is-destination";
          else if (destinationIds.has(id)) className += " is-path";

          if (!moving.has(id)) {
            blocked = id === ROOT || Boolean(destinationProblem(container, node));
            if (blocked) className += " is-blocked";
          }
        } else {
          if (pathIds.has(id)) className += " is-path";
          if (id === (selected || ROOT)) className += " is-selected";
        }

        if (node?.historical) className += " is-historical";
        if (node && node.active === "0" && !node.historical) {
          className += " is-inactive";
        }

        const group = svg("g", {
          class: className,
          transform: `translate(${point.x},${point.y})`,
          tabindex: blocked ? -1 : 0,
          role: "button",
          "aria-label": node ? pathFor(node) : "All storage locations",
          "data-location-id": id === ROOT ? "" : id
        });

        if (node && moveState && blocked && !moving.has(id)) {
          group.append(svg("title", {}, destinationProblem(container, node)));
        } else {
          group.append(svg("title", {}, node ? pathFor(node) : "All authorized locations"));
        }

        group.append(
          svg("rect", {class: "b3s-svg-box", width: W, height: H, rx: 8}),
          svg("text", {class: "b3s-svg-name", x: 11, y: 20}, clip(name, Math.max(12, Math.floor(W / 7.6)))),
          svg("text", {class: "b3s-svg-sub", x: 11, y: 36}, clip(subtitle, Math.max(14, Math.floor(W / 6.1))))
        );

        if (info && info.capacity) {
          const inner = W - 22;
          group.append(
            svg("rect", {class: "b3s-svg-track", x: 11, y: H - 9, width: inner, height: 3, rx: 1.5}),
            svg("rect", {
              class: "b3s-svg-fill",
              x: 11,
              y: H - 9,
              width: Math.max(2, inner * info.used / info.capacity),
              height: 3,
              rx: 1.5
            })
          );
        }

        const activate = () => {
          if (moveState && container) {
            if (moving.has(id) || blocked) return;
            moveState.destination = id;
            render();
            return;
          }
          choose(id === ROOT ? "" : id);
        };

        group.addEventListener("click", activate);
        group.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activate();
          }
        });

        shapes.append(group);
      };

      let rootTotal = 0;
      for (const item of kidsOf(ROOT)) rootTotal += summary(item).samples;

      drawNode(ROOT, "All locations", `root · ${plural(rootTotal, "Sample")}`, null, null);

      for (const id of place.keys()) {
        if (id === ROOT) continue;
        const node = byId.get(id);
        const info = summary(node);
        const grid = gridCapacity(node) ? ` ${node.c3Rows}×${node.c3Columns}` : "";
        drawNode(
          id,
          displayName(node),
          node.historical
            ? `Historical · ${info.samples}`
            : `${typeLabel(node)}${grid} · ${info.samples}`,
          info,
          node
        );
      }

      target.append(drawing);
      revealGraphFocus();
    }

    // Scroll the diagram (not the page) to the selected node.
    function revealGraphFocus() {
      const target = find("b3s-graph");
      if (!target || find("b3s-path-tree")?.hidden) return;

      const focus = target.querySelector(
        ".b3s-svg-node.is-destination, .b3s-svg-node.is-selected"
      );
      if (!focus || typeof focus.getBBox !== "function") return;

      const box = focus.getBoundingClientRect();
      const frame = target.getBoundingClientRect();

      // Move as little as possible and keep the ancestors in view:
      // only scroll when the node is outside the frame, and then put it
      // at the nearest edge instead of centring it.
      if (box.right > frame.right) {
        target.scrollLeft += box.right - frame.right + 16;
      } else if (box.left < frame.left) {
        target.scrollLeft -= frame.left - box.left + 16;
      }
      if (box.bottom > frame.bottom || box.top < frame.top) {
        target.scrollTop += box.top - frame.top - frame.height / 2 + box.height / 2;
      }
    }

    // Accessible list fallback for very large hierarchies.
    function renderGraphList(target, visible) {
      const ids = new Set(visible.map(item => item.id));

      const roots = visible.filter(item =>
        !item.parent || !ids.has(item.parent)
      );

      function makeBranch(node, ancestors) {
        if (ancestors.has(node.id)) return null;

        const visited = new Set(ancestors);
        visited.add(node.id);

        const item = mk(
          "li",
          null,
          "b3s-branch b3s-graph-branch"
        );

        const button = mk(
          "button",
          null,
          "b3s-path-card"
        );

        button.type = "button";
        button.title = pathFor(node);
        button.dataset.locationId = node.id;

        if (selected === node.id) {
          button.classList.add("is-selected");
        }

        button.append(
          mk(
            "strong",
            displayName(node)
          ),
          mk(
            "small",
            node.historical
              ? "Historical · read-only"
              : `${node.type} · ${
                  node.active === "1"
                    ? "Active"
                    : "Inactive"
                }`
          )
        );

        button.addEventListener(
          "click",
          () => choose(node.id)
        );

        item.append(button);

        const nested = (
          children.get(node.id) || []
        ).filter(child => ids.has(child.id));

        if (nested.length) {
          const ul = mk(
            "ul",
            null,
            "b3s-branches"
          );

          for (const child of nested) {
            const element = makeBranch(
              child,
              visited
            );

            if (element) ul.append(element);
          }

          if (ul.children.length) item.append(ul);
        }

        return item;
      }

      const list = mk(
        "ul",
        null,
        "b3s-branches b3s-path-root"
      );

      for (const node of roots) {
        const element = makeBranch(
          node,
          new Set()
        );

        if (element) list.append(element);
      }

      target.append(list);

      if (!list.children.length) {
        target.append(
          mk(
            "p",
            "No locations available for this view.",
            "b3s-note"
          )
        );
      }
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
        const line = mk(
          "div",
          null,
          "b3s-history-record"
        );

        const location = byId.get(row.location);

        const path = location
          ? pathFor(location)
          : "Historical location";

        const position = String(
          row.position || ""
        ).trim();

        const fullPath = position
          ? `${path} › ${position.toUpperCase()}`
          : `${path} · position not recorded`;

        const code = String(row.sample || "Sample");

        if (
          typeof row.url === "string" &&
          row.url.startsWith("/") &&
          !row.url.startsWith("//")
        ) {
          const link = mk("a", code);
          link.href = row.url;
          line.append(link);
        } else {
          line.append(mk("strong", code));
        }

        line.append(
          mk(
            "span",
            fullPath,
            "b3s-history-path"
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


    function manageable(node) {
      if (
        !node ||
        node.historical ||
        !node.workspace
      ) {
        return false;
      }

      const select = find("b3s-create-workspace");
      if (!select) return false;

      return [...select.options].some(option =>
        option.value === node.workspace
      );
    }

    function beginEdit(node) {
      if (!manageable(node)) return;

      const form = find("b3s-edit-form");
      if (!form) return;

      form.elements.namedItem("location_id").value =
        node.id;

      form.elements.namedItem("name").value =
        node.name;

      form.elements.namedItem("location_type").value =
        node.type;

      form.elements.namedItem("rank").value =
        node.rank || "1";

      form.elements.namedItem("notes").value =
        node.notes || "";

      form.hidden = false;

      form.scrollIntoView({
        block: "nearest",
        behavior: "smooth"
      });
    }

    function beginChild(node) {
      if (
        !manageable(node) ||
        node.active !== "1"
      ) {
        return;
      }

      const workspaceSelect =
        find("b3s-create-workspace");

      const parentSelect =
        find("b3s-create-parent");

      const form = find("b3s-location-form");

      workspaceSelect.value = node.workspace;

      workspaceSelect.dispatchEvent(
        new Event("change")
      );

      parentSelect.value = node.id;

      form.scrollIntoView({
        block: "nearest",
        behavior: "smooth"
      });
    }


    async function changeStatus(node) {
      if (!manageable(node)) return;

      const form = find("b3s-status-form");
      if (!form) return;

      if (node.active !== "1") {
        if (!window.confirm("Reactivate this location?")) {
          return;
        }

        form.elements.namedItem("action").value =
          "reactivate_location";
        form.elements.namedItem("location_id").value =
          node.id;
        form.elements.namedItem("confirm").value = "";
        form.requestSubmit();
        return;
      }

      let preview;

      try {
        const url = new URL(window.location.href);
        url.search = "";
        url.searchParams.set(
          "b3s_delete_preview",
          node.id
        );

        const response = await fetch(url.toString(), {
          credentials: "same-origin",
          headers: {"Accept": "application/json"}
        });

        preview = await response.json();

        if (!response.ok) {
          throw new Error(
            preview.error || "Unable to inspect this location."
          );
        }
      } catch (error) {
        window.alert(
          "Storage deletion could not be validated: " +
          error.message
        );
        return;
      }

      if (preview.can_delete) {
        if (!window.confirm(
          "Permanently delete '" + displayName(node) +
          "' and " + preview.descendant_count +
          " descendant location(s)?\n\n" +
          "No Samples are linked. This cannot be undone."
        )) {
          return;
        }

        form.elements.namedItem("action").value =
          "delete_empty_subtree";

        form.elements.namedItem("location_id").value =
          node.id;

        form.elements.namedItem("confirm").value =
          "DELETE";

        form.elements.namedItem("preview_token").value = "";
        form.elements.namedItem("reason").value = "";

        form.requestSubmit();
        return;
      }

      if (!preview.can_unassign || !preview.confirm_token) {
        window.alert(
          "Deletion is blocked by protected dependencies " +
          "or insufficient Sample permissions.\n\n" +
          "Affected Samples: " + preview.sample_count +
          "\nAssignments: " + preview.assignment_count +
          "\nUnauthorized Samples: " +
          preview.unauthorized_sample_count +
          "\nLegacy path conflicts: " +
          preview.legacy_conflict_count +
          "\n\nReconcile conflicting legacy paths before " +
          "deletion. No records have been changed."
        );
        return;
      }

      const dialog = find("b3s-delete-dialog");

      if (!dialog || typeof dialog.showModal !== "function") {
        window.alert(
          "The deletion confirmation dialog is unavailable. " +
          "No records have been changed."
        );
        return;
      }

      const values = {
        "b3s-delete-target": preview.root_path,
        "b3s-delete-locations": preview.location_count,
        "b3s-delete-samples": preview.sample_count,
        "b3s-delete-assignments": preview.assignment_count,
        "b3s-delete-orphaned": preview.orphaned_count,
        "b3s-delete-textual": preview.textual_count
      };

      for (const [id, value] of Object.entries(values)) {
        const element = find(id);

        if (!element) {
          window.alert(
            "Deletion confirmation form is incomplete."
          );
          return;
        }

        element.textContent = String(value);
      }

      const dependencies = Object.entries(
        preview.blockers || {}
      ).filter(([name]) =>
        name === "core.StorageSceneConfiguration" ||
        name === "core.StorageLocationLayoutV8146C3"
      );

      find("b3s-delete-dependencies").textContent =
        dependencies.length
          ? "Related scene/layout configurations that will " +
            "also be removed: " +
            dependencies.map(([name, count]) =>
              name + ": " + count
            ).join(", ")
          : "No related scene/layout configurations found.";

      dialog.dataset.locationId = node.id;
      dialog.dataset.previewToken = preview.confirm_token;

      find("b3s-delete-reason").value = "";
      find("b3s-delete-confirm-text").value = "";

      dialog.showModal();
    }

    const deletionDialog = find("b3s-delete-dialog");

    find("b3s-delete-cancel")?.addEventListener(
      "click",
      () => deletionDialog?.close()
    );

    find("b3s-delete-submit")?.addEventListener(
      "click",
      () => {
        if (!deletionDialog?.open) return;

        const reason = find("b3s-delete-reason").value.trim();

        const confirmation =
          find("b3s-delete-confirm-text").value.trim();

        if (reason.length < 5 || reason.length > 1000) {
          window.alert(
            "Provide a deletion reason between 5 and " +
            "1000 characters."
          );
          return;
        }

        if (confirmation !== "DELETE") {
          window.alert(
            "Type DELETE to confirm deletion."
          );
          return;
        }

        const form = find("b3s-status-form");
        const token = deletionDialog.dataset.previewToken;
        const location = deletionDialog.dataset.locationId;

        if (!form || !token || !location) {
          window.alert(
            "Deletion confirmation is incomplete."
          );
          return;
        }

        form.elements.namedItem("action").value =
          "delete_subtree_and_unassign";

        form.elements.namedItem("location_id").value =
          location;

        form.elements.namedItem("confirm").value =
          confirmation;

        form.elements.namedItem("preview_token").value =
          token;

        form.elements.namedItem("reason").value =
          reason;

        deletionDialog.close();
        form.requestSubmit();
      }
    );

    function renderManage() {
      const list = find("b3s-existing-locations");
      const detail = find("b3s-manage-selected");

      if (!list || !detail) return;

      list.replaceChildren();
      detail.replaceChildren();

      const visible = visibleNodes();
      const selectedNode = byId.get(selected);

      for (const node of visible) {
        const row = mk(
          "div",
          null,
          "b3s-manage-row"
        );

        const select = mk(
          "button",
          null,
          "b3s-manage-select"
        );

        select.type = "button";

        select.append(
          mk("strong", displayName(node)),
          mk(
            "small",
            node.historical
              ? "Historical · read-only"
              : `${node.type} · ${
                  node.active === "1"
                    ? "Active"
                    : "Inactive"
                }`
          )
        );

        if (selected === node.id) {
          select.classList.add("is-selected");
        }

        select.addEventListener(
          "click",
          () => choose(node.id)
        );

        row.append(select);

        if (manageable(node)) {
          const edit = mk(
            "button",
            "Edit",
            "btn btn-sm btn-outline-secondary"
          );

          edit.type = "button";

          edit.addEventListener(
            "click",
            () => {
              choose(node.id);
              beginEdit(node);
            }
          );

          row.append(edit);
        }

        list.append(row);
      }

      if (!visible.length) {
        list.append(
          mk(
            "p",
            "No locations available.",
            "b3s-note"
          )
        );
      }

      const editForm = find("b3s-edit-form");

      if (!selectedNode) {
        detail.append(
          mk(
            "p",
            "Select a location to manage it.",
            "b3s-note"
          )
        );

        if (editForm) editForm.hidden = true;
        return;
      }

      detail.append(
        mk("strong", displayName(selectedNode)),
        mk(
          "p",
          pathFor(selectedNode),
          "b3s-note"
        )
      );

      if (!manageable(selectedNode)) {
        detail.append(
          mk(
            "p",
            selectedNode.historical
              ? "Historical registration: read-only."
              : "You cannot manage this location.",
            "b3s-note"
          )
        );

        if (editForm) editForm.hidden = true;
        return;
      }

      const actions = mk(
        "div",
        null,
        "b3s-manage-actions"
      );

      const edit = mk(
        "button",
        "Edit",
        "btn btn-sm btn-outline-primary"
      );

      edit.type = "button";
      edit.addEventListener(
        "click",
        () => beginEdit(selectedNode)
      );

      actions.append(edit);

      const status = mk(
        "button",
        selectedNode.active === "1"
          ? "Delete location"
          : "Reactivate",
        "btn btn-sm btn-outline-danger"
      );

      status.type = "button";
      status.addEventListener(
        "click",
        () => changeStatus(selectedNode)
      );

      actions.append(status);
      detail.append(actions);
    }

    // ---- Board: the selected place drawn, every position clickable ----
    // A grid (box, rack) or named compartments (doors, drawers, shelves).
    // Colour says empty / recorded / more than one; a click opens the
    // actions for that position.
    let boardEditNode = "";    // node id whose drawing is being edited
    let boardPick = null;      // {node, slot}
    let boardPending = null;   // assignment waiting for a free position

    function boardNames(node) {
      if (node.c3Organization === "slots") return slotLabels(node);
      const names = [];
      if (!gridCapacity(node)) return names;
      for (let r = 0; r < gridRows(node); r++) {
        for (let c = 0; c < gridColumns(node); c++) {
          names.push(String.fromCharCode(65 + r) + (c + 1));
        }
      }
      return names;
    }

    function boardSlotOf(node, item) {
      if (node.c3Organization === "slots") return slotName(node, item.position);
      return window.B3StorageV814.gridSlot(
        item.position, gridRows(node), gridColumns(node)
      );
    }

    function boardUsage(node) {
      const bySlot = new Map();
      const outside = [];
      for (const item of samples.filter(it => it.location === node.id)) {
        const slot = boardSlotOf(node, item);
        if (!slot) { outside.push(item); continue; }
        if (!bySlot.has(slot)) bySlot.set(slot, []);
        bySlot.get(slot).push(item);
      }
      return {bySlot, outside};
    }

    function boardStateOf(items) {
      return !items || !items.length
        ? "is-empty"
        : items.length > 1 ? "is-conflict" : "is-used";
    }

    function boardLink(item) {
      const link = mk("a", item.sample || "Sample");
      if (item.url) link.href = item.url;
      return link;
    }

    function boardTarget(node, slot, items) {
      if (boardPending) {
        if (items.length) {
          boardNote = `${slot} is taken. Pick a free position.`;
          renderBoard();
          return;
        }
        window.location.href = pickUrl([
          ["preview_sample", "1"],
          ["assignment_id", boardPending.id],
          ["destination_id", node.id],
          ["position", slot]
        ], "storage-sample-preview");
        return;
      }
      boardPick = {node: node.id, slot};
      renderBoard();
    }

    let boardNote = "";

    function renderBoard() {
      const section = find("b3s-board");
      const canvas = find("b3s-board-canvas");
      const detail = find("b3s-board-detail");
      if (!section || !canvas || !detail) return;

      const node = byId.get(selected);
      const names = node && !node.historical ? boardNames(node) : [];
      const mayDraw = Boolean(
        node && !node.historical && node.active === "1" && manageable(node)
      );

      if (!node || boardEditNode !== node.id) boardEditNode = "";

      section.hidden = !names.length && !mayDraw;
      canvas.replaceChildren();
      detail.replaceChildren();

      if (!names.length) {
        boardPick = null;
        boardPending = null;
        if (!mayDraw) return;
        find("b3s-board-count").textContent = "no drawing yet";
        canvas.append(
          mk(
            "p",
            "No positions are drawn for this place. Draw a grid " +
              "(rows and columns) or name its compartments (doors, " +
              "drawers, shelves) to see and fill each position.",
            "b3s-note"
          )
        );
        if (boardEditNode === node.id) {
          detail.append(boardEditor(node, {bySlot: new Map(), outside: []}));
        } else {
          const draw = mk("button", "Draw positions…", "btn btn-sm btn-primary");
          draw.type = "button";
          draw.addEventListener("click", () => {
            boardEditNode = node.id;
            renderBoard();
          });
          detail.append(draw);
        }
        return;
      }

      if (boardPick && boardPick.node !== node.id) boardPick = null;
      if (boardPending && boardPending.location !== node.id) boardPending = null;

      const usage = boardUsage(node);
      const isSlots = node.c3Organization === "slots";
      const canEdit = manageable(node);

      if (isSlots) {
        const cabinet = mk(
          "div", null,
          "b3s-bd-slots " + (node.c3Direction === "row" ? "is-row" : "is-stack")
        );
        for (const name of names) {
          const items = usage.bySlot.get(name) || [];
          const tile = mk(
            "button", null,
            `b3s-bd-slot ${boardStateOf(items)}` +
              (boardPick && boardPick.slot === name ? " is-picked" : "")
          );
          tile.type = "button";
          tile.dataset.slot = name;
          tile.append(
            mk("strong", name),
            mk(
              "small",
              items.length
                ? items.map(it => it.sample || "Sample").join(", ")
                : "empty"
            )
          );
          cabinet.append(tile);
        }
        canvas.append(cabinet);
      } else {
        const rows = gridRows(node);
        const cols = gridColumns(node);
        const grid = mk("div", null, "b3s-bd-grid");
        grid.style.setProperty("--cols", String(cols));
        grid.append(mk("span", "", "b3s-bd-axis"));
        for (let c = 1; c <= cols; c++) grid.append(mk("span", String(c), "b3s-bd-axis"));
        for (let r = 0; r < rows; r++) {
          grid.append(mk("span", String.fromCharCode(65 + r), "b3s-bd-axis"));
          for (let c = 1; c <= cols; c++) {
            const slot = String.fromCharCode(65 + r) + c;
            const items = usage.bySlot.get(slot) || [];
            const cell = mk(
              "button", "",
              `b3s-bd-cell ${boardStateOf(items)}` +
                (boardPick && boardPick.slot === slot ? " is-picked" : "")
            );
            cell.type = "button";
            cell.dataset.slot = slot;
            cell.title = items.length
              ? `${slot}: ${items.map(it => it.sample || "Sample").join(", ")}`
              : `${slot}: empty`;
            cell.setAttribute("aria-label", cell.title);
            grid.append(cell);
          }
        }
        canvas.append(grid);
      }

      const total = names.length;
      const used = names.filter(n => usage.bySlot.has(n)).length;
      find("b3s-board-count").textContent =
        `${used} of ${total} ${isSlots ? "compartments" : "positions"} in use`;

      // ---- side panel ----
      if (boardEditNode === node.id) {
        detail.append(boardEditor(node, usage));
        return;
      }

      if (boardPending) {
        detail.append(
          mk("h4", "Choose a free position"),
          mk(
            "p",
            `${boardPending.sample || "Sample"} will move to the position ` +
              "you click. You will see a preview before anything changes.",
            "b3s-note"
          )
        );
        if (boardNote) detail.append(mk("p", boardNote, "b3s-bd-warn"));
        const cancel = mk("button", "Cancel", "btn btn-sm btn-outline-secondary");
        cancel.type = "button";
        cancel.addEventListener("click", () => {
          boardPending = null;
          boardNote = "";
          renderBoard();
        });
        detail.append(cancel);
        return;
      }

      boardNote = "";

      if (!boardPick) {
        detail.append(
          mk("h4", displayName(node)),
          mk(
            "p",
            canEdit
              ? "Click a free position to put a Sample there, or an occupied one to open, move or reposition it."
              : "Click a position to see what is recorded there.",
            "b3s-note"
          )
        );
      } else {
        const slot = boardPick.slot;
        const items = usage.bySlot.get(slot) || [];
        detail.append(
          mk(
            "small",
            items.length > 1 ? "MORE THAN ONE" : items.length ? "IN USE" : "EMPTY",
            "b3s-chip"
          ),
          mk("h4", isSlots ? slot : `Position ${slot}`),
          mk("p", `${pathFor(node)} › ${slot}`, "b3s-note")
        );

        if (items.length) {
          const list = mk("ul", null, "b3s-bd-samples");
          for (const item of items) {
            const li = mk("li");
            li.append(boardLink(item));
            if (canEdit && item.id) {
              const move = mk("button", "Move…", "btn btn-sm btn-outline-primary");
              move.type = "button";
              move.addEventListener("click", () => pickSampleMove(node, [item]));
              const reposition = mk(
                "button", "Change position", "btn btn-sm btn-outline-secondary"
              );
              reposition.type = "button";
              reposition.addEventListener("click", () => {
                boardPending = item;
                boardPick = null;
                renderBoard();
              });
              li.append(move, reposition);
            }
            list.append(li);
          }
          detail.append(list);
        } else if (canEdit) {
          detail.append(boardPutForm(node, slot));
        } else {
          detail.append(mk("p", "Nothing recorded here.", "b3s-note"));
        }
      }

      if (usage.outside.length) {
        const box = mk("div", null, "b3s-bd-outside");
        box.append(
          mk(
            "h5",
            `${plural(usage.outside.length, "Sample")} without a position on this drawing`
          )
        );
        const list = mk("ul", null, "b3s-bd-samples");
        for (const item of usage.outside.slice(0, 25)) {
          const li = mk("li");
          li.append(boardLink(item));
          if (item.position) li.append(mk("small", ` (${item.position})`));
          if (canEdit && item.id) {
            const place = mk("button", "Place…", "btn btn-sm btn-outline-secondary");
            place.type = "button";
            place.addEventListener("click", () => {
              boardPending = item;
              boardPick = null;
              renderBoard();
            });
            li.append(place);
          }
          list.append(li);
        }
        box.append(list);
        detail.append(box);
      }

      const actions = mk("div", null, "b3s-manage-actions");
      const here = samples.filter(it => it.location === node.id && it.id);
      if (canEdit && here.length && window.B3StoragePicker) {
        const all = mk(
          "button",
          here.length === 1 ? "Move the Sample…" : `Move all ${here.length} Samples…`,
          "btn btn-sm btn-outline-primary"
        );
        all.type = "button";
        all.addEventListener("click", () => pickSampleMove(node, here));
        actions.append(all);
      }
      if (movable(node)) {
        const move = mk("button", "Move this location", "btn btn-sm btn-outline-primary");
        move.type = "button";
        move.addEventListener("click", () => beginMove(node));
        actions.append(move);
      }
      if (canEdit && mayDraw) {
        const edit = mk("button", "Edit drawing", "btn btn-sm btn-outline-secondary");
        edit.type = "button";
        edit.addEventListener("click", () => {
          boardEditNode = node.id;
          renderBoard();
        });
        actions.append(edit);
      }
      if (actions.children.length) detail.append(actions);
    }

    // Edit the drawing of the selected place. The server refuses any change
    // that would leave a Sample without a valid position.
    function boardEditor(node, usage) {
      const box = mk("div", null, "b3s-bd-editor");
      box.append(mk("h4", "Edit drawing"));

      let org = node.c3Organization === "slots" || node.c3Organization === "grid"
        ? node.c3Organization : "grid";
      let rows = gridRows(node) || 9;
      let cols = gridColumns(node) || 9;
      let dir = node.c3Direction === "row" ? "row" : "column";
      let slots = node.c3Organization === "slots"
        ? slotLabels(node).map(name => ({name, old: name}))
        : [{name: "Door 1", old: ""}, {name: "Door 2", old: ""}];
      const fields = mk("div", null, "b3s-bd-ed-fields");
      const msg = mk("p", "", "b3s-bd-warn");

      const drawFields = () => {
        fields.replaceChildren();
        if (org === "grid") {
          const r = document.createElement("input");
          r.type = "number"; r.min = "1"; r.max = "26"; r.value = String(rows);
          r.className = "form-control form-control-sm";
          r.addEventListener("input", () => { rows = Number(r.value) || 0; });
          const c = document.createElement("input");
          c.type = "number"; c.min = "1"; c.max = "24"; c.value = String(cols);
          c.className = "form-control form-control-sm";
          c.addEventListener("input", () => { cols = Number(c.value) || 0; });
          const l1 = mk("label", "Rows (A…)"); l1.append(r);
          const l2 = mk("label", "Columns"); l2.append(c);
          fields.append(l1, l2, mk(
            "p",
            "Positions are named A1, B7… You cannot make the grid smaller " +
              "than a position that holds a Sample.",
            "b3s-note"
          ));
          return;
        }
        slots.forEach((slot, index) => {
          const row = mk("div", null, "b3s-bd-ed-slot");
          const input = document.createElement("input");
          input.type = "text"; input.maxLength = 40; input.value = slot.name;
          input.className = "form-control form-control-sm";
          input.addEventListener("input", () => { slot.name = input.value; });
          const holding = slot.old ? (usage.bySlot.get(slot.old) || []).length : 0;
          const remove = mk("button", "Remove", "btn btn-sm btn-outline-secondary");
          remove.type = "button";
          remove.disabled = slots.length <= 1;
          remove.addEventListener("click", () => {
            slots.splice(index, 1);
            drawFields();
          });
          row.append(input, remove);
          if (holding) row.append(mk("small", `${holding} Sample(s) here: rename keeps them; removing is refused.`, "b3s-note"));
          fields.append(row);
        });
        const add = mk("button", "Add a compartment", "btn btn-sm btn-outline-secondary");
        add.type = "button";
        add.disabled = slots.length >= 40;
        add.addEventListener("click", () => {
          slots.push({name: `Door ${slots.length + 1}`, old: ""});
          drawFields();
        });
        const select = document.createElement("select");
        select.className = "form-select form-select-sm";
        for (const [value, label] of [["column", "Stacked (top to bottom)"], ["row", "Side by side"]]) {
          const o = document.createElement("option");
          o.value = value; o.textContent = label; o.selected = value === dir;
          select.append(o);
        }
        select.addEventListener("change", () => { dir = select.value; });
        const ld = mk("label", "Layout"); ld.append(select);
        fields.append(add, ld);
      };

      const orgSelect = document.createElement("select");
      orgSelect.className = "form-select form-select-sm";
      for (const [value, label] of [["grid", "Grid of positions (box, rack)"], ["slots", "Named compartments (doors, drawers)"], ["free", "No drawing"]]) {
        const o = document.createElement("option");
        o.value = value; o.textContent = label; o.selected = value === org;
        orgSelect.append(o);
      }
      if (org !== "grid" && org !== "slots") orgSelect.value = "grid";
      orgSelect.addEventListener("change", () => {
        org = orgSelect.value;
        drawFields();
      });
      const lo = mk("label", "Kind of drawing");
      lo.append(orgSelect);
      box.append(lo, fields);
      drawFields();

      const save = mk("button", "Save drawing", "btn btn-sm btn-primary");
      save.type = "button";
      save.addEventListener("click", () => {
        const form = find("b3s-bd-layout");
        if (!form) return;
        if (org === "slots") {
          const seen = new Set();
          for (const slot of slots) {
            const name = slot.name.trim().replace(/\s+/g, " ");
            if (!name) { msg.textContent = "Every compartment needs a name."; return; }
            if (seen.has(name.toLowerCase())) { msg.textContent = `"${name}" is used twice.`; return; }
            seen.add(name.toLowerCase());
          }
        }
        for (const el of form.querySelectorAll("[data-gen]")) el.remove();
        const add = (name, value) => {
          const input = document.createElement("input");
          input.type = "hidden"; input.name = name; input.value = String(value);
          input.dataset.gen = "1";
          form.append(input);
        };
        add("location_id", node.id);
        add("organization", org);
        if (org === "grid") { add("rows", rows); add("columns", cols); }
        if (org === "slots") {
          add("slot_direction", dir);
          for (const slot of slots) { add("slot_label", slot.name); add("slot_old", slot.old); }
        }
        form.submit();
      });
      const cancel = mk("button", "Cancel", "btn btn-sm btn-outline-secondary");
      cancel.type = "button";
      cancel.addEventListener("click", () => {
        boardEditNode = "";
        renderBoard();
      });
      const actions = mk("div", null, "b3s-manage-actions");
      actions.append(save, cancel);
      box.append(msg, actions);
      return box;
    }

    // Empty position: search any Sample by ID (placed or not yet placed)
    // and send it through the same preview-and-confirm page used for
    // selections made in the Samples list.
    function boardSendToBulk(node, slot, sample) {
      const form = find("b3s-bd-bulk");
      if (!form) return;
      for (const el of form.querySelectorAll("[data-gen]")) el.remove();
      const add = (name, value) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = String(value);
        input.dataset.gen = "1";
        form.append(input);
      };
      add("action", "preview");
      add("sample_ids", sample.id);
      add("destination_id", node.id);
      add("position_" + sample.id, slot);
      form.submit();
    }

    function boardPutForm(node, slot) {
      const form = mk("div", null, "b3s-bd-put");
      const label = mk("label", "Put a Sample here");
      const input = document.createElement("input");
      input.type = "search";
      input.className = "form-control form-control-sm";
      input.placeholder = "Type part of the Sample ID";
      input.autocomplete = "off";
      label.append(input);

      const results = mk("ul", null, "b3s-bd-results");
      const status = mk("p", "", "b3s-note");
      let timer = 0;
      let counter = 0;

      const run = () => {
        const text = input.value.trim();
        const url = find("b3s-board")?.dataset.searchUrl;
        results.replaceChildren();
        if (!url || text.length < 2) {
          status.textContent = text ? "Type at least 2 characters." : "";
          return;
        }
        const ticket = ++counter;
        status.textContent = "Searching…";
        fetch(url + "?q=" + encodeURIComponent(text), {
          credentials: "same-origin",
          headers: {Accept: "application/json"}
        })
          .then(response => response.ok ? response.json() : {results: []})
          .then(data => {
            if (ticket !== counter) return;
            results.replaceChildren();
            const list = data.results || [];
            status.textContent = list.length
              ? ""
              : "No Sample found that you can place.";
            for (const item of list) {
              const li = mk("li");
              const button = mk("button", null, "b3s-bd-result");
              button.type = "button";
              button.append(
                mk("strong", item.sample),
                mk("small", item.where ? item.where : "not placed yet")
              );
              button.addEventListener("click", () =>
                boardSendToBulk(node, slot, item)
              );
              li.append(button);
              results.append(li);
            }
          })
          .catch(() => {
            if (ticket === counter) status.textContent = "Search failed.";
          });
      };

      input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(run, 250);
      });

      form.append(label, results, status);

      const addUrl = find("b3s-board")?.dataset.addUrl;
      if (addUrl) {
        const add = mk("a", "Register a new Sample", "btn btn-sm btn-outline-secondary");
        add.href = addUrl;
        form.append(add);
      }
      return form;
    }

    function wireBoard() {
      const canvas = find("b3s-board-canvas");
      if (!canvas) return;
      canvas.addEventListener("click", event => {
        const target = event.target.closest("[data-slot]");
        if (!target) return;
        const node = byId.get(selected);
        if (!node) return;
        const items = boardUsage(node).bySlot.get(target.dataset.slot) || [];
        boardTarget(node, target.dataset.slot, items);
      });
    }

    // Move Samples one by one or all together: pick the first free
    // position and the Samples fill the next free ones.
    function pickSampleMove(node, items) {
      window.B3StoragePicker.open({
        title: items.length === 1
          ? "Move Sample"
          : `Move ${items.length} Samples`,
        mode: "place",
        count: items.length,
        workspace: node.workspace,
        ignore: items.map(item => item.id),
        confirmLabel: "Preview move",
        onPick: result => {
          if (items.length === 1) {
            window.location.href = pickUrl([
              ["preview_sample", "1"],
              ["assignment_id", items[0].id],
              ["destination_id", result.id],
              ["position", result.positions[0] || ""]
            ], "storage-sample-preview");
            return;
          }

          const params = [["preview_bulk_samples", "1"]];
          items.forEach((item, index) => {
            params.push(
              ["bulk_assignment_id", item.id],
              ["bulk_destination_id", result.id],
              ["bulk_position", result.positions[index] || ""]
            );
          });
          window.location.href = pickUrl(params, "storage-sample-bulk-preview");
        }
      });
    }

    function render() {
      renderTree();
      renderContents();
      renderLegacy();
      renderGraph();
      renderBoard();
      renderManage();
    }

    function showTab(tab) {
      for (const other of root.querySelectorAll(
        "[data-b3s-tab]"
      )) {
        other.setAttribute(
          "aria-selected",
          String(other.dataset.b3sTab === tab)
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

      if (tab === "tree") revealGraphFocus();
    }

    wireBoard();

    for (const button of root.querySelectorAll(
      "[data-b3s-tab]"
    )) {
      button.addEventListener("click", () => {
        showTab(button.dataset.b3sTab);
      });
    }

    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && moveState) cancelMove();
    });

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

    const cancelEdit = find("b3s-cancel-edit");

    if (cancelEdit) {
      cancelEdit.addEventListener("click", () => {
        find("b3s-edit-form").hidden = true;
      });
    }


    const newLocation = find("b3s-new-location");
    const locationDialog = find("b3s-location-dialog");

    function closeLocationDialog() {
      if (!locationDialog) return;

      if (typeof locationDialog.close === "function") {
        locationDialog.close();
      } else {
        locationDialog.removeAttribute("open");
      }
    }

    function openLocationDialog() {
      if (!locationDialog) return;

      const node = byId.get(selected);

      const workspaceSelect =
        find("b3s-create-workspace");

      const parentSelect =
        find("b3s-create-parent");

      if (!workspaceSelect || !parentSelect) return;

      const eligible =
        node && manageable(node) && node.active === "1";

      if (eligible) {
        workspaceSelect.value = node.workspace;
      } else {
        const currentStorage =
          find("b3s-workspace-filter")?.value || "";

        if (
          currentStorage &&
          [...workspaceSelect.options].some(
            option => option.value === currentStorage
          )
        ) {
          workspaceSelect.value = currentStorage;
        }
      }

      workspaceSelect.dispatchEvent(
        new Event("change")
      );

      // A historical projection is never a real parent.
      parentSelect.value = eligible ? node.id : "";

      if (
        typeof locationDialog.showModal === "function"
      ) {
        if (!locationDialog.open) {
          locationDialog.showModal();
        }
      } else {
        locationDialog.setAttribute("open", "");
      }

      locationDialog.querySelector(
        '[name="name"]'
      )?.focus();
    }

    newLocation?.addEventListener(
      "click",
      openLocationDialog
    );

    find("b3s-close-location")?.addEventListener(
      "click",
      closeLocationDialog
    );

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

            const forbidden =
              option.dataset.workspace !== selectedWorkspace;

            option.hidden = forbidden;
            option.disabled = forbidden;
          }

          createParent.value = "";
        }
      );

      createWorkspace.dispatchEvent(
        new Event("change")
      );
    }

    // A server-side move preview (or its error) reopens the
    // path tree with the container selected.
    const previewContainer = String(
      root.dataset.b3sPreviewContainer || ""
    );

    if (byId.has(previewContainer)) {
      selected = previewContainer;
    }

    // Deep links from the Sample pages:
    // ?location=<id> opens a place, ?move_assignment=<id> opens the
    // destination picker for that Sample.
    const params = new URLSearchParams(window.location.search);
    const wantedLocation = params.get("location") || "";
    const wantedMove = params.get("move_assignment") || "";
    const wantedItem = wantedMove
      ? samples.find(item => String(item.id) === wantedMove)
      : null;

    if (wantedItem && byId.has(wantedItem.location)) {
      selected = wantedItem.location;
    } else if (byId.has(wantedLocation)) {
      selected = wantedLocation;
    }

    render();

    if (wantedItem && byId.has(wantedItem.location) && window.B3StoragePicker) {
      pickSampleMove(byId.get(wantedItem.location), [wantedItem]);
    }

    if (root.dataset.b3sPreviewSamples === "1") {
      showTab("movements");
      (
        find("storage-sample-bulk-preview") ||
        find("storage-sample-preview")
      )?.scrollIntoView({block: "start"});
    }

    if (root.dataset.b3sPreviewOpen === "1") {
      showTab("tree");
      find("storage-container-preview")?.scrollIntoView({
        block: "start"
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded", initialize, {once: true}
    );
  } else {
    initialize();
  }
})();
