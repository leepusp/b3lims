/*
 * B3 LIMS V8.9B — independent read-only 2D navigation.
 *
 * Only Django-authorized, already-rendered storage data are used.
 * Historical nodes are virtual and never become movement targets.
 */
(() => {
  "use strict";

  const byId = id => document.getElementById(id);
  const host = byId("b3-v5-views");
  const aside = host?.querySelector(".b3-v5-two");
  const source = byId("storage-explorer-data");

  if (!aside || !source?.content) return;

  const nodes = new Map();
  const samples = [];
  const str = value => value == null ? "" : String(value);

  function addNode(raw, historical) {
    const id = str(raw.id);

    if (!id || nodes.has(id)) return;

    nodes.set(id, {
      id,
      parent: str(raw.parent),
      name: str(raw.name) || "Location",
      kind: str(raw.kind),
      type: str(raw.type),
      path: str(raw.path),
      historical: Boolean(historical || raw.legacy)
    });
  }

  // Registered physical locations visible to this user.
  source.content
    .querySelectorAll("[data-location-id]")
    .forEach(el => {
      addNode({
        id: el.dataset.locationId,
        parent: el.dataset.parentId,
        name: el.dataset.locationName,
        kind: el.dataset.locationKind,
        type: el.dataset.locationType,
        path: el.dataset.locationPath
      }, false);
    });

  // Existing authorized physical Sample assignments.
  source.content
    .querySelectorAll("[data-assignment-location]")
    .forEach(el => {
      if (
        el.dataset.assignmentStatus &&
        el.dataset.assignmentStatus !== "active"
      ) return;

      samples.push({
        box: str(el.dataset.assignmentLocation),
        id: el.dataset.assignmentSampleId || null,
        code: str(el.dataset.assignmentSample) || "Sample",
        position: str(el.dataset.assignmentPosition),
        legacy: false
      });
    });

  // Historical read-only projection already supplied by Django.
  const legacyScript = byId("storage-legacy-projection");

  if (legacyScript) {
    try {
      const legacy = JSON.parse(
        legacyScript.textContent || "{}"
      );

      if (
        Array.isArray(legacy.nodes) &&
        Array.isArray(legacy.samples)
      ) {
        legacy.nodes.forEach(node => addNode(node, true));

        legacy.samples.forEach(sample => {
          if (sample && sample.status !== "inactive") {
            samples.push(sample);
          }
        });
      }
    } catch (error) {
      console.error(
        "Unable to load authorized historical 2D projection",
        error
      );
    }
  }

  const natural = (a, b) =>
    a.name.localeCompare(
      b.name, "en", {numeric: true}
    ) || a.id.localeCompare(b.id);

  // Index relationships once; avoid repeated full-tree scans.
  const childIndex = new Map();

  for (const node of nodes.values()) {
    const parent =
      node.parent && nodes.has(node.parent)
        ? node.parent
        : null;

    if (!childIndex.has(parent)) {
      childIndex.set(parent, []);
    }

    childIndex.get(parent).push(node);
  }

  for (const entries of childIndex.values()) {
    entries.sort(natural);
  }

  const children = parent => childIndex.get(parent) || [];

  const sampleCount = new Map();

  for (const sample of samples) {
    const key = str(sample.box);

    sampleCount.set(
      key,
      (sampleCount.get(key) || 0) + 1
    );
  }

  function trail(id) {
    const result = [];
    const seen = new Set();
    let cur = nodes.get(id);

    while (
      cur &&
      !seen.has(cur.id) &&
      result.length < 64
    ) {
      seen.add(cur.id);
      result.unshift(cur);
      cur = nodes.get(cur.parent);
    }

    return result;
  }

  const nav = document.createElement("section");

  nav.id = "b3-v89b-2d-navigation";
  nav.className = "border rounded p-2 mb-2 bg-light";
  nav.setAttribute(
    "aria-label",
    "2D storage hierarchy"
  );

  const heading = document.createElement("div");
  heading.className = "fw-semibold small mb-1";

  const breadcrumbs = document.createElement("div");
  breadcrumbs.className =
    "d-flex flex-wrap gap-1 mb-2";

  const choices = document.createElement("div");
  choices.className =
    "d-flex flex-wrap gap-1";

  const note = document.createElement("div");
  note.className = "small text-muted mt-2";

  nav.append(
    heading,
    breadcrumbs,
    choices,
    note
  );

  const summary = byId("b3-v5-summary");

  if (summary?.parentNode === aside) {
    aside.insertBefore(nav, summary);
  } else {
    aside.prepend(nav);
  }

  let active = null;

  function button(parent, label, fn, pressed = false) {
    const item = document.createElement("button");

    item.type = "button";
    item.className =
      `btn btn-sm ${
        pressed
          ? "btn-primary"
          : "btn-outline-secondary"
      }`;

    item.textContent = label;
    item.addEventListener("click", fn);
    parent.append(item);

    return item;
  }

  const demoActive = () =>
    byId("storage-3d-example")
      ?.getAttribute("aria-pressed") === "true";

  function render() {
    nav.hidden = demoActive();

    breadcrumbs.replaceChildren();
    choices.replaceChildren();

    const here = active ? nodes.get(active) : null;
    const path = here ? trail(here.id) : [];

    heading.textContent = here
      ? here.name
      : "2D · Storage locations";

    button(
      breadcrumbs,
      "Overview",
      () => choose(null),
      !here
    );

    path.forEach(node => {
      button(
        breadcrumbs,
        node.name,
        () => choose(node.id),
        node.id === active
      );
    });

    const direct = children(here?.id ?? null);

    direct.forEach(node => {
      const descendants = children(node.id).length;
      const count = sampleCount.get(node.id) || 0;

      const suffix = node.historical
        ? " · historical"
        : "";

      const item = button(
        choices,
        `${node.name}${suffix}${
          count ? ` · ${count} Sample(s)` : ""
        }`,
        () => choose(node.id)
      );

      item.title =
        `${node.type || node.kind || "Location"}; ` +
        `${descendants} child location(s)`;
    });

    note.textContent =
      here && !direct.length
        ? "Recorded positions are displayed below. " +
          "Empty cells are not confirmed free."
        : "Choose a freezer, rack or box. " +
          "Historical locations are read-only.";
  }

  function displayBox(node) {
    const chain = trail(node.id);

    const selectedSamples = samples
      .filter(sample => str(sample.box) === node.id)
      .map(sample => ({
        box: node.id,
        key: sample.id != null
          ? str(sample.id)
          : `demo:${node.id}:` +
            `${str(sample.position)}:` +
            `${str(sample.code)}`,
        code: str(sample.code) || "Sample",
        position: str(sample.position),
        legacy: Boolean(
          node.historical || sample.legacy
        ),
        url:
          typeof sample.url === "string" &&
          sample.url.startsWith("/") &&
          !sample.url.startsWith("//")
            ? sample.url
            : null,
        organism: sample.organism || ""
      }));

    const hasBoxProfile =
      /(?:^|[^a-z])(box|caixa)(?:$|[^a-z])/i.test(
        `${node.kind} ${node.type} ${node.name}`
      );

    const isLeafWithSamples =
      selectedSamples.length &&
      !children(node.id).length;

    const box =
      hasBoxProfile || isLeafWithSamples
        ? {
            id: node.id,
            name: node.name,
            path:
              node.path ||
              chain.map(item => item.name).join(" > ")
          }
        : null;

    // Reuse the established read-only 2D position renderer.
    document.dispatchEvent(
      new CustomEvent("b3-spatial-v5-box", {
        detail: {
          mode: "live",
          box,
          samples: box ? selectedSamples : [],
          picked: null
        }
      })
    );
  }

  function choose(id, notify = true) {
    if (id !== null && !nodes.has(str(id))) {
      return;
    }

    active = id === null ? null : str(id);

    const node = active
      ? nodes.get(active)
      : null;

    render();

    if (node) {
      displayBox(node);
    } else {
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

    if (notify && !demoActive()) {
      // Presentation-only selection for the 3D viewer.
      document.dispatchEvent(
        new CustomEvent("b3-storage-2d-navigate", {
          detail: {id: active}
        })
      );

      // Only registered physical locations may reach
      // the existing Django explorer selection flow.
      if (node && !node.historical) {
        document.dispatchEvent(
          new CustomEvent("b3-storage-select-request", {
            detail: {id: node.id}
          })
        );
      }
    }
  }

  document.addEventListener(
    "b3-storage-location-selected",
    event => {
      const id = str(event.detail?.id);

      if (!demoActive() && nodes.has(id)) {
        choose(id, false);
      }
    }
  );

  document.addEventListener(
    "b3-storage-legacy-selected",
    event => {
      const id = str(event.detail?.id);

      if (!demoActive() && nodes.has(id)) {
        choose(id, false);
      }
    }
  );

  document.addEventListener(
    "b3-spatial-v5-box",
    event => {
      if (event.detail?.mode !== "live") {
        return;
      }

      const id = str(event.detail?.box?.id);

      if (nodes.has(id) && active !== id) {
        active = id;
        render();
      }
    }
  );

  for (
    const id of [
      "storage-3d-real",
      "storage-3d-example"
    ]
  ) {
    byId(id)?.addEventListener(
      "click",
      () => window.requestAnimationFrame(render)
    );
  }

  render();
})();
