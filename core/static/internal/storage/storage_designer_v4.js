/* B3 LIMS Storage Designer v4 — enhance the existing, server-validated location form.
 * This file creates no locations client-side and never submits automatically.
 */
(() => {
    "use strict";

    const $ = id => document.getElementById(id);
    const browseTab = $("storage-designer-browse");
    const buildTab = $("storage-designer-build");
    const browsePanel = $("storage-designer-browse-panel");
    const buildPanel = $("storage-designer-build-panel");
    const builderSlot = $("storage-designer-builder-target");
    const buildNote = $("storage-designer-build-note");
    const addChild = $("storage-designer-add-child");
    const addRoot = $("storage-designer-add-root");
    const demoButton = $("storage-3d-example");
    const liveButton = $("storage-3d-real");
    const source = $("storage-explorer-data");

    if (!browseTab || !buildTab || !builderSlot || !source) return;

    const locations = new Map(Array.from(
        source.content.querySelectorAll("[data-location-id]")
    ).map(node => [node.dataset.locationId, {
        id: node.dataset.locationId,
        name: node.dataset.locationName || "Location",
        kind: (node.dataset.locationKind || node.dataset.locationType || "").toLowerCase(),
        active: node.dataset.locationActive !== "0"
    }]));

    const createAction = Array.from(document.querySelectorAll(
        '[name="action"]'
    )).find(input => input.value === "create_location");
    const form = createAction?.form || null;
    let selectedId = null;
    let exampleMode = false;

    // Preserve the original Django form, its CSRF token, fields, permissions and validation.
    if (form) {
        const card = form.closest(".card");
        // Never move a broad card containing multiple unrelated forms.
        if (card && card.querySelectorAll("form").length === 1) {
            builderSlot.append(card);
        } else {
            builderSlot.append(form);
        }
        buildNote.textContent = "This creates a real location in B3 LIMS. Review the parent and type before saving.";
    } else {
        buildNote.textContent = "Location creation is unavailable for this account. Contact an authorized infrastructure manager.";
    }

    const parentField = form?.elements.namedItem("parent_id") || null;
    const typeField = form?.elements.namedItem("location_type") || null;
    const nameField = form?.elements.namedItem("name") || null;

    function chooseOption(field, value) {
        if (!(field instanceof HTMLSelectElement)) return false;
        const option = Array.from(field.options).find(item => item.value === value && !item.disabled);
        if (!option) return false;
        field.value = value;
        field.dispatchEvent(new Event("change", {bubbles: true}));
        return true;
    }

    function nextType(kind) {
        if (/^(room|sala)$/.test(kind)) return "freezer";
        if (/freezer|refrigerator|fridge|equipamento|equipment/.test(kind)) return "rack";
        if (/rack|shelf|basket|gaveta|cesto/.test(kind)) return "box";
        return null;
    }

    function showPanel(section) {
        const building = section === "build" && !exampleMode && Boolean(form);
        browsePanel.hidden = building;
        buildPanel.hidden = !building;
        browseTab.className = `btn btn-sm ${building ? "btn-outline-secondary" : "btn-primary"}`;
        buildTab.className = `btn btn-sm ${building ? "btn-primary" : "btn-outline-secondary"}`;
        browseTab.setAttribute("aria-pressed", String(!building));
        buildTab.setAttribute("aria-pressed", String(building));
    }

    function updateBuildButtons() {
        const allowed = !exampleMode && Boolean(form);
        buildTab.disabled = !allowed;
        addRoot.disabled = !allowed;
        addChild.disabled = !allowed || !selectedId || !locations.get(selectedId)?.active;
        addChild.title = !selectedId
            ? "Select an active parent location first"
            : !locations.get(selectedId)?.active
                ? "An inactive location cannot be used as the parent"
                : "Create a child under the selected location";
    }

    function prepareBuild(parentId) {
        if (exampleMode || !form) return;
        if (parentId) {
            const location = locations.get(parentId);
            if (!location || !location.active) return;
            if (!chooseOption(parentField, parentId)) {
                buildNote.textContent = "This parent is not an available destination in the creation form. Choose an allowed parent manually.";
            } else {
                const suggestion = nextType(location.kind);
                if (suggestion) chooseOption(typeField, suggestion);
                buildNote.textContent = `Creating under ${location.name}. Review the location type, name, rank and notes before saving.`;
            }
        } else {
            chooseOption(parentField, "");
            chooseOption(typeField, "room");
            buildNote.textContent = "Creating a root location. This is a real inventory record, not an example.";
        }
        showPanel("build");
        if (nameField instanceof HTMLElement) nameField.focus();
    }

    browseTab.addEventListener("click", () => showPanel("browse"));
    buildTab.addEventListener("click", () => {
        if (!exampleMode && form) showPanel("build");
    });
    addChild.addEventListener("click", () => prepareBuild(selectedId));
    addRoot.addEventListener("click", () => prepareBuild(null));

    document.addEventListener("b3-storage-select-request", event => {
        if (exampleMode) return;
        const id = event.detail?.id;
        selectedId = id != null && locations.has(String(id)) ? String(id) : null;
        updateBuildButtons();
    });
    document.addEventListener(
        "b3-storage-legacy-selected",
        () => {
            // Virtual locations cannot be used as creation parents.
            selectedId = null;
            showPanel("browse");
            updateBuildButtons();
        }
    );

    document.addEventListener("b3-storage-location-selected", event => {
        if (exampleMode) return;
        const id = event.detail?.id;
        selectedId = id != null && locations.has(String(id)) ? String(id) : null;
        updateBuildButtons();
    });

    demoButton?.addEventListener("click", () => {
        exampleMode = true;
        showPanel("browse");
        updateBuildButtons();
    });
    liveButton?.addEventListener("click", () => {
        exampleMode = false;
        selectedId = null;
        showPanel("browse");
        updateBuildButtons();
    });

    if (form) {
        form.addEventListener("submit", event => {
            if (!exampleMode) return;
            event.preventDefault();
            buildNote.textContent = "Example mode cannot create inventory. Return to Live inventory.";
        });
    }

    showPanel("browse");
    updateBuildButtons();
})();
