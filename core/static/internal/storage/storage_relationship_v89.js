(() => {
  "use strict";

  function initialize() {
    const panel = document.getElementById("storage-relationship-v89");
    const source = document.getElementById("storage-explorer-data");
    const workspaceSource = document.getElementById(
      "storage-relationship-workspaces-v89"
    );
    const assignmentSource = document.getElementById(
      "storage-explorer-assignment-data"
    );
    const selector = document.getElementById(
      "storage-relationship-workspace-select-v89"
    );
    const diagram = document.getElementById(
      "storage-relationship-diagram-v89"
    );
    const status = document.getElementById(
      "storage-relationship-status-v89"
    );
    const explorer = document.getElementById("storage-explorer-tree");

    if (![panel, source, workspaceSource, selector,
          diagram, status, explorer].every(Boolean)) return;

    const numeric = value => /^\d+$/.test(String(value));

    const workspaces = Array.from(
      workspaceSource.content.querySelectorAll("[data-workspace-id]")
    ).map(node => ({
      id: node.dataset.workspaceId,
      name: node.dataset.workspaceName,
      scope: node.dataset.workspaceScope
    })).filter(item => numeric(item.id));

    const allowed = new Set(workspaces.map(item => item.id));

    const entries = Array.from(
      source.content.querySelectorAll("[data-location-id]")
    ).map(node => ({
      id: node.dataset.locationId,
      parent: node.dataset.parentId || "",
      workspace: node.dataset.workspaceId || "",
      name: node.dataset.locationName || "Location",
      type: node.dataset.locationType || "Location",
      active: node.dataset.locationActive === "1"
    })).filter(item =>
      numeric(item.id) &&
      allowed.has(item.workspace) &&
      (!item.parent || numeric(item.parent))
    );

    const byId = new Map(entries.map(item => [item.id, item]));

    function validChain(entry) {
      const visited = new Set();
      let node = entry;

      while (node) {
        if (visited.has(node.id) ||
            node.workspace !== entry.workspace) {
          return false;
        }

        visited.add(node.id);

        if (!node.parent) return true;

        node = byId.get(node.parent);
        if (!node) return false;
      }

      return false;
    }

    const safeNodes = entries.filter(validChain);
    const safeIds = new Set(safeNodes.map(item => item.id));
    const children = new Map();

    for (const entry of safeNodes) {
      const key = `${entry.workspace}:${entry.parent}`;

      if (!children.has(key)) children.set(key, []);
      children.get(key).push(entry);
    }

    const collator = new Intl.Collator(undefined, {
      numeric: true,
      sensitivity: "base"
    });

    for (const group of children.values()) {
      group.sort((a, b) => collator.compare(a.name, b.name));
    }

    const counts = new Map();

    if (assignmentSource) {
      for (const node of assignmentSource.content.querySelectorAll(
        "[data-assignment-location]"
      )) {
        if (node.dataset.assignmentStatus !== "active") continue;

        const id = node.dataset.assignmentLocation;
        if (!safeIds.has(id)) continue;

        counts.set(id, (counts.get(id) || 0) + 1);
      }
    }


    // Aggregate direct active assignments across authorized ancestors.
    // This count is not a measurement of physical capacity.
    const subtreeCounts = new Map();

    for (const [locationId, directCount] of counts) {
      const origin = byId.get(locationId);
      const visited = new Set();
      let current = origin;

      while (
        current &&
        safeIds.has(current.id) &&
        !visited.has(current.id) &&
        current.workspace === origin.workspace
      ) {
        visited.add(current.id);

        subtreeCounts.set(
          current.id,
          (subtreeCounts.get(current.id) || 0) + directCount
        );

        current = byId.get(current.parent);
      }
    }

    function physicalPath(item) {
      const names = [];
      const visited = new Set();
      let current = item;

      while (
        current &&
        safeIds.has(current.id) &&
        !visited.has(current.id) &&
        current.workspace === item.workspace
      ) {
        visited.add(current.id);
        names.unshift(current.name);
        current = byId.get(current.parent);
      }

      return names.join(" > ");
    }


    // V8.10 read-only hierarchy styling.
    const visualStyle = document.createElement("style");

    visualStyle.textContent = `
      #storage-relationship-diagram-v89 .b3-v810-branch {
        position: relative;
        border-left-width: 2px !important;
      }

      #storage-relationship-diagram-v89 .b3-v810-node {
        position: relative;
        padding: 0.5rem 0.7rem;
        border: 1px solid var(--bs-border-color, #dee2e6);
        border-radius: 0.65rem;
        background: var(--bs-body-bg, #fff);
        margin-bottom: 0.4rem;
      }

      #storage-relationship-diagram-v89 .b3-v810-node::before {
        content: "";
        position: absolute;
        width: 0.65rem;
        left: -0.65rem;
        top: 50%;
        border-top: 2px solid var(--bs-border-color, #dee2e6);
      }

      #storage-relationship-diagram-v89
      .b3-v810-node.b3-v810-selected {
        border-color: var(--bs-primary, #0d6efd);
        background: var(--bs-primary-bg-subtle, #e7f1ff);
      }

      #storage-relationship-diagram-v89 .b3-v810-summary {
        margin-left: auto;
        padding: 0.2rem 0.55rem;
        border-radius: 999px;
        background: var(--bs-secondary-bg, #e9ecef);
      }

      #storage-relationship-diagram-v89 .b3-v810-toggle {
        min-width: 2rem;
      }
    `;


    visualStyle.textContent += `
      #storage-relationship-diagram-v89
      .b3-v810-preview-origin {
        border-left: 4px solid var(--bs-warning, #ffc107);
      }

      #storage-relationship-diagram-v89
      .b3-v810-preview-destination {
        border-right: 4px solid var(--bs-info, #0dcaf0);
      }

      #storage-relationship-diagram-v89
      .b3-v810-preview-affected {
        outline: 1px dashed var(--bs-warning, #ffc107);
        outline-offset: -3px;
      }
    `;

    panel.append(visualStyle);

    const expanded = new Set();
    let selectedId = "";

    function element(tag, classes, value) {
      const node = document.createElement(tag);
      if (classes) node.className = classes;
      if (value !== undefined) node.textContent = value;
      return node;
    }


    // Movement highlights use completed Django previews only.
    // They do not submit, validate or authorize transfers.
    const previewOrigins = new Set();
    const previewDestinations = new Set();
    const previewAffected = new Set();

    function uniquePathId(path) {
      const normalized = String(path || "").trim();
      if (!normalized) return "";

      const matches = safeNodes.filter(
        item => physicalPath(item) === normalized
      );

      return matches.length === 1 ? matches[0].id : "";
    }

    function addPreviewMarker(target, id) {
      const key = String(id || "");
      if (safeIds.has(key)) target.add(key);
    }

    const comparisons = document.querySelectorAll(
      "[data-b3-v89-movement-comparison]"
    );

    for (const comparison of comparisons) {
      const kind = comparison.dataset.b3V89MovementComparison;

      if (kind === "container") {
        const originId = String(
          comparison.dataset.b3V810ContainerId || ""
        );
        const destinationId = String(
          comparison.dataset.b3V810DestinationId || ""
        );

        if (safeIds.has(originId) && safeIds.has(destinationId)) {
          const origin = byId.get(originId);
          const destination = byId.get(destinationId);

          // Cross-workspace movements are not represented as
          // authorized by this visualization.
          if (origin &&
              destination &&
              origin.workspace === destination.workspace) {
            previewOrigins.add(originId);
            previewDestinations.add(destinationId);

            for (const candidate of safeNodes) {
              if (candidate.workspace !== origin.workspace ||
                  candidate.id === originId) continue;

              const visited = new Set();
              let ancestor = candidate.parent;

              while (ancestor && !visited.has(ancestor)) {
                if (ancestor === originId) {
                  previewAffected.add(candidate.id);
                  break;
                }

                visited.add(ancestor);

                const parent = byId.get(ancestor);
                if (!parent ||
                    !safeIds.has(parent.id) ||
                    parent.workspace !== origin.workspace) break;

                ancestor = parent.parent;
              }
            }
          }
        }

        continue;
      }

      if (kind !== "sample" && kind !== "bulk") continue;

      for (const movement of comparison.querySelectorAll(
        "[data-b3-v89-movement-row]"
      )) {
        const before = movement.querySelector(
          "[data-b3-v89-path-before]"
        );
        const after = movement.querySelector(
          "[data-b3-v89-path-after]"
        );

        const originId = uniquePathId(before?.textContent);
        const destinationId = uniquePathId(after?.textContent);

        // Do not visually endorse cross-workspace transfers.
        const origin = byId.get(originId);
        const destination = byId.get(destinationId);

        if (origin &&
            destination &&
            origin.workspace === destination.workspace) {
          addPreviewMarker(previewOrigins, originId);
          addPreviewMarker(previewDestinations, destinationId);
        }
      }
    }

    function renderBranch(item, depth) {
      const branch = element("div", "ms-3 border-start ps-2 my-1 b3-v810-branch");
      const row = element(
        "div",
        "d-flex align-items-center gap-2 flex-wrap b3-v810-node"
      );

      const descendants = children.get(
        `${item.workspace}:${item.id}`
      ) || [];

      const isExpanded = expanded.has(item.id);

      const toggle = element(
        "button",
        "btn btn-sm btn-outline-secondary b3-v810-toggle",
        isExpanded ? "−" : "+"
      );

      toggle.type = "button";
      toggle.disabled = !descendants.length;
      toggle.setAttribute(
        "aria-label",
        `${isExpanded ? "Collapse" : "Expand"} ${item.name}`
      );
      toggle.setAttribute("aria-expanded", String(isExpanded));

      toggle.addEventListener("click", () => {
        if (expanded.has(item.id)) expanded.delete(item.id);
        else expanded.add(item.id);
        render();
      });

      const choose = element(
        "button",
        `btn btn-sm ${
          item.id === selectedId
            ? "btn-primary"
            : "btn-outline-primary"
        }`,
        item.name
      );
        if (item.id === selectedId) {
          row.classList.add("b3-v810-selected");
        }


      choose.type = "button";
      choose.dataset.locationId = item.id;
      choose.setAttribute(
        "aria-pressed",
        String(item.id === selectedId)
      );
      choose.addEventListener("click", () => focusExplorer(item.id));

      const directCount = counts.get(item.id) || 0;
              const totalCount = subtreeCounts.get(item.id) || 0;
              const path = physicalPath(item);

              const summary = element(
                "span",
                "small text-muted b3-v810-summary",
                `${item.type} · ${directCount} direct · ` +
                `${totalCount} in subtree` +
                (item.active ? "" : " · inactive")
              );

              choose.title = path;
              summary.title = path;
              choose.setAttribute("aria-label", `Select ${path}`);


        if (previewAffected.has(item.id)) {
          row.classList.add("b3-v810-preview-affected");
        }
        if (previewOrigins.has(item.id)) {
          row.classList.add("b3-v810-preview-origin");
        }
        if (previewDestinations.has(item.id)) {
          row.classList.add("b3-v810-preview-destination");
        }

      row.append(toggle, choose, summary);
      branch.append(row);

      if (isExpanded && depth < 80) {
        for (const child of descendants) {
          branch.append(renderBranch(child, depth + 1));
        }
      }

      return branch;
    }

    function render() {
      diagram.replaceChildren();

      const workspaceId = selector.value;
      const workspace = workspaces.find(
        item => item.id === workspaceId
      );

      if (!workspace) {
        status.textContent =
          "No authorized physical storage workspace available.";
        return;
      }

      const roots = children.get(`${workspaceId}:`) || [];
      const count = safeNodes.filter(
        item => item.workspace === workspaceId
      ).length;

      status.textContent =
        `${workspace.name}: ${count} accessible location(s).`;

      if (!roots.length) {
        diagram.append(element(
          "p",
          "small text-muted",
          "No registered hierarchy in this workspace."
        ));
        return;
      }

      const fragment = document.createDocumentFragment();

      for (const root of roots) {
        fragment.append(renderBranch(root, 0));
      }

      diagram.append(fragment);
    }

    function focusExplorer(id) {
      const item = byId.get(id);
      if (!item || !safeIds.has(id)) return;

      const details = document.getElementById(
        "storage-designer-inventory-details"
      );
      if (details) details.open = true;

      const search = document.getElementById(
        "storage-explorer-search"
      );

      if (search && search.value) {
        search.value = "";
        search.dispatchEvent(new Event("input", {bubbles: true}));
      }

      const ancestors = [];
      const visited = new Set();
      let current = item;

      while (current &&
             current.parent &&
             !visited.has(current.parent)) {
        visited.add(current.parent);
        ancestors.unshift(current.parent);
        current = byId.get(current.parent);
      }

      for (const ancestorId of ancestors) {
        const toggle = explorer.querySelector(
          `.b3-storage-tree-toggle[data-location-id="${ancestorId}"]`
        );

        if (toggle &&
            toggle.getAttribute("aria-expanded") === "false") {
          toggle.click();
        }
      }

      const button = explorer.querySelector(
        `.b3-storage-tree-item[data-location-id="${id}"]`
      );

      if (button) {
        button.click();
        button.focus();
        selectedId = id;

        status.textContent =
          `Selected ${item.name}. Details opened in Inventory explorer.`;
      } else {
        status.textContent =
          `Location ${item.name} is not selectable in the current view.`;
      }

      render();
    }

    for (const workspace of workspaces) {
      const option = element(
        "option",
        "",
        `${workspace.name} (${workspace.scope})`
      );

      option.value = workspace.id;
      selector.append(option);
    }

    selector.addEventListener("change", () => {
      selectedId = "";
      render();
    });

    explorer.addEventListener("click", event => {
      const button = event.target.closest(
        ".b3-storage-tree-item[data-location-id]"
      );

      if (!button) return;

      const location = byId.get(button.dataset.locationId);

      if (!location || !safeIds.has(location.id)) return;

      selector.value = location.workspace;
      selectedId = location.id;
      render();
    });


    // Keep the hierarchy map synchronized with authorized
    // selections originating from other storage components.
    document.addEventListener(
      "b3-storage-location-selected",
      event => {
        const value = event.detail?.id;
        const id = value == null ? "" : String(value);

        if (!safeIds.has(id)) return;

        const location = byId.get(id);
        if (!location || !allowed.has(location.workspace)) return;

        selector.value = location.workspace;
        selectedId = id;

        const visited = new Set([id]);
        let ancestor = location.parent;

        while (ancestor && !visited.has(ancestor)) {
          visited.add(ancestor);

          const parent = byId.get(ancestor);

          if (!parent ||
              !safeIds.has(ancestor) ||
              parent.workspace !== location.workspace) {
            break;
          }

          expanded.add(ancestor);
          ancestor = parent.parent;
        }

        render();
      }
    );

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
})();
