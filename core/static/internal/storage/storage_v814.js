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
        const button = mk(
          "button",
          null,
          "b3s-node"
        );

        button.type = "button";
        button.dataset.locationId = node.id;
        button.title = pathFor(node);

        if (node.id === selected) {
          button.classList.add("is-selected");
        }

        if (node.historical) {
          button.classList.add("is-historical");
        }

        button.append(
          mk(
            "span",
            displayName(node),
            "b3s-node-label"
          )
        );

        if (node.historical) {
          button.append(
            mk("small", "Historical", "b3s-node-status")
          );
        } else if (node.active !== "1") {
          button.append(
            mk("small", "Inactive", "b3s-node-status")
          );
        }

        button.addEventListener(
          "click",
          () => choose(node.id)
        );

        li.append(button);

        const childNodes = (
          children.get(node.id) || []
        ).filter(item => ids.has(item.id));

        if (childNodes.length) {
          const ul = mk("ul", null, "b3s-branches");

          for (const child of childNodes) {
            const childElement = branch(
              child,
              nextVisited
            );

            if (childElement) {
              ul.append(childElement);
            }
          }

          if (ul.children.length) {
            li.append(ul);
          }
        }

        return li;
      }

      const list = mk(
        "ul",
        null,
        "b3s-branches b3s-tree-root"
      );

      for (const node of roots) {
        const element = branch(node, new Set());
        if (element) list.append(element);
      }

      container.append(list);

      if (!list.children.length) {
        container.append(
          mk(
            "p",
            "No locations match this filter.",
            "b3s-note"
          )
        );
      }

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
          mk("strong", displayName(child)),
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

      const visible = visibleNodes();
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


    function renderPositionMap() {
      const host = find("b3s-position-map");
      if (!host) return;

      host.replaceChildren();

      const node = byId.get(selected);
      if (!node) return;

      const items = node.historical
        ? visibleLegacySamples.filter(
            item => item.location === node.id
          )
        : samples.filter(
            item => item.location === node.id
          );

      const withPositions = items
        .filter(item => String(item.position || "").trim())
        .sort((a, b) =>
          String(a.position).localeCompare(
            String(b.position),
            undefined,
            {numeric: true, sensitivity: "base"}
          )
        );

      if (!withPositions.length) return;

      const title = mk(
        "h4",
        "Recorded positions — " + displayName(node)
      );

      const note = mk(
        "p",
        "Only recorded positions are shown. " +
        "Other positions have not been verified as free.",
        "b3s-note"
      );

      const grid = mk(
        "div",
        null,
        "b3s-position-grid"
      );

      for (const item of withPositions) {
        const cell = mk(
          "div",
          null,
          "b3s-position-cell"
        );

        cell.append(
          mk(
            "strong",
            String(item.position).toUpperCase()
          )
        );

        const code = String(item.sample || "");

        if (
          item.url &&
          String(item.url).startsWith("/")
        ) {
          const link = mk("a", code);
          link.href = item.url;
          cell.append(link);
        } else {
          cell.append(mk("span", code));
        }

        grid.append(cell);
      }

      host.append(title, note, grid);
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

    function changeStatus(node) {
      if (!manageable(node)) return;

      const action = node.active === "1"
        ? "deactivate_location"
        : "reactivate_location";

      const warning = node.active === "1"
        ? "Remove this location from active storage? " +
          "No database record will be deleted. " +
          "Active child locations or Sample assignments " +
          "may prevent this operation."
        : "Reactivate this physical location?";

      if (!window.confirm(warning)) {
        return;
      }

      const form = find("b3s-status-form");

      form.elements.namedItem("action").value =
        action;

      form.elements.namedItem("location_id").value =
        node.id;

      form.requestSubmit();
    }

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
          ? "Remove from active storage"
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

    function render() {
      renderTree();
      renderContents();
      renderPositionMap();
      renderLegacy();
      renderGraph();
      renderManage();
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
