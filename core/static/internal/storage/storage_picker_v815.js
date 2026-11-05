/*
 * Destination picker: the storage tree on the left, a drawing of the
 * highlighted place on the right (grid of positions or named
 * compartments). The browser only proposes a destination; every move is
 * previewed and checked again by the server.
 *
 *   B3StoragePicker.open({
 *     title, mode: "node" | "place", count, workspace, exclude,
 *     ignore: [assignmentId, ...],   // samples being moved
 *     confirmLabel, onPick({id, path, positions})
 *   })
 */
(() => {
  "use strict";

  // ---- pure helpers (also used by the node tests) ------------------

  function gridName(row, column) {
    return String.fromCharCode(65 + row) + (column + 1);
  }

  // Canonical name of a recorded position inside one location.
  function canonicalPosition(layout, position) {
    const text = String(position || "").trim();

    if (!text) return "";

    if (layout.kind === "grid") {
      const match = /^([A-Z])0*([1-9][0-9]*)$/.exec(text.toUpperCase());

      if (!match) return "";

      const row = match[1].charCodeAt(0) - 65;
      const column = Number(match[2]) - 1;

      return row < layout.rows && column < layout.columns
        ? gridName(row, column)
        : "";
    }

    if (layout.kind === "slots") {
      const found = layout.slots.find(
        name => name.toLowerCase() === text.toLowerCase()
      );

      return found || "";
    }

    return "";
  }

  // Every position of a layout, in the order samples fill them.
  function allPositions(layout) {
    if (layout.kind === "grid") {
      const names = [];

      for (let r = 0; r < layout.rows; r++) {
        for (let c = 0; c < layout.columns; c++) {
          names.push(gridName(r, c));
        }
      }

      return names;
    }

    return layout.kind === "slots" ? layout.slots.slice() : [];
  }

  // `count` free positions, starting at `start` and going forward.
  function freeRun(order, occupied, start, count) {
    const from = order.indexOf(start);

    if (from < 0 || occupied.has(start)) return [];

    const run = [];

    for (let i = from; i < order.length && run.length < count; i++) {
      if (!occupied.has(order[i])) run.push(order[i]);
    }

    return run;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      canonicalPosition, allPositions, freeRun, gridName
    };
  }

  if (typeof document === "undefined") return;

  // ---- data ---------------------------------------------------------

  function readData() {
    const locationSource = document.getElementById("b3s-location-data");
    const sampleSource = document.getElementById("b3s-sample-data");

    if (!locationSource?.content || !sampleSource?.content) return null;

    const nodes = new Map();

    for (const item of locationSource.content.querySelectorAll("[data-id]")) {
      const d = item.dataset;
      let slots = [];

      try {
        slots = JSON.parse(d.c3Slots || "[]");
      } catch (error) {
        slots = [];
      }

      const organization = d.c3Organization;
      const layout = organization === "grid"
        ? {
            kind: "grid",
            rows: Number(d.c3Rows) || 0,
            columns: Number(d.c3Columns) || 0
          }
        : organization === "slots"
          ? {
              kind: "slots",
              slots: Array.isArray(slots) ? slots : [],
              direction: d.c3Direction === "row" ? "row" : "column"
            }
          : {kind: "free"};

      nodes.set(d.id, {
        id: d.id,
        parent: d.parent || "",
        workspace: d.workspace || "",
        name: d.name || "",
        type: d.type || "other",
        path: d.path || d.name || "",
        active: d.active === "1",
        rank: Number(d.rank) || 0,
        layout,
        children: [],
        samples: []
      });
    }

    for (const node of nodes.values()) {
      nodes.get(node.parent)?.children.push(node);
    }

    for (const node of nodes.values()) {
      node.children.sort(
        (a, b) => a.rank - b.rank || a.name.localeCompare(b.name)
      );
    }

    for (const item of sampleSource.content.querySelectorAll("[data-id]")) {
      const d = item.dataset;

      nodes.get(d.location)?.samples.push({
        id: d.id,
        sample: d.sample || "",
        position: d.position || ""
      });
    }

    return nodes;
  }

  function subtreeIds(node) {
    const ids = new Set([node.id]);
    const stack = [...node.children];

    while (stack.length) {
      const current = stack.pop();

      if (ids.has(current.id)) continue;
      ids.add(current.id);
      stack.push(...current.children);
    }

    return ids;
  }

  function subtreeSamples(node) {
    let total = node.samples.length;

    for (const child of node.children) total += subtreeSamples(child);

    return total;
  }

  // ---- interface ----------------------------------------------------

  function el(tag, className, text) {
    const node = document.createElement(tag);

    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;

    return node;
  }

  function open(options) {
    const nodes = readData();

    if (!nodes) return;

    const mode = options.mode === "place" ? "place" : "node";
    const count = Math.max(1, Number(options.count) || 1);
    const ignore = new Set((options.ignore || []).map(String));
    const blocked = options.exclude && nodes.get(String(options.exclude))
      ? subtreeIds(nodes.get(String(options.exclude)))
      : new Set();

    const usable = node =>
      node.active &&
      node.type !== "position" &&
      (!options.workspace || node.workspace === String(options.workspace)) &&
      !blocked.has(node.id);

    const roots = [...nodes.values()].filter(
      node => !node.parent || !nodes.has(node.parent)
    ).filter(node =>
      !options.workspace || node.workspace === String(options.workspace)
    ).sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));

    // Small storages open fully; large ones open the first level.
    const expanded = new Set(
      nodes.size <= 80
        ? [...nodes.values()].filter(node => node.children.length).map(node => node.id)
        : roots.map(node => node.id)
    );
    let shown = null;      // node drawn on the right
    let chosen = null;     // {node, positions}
    let hover = [];
    let query = "";

    const dialog = el("dialog", "b3s-location-dialog b3s-pk");
    const head = el("div", "b3s-dialog-header");
    const title = el("h2", null, options.title || "Choose a destination");
    const close = el("button", "btn btn-sm btn-outline-secondary", "Close");
    const body = el("div", "b3s-pk-body");
    const left = el("div", "b3s-pk-tree");
    const right = el("div", "b3s-pk-draw");
    const foot = el("div", "b3s-pk-foot");
    const summary = el("p", "b3s-pk-summary");
    const confirm = el(
      "button", "btn btn-primary", options.confirmLabel || "Use this place"
    );
    const cancel = el("button", "btn btn-outline-secondary", "Cancel");
    const search = el("input", "b3s-pk-search");

    close.type = confirm.type = cancel.type = "button";
    search.type = "search";
    search.placeholder = "Search by name";
    search.setAttribute("aria-label", "Search storage");

    head.append(el("div", null), close);
    head.firstChild.append(
      title,
      el(
        "p", "b3s-note",
        mode === "place"
          ? (count > 1
            ? `Pick where the ${count} Samples go: click the first free position and they take the next free ones.`
            : "Pick a place in the tree, then a free position.")
          : "Pick the place to move into. Everything inside moves with it."
      )
    );
    foot.append(summary, cancel, confirm);
    body.append(left, right);
    dialog.append(head, body, foot);
    document.body.append(dialog);

    function destroy() {
      dialog.close();
      dialog.remove();
    }

    close.addEventListener("click", destroy);
    cancel.addEventListener("click", destroy);
    dialog.addEventListener("cancel", () => setTimeout(destroy, 0));

    // ---- tree

    function matches(node) {
      if (!query) return true;

      if (node.name.toLowerCase().includes(query)) return true;

      return node.children.some(matches);
    }

    function renderNode(node, depth, host) {
      if (!matches(node)) return;

      const open = query ? true : expanded.has(node.id);
      const row = el("div", "b3s-pk-row");
      const ok = usable(node);

      row.style.paddingLeft = (depth * 14 + 4) + "px";

      if (shown && shown.id === node.id) row.classList.add("is-shown");
      if (!ok) row.classList.add("is-blocked");

      const toggle = el(
        "button", "b3s-pk-toggle",
        node.children.length ? (open ? "▾" : "▸") : "·"
      );

      toggle.type = "button";
      toggle.disabled = !node.children.length;
      toggle.setAttribute("aria-label", open ? "Collapse" : "Expand");
      toggle.addEventListener("click", () => {
        if (expanded.has(node.id)) expanded.delete(node.id);
        else expanded.add(node.id);
        renderTree();
      });

      const name = el("button", "b3s-pk-name");

      name.type = "button";
      name.append(
        el("span", "b3s-pk-type", node.type),
        el("span", null, node.name)
      );

      const total = subtreeSamples(node);

      if (total) {
        name.append(el("span", "b3s-pk-count", String(total)));
      }

      name.addEventListener("click", () => show(node));
      row.append(toggle, name);
      host.append(row);

      if (open) {
        for (const child of node.children) renderNode(child, depth + 1, host);
      }
    }

    function renderTree() {
      const list = left.querySelector(".b3s-pk-list") || el("div", "b3s-pk-list");

      list.replaceChildren();

      for (const node of roots) renderNode(node, 0, list);

      if (!list.children.length) {
        list.append(el("p", "b3s-note", "Nothing matches."));
      }

      if (!left.contains(list)) left.append(search, list);
    }

    search.addEventListener("input", () => {
      query = search.value.trim().toLowerCase();
      renderTree();
    });

    // ---- drawing

    function occupancy(node) {
      const map = new Map();

      for (const item of node.samples) {
        if (ignore.has(item.id)) continue;

        const key = canonicalPosition(node.layout, item.position);

        if (!key) continue;
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(item.sample);
      }

      return map;
    }

    function pickPosition(node, name, order, used) {
      const run = freeRun(order, new Set(used.keys()), name, count);

      chosen = {node, positions: run};
      renderDraw();
      renderFoot();
    }

    function position(node, name, order, used, host) {
      const taken = used.get(name) || [];
      const mine = chosen && chosen.node.id === node.id &&
        chosen.positions.includes(name);
      const preview = hover.includes(name);
      const button = el(
        "button",
        "b3s-pk-pos" +
          (taken.length ? " is-used" : "") +
          (mine ? " is-chosen" : "") +
          (preview && !mine ? " is-preview" : "")
      );

      button.type = "button";
      button.dataset.position = name;
      button.title = taken.length
        ? `${name}: ${taken.join(", ")}`
        : `${name}: free`;
      button.setAttribute("aria-label", button.title);

      if (node.layout.kind === "slots") {
        button.append(el("strong", null, name));

        if (taken.length) {
          button.append(el("span", "b3s-pk-in", taken.join(", ")));
        }
      }

      if (mode === "place") {
        button.disabled = taken.length > 0;
        button.addEventListener("click", () =>
          pickPosition(node, name, order, used)
        );
        button.addEventListener("mouseenter", () => {
          hover = freeRun(order, new Set(used.keys()), name, count);
          host.querySelectorAll(".b3s-pk-pos").forEach(cell => {
            cell.classList.toggle(
              "is-preview",
              hover.includes(cell.dataset.position) &&
                !cell.classList.contains("is-chosen")
            );
          });
        });
      } else {
        button.disabled = true;
      }

      return button;
    }

    function renderDraw() {
      right.replaceChildren();

      if (!shown) {
        right.append(
          el("p", "b3s-note", "Pick a place in the tree to see how it is organised.")
        );
        return;
      }

      const node = shown;
      const layout = node.layout;
      const used = occupancy(node);
      const order = allPositions(layout);

      right.append(
        el("h3", "b3s-pk-title", node.name),
        el("p", "b3s-note", node.path)
      );

      const box = el("div", "b3s-pk-canvas");

      if (layout.kind === "grid" && layout.rows && layout.columns) {
        const size = Math.max(14, Math.min(30, Math.floor(420 / layout.columns)));
        const grid = el("div", "b3s-pk-grid");

        grid.style.gridTemplateColumns =
          `18px repeat(${layout.columns}, ${size}px)`;
        grid.append(el("span"));

        for (let c = 1; c <= layout.columns; c++) {
          grid.append(el("span", "b3s-pk-axis", size >= 18 ? String(c) : ""));
        }

        for (let r = 0; r < layout.rows; r++) {
          grid.append(el("span", "b3s-pk-axis", String.fromCharCode(65 + r)));

          for (let c = 0; c < layout.columns; c++) {
            const cell = position(node, gridName(r, c), order, used, box);

            cell.style.width = cell.style.height = size + "px";
            grid.append(cell);
          }
        }

        box.append(grid);
        right.append(
          box,
          el(
            "p", "b3s-note",
            `${used.size} of ${order.length} positions used. ` +
            "Filled: has a Sample. Outlined: free."
          )
        );
      } else if (layout.kind === "slots" && layout.slots.length) {
        const cabinet = el(
          "div",
          "b3s-pk-cabinet " + (layout.direction === "row" ? "is-row" : "is-stack")
        );

        for (const name of layout.slots) {
          cabinet.append(position(node, name, order, used, box));
        }

        box.append(cabinet);
        right.append(
          box,
          el("p", "b3s-note", `${used.size} of ${order.length} compartments used.`)
        );
      } else {
        right.append(
          el(
            "p", "b3s-note",
            node.children.length
              ? "This place has no positions of its own. Open it in the tree to choose a place inside."
              : "This place has no positions. Samples are recorded here as a whole."
          )
        );
      }

      const direct = node.samples.length;

      if (direct && layout.kind === "free") {
        right.append(
          el("p", "b3s-note", `${direct} Sample(s) recorded here.`)
        );
      }

      // Places without positions are chosen as a whole.
      if (layout.kind === "free" || mode === "node") {
        const whole = el(
          "button", "btn btn-sm btn-outline-primary",
          mode === "node" ? "Move into this place" : "Choose this place"
        );

        whole.type = "button";
        whole.disabled = !usable(node);
        whole.addEventListener("click", () => {
          chosen = {node, positions: []};
          renderDraw();
          renderFoot();
        });
        right.append(whole);

        if (!usable(node) && blocked.has(node.id)) {
          right.append(
            el("p", "b3s-note", "A place cannot be moved inside itself.")
          );
        }
      }
    }

    function renderFoot() {
      if (!chosen) {
        summary.textContent = mode === "place"
          ? "Nothing chosen yet."
          : "Pick the destination.";
        confirm.disabled = true;
        return;
      }

      const {node, positions} = chosen;
      const layout = node.layout;
      const needs = mode === "place" && layout.kind !== "free";
      const short = needs && positions.length < count;

      summary.textContent =
        node.path +
        (positions.length ? " › " + positions.join(", ") : "") +
        (short
          ? `. Only ${positions.length} free position(s) from here, ${count} needed.`
          : "");
      confirm.disabled = short || (needs && !positions.length);
    }

    function show(node) {
      shown = node;
      hover = [];

      if (chosen && chosen.node.id !== node.id) {
        // keep the choice until the person picks again
      }

      renderTree();
      renderDraw();
    }

    confirm.addEventListener("click", () => {
      if (!chosen) return;

      const result = {
        id: chosen.node.id,
        path: chosen.node.path,
        positions: chosen.positions.slice()
      };

      destroy();
      options.onPick(result);
    });

    renderTree();
    renderDraw();
    renderFoot();
    dialog.showModal();
  }

  window.B3StoragePicker = {open};
})();
