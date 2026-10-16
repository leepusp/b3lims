/*
 * B3 LIMS V8.11 — Graphical storage hierarchy.
 *
 * Read-only visualization of already authorized Django data.
 * Historical nodes are never physical movement targets.
 */
(() => {
  "use strict";

  const s = v => v == null ? "" : String(v);

  function build(physical, history, assignments, recorded) {
    const nodes = new Map();
    const samples = new Map();
    const counts = new Map();

    for (const [rows, prefix] of [
      [physical, "p"],
      [history, "h"]
    ]) {
      for (const raw of rows) {
        if (!raw || !s(raw.id)) continue;

        const key = `${prefix}:${s(raw.id)}`;

        if (!nodes.has(key)) {
          nodes.set(key, {
            key,
            id: s(raw.id),
            parent: s(raw.parent),
            name: s(raw.name) || "Location",
            type: s(raw.kind || raw.type) || "Location",
            historical: prefix === "h",
            path: s(raw.path)
          });
        }
      }
    }

    // Resolve parent relationships without mixing
    // historical and registered location identities.
    for (const n of nodes.values()) {
      let key = `${n.historical ? "h" : "p"}:${n.parent}`;

      n.parentKey =
        n.parent && nodes.has(key) ? key : null;

      const visited = new Set([n.key]);

      while (key && nodes.has(key)) {
        if (visited.has(key)) {
          n.parentKey = null;
          break;
        }

        visited.add(key);

        const ancestor = nodes.get(key);

        key = ancestor.parent
          ? `${ancestor.historical ? "h" : "p"}:${ancestor.parent}`
          : "";
      }
    }

    const seenSamples = new Set();

    for (const [rows, prefix] of [
      [assignments, "p"],
      [recorded, "h"]
    ]) {
      for (const raw of rows) {
        if (!raw || raw.status === "inactive") continue;

        if (
          prefix === "p" &&
          raw.status &&
          raw.status !== "active"
        ) continue;

        const boxKey =
          `${prefix}:${s(raw.box || raw.location)}`;

        if (!nodes.has(boxKey)) continue;

        const sample = {
          key: [
            boxKey,
            s(raw.id),
            s(raw.code),
            s(raw.position)
          ].join("|"),
          code: s(raw.code) || "Sample",
          position: s(raw.position),
          boxKey
        };

        if (seenSamples.has(sample.key)) continue;

        seenSamples.add(sample.key);

        if (!samples.has(boxKey)) {
          samples.set(boxKey, []);
        }

        samples.get(boxKey).push(sample);

        let key = boxKey;
        const visited = new Set();

        while (
          key &&
          !visited.has(key) &&
          nodes.has(key)
        ) {
          visited.add(key);

          counts.set(
            key,
            (counts.get(key) || 0) + 1
          );

          key = nodes.get(key).parentKey;
        }
      }
    }

    return {nodes, samples, counts};
  }

  function position(
    model,
    collapsed = new Set(),
    selected = null,
    term = ""
  ) {
    const children = new Map();
    const result = [];
    const edges = [];

    for (const n of model.nodes.values()) {
      if (!children.has(n.parentKey)) {
        children.set(n.parentKey, []);
      }

      children.get(n.parentKey).push(n);
    }

    const compare = (a, b) =>
      a.name.localeCompare(b.name, "en", {
        numeric: true
      }) || a.key.localeCompare(b.key);

    for (const group of children.values()) {
      group.sort(compare);
    }

    const matches = new Set();
    const query = term.trim().toLowerCase();

    if (query) {
      for (const n of model.nodes.values()) {
        const sampleMatch = (
          model.samples.get(n.key) || []
        ).some(sample =>
          `${sample.code} ${sample.position}`
            .toLowerCase()
            .includes(query)
        );

        if (
          !`${n.name} ${n.type} ${n.path}`
            .toLowerCase()
            .includes(query) &&
          !sampleMatch
        ) continue;

        let key = n.key;
        const visited = new Set();

        while (key && !visited.has(key)) {
          visited.add(key);
          matches.add(key);

          key = model.nodes.get(key)?.parentKey || null;
        }
      }
    }

    let row = 0;
    let maxDepth = 0;

    const visited = new Set();

    const visit = (node, depth) => {
      if (
        visited.has(node.key) ||
        (query && !matches.has(node.key))
      ) return null;

      visited.add(node.key);

      const descendants = [];

      if (!collapsed.has(node.key) || query) {
        for (const child of children.get(node.key) || []) {
          const p = visit(child, depth + 1);

          if (p) {
            descendants.push({
              key: child.key,
              p
            });
          }
        }

        // Load only a limited number of sample nodes
        // for the selected box.
        if (selected === node.key) {
          const list = (
            model.samples.get(node.key) || []
          ).slice(0, 24);

          for (const sample of list) {
            const p = {
              x: 24 + (depth + 1) * 235,
              y: 45 + row++ * 77
            };

            const key = `s:${sample.key}`;

            result.push({
              key,
              sample,
              x: p.x,
              y: p.y
            });

            descendants.push({key, p});

            maxDepth = Math.max(
              maxDepth,
              depth + 1
            );
          }
        }
      }

      const p = {
        x: 24 + depth * 235,
        y: descendants.length
          ? (
              descendants[0].p.y +
              descendants[descendants.length - 1].p.y
            ) / 2
          : 45 + row++ * 77
      };

      result.push({
        key: node.key,
        node,
        x: p.x,
        y: p.y,
        count: model.counts.get(node.key) || 0,
        hasChildren:
          (children.get(node.key) || []).length > 0
      });

      for (const child of descendants) {
        edges.push({
          a: p,
          b: child.p
        });
      }

      maxDepth = Math.max(maxDepth, depth);

      return p;
    };

    for (const root of children.get(null) || []) {
      visit(root, 0);
    }

    // Defensive fallback for malformed relationships.
    for (const n of model.nodes.values()) {
      if (!visited.has(n.key)) {
        visit(n, 0);
      }
    }

    return {
      result,
      edges,
      width: Math.max(
        500,
        24 + maxDepth * 235 + 230
      ),
      height: Math.max(
        280,
        45 + Math.max(row, 1) * 77 + 28
      )
    };
  }

  // Expose pure functions for Node regression tests.
  if (typeof window !== "undefined") {
    window.B3GraphV811 = {build, position};
  }

  if (typeof document === "undefined") return;

  const host = document.getElementById(
    "b3-v810-hierarchy-view"
  );

  const source = document.getElementById(
    "storage-explorer-data"
  );

  if (!host || !source?.content) return;

  const style = document.createElement("style");

  style.textContent = `
    .b3gv {
      border:1px solid #d2dfe6;
      border-radius:9px;
      background:#fff;
      overflow:hidden;
      color:#1f3a49;
    }
    .b3gv-tools {
      display:flex;
      align-items:center;
      gap:10px;
      flex-wrap:wrap;
      padding:12px;
      background:#f4f7fa;
    }
    .b3gv-tools strong {margin-right:auto}
    .b3gv-tools input {max-width:265px}
    .b3gv-tools select {max-width:220px}
    .b3gv-status,.b3gv-detail {
      padding:10px 12px;
      font-size:.82rem;
      color:#526c7b;
      border-top:1px solid #e1e9ed;
    }
    .b3gv-canvas {
      background-color:#fafcfd;
      background-image:radial-gradient(
        #d9e2e8 .65px,transparent .65px
      );
      background-size:16px 16px;
      overflow:auto;
      max-height:650px;
      min-height:280px;
    }
    .b3gv-stage {
      position:relative;
      min-height:280px;
    }
    .b3gv-wires {
      position:absolute;
      inset:0;
      pointer-events:none;
    }
    .b3gv-node {
      position:absolute;
      width:195px;
      height:56px;
      background:#eaf3f8;
      border:1px solid #a7bfca;
      border-left:4px solid #317d9e;
      border-radius:8px;
      padding:5px 8px;
      display:flex;
      flex-direction:column;
      justify-content:center;
      text-align:left;
      color:#213c4b;
      cursor:pointer;
    }
    .b3gv-node.historical {
      background:#fff1d9;
      border-color:#cba86e;
      border-left-color:#b98739;
    }
    .b3gv-node.selected {
      box-shadow:0 0 0 3px #1172a055;
      background:#d7edf8;
    }
    .b3gv-node strong {
      font-size:.82rem;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }
    .b3gv-node small {
      color:#526a78;
      font-size:.7rem;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
    }
    .b3gv-toggle {
      position:absolute;
      width:24px;
      height:24px;
      border:1px solid #8faebd;
      background:#fff;
      color:#235d7d;
      border-radius:50%;
      font-weight:700;
      z-index:2;
    }
    .b3gv-empty {padding:22px}
    .b3gv-detail {
      line-height:1.8;
      overflow-wrap:anywhere;
    }
    @media(prefers-color-scheme:dark) {
      .b3gv {background:#202d36;color:#eef4f8}
      .b3gv-tools {background:#263943}
      .b3gv-node {background:#2d4b5b;color:#e8f1f7}
      .b3gv-node.historical {
        background:#4d3924;
        color:#fbe7ce;
      }
      .b3gv-node small {color:#b9cad4}
      .b3gv-canvas {background-color:#22313b}
    }
  `;

  document.head.append(style);

  const make = (tag, klass, value) => {
    const el = document.createElement(tag);

    if (klass) el.className = klass;
    if (value !== undefined) el.textContent = value;

    return el;
  };

  const elements = (template, selector, fn) =>
    template?.content
      ? Array.from(
          template.content.querySelectorAll(selector),
          fn
        )
      : [];

  function init() {
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
      document.getElementById(
        "storage-explorer-assignment-data"
      ),
      "[data-assignment-location]",
      el => ({
        box: el.dataset.assignmentLocation,
        id: el.dataset.assignmentId,
        code: el.dataset.assignmentSample,
        position: el.dataset.assignmentPosition,
        status: el.dataset.assignmentStatus
      })
    );

    let history = [];
    let recorded = [];
    let error = "";

    try {
      const raw = document.getElementById(
        "storage-legacy-projection"
      );

      if (raw) {
        const parsed = JSON.parse(
          raw.textContent || "{}"
        );

        if (
          !Array.isArray(parsed.nodes) ||
          !Array.isArray(parsed.samples)
        ) {
          throw Error("Invalid historical projection");
        }

        history = parsed.nodes;
        recorded = parsed.samples;
      }

      // Respect the active saved-scene filter.
      const scene = document.getElementById(
        "storage-scene-projection-v8"
      );

      const projection = scene
        ? JSON.parse(scene.textContent || "null")
        : null;

      if (projection != null) {
        if (!window.B3StorageSceneFilterV8?.scope) {
          throw Error("Scene filter unavailable");
        }

        const scoped = window.B3StorageSceneFilterV8.scope(
          [
            ...physical.map(x => ({
              ...x,
              historical: false
            })),
            ...history.map(x => ({
              ...x,
              historical: true
            }))
          ],
          [
            ...assignments.map(x => ({
              ...x,
              historical: false
            })),
            ...recorded.map(x => ({
              ...x,
              historical: true
            }))
          ],
          projection
        );

        if (
          !Array.isArray(scoped.nodes) ||
          !Array.isArray(scoped.samples)
        ) {
          throw Error("Invalid scene scope");
        }

        physical = scoped.nodes.filter(
          x => !x.historical
        );

        history = scoped.nodes.filter(
          x => x.historical
        );

        assignments = scoped.samples.filter(
          x => !x.historical
        );

        recorded = scoped.samples.filter(
          x => x.historical
        );
      }
    } catch (exc) {
      console.error(
        "B3 LIMS hierarchy projection",
        exc
      );

      // Fail closed rather than showing unrelated data.
      physical = [];
      history = [];
      assignments = [];
      recorded = [];

      error =
        "Storage projection could not be safely loaded.";
    }

    const model = build(
      physical,
      history,
      assignments,
      recorded
    );

    // The original V8.9 tree controller remains loaded,
    // but its simplified panel is replaced visually.
    const oldPanel = document.getElementById(
      "storage-relationship-v89"
    );

    if (oldPanel) oldPanel.hidden = true;

    const shell = make("section", "b3gv");
    const tools = make("div", "b3gv-tools");

    const title = make(
      "strong",
      "",
      "Graphical storage hierarchy"
    );

    const search = make(
      "input",
      "form-control form-control-sm"
    );

    search.type = "search";
    search.placeholder = "Search locations or Samples";

    search.setAttribute(
      "aria-label",
      "Search storage hierarchy"
    );

    const scope = make(
      "select",
      "form-select form-select-sm"
    );

    for (const [value, label] of [
      ["all", "All authorized"],
      ["p", "Registered physical"],
      ["h", "Historical / read-only"]
    ]) {
      const option = make("option", "", label);
      option.value = value;
      scope.append(option);
    }

    tools.append(title, search, scope);

    const status = make("div", "b3gv-status");
    const canvas = make("div", "b3gv-canvas");
    const details = make("div", "b3gv-detail");

    shell.append(
      tools,
      status,
      canvas,
      details
    );

    host.prepend(shell);

    let selected = null;
    const collapsed = new Set();

    function ancestry(node) {
      const path = [];
      const visited = new Set();

      let key = node?.key;

      while (
        key &&
        !visited.has(key) &&
        model.nodes.has(key)
      ) {
        visited.add(key);

        const item = model.nodes.get(key);

        path.unshift(item.name);
        key = item.parentKey;
      }

      return path.join(" › ");
    }

    function render() {
      canvas.replaceChildren();
      details.replaceChildren();

      const demo = document.getElementById(
        "storage-3d-example"
      )?.getAttribute("aria-pressed") === "true";

      if (demo) {
        status.textContent =
          "Example mode is isolated.";

        canvas.append(make(
          "p",
          "b3gv-empty",
          "Select Live inventory to inspect authorized storage."
        ));

        return;
      }

      const subset = scope.value === "all"
        ? model
        : {
            nodes: new Map(
              [...model.nodes].filter(
                ([key]) =>
                  key.startsWith(scope.value + ":")
              )
            ),
            samples: new Map(
              [...model.samples].filter(
                ([key]) =>
                  key.startsWith(scope.value + ":")
              )
            ),
            counts: model.counts
          };

      const graph = position(
        subset,
        collapsed,
        selected,
        search.value
      );

      const totalSamples = [
        ...subset.samples.values()
      ].reduce(
        (n, items) => n + items.length,
        0
      );

      status.textContent = error ||
        `${subset.nodes.size} locations · ` +
        `${totalSamples} recorded Samples · ` +
        "Click a box to show positions.";

      if (!graph.result.length) {
        canvas.append(make(
          "p",
          "b3gv-empty",
          error ||
            "No authorized locations available in this view."
        ));

        return;
      }

      const stage = make(
        "div",
        "b3gv-stage"
      );

      stage.style.width = graph.width + "px";
      stage.style.height = graph.height + "px";

      const svg = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "svg"
      );

      svg.setAttribute("class", "b3gv-wires");
      svg.setAttribute("width", String(graph.width));
      svg.setAttribute("height", String(graph.height));
      svg.setAttribute("aria-hidden", "true");

      for (const edge of graph.edges) {
        const line = document.createElementNS(
          "http://www.w3.org/2000/svg",
          "path"
        );

        const x1 = edge.a.x + 195;
        const y1 = edge.a.y + 28;
        const x2 = edge.b.x;
        const y2 = edge.b.y + 28;
        const mid = (x1 + x2) / 2;

        line.setAttribute(
          "d",
          `M${x1} ${y1} H${mid} V${y2} H${x2}`
        );

        line.setAttribute("stroke", "#8ba4b2");
        line.setAttribute("stroke-width", "1.7");
        line.setAttribute("fill", "none");

        svg.append(line);
      }

      stage.append(svg);

      for (const item of graph.result) {
        const button = make(
          "button",
          "b3gv-node"
        );

        button.type = "button";
        button.style.left = item.x + "px";
        button.style.top = item.y + "px";

        button.classList.toggle(
          "historical",
          item.node?.historical ||
          Boolean(
            item.sample &&
            item.sample.boxKey.startsWith("h:")
          )
        );

        button.classList.toggle(
          "selected",
          item.key === selected
        );

        button.append(
          make(
            "strong",
            "",
            item.node?.name ||
              item.sample?.code ||
              "Location"
          ),
          make(
            "small",
            "",
            item.sample
              ? (
                  item.sample.position ||
                  "Position not recorded"
                )
              : (
                  `${item.node.type} · ` +
                  `${item.count} Samples` +
                  (
                    item.node.historical
                      ? " · Historical"
                      : ""
                  )
                )
          )
        );

        button.addEventListener("click", () => {
          selected = item.sample
            ? item.sample.boxKey
            : item.key;

          render();

          if (item.node) {
            document.dispatchEvent(
              new CustomEvent(
                "b3-storage-2d-navigate",
                {
                  detail: {id: item.node.id}
                }
              )
            );

            // Only registered physical locations can
            // enter the Django explorer selection flow.
            if (!item.node.historical) {
              document.dispatchEvent(
                new CustomEvent(
                  "b3-storage-select-request",
                  {
                    detail: {id: item.node.id}
                  }
                )
              );
            }
          }
        });

        stage.append(button);

        if (item.node && item.hasChildren) {
          const toggle = make(
            "button",
            "b3gv-toggle",
            collapsed.has(item.key) ? "+" : "−"
          );

          toggle.type = "button";
          toggle.style.left =
            item.x + 178 + "px";

          toggle.style.top =
            item.y - 12 + "px";

          toggle.setAttribute(
            "aria-label",
            `${
              collapsed.has(item.key)
                ? "Expand"
                : "Collapse"
            } ${item.node.name}`
          );

          toggle.addEventListener("click", () => {
            if (collapsed.has(item.key)) {
              collapsed.delete(item.key);
            } else {
              collapsed.add(item.key);
            }

            render();
          });

          stage.append(toggle);
        }
      }

      canvas.append(stage);

      const node = model.nodes.get(selected);

      if (node && subset.nodes.has(node.key)) {
        details.append(
          make("strong", "", node.name),
          make("div", "", ancestry(node)),
          make(
            "div",
            "",
            `${model.counts.get(node.key) || 0} ` +
            "Samples in subtree · " +
            (
              node.historical
                ? "Historical, no movements"
                : "Registered physical location"
            )
          )
        );

        const list = model.samples.get(node.key) || [];

        if (list.length) {
          details.append(make(
            "div",
            "",
            list.slice(0, 24).map(
              x => `${x.position || "?"}: ${x.code}`
            ).join(" · ")
          ));
        }
      }
    }

    search.addEventListener("input", render);

    scope.addEventListener("change", () => {
      selected = null;
      render();
    });

    for (const id of [
      "storage-3d-example",
      "storage-3d-real"
    ]) {
      document.getElementById(id)?.addEventListener(
        "click",
        () => queueMicrotask(render)
      );
    }

    document.addEventListener(
      "b3-storage-location-selected",
      event => {
        const id = s(event.detail?.id);

        if (model.nodes.has("p:" + id)) {
          selected = "p:" + id;
          render();
        }
      }
    );

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      init,
      {once: true}
    );
  } else {
    init();
  }
})();
