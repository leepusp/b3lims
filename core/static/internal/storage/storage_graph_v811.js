/*
 * B3 LIMS V8.11B — Graphical storage hierarchy refinement.
 * White theme + richer interaction + graph/outline modes.
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
    term = "",
    showSamples = true
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

        if (showSamples && selected === node.key) {
          const list = (
            model.samples.get(node.key) || []
          ).slice(0, 36);

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
            maxDepth = Math.max(maxDepth, depth + 1);
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
          from: node.key,
          to: child.key,
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

    for (const n of model.nodes.values()) {
      if (!visited.has(n.key)) {
        visit(n, 0);
      }
    }

    return {
      result,
      edges,
      width: Math.max(
        560,
        24 + maxDepth * 235 + 230
      ),
      height: Math.max(
        300,
        45 + Math.max(row, 1) * 77 + 36
      )
    };
  }

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
      border: 1px solid #d8e3ea;
      border-radius: 12px;
      background: #ffffff;
      overflow: hidden;
      color: #1d3642;
      box-shadow: 0 1px 2px rgba(16, 42, 67, 0.05);
    }
    .b3gv-tools {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding: 12px;
      background: #ffffff;
      border-bottom: 1px solid #e5edf2;
    }
    .b3gv-tools strong {
      margin-right: auto;
      color: #17384a;
      font-size: 1.02rem;
    }
    .b3gv-tools input,
    .b3gv-tools select {
      max-width: 250px;
    }
    .b3gv-tools label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin: 0;
      font-size: .86rem;
      color: #4d6675;
      white-space: nowrap;
    }
    .b3gv-tools .btn-sm {
      padding: .28rem .55rem;
    }
    .b3gv-status,
    .b3gv-detail {
      padding: 10px 12px;
      font-size: .85rem;
      color: #526c7b;
      border-top: 1px solid #e5edf2;
      background: #ffffff;
    }
    .b3gv-canvas {
      background: #ffffff;
      overflow: auto;
      max-height: 670px;
      min-height: 310px;
    }
    .b3gv-stage-wrap {
      padding: 14px;
      min-width: 100%;
    }
    .b3gv-stage {
      position: relative;
      transform-origin: top left;
    }
    .b3gv-wires {
      position: absolute;
      inset: 0;
      pointer-events: none;
    }
    .b3gv-node {
      position: absolute;
      width: 195px;
      min-height: 58px;
      background: #ffffff;
      border: 1px solid #c9d8e2;
      border-left: 4px solid #2d7ff9;
      border-radius: 10px;
      padding: 7px 9px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      text-align: left;
      color: #1f3340;
      cursor: pointer;
      transition: box-shadow .15s ease, transform .15s ease, border-color .15s ease;
    }
    .b3gv-node:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba(29, 54, 66, .10);
    }
    .b3gv-node.historical {
      background: #fff8ef;
      border-color: #e6c490;
      border-left-color: #c68b38;
    }
    .b3gv-node.selected {
      box-shadow: 0 0 0 3px rgba(45,127,249,.18);
      border-color: #7db2ff;
      background: #f5faff;
    }
    .b3gv-node.focus {
      box-shadow: 0 0 0 2px rgba(45,127,249,.12);
    }
    .b3gv-node strong {
      font-size: .84rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .b3gv-node small {
      color: #667b88;
      font-size: .72rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .b3gv-toggle {
      position: absolute;
      width: 24px;
      height: 24px;
      border: 1px solid #b7c9d5;
      background: #ffffff;
      color: #295d7c;
      border-radius: 50%;
      font-weight: 700;
      z-index: 2;
      box-shadow: 0 1px 2px rgba(16, 42, 67, .08);
    }
    .b3gv-empty {
      padding: 24px;
      color: #647b89;
    }
    .b3gv-detail {
      line-height: 1.7;
      overflow-wrap: anywhere;
    }
    .b3gv-detail strong {
      color: #1c3643;
      display: inline-block;
      margin-bottom: 3px;
    }
    .b3gv-badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 6px;
    }
    .b3gv-badge {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: .73rem;
      background: #eef5fb;
      color: #315067;
      border: 1px solid #d7e5ef;
    }
    .b3gv-outline {
      padding: 16px 14px 18px;
      background: #ffffff;
    }
    .b3gv-outline ul {
      list-style: none;
      margin: 0;
      padding-left: 20px;
      border-left: 1px dashed #d4e0e8;
    }
    .b3gv-outline > ul {
      padding-left: 0;
      border-left: none;
    }
    .b3gv-outline li {
      margin: 8px 0;
    }
    .b3gv-outline-row {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .b3gv-outline-row button {
      border-radius: 8px;
    }
    .b3gv-outline-tag {
      font-size: .73rem;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid #d7e5ef;
      background: #f6fafc;
      color: #5d7380;
    }
    .b3gv-outline-row .historical-tag {
      background: #fff6e8;
      border-color: #ecd0a4;
      color: #8c6428;
    }
    .b3gv-divider {
      height: 1px;
      background: #e5edf2;
      margin: 10px 0;
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
      ? Array.from(template.content.querySelectorAll(selector), fn)
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
      document.getElementById("storage-explorer-assignment-data"),
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
      const raw = document.getElementById("storage-legacy-projection");

      if (raw) {
        const parsed = JSON.parse(raw.textContent || "{}");

        if (
          !Array.isArray(parsed.nodes) ||
          !Array.isArray(parsed.samples)
        ) {
          throw Error("Invalid historical projection");
        }

        history = parsed.nodes;
        recorded = parsed.samples;
      }

      const scene = document.getElementById("storage-scene-projection-v8");
      const projection = scene
        ? JSON.parse(scene.textContent || "null")
        : null;

      if (projection != null) {
        if (!window.B3StorageSceneFilterV8?.scope) {
          throw Error("Scene filter unavailable");
        }

        const scoped = window.B3StorageSceneFilterV8.scope(
          [
            ...physical.map(x => ({...x, historical: false})),
            ...history.map(x => ({...x, historical: true}))
          ],
          [
            ...assignments.map(x => ({...x, historical: false})),
            ...recorded.map(x => ({...x, historical: true}))
          ],
          projection
        );

        if (
          !Array.isArray(scoped.nodes) ||
          !Array.isArray(scoped.samples)
        ) {
          throw Error("Invalid scene scope");
        }

        physical = scoped.nodes.filter(x => !x.historical);
        history = scoped.nodes.filter(x => x.historical);
        assignments = scoped.samples.filter(x => !x.historical);
        recorded = scoped.samples.filter(x => x.historical);
      }
    } catch (exc) {
      console.error("B3 hierarchy projection", exc);

      physical = [];
      history = [];
      assignments = [];
      recorded = [];
      error = "Storage projection could not be safely loaded.";
    }

    const model = build(physical, history, assignments, recorded);

    const oldPanel = document.getElementById("storage-relationship-v89");
    if (oldPanel) oldPanel.hidden = true;

    const shell = make("section", "b3gv");
    const tools = make("div", "b3gv-tools");
    const status = make("div", "b3gv-status");
    const canvas = make("div", "b3gv-canvas");
    const details = make("div", "b3gv-detail");

    const title = make("strong", "", "Graphical storage hierarchy");

    const search = make("input", "form-control form-control-sm");
    search.type = "search";
    search.placeholder = "Search locations or Samples";
    search.setAttribute("aria-label", "Search storage hierarchy");

    const scope = make("select", "form-select form-select-sm");
    for (const [value, label] of [
      ["all", "All authorized"],
      ["p", "Registered physical"],
      ["h", "Historical / read-only"]
    ]) {
      const option = make("option", "", label);
      option.value = value;
      scope.append(option);
    }

    const mode = make("select", "form-select form-select-sm");
    for (const [value, label] of [
      ["graph", "Graph"],
      ["outline", "Outline"]
    ]) {
      const option = make("option", "", label);
      option.value = value;
      mode.append(option);
    }

    const samplesLabel = make("label", "");
    const samplesToggle = make("input", "");
    samplesToggle.type = "checkbox";
    samplesToggle.checked = true;
    samplesLabel.append(samplesToggle, document.createTextNode("Show samples"));

    const zoomLabel = make("label", "");
    const zoomRange = make("input", "");
    zoomRange.type = "range";
    zoomRange.min = "70";
    zoomRange.max = "150";
    zoomRange.step = "5";
    zoomRange.value = "100";
    zoomRange.style.width = "120px";
    const zoomText = make("span", "", "100%");
    zoomLabel.append(document.createTextNode("Zoom"), zoomRange, zoomText);

    const expandAll = make("button", "btn btn-sm btn-outline-secondary", "Expand all");
    expandAll.type = "button";

    const collapseAll = make("button", "btn btn-sm btn-outline-secondary", "Collapse all");
    collapseAll.type = "button";

    tools.append(
      title,
      search,
      scope,
      mode,
      samplesLabel,
      zoomLabel,
      expandAll,
      collapseAll
    );

    shell.append(tools, status, canvas, details);
    host.prepend(shell);

    let selected = null;
    let hovered = null;
    let currentMode = "graph";
    let showSamples = true;
    let zoom = 100;
    const collapsed = new Set();

    function childrenMap(nodesMap) {
      const map = new Map();
      for (const n of nodesMap.values()) {
        if (!map.has(n.parentKey)) {
          map.set(n.parentKey, []);
        }
        map.get(n.parentKey).push(n);
      }
      for (const list of map.values()) {
        list.sort((a, b) =>
          a.name.localeCompare(b.name, "en", {numeric: true})
        );
      }
      return map;
    }

    function visibleSubset() {
      if (scope.value === "all") return model;

      return {
        nodes: new Map(
          [...model.nodes].filter(([key]) =>
            key.startsWith(scope.value + ":")
          )
        ),
        samples: new Map(
          [...model.samples].filter(([key]) =>
            key.startsWith(scope.value + ":")
          )
        ),
        counts: model.counts
      };
    }

    function ancestorsOf(key, nodesMap) {
      const out = new Set();
      let current = key;
      const visited = new Set();

      while (current && !visited.has(current)) {
        visited.add(current);
        out.add(current);

        if (current.startsWith("s:")) {
          current = current.slice(2).split("|")[0];
          continue;
        }

        current = nodesMap.get(current)?.parentKey || null;
      }

      return out;
    }

    function dispatchNodeSelection(node) {
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

    function nodeDetails(node, subset) {
      details.replaceChildren();

      if (!node) {
        details.textContent =
          "Select a node to inspect its path, type and recorded Samples.";
        return;
      }

      const path = [];
      let key = node.key;
      const visited = new Set();

      while (key && !visited.has(key) && subset.nodes.has(key)) {
        visited.add(key);
        const item = subset.nodes.get(key);
        path.unshift(item.name);
        key = item.parentKey;
      }

      details.append(
        make("strong", "", node.name),
        make("div", "", path.join(" › ")),
        make(
          "div",
          "",
          `${subset.counts.get(node.key) || 0} Samples in subtree`
        )
      );

      const badges = make("div", "b3gv-badges");
      const type = make("span", "b3gv-badge", node.type);
      const nature = make(
        "span",
        "b3gv-badge",
        node.historical ? "Historical / read-only" : "Registered physical"
      );
      badges.append(type, nature);
      details.append(badges);

      const list = subset.samples.get(node.key) || [];
      if (list.length) {
        details.append(make("div", "b3gv-divider"));
        details.append(
          make(
            "div",
            "",
            list
              .slice(0, 24)
              .map(x => `${x.position || "?"}: ${x.code}`)
              .join(" · ")
          )
        );
      }
    }

    function renderOutline(subset) {
      const wrap = make("div", "b3gv-outline");
      const children = childrenMap(subset.nodes);

      const query = search.value.trim().toLowerCase();

      const matchesNode = node => {
        if (!query) return true;

        const sampleMatch = (subset.samples.get(node.key) || []).some(
          sample =>
            `${sample.code} ${sample.position}`.toLowerCase().includes(query)
        );

        return (
          `${node.name} ${node.type} ${node.path}`.toLowerCase().includes(query) ||
          sampleMatch
        );
      };

      const hasMatchingDescendant = node => {
        if (matchesNode(node)) return true;
        for (const child of children.get(node.key) || []) {
          if (hasMatchingDescendant(child)) return true;
        }
        return false;
      };

      function renderNode(node) {
        if (!hasMatchingDescendant(node)) return null;

        const li = make("li", "");
        const row = make("div", "b3gv-outline-row");

        if ((children.get(node.key) || []).length > 0) {
          const t = make(
            "button",
            "btn btn-sm btn-outline-secondary",
            collapsed.has(node.key) ? "+" : "−"
          );
          t.type = "button";
          t.addEventListener("click", () => {
            if (collapsed.has(node.key)) collapsed.delete(node.key);
            else collapsed.add(node.key);
            render();
          });
          row.append(t);
        }

        const btn = make(
          "button",
          "btn btn-sm " + (selected === node.key ? "btn-primary" : "btn-outline-secondary"),
          node.name
        );
        btn.type = "button";
        btn.addEventListener("click", () => {
          selected = node.key;
          dispatchNodeSelection(node);
          render();
        });

        const type = make("span", "b3gv-outline-tag", node.type);
        const nature = make(
          "span",
          "b3gv-outline-tag" + (node.historical ? " historical-tag" : ""),
          node.historical ? "Historical" : "Registered"
        );
        const count = make(
          "span",
          "b3gv-outline-tag",
          `${subset.counts.get(node.key) || 0} Samples`
        );

        row.append(btn, type, nature, count);
        li.append(row);

        if (showSamples && selected === node.key) {
          const samples = subset.samples.get(node.key) || [];
          if (samples.length) {
            const sampleLine = make(
              "div",
              "mt-2 ms-2 text-muted",
              samples
                .slice(0, 24)
                .map(x => `${x.position || "?"}: ${x.code}`)
                .join(" · ")
            );
            li.append(sampleLine);
          }
        }

        if (!collapsed.has(node.key)) {
          const childNodes = children.get(node.key) || [];
          if (childNodes.length) {
            const ul = make("ul", "");
            for (const child of childNodes) {
              const childLi = renderNode(child);
              if (childLi) ul.append(childLi);
            }
            li.append(ul);
          }
        }

        return li;
      }

      const roots = children.get(null) || [];
      const rootList = make("ul", "");

      for (const root of roots) {
        const rootLi = renderNode(root);
        if (rootLi) rootList.append(rootLi);
      }

      if (!rootList.children.length) {
        wrap.append(
          make("p", "b3gv-empty", error || "No authorized locations available in this view.")
        );
        return wrap;
      }

      wrap.append(rootList);
      return wrap;
    }

    function renderGraph(subset) {
      const graph = position(
        subset,
        collapsed,
        selected,
        search.value,
        showSamples
      );

      if (!graph.result.length) {
        canvas.append(
          make(
            "p",
            "b3gv-empty",
            error || "No authorized locations available in this view."
          )
        );
        return;
      }

      const focus = ancestorsOf(hovered || selected, subset.nodes);

      const stageWrap = make("div", "b3gv-stage-wrap");
      const stage = make("div", "b3gv-stage");
      stage.style.width = graph.width + "px";
      stage.style.height = graph.height + "px";
      stage.style.transform = `scale(${zoom / 100})`;

      const scaledWrapHeight = Math.max(
        320,
        graph.height * (zoom / 100) + 24
      );
      stageWrap.style.minHeight = scaledWrapHeight + "px";

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "b3gv-wires");
      svg.setAttribute("width", String(graph.width));
      svg.setAttribute("height", String(graph.height));
      svg.setAttribute("aria-hidden", "true");

      for (const edge of graph.edges) {
        const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
        const x1 = edge.a.x + 195;
        const y1 = edge.a.y + 28;
        const x2 = edge.b.x;
        const y2 = edge.b.y + 28;
        const mid = (x1 + x2) / 2;

        line.setAttribute(
          "d",
          `M${x1} ${y1} H${mid} V${y2} H${x2}`
        );

        const active =
          focus.has(edge.from) && focus.has(edge.to);

        line.setAttribute("stroke", active ? "#2d7ff9" : "#b7c8d4");
        line.setAttribute("stroke-width", active ? "2.4" : "1.6");
        line.setAttribute("fill", "none");
        svg.append(line);
      }

      stage.append(svg);

      for (const item of graph.result) {
        const button = make("button", "b3gv-node");
        button.type = "button";
        button.style.left = item.x + "px";
        button.style.top = item.y + "px";

        button.classList.toggle(
          "historical",
          item.node?.historical ||
          Boolean(item.sample && item.sample.boxKey.startsWith("h:"))
        );

        button.classList.toggle("selected", item.key === selected);
        button.classList.toggle("focus", focus.has(item.key));

        button.append(
          make(
            "strong",
            "",
            item.node?.name || item.sample?.code || "Location"
          ),
          make(
            "small",
            "",
            item.sample
              ? (item.sample.position || "Position not recorded")
              : (
                  `${item.node.type} · ${item.count} Samples` +
                  (item.node.historical ? " · Historical" : "")
                )
          )
        );

        button.addEventListener("mouseenter", () => {
          hovered = item.sample ? item.sample.boxKey : item.key;
          render();
        });

        button.addEventListener("mouseleave", () => {
          hovered = null;
          render();
        });

        button.addEventListener("click", () => {
          selected = item.sample ? item.sample.boxKey : item.key;
          render();

          if (item.node) {
            dispatchNodeSelection(item.node);
          }
        });

        button.addEventListener("dblclick", () => {
          if (item.node?.hasChildren || item.hasChildren) {
            if (collapsed.has(item.key)) collapsed.delete(item.key);
            else collapsed.add(item.key);
            render();
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
          toggle.style.left = item.x + 178 + "px";
          toggle.style.top = item.y - 12 + "px";

          toggle.setAttribute(
            "aria-label",
            `${collapsed.has(item.key) ? "Expand" : "Collapse"} ${item.node.name}`
          );

          toggle.addEventListener("click", evt => {
            evt.stopPropagation();
            if (collapsed.has(item.key)) collapsed.delete(item.key);
            else collapsed.add(item.key);
            render();
          });

          stage.append(toggle);
        }
      }

      stageWrap.append(stage);
      canvas.append(stageWrap);
    }

    function render() {
      canvas.replaceChildren();

      const demo =
        document.getElementById("storage-3d-example")
          ?.getAttribute("aria-pressed") === "true";

      if (demo) {
        status.textContent = "Example mode is isolated.";
        details.textContent = "Switch to Live inventory to inspect authorized storage.";
        canvas.append(
          make(
            "p",
            "b3gv-empty",
            "Select Live inventory to inspect authorized storage."
          )
        );
        return;
      }

      const subset = visibleSubset();

      const totalSamples = [...subset.samples.values()].reduce(
        (n, items) => n + items.length,
        0
      );

      status.textContent = error ||
        `${subset.nodes.size} locations · ${totalSamples} recorded Samples · ` +
        `${currentMode === "graph" ? "Graph" : "Outline"} view`;

      const selectedNode = subset.nodes.get(selected);
      nodeDetails(selectedNode, subset);

      if (currentMode === "outline") {
        canvas.append(renderOutline(subset));
      } else {
        renderGraph(subset);
      }
    }

    expandAll.addEventListener("click", () => {
      collapsed.clear();
      render();
    });

    collapseAll.addEventListener("click", () => {
      const subset = visibleSubset();
      for (const key of subset.nodes.keys()) {
        collapsed.add(key);
      }
      render();
    });

    search.addEventListener("input", render);

    scope.addEventListener("change", () => {
      selected = null;
      render();
    });

    mode.addEventListener("change", () => {
      currentMode = mode.value;
      render();
    });

    samplesToggle.addEventListener("change", () => {
      showSamples = samplesToggle.checked;
      render();
    });

    zoomRange.addEventListener("input", () => {
      zoom = Number(zoomRange.value);
      zoomText.textContent = `${zoom}%`;
      render();
    });

    for (const id of ["storage-3d-example", "storage-3d-real"]) {
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
    document.addEventListener("DOMContentLoaded", init, {once: true});
  } else {
    init();
  }
})();
