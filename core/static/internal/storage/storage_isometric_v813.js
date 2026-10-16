/*
 * B3 LIMS V8.13 — SVG isometric storage viewer.
 *
 * Uses authorized Django projections.
 * No canvas, WebGL, Three.js or database writes.
 * Historical locations are read-only.
 */
(() => {
  "use strict";

  const str = value =>
    value == null ? "" : String(value);

  function build(physical, historical, assignments, recorded) {
    const nodes = new Map();
    const samples = new Map();
    const counts = new Map();

    for (const [rows, prefix] of [
      [physical, "p"],
      [historical, "h"]
    ]) {
      for (const raw of rows) {
        if (!raw || !str(raw.id)) continue;

        const key = `${prefix}:${str(raw.id)}`;

        if (nodes.has(key)) continue;

        nodes.set(key, {
          key,
          id: str(raw.id),
          parent: str(raw.parent),
          parentKey: null,
          name: str(raw.name) || "Location",
          kind: str(raw.kind || raw.type).toLowerCase(),
          path: str(raw.path || raw.name),
          historical: prefix === "h"
        });
      }
    }

    for (const node of nodes.values()) {
      const prefix = node.historical ? "h:" : "p:";

      const parent = node.parent
        ? prefix + node.parent
        : null;

      if (!parent || !nodes.has(parent)) continue;

      let current = parent;
      const seen = new Set([node.key]);
      let valid = true;

      while (current) {
        if (seen.has(current)) {
          valid = false;
          break;
        }

        seen.add(current);

        const ancestor = nodes.get(current);

        if (!ancestor) {
          valid = false;
          break;
        }

        current = ancestor.parent
          ? prefix + ancestor.parent
          : null;
      }

      if (valid) node.parentKey = parent;
    }

    const used = new Set();

    for (const [rows, prefix] of [
      [assignments, "p"],
      [recorded, "h"]
    ]) {
      for (const raw of rows) {
        if (!raw) continue;

        if (
          prefix === "p" &&
          raw.status &&
          raw.status !== "active"
        ) continue;

        const box = prefix + ":" +
          str(raw.box || raw.location);

        if (!nodes.has(box)) continue;

        const identity = [
          box,
          str(raw.id || raw.code),
          str(raw.position)
        ].join("|");

        if (used.has(identity)) continue;
        used.add(identity);

        const sample = {
          id: raw.id ?? null,
          box: nodes.get(box).id,
          code: str(raw.code) || "Sample",
          position: str(raw.position),
          organism: str(raw.organism),
          url: str(raw.url),
          status: "active",
          legacy: prefix === "h",
          key: identity
        };

        if (!samples.has(box)) samples.set(box, []);
        samples.get(box).push(sample);

        let current = box;
        const seen = new Set();

        while (current && !seen.has(current)) {
          seen.add(current);

          counts.set(
            current,
            (counts.get(current) || 0) + 1
          );

          current = nodes.get(current)?.parentKey || null;
        }
      }
    }

    return {nodes, samples, counts};
  }

  function layout(model, focus = null) {
    const children = new Map();

    for (const node of model.nodes.values()) {
      const parent = node.parentKey || null;

      if (!children.has(parent)) {
        children.set(parent, []);
      }

      children.get(parent).push(node);
    }

    for (const group of children.values()) {
      group.sort((a, b) =>
        a.name.localeCompare(b.name, "en", {
          numeric: true
        })
      );
    }

    const root = focus && model.nodes.has(focus)
      ? model.nodes.get(focus)
      : null;

    const roots = root
      ? [root]
      : children.get(null) || [];

    const items = [];
    const edges = [];
    const positions = new Map();
    const seen = new Set();

    // Overview: two levels. Focused view: three levels.
    const maxDepth = root ? 2 : 1;

    function visit(node, depth) {
      if (seen.has(node.key) || items.length >= 80) {
        return;
      }

      seen.add(node.key);

      const point = {
        x: 28 + depth * 245,
        y: 30 + items.length * 113
      };

      positions.set(node.key, point);

      items.push({
        node,
        point,
        count: model.counts.get(node.key) || 0
      });

      if (depth >= maxDepth) return;

      for (const child of children.get(node.key) || []) {
        if (items.length >= 80) break;

        visit(child, depth + 1);

        const destination = positions.get(child.key);

        if (destination) {
          edges.push({
            from: node.key,
            to: child.key,
            a: point,
            b: destination
          });
        }
      }
    }

    for (const node of roots) {
      if (items.length >= 80) break;
      visit(node, 0);
    }

    return {
      items,
      edges,
      truncated: seen.size < (
        root ? 1 : model.nodes.size
      ) && items.length >= 80,
      width: Math.max(
        560,
        ...items.map(item => item.point.x + 225)
      ),
      height: Math.max(370, 65 + items.length * 113)
    };
  }

  if (typeof window !== "undefined") {
    window.B3StorageSVGV813 = {
      build,
      layout,
      ready: false
    };
  }

  if (typeof document === "undefined") return;

  const byId = id => document.getElementById(id);
  const viewport = byId("storage-isometric-v813");
  const source = byId("storage-explorer-data");

  if (!viewport || !source?.content) return;

  const elements = (template, selector, mapper) =>
    template?.content
      ? Array.from(
          template.content.querySelectorAll(selector),
          mapper
        )
      : [];

  let physical = elements(
    source,
    "[data-location-id]",
    el => ({
      id: el.dataset.locationId,
      parent: el.dataset.parentId,
      name: el.dataset.locationName,
      kind: el.dataset.locationKind,
      type: el.dataset.locationType,
      path: el.dataset.locationPath
    })
  );

  let assignments = elements(
    source,
    "[data-assignment-location]",
    el => ({
      id: el.dataset.assignmentId,
      box: el.dataset.assignmentLocation,
      code: el.dataset.assignmentSample,
      position: el.dataset.assignmentPosition,
      organism: el.dataset.assignmentOrganism,
      url: el.dataset.assignmentUrl,
      status: el.dataset.assignmentStatus
    })
  );

  let historical = [];
  let recorded = [];
  let error = "";

  try {
    const historySource = byId(
      "storage-legacy-projection"
    );

    if (historySource) {
      const parsed = JSON.parse(
        historySource.textContent || "{}"
      );

      if (
        !Array.isArray(parsed.nodes) ||
        !Array.isArray(parsed.samples)
      ) {
        throw Error("Invalid historical projection");
      }

      historical = parsed.nodes;
      recorded = parsed.samples;
    }

    const sceneSource = byId(
      "storage-scene-projection-v8"
    );

    if (sceneSource) {
      const scene = JSON.parse(
        sceneSource.textContent || "null"
      );

      if (scene != null) {
        if (!window.B3StorageSceneFilterV8?.scope) {
          throw Error("Scene filter unavailable");
        }

        const scoped =
          window.B3StorageSceneFilterV8.scope(
            [
              ...physical.map(n => ({
                ...n,
                historical: false
              })),
              ...historical.map(n => ({
                ...n,
                historical: true
              }))
            ],
            [
              ...assignments.map(s => ({
                ...s,
                historical: false
              })),
              ...recorded.map(s => ({
                ...s,
                historical: true
              }))
            ],
            scene
          );

        if (
          !Array.isArray(scoped.nodes) ||
          !Array.isArray(scoped.samples)
        ) {
          throw Error("Invalid scene scope");
        }

        physical = scoped.nodes.filter(
          n => !n.historical
        );

        historical = scoped.nodes.filter(
          n => n.historical
        );

        assignments = scoped.samples.filter(
          s => !s.historical
        );

        recorded = scoped.samples.filter(
          s => s.historical
        );
      }
    }
  } catch (exc) {
    console.error(
      "B3 SVG storage projection",
      exc
    );

    physical = [];
    assignments = [];
    historical = [];
    recorded = [];

    error =
      "The authorized storage projection could not be loaded.";
  }

  const model = build(
    physical,
    historical,
    assignments,
    recorded
  );

  const SVG_NS = "http://www.w3.org/2000/svg";

  const svgElement = (name, attrs = {}) => {
    const element = document.createElementNS(
      SVG_NS, name
    );

    for (const [key, value] of Object.entries(attrs)) {
      element.setAttribute(key, String(value));
    }

    return element;
  };

  const htmlElement = (tag, text, className) => {
    const element = document.createElement(tag);

    if (text !== undefined) {
      element.textContent = text;
    }

    if (className) element.className = className;

    return element;
  };

  const style = htmlElement("style");

  style.textContent = `
    #storage-isometric-v813 {
      background: #ffffff;
      color: #243c4a;
      min-height: 420px;
      width: 100%;
      display: flex;
      flex-direction: column;
      border-radius: 8px;
      overflow: hidden;
    }
    .b3-iso-tools {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 12px;
      background: #ffffff;
      border-bottom: 1px solid #e1e9ee;
    }
    .b3-iso-canvas {
      flex: 1;
      min-height: 330px;
      max-height: 630px;
      overflow: auto;
      background: #ffffff;
    }
    .b3-iso-canvas svg {
      display: block;
      max-width: none;
      height: auto;
    }
    .b3-iso-card {
      cursor: pointer;
      outline: none;
    }
    .b3-iso-card:focus .b3-iso-front {
      stroke: #126cff;
      stroke-width: 3;
    }
    .b3-iso-card:hover .b3-iso-front {
      stroke: #126cff;
      stroke-width: 2.5;
    }
    .b3-iso-footer {
      border-top: 1px solid #e1e9ee;
      padding: 10px 12px;
      font-size: .85rem;
      background: #ffffff;
      overflow-wrap: anywhere;
    }
    .b3-iso-footer strong {
      color: #1b394d;
    }
  `;

  document.head.append(style);

  const toolbar = htmlElement("div", undefined, "b3-iso-tools");
  const canvasHost = htmlElement(
    "div", undefined, "b3-iso-canvas"
  );
  const footer = htmlElement(
    "div", undefined, "b3-iso-footer"
  );

  const back = htmlElement(
    "button", "Up one level",
    "btn btn-sm btn-outline-secondary"
  );

  const overview = htmlElement(
    "button", "All equipment",
    "btn btn-sm btn-outline-secondary"
  );

  const zoom = htmlElement("input");
  zoom.type = "range";
  zoom.min = "70";
  zoom.max = "150";
  zoom.step = "10";
  zoom.value = "100";
  zoom.setAttribute("aria-label", "Isometric zoom");

  const zoomLabel = htmlElement("span", "100%");

  toolbar.append(
    back,
    overview,
    htmlElement("span", "Zoom"),
    zoom,
    zoomLabel
  );

  viewport.append(toolbar, canvasHost, footer);

  const status = byId("storage-3d-status");
  const listing = byId("storage-3d-objects");
  const crumbs = byId("storage-3d-breadcrumbs");
  const selectionText = byId("storage-3d-selection");

  const modes = document.querySelectorAll(
    "[data-v5-view]"
  );

  for (const button of modes) {
    if (button.dataset.v5View === "split") {
      button.textContent = "Isometric + 2D";
    }

    if (button.dataset.v5View === "3d") {
      button.textContent = "Isometric";
    }
  }

  function text(svg, x, y, value, size, weight) {
    const node = svgElement("text", {
      x, y,
      "font-size": size,
      "font-weight": weight || "normal",
      fill: "#20394a"
    });

    node.textContent = value;
    svg.append(node);

    return node;
  }

  let focus = null;
  let zoomValue = 100;

  function getChildren(key) {
    return [...model.nodes.values()]
      .filter(node =>
        (node.parentKey || null) === key
      )
      .sort((a, b) =>
        a.name.localeCompare(b.name, "en", {
          numeric: true
        })
      );
  }

  function pathFor(node) {
    const result = [];
    const visited = new Set();
    let current = node;

    while (current && !visited.has(current.key)) {
      visited.add(current.key);
      result.unshift(current.name);

      current = current.parentKey
        ? model.nodes.get(current.parentKey)
        : null;
    }

    return result.join(" › ");
  }

  function publishSelection(node) {
    const directSamples =
      model.samples.get(node.key) || [];

    const isBox = node.kind.includes("box") ||
      directSamples.length > 0;

    document.dispatchEvent(
      new CustomEvent("b3-spatial-v5-box", {
        detail: {
          mode: "live",
          box: isBox ? {
            id: node.id,
            name: node.name,
            path: pathFor(node)
          } : null,
          samples: isBox ? directSamples : [],
          picked: null
        }
      })
    );

    document.dispatchEvent(
      new CustomEvent("b3-storage-2d-navigate", {
        detail: {id: node.id}
      })
    );

    if (!node.historical) {
      document.dispatchEvent(
        new CustomEvent("b3-storage-select-request", {
          detail: {id: node.id}
        })
      );
    }
  }

  function select(key, notify = true) {
    if (key && !model.nodes.has(key)) return;

    focus = key;
    render();

    if (notify && key) {
      publishSelection(model.nodes.get(key));
    } else if (notify && !key) {
      document.dispatchEvent(
        new CustomEvent("b3-spatial-v5-box", {
          detail: {
            mode: "live",
            box: null,
            samples: [],
            picked: null
          }
        })
      );
    }
  }

  function drawCard(svg, item) {
    const {node, point, count} = item;
    const {x, y} = point;

    const group = svgElement("g", {
      class: "b3-iso-card",
      role: "button",
      tabindex: "0",
      "aria-label": `${node.name}, ${count} Samples`
    });

    const top = node.historical
      ? "#ffe5be" : "#daeaf3";

    const front = node.historical
      ? "#fff7ea" : "#ffffff";

    const side = node.historical
      ? "#e8ba79" : "#a8c8d9";

    const surfaces = [
      ["polygon", {
        points:
          `${x},${y+29} ${x+164},${y+29} ` +
          `${x+190},${y+12} ${x+26},${y+12}`,
        fill: top, stroke: "#90aaba"
      }],
      ["polygon", {
        points:
          `${x+164},${y+29} ${x+190},${y+12} ` +
          `${x+190},${y+70} ${x+164},${y+87}`,
        fill: side, stroke: "#90aaba"
      }],
      ["rect", {
        x, y: y+29,
        width: 164, height: 58,
        rx: 5,
        class: "b3-iso-front",
        fill: front,
        stroke: "#90aaba"
      }]
    ];

    for (const [tag, attrs] of surfaces) {
      group.append(svgElement(tag, attrs));
    }

    const name = node.name.length > 22
      ? node.name.slice(0, 21) + "…"
      : node.name;

    text(group, x+9, y+50, name, 12, "600");
    text(
      group, x+9, y+69,
      `${node.kind || "location"} · ${count} Samples`,
      10
    );

    const title = svgElement("title");
    title.textContent =
      pathFor(node) +
      (node.historical
        ? " — Historical, read-only"
        : " — Registered location");

    group.append(title);

    group.addEventListener("click", () => {
      select(node.key);
    });

    group.addEventListener("keydown", event => {
      if (
        event.key === "Enter" ||
        event.key === " "
      ) {
        event.preventDefault();
        select(node.key);
      }
    });

    svg.append(group);
  }

  function updateNavigation() {
    const node = focus
      ? model.nodes.get(focus)
      : null;

    back.disabled = !node;
    overview.disabled = !node;

    if (selectionText) {
      selectionText.textContent = node
        ? pathFor(node)
        : "Select a location.";
    }

    if (crumbs) {
      crumbs.replaceChildren();

      const button = htmlElement(
        "button", "Overview",
        "btn btn-sm btn-link p-0"
      );

      button.type = "button";
      button.addEventListener("click", () => {
        select(null);
      });

      crumbs.append(button);

      if (node) {
        const label = htmlElement(
          "span", " › " + pathFor(node)
        );

        crumbs.append(label);
      }
    }

    if (listing) {
      listing.replaceChildren();

      const children = getChildren(focus);

      for (const child of children) {
        const button = htmlElement(
          "button",
          child.name,
          "btn btn-sm btn-outline-secondary mb-1"
        );

        button.type = "button";

        button.addEventListener("click", () => {
          select(child.key);
        });

        listing.append(button);
      }
    }
  }

  function render() {
    updateNavigation();
    canvasHost.replaceChildren();
    footer.replaceChildren();

    if (error) {
      footer.textContent = error;
      if (status) status.textContent = error;
      return;
    }

    const graph = layout(model, focus);

    if (!graph.items.length) {
      const message =
        "No authorized storage locations are available.";

      footer.textContent = message;
      if (status) status.textContent = message;
      return;
    }

    const svg = svgElement("svg", {
      viewBox: `0 0 ${graph.width} ${graph.height}`,
      width: graph.width,
      height: graph.height,
      role: "group",
      "aria-label": "Isometric storage hierarchy"
    });

    svg.style.width =
      Math.round(
        graph.width * zoomValue / 100
      ) + "px";

    for (const edge of graph.edges) {
      const {a, b} = edge;

      const x1 = a.x + 190;
      const y1 = a.y + 49;
      const x2 = b.x;
      const y2 = b.y + 49;

      const mid = (x1 + x2) / 2;

      svg.append(
        svgElement("path", {
          d: `M${x1},${y1} H${mid} V${y2} H${x2}`,
          fill: "none",
          stroke: "#b3c8d6",
          "stroke-width": 2
        })
      );
    }

    for (const item of graph.items) {
      drawCard(svg, item);
    }

    canvasHost.append(svg);

    const current = focus
      ? model.nodes.get(focus)
      : null;

    const label = current
      ? pathFor(current)
      : "All authorized equipment";

    footer.append(
      htmlElement("strong", label)
    );

    const count = current
      ? model.counts.get(current.key) || 0
      : [...model.samples.values()].reduce(
          (sum, samples) => sum + samples.length,
          0
        );

    footer.append(
      htmlElement(
        "div",
        `${count} recorded Samples · ` +
        `${graph.items.length} visible locations`
      )
    );

    if (current?.historical) {
      footer.append(
        htmlElement(
          "div",
          "Historical registration — read-only. " +
          "Not an authorized movement destination."
        )
      );
    }

    const samples = current
      ? model.samples.get(current.key) || []
      : [];

    if (samples.length) {
      footer.append(
        htmlElement(
          "div",
          samples.slice(0, 30).map(sample =>
            `${sample.position || "?"}: ${sample.code}`
          ).join(" · ")
        )
      );
    }

    if (graph.truncated) {
      footer.append(
        htmlElement(
          "div",
          "Large hierarchy: select a location " +
          "to inspect its descendants."
        )
      );
    }

    if (status) {
      status.textContent =
        "SVG isometric renderer active. " +
        "No WebGL required.";
    }
  }

  back.addEventListener("click", () => {
    const node = focus
      ? model.nodes.get(focus)
      : null;

    select(node?.parentKey || null);
  });

  overview.addEventListener("click", () => {
    select(null);
  });

  zoom.addEventListener("input", () => {
    zoomValue = Number(zoom.value);
    zoomLabel.textContent = zoomValue + "%";
    render();
  });

  document.addEventListener(
    "b3-storage-location-selected",
    event => {
      const key = "p:" + str(event.detail?.id);

      if (model.nodes.has(key) && focus !== key) {
        select(key, false);
      }
    }
  );

  window.B3StorageSVGV813.ready = true;

  render();
})();
