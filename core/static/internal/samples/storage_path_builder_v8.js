/*
 * B3 LIMS V8 — extension to the existing chip-based Path Builder.
 *
 * Registered anchors come from Django.
 * Free-text paths stay unverified.
 * Availability is checked again during the server transaction.
 */
(() => {
    "use strict";

    function init() {
        const form = document.getElementById("mainSampleForm");
        const container = document.getElementById(
            "dynamicStorageContainer"
        );
        const input = document.getElementById("storageInputVisual");
        const path = document.getElementById(
            "storage_location_hidden"
        );
        const mode = document.getElementById("storage_mode_v8");
        const anchorId = document.getElementById(
            "storage_anchor_id_v8"
        );
        const suggestions = document.getElementById(
            "storageAnchorSuggestionsV8"
        );
        const status = document.getElementById(
            "storageAnchorStatusV8"
        );
        const panel = document.getElementById(
            "storagePositionPanelV8"
        );
        const rows = document.getElementById(
            "storagePositionRowsV8"
        );

        if (
            !form || !container || !input || !path ||
            !mode || !anchorId || !suggestions ||
            !status || !panel || !rows
        ) return;

        let anchors = [];
        let selectedAnchor = null;
        let selectedSamplePosition = "";
        const positionLeafFlag = document.getElementById(
            "storage_position_leaf_v8146c2"
        );
        let renderedCount = -1;

        const eligible = anchor =>
            Boolean(
                anchor &&
                Number.isSafeInteger(Number(anchor.id)) &&
                Number(anchor.id) > 0 &&
                String(anchor.location_type).toLowerCase() !== "position"
            );

        function sampleCount() {
            const defaultCount = Number(
                document.getElementById(
                    "aliquotCountInput"
                )?.value || 1
            );

            const quantities = Array.from(
                form.querySelectorAll(
                    '[name="dist_quantity[]"]'
                )
            );

            const biobanks = Array.from(
                form.querySelectorAll(
                    '[name="dist_biobank_id[]"]'
                )
            );

            const selected = biobanks
                .map((node, index) => ({
                    id: String(node.value || "").trim(),
                    quantity: quantities[index]?.value
                }))
                .filter(row => row.id);

            if (!selected.length) {
                return defaultCount;
            }

            return selected.reduce(
                (total, row) =>
                    total + Number(
                        row.quantity || defaultCount
                    ),
                0
            );
        }

        function updatePositionRows() {
            const physical = mode.value === "physical";
            panel.hidden = !physical ||
                (sampleCount() === 1 && Boolean(selectedSamplePosition));

            if (!physical) {
                rows.querySelectorAll("input").forEach(node => {
                    node.disabled = true;
                });
                return;
            }

            const count = sampleCount();

            if (
                !Number.isSafeInteger(count) ||
                count < 1 ||
                count > 200
            ) {
                rows.replaceChildren();
                renderedCount = -1;
                status.textContent =
                    "Choose a valid quantity of up to 200 " +
                    "Samples for physical position entry.";
                return;
            }

            if (count === renderedCount) {
                rows.querySelectorAll("input").forEach((node, index) => {
                    node.disabled = false;
                    node.readOnly = (
                        index === 0 && Boolean(selectedSamplePosition)
                    );
                    if (node.readOnly) {
                        node.value = selectedSamplePosition;
                    }
                });
                return;
            }

            const existing = Array.from(
                rows.querySelectorAll("input")
            ).map(node => node.value);

            rows.replaceChildren();

            for (let index = 0; index < count; index++) {
                const wrapper = document.createElement("div");
                wrapper.className = "mb-2";

                const label = document.createElement("label");
                label.className = "form-label small";
                label.textContent = `Sample ${index + 1} position`;

                const field = document.createElement("input");
                field.type = "text";
                field.name = "storage_positions[]";
                field.className = "form-control form-control-sm";
                field.placeholder = "Ex: A1";
                field.autocomplete = "off";
                field.maxLength = 100;
                field.required = true;
                field.value = (
                    index === 0 && selectedSamplePosition
                        ? selectedSamplePosition
                        : existing[index] || ""
                );
                field.readOnly = (
                    index === 0 && Boolean(selectedSamplePosition)
                );

                wrapper.append(label, field);
                rows.append(wrapper);
            }

            renderedCount = count;
        }

        // Drawing of the chosen location: click free cells to fill the
        // "Sample N position" fields in order; click again to release.
        const mapHost = document.createElement("div");
        mapHost.id = "storagePositionMapV8";
        mapHost.className = "b3-pos-map";
        rows.before(mapHost);

        function nameOf(slot) {
            return String(slot || "").trim();
        }

        function renderMap() {
            mapHost.replaceChildren();
            mapHost.hidden = true;

            const anchor = selectedAnchor;

            if (
                !anchor || mode.value !== "physical" ||
                !["grid", "slots"].includes(anchor.organization)
            ) return;

            const fields = Array.from(
                rows.querySelectorAll('input[name="storage_positions[]"]')
            );
            const taken = new Set(
                (anchor.occupied || []).map(v => nameOf(v).toLowerCase())
            );
            const chosen = new Map();

            fields.forEach((field, index) => {
                const value = nameOf(field.value).toLowerCase();

                if (value) chosen.set(value, index);
            });

            function click(name) {
                const key = name.toLowerCase();

                if (taken.has(key)) return;

                if (chosen.has(key)) {
                    fields[chosen.get(key)].value = "";
                } else {
                    const free = fields.find(f => !nameOf(f.value))
                        || (fields.length === 1 ? fields[0] : null);

                    if (!free) {
                        status.textContent =
                            "Every Sample already has a position. " +
                            "Click a chosen position to release it first.";
                        return;
                    }

                    free.value = name;
                }

                fields.forEach(f => f.dispatchEvent(
                    new Event("input", {bubbles: true})
                ));
                renderMap();
            }

            function cell(name, className) {
                const key = name.toLowerCase();
                const button = document.createElement("button");

                button.type = "button";
                button.className = className + (
                    taken.has(key) ? " is-taken"
                    : chosen.has(key) ? " is-chosen" : ""
                );
                button.title = taken.has(key)
                    ? name + " (occupied)"
                    : chosen.has(key)
                        ? name + " (Sample " + (chosen.get(key) + 1) + ")"
                        : name + " (free)";
                button.setAttribute("aria-label", button.title);
                button.addEventListener("click", () => click(name));

                if (chosen.has(key) && fields.length > 1) {
                    button.textContent = String(chosen.get(key) + 1);
                }

                return button;
            }

            const title = document.createElement("div");

            title.className = "b3-pos-title";
            title.textContent = anchor.name + " · click free positions " +
                "for each Sample (white = free, dark = occupied)";
            mapHost.append(title);

            if (anchor.organization === "grid") {
                const r = Number(anchor.rows);
                const c = Number(anchor.columns);
                const size = Math.max(14, Math.min(28, Math.floor(420 / c)));
                const grid = document.createElement("div");

                grid.className = "b3-pos-grid";
                grid.style.gridTemplateColumns =
                    `18px repeat(${c}, ${size}px)`;
                grid.append(document.createElement("span"));

                for (let col = 1; col <= c; col++) {
                    const head = document.createElement("span");

                    head.className = "b3-pos-axis";
                    head.textContent = size >= 18 ? col : "";
                    grid.append(head);
                }

                for (let row = 0; row < r; row++) {
                    const head = document.createElement("span");

                    head.className = "b3-pos-axis";
                    head.textContent = String.fromCharCode(65 + row);
                    grid.append(head);

                    for (let col = 0; col < c; col++) {
                        const btn = cell(
                            String.fromCharCode(65 + row) + (col + 1),
                            "b3-pos-cell"
                        );

                        btn.style.width = btn.style.height = size + "px";
                        grid.append(btn);
                    }
                }

                mapHost.append(grid);
            } else {
                const cabinet = document.createElement("div");

                cabinet.className = "b3-pos-cabinet " + (
                    anchor.direction === "row" ? "is-row" : "is-stack"
                );

                for (const name of anchor.slots || []) {
                    const btn = cell(name, "b3-pos-slot");

                    btn.textContent = btn.textContent
                        ? name + " · Sample " + btn.textContent
                        : name;
                    cabinet.append(btn);
                }

                mapHost.append(cabinet);
            }

            mapHost.hidden = false;
        }

        rows.addEventListener("input", renderMap);

        // Tree browser: start at the top places and step down level by
        // level; the nearest registered levels below the current one are
        // offered as buttons.
        const browse = document.getElementById("storageBrowseV8");

        function depthOf(anchor) {
            return String(anchor.full_path).split(" > ").length;
        }

        const workspaceSelect = document.getElementById(
            "storageChildWorkspaceV8146"
        );

        // Registered levels of the chosen workspace only; nothing is
        // offered until a workspace is selected.
        function scoped() {
            const chosen = workspaceSelect ? workspaceSelect.value : "";

            return chosen
                ? anchors.filter(item => String(item.workspace_id) === chosen)
                : [];
        }

        function renderBrowse() {
            if (!browse) return;
            browse.replaceChildren();

            const pool = scoped();

            if (!pool.length) return;

            const here = selectedAnchor;
            const prefix = here ? here.full_path + " > " : "";
            const below = pool.filter(item =>
                !here || String(item.full_path).startsWith(prefix)
            );

            const minDepth = below.length
                ? Math.min(...below.map(depthOf)) : 0;
            const next = below
                .filter(item => depthOf(item) === minDepth)
                .sort((a, b) => a.name.localeCompare(b.name))
                .slice(0, 40);

            const title = document.createElement("div");

            title.className = "form-text mb-1";
            title.textContent = here
                ? "Inside " + here.full_path + (
                    next.length ? " — go deeper:"
                        : " — no registered levels below."
                )
                : "Browse registered storage — start with:";
            browse.append(title);

            const bar = document.createElement("div");

            bar.className = "d-flex flex-wrap gap-1";

            if (here) {
                const up = document.createElement("button");
                const parentPath = String(here.full_path)
                    .split(" > ").slice(0, -1).join(" > ");
                const parent = pool.find(
                    item => item.full_path === parentPath
                );

                up.type = "button";
                up.className = "btn btn-sm btn-outline-secondary";
                up.textContent = "↑ Up";
                up.addEventListener("click", () => {
                    if (parent) {
                        choose(parent);
                    } else {
                        window.setStorageLocationFromText("");
                    }
                });
                bar.append(up);
            }

            for (const item of next) {
                const button = document.createElement("button");

                button.type = "button";
                button.className = "btn btn-sm btn-outline-primary";
                button.textContent = item.name + (
                    ["grid", "slots"].includes(item.organization)
                        ? " ▦" : ""
                );
                button.title = item.full_path + " · " + item.location_type;
                button.addEventListener("click", () => choose(item));
                bar.append(button);
            }

            browse.append(bar);
        }

        function synchronize() {
            if (
                selectedAnchor &&
                path.value.trim() !== (
                    selectedAnchor.full_path +
                    (selectedSamplePosition
                        ? " > " + selectedSamplePosition
                        : "")
                )
            ) {
                selectedAnchor = null;
                selectedSamplePosition = "";
                anchorId.value = "";
            }

            if (selectedAnchor && eligible(selectedAnchor)) {
                mode.value = "physical";
                anchorId.value = String(selectedAnchor.id);
                status.textContent =
                    "Linked physical location: " +
                    selectedAnchor.full_path +
                    ". Occupancy is checked when saving.";
            } else {
                mode.value = path.value.trim()
                    ? "unverified"
                    : "unassigned";

                anchorId.value = "";

                status.textContent = path.value.trim()
                    ? "This path is not (fully) in the registered " +
                      "storage tree, so it is saved as text only and no " +
                      "position is reserved. Pick levels from the " +
                      "buttons above to link it, or register the " +
                      "missing levels in Storage."
                    : "No storage assigned. Select a registered " +
                      "physical location to register Sample positions.";
            }

            if (positionLeafFlag) {
                positionLeafFlag.value = (
                    selectedAnchor && selectedSamplePosition
                ) ? "1" : "0";
            }

            updatePositionRows();
            renderMap();
            renderBrowse();
        }

        function choose(anchor, position = "") {
            if (
                typeof window.setStorageLocationFromText !== "function"
            ) {
                status.textContent =
                    "The original Path Builder is unavailable.";
                return;
            }

            const leaf = String(position || "").trim();

            window.setStorageLocationFromText(
                anchor.full_path + (leaf ? " > " + leaf : "")
            );

            input.value = "";
            selectedAnchor = eligible(anchor) ? anchor : null;
            selectedSamplePosition = selectedAnchor ? leaf : "";
            suggestions.replaceChildren();
            synchronize();
        }

        function showSuggestions() {
            suggestions.replaceChildren();

            const query = input.value.trim().toLowerCase();

            if (!query || !scoped().length) return;

            const prefix = path.value.trim();

            const matches = scoped()
                .filter(anchor => {
                    const childOfCurrent =
                        prefix &&
                        anchor.full_path.startsWith(
                            prefix + " > "
                        );

                    const textMatch =
                        anchor.name.toLowerCase().includes(query) ||
                        anchor.full_path.toLowerCase().includes(query);

                    return textMatch &&
                        (!prefix || childOfCurrent ||
                         anchor.full_path.toLowerCase()
                            .includes(query));
                })
                .slice(0, 12);

            for (const anchor of matches) {
                const button = document.createElement("button");
                button.type = "button";
                button.className =
                    "list-group-item list-group-item-action small";

                button.textContent =
                    anchor.full_path +
                    " · " +
                    anchor.location_type +
                    (eligible(anchor)
                        ? " · physical position host"
                        : " · hierarchy level");

                button.addEventListener("click", () => {
                    choose(anchor);
                });

                suggestions.append(button);
            }
        }

        const previousSetter = window.setStorageLocationFromText;

        if (typeof previousSetter === "function") {
            window.setStorageLocationFromText = value => {
                previousSetter(value);
                selectedAnchor = null;
                selectedSamplePosition = "";
                synchronize();
            };
        }

        input.addEventListener("input", showSuggestions);

        if (workspaceSelect) {
            workspaceSelect.addEventListener("change", () => {
                suggestions.replaceChildren();
                renderBrowse();
            });
        }

        // Keep the original Enter, Backspace and chip removal.
        // Synchronize after the original listener updates the path.
        input.addEventListener("keydown", event => {
            if (
                ["Enter", ",", ";", "Backspace"].includes(event.key)
            ) {
                setTimeout(() => {
                    synchronize();
                    showSuggestions();
                }, 0);
            }
        });

        container.addEventListener("click", () => {
            setTimeout(synchronize, 0);
        });

        form.addEventListener("input", event => {
            if (
                event.target.name === "aliquot_count" ||
                event.target.name === "dist_quantity[]"
            ) {
                updatePositionRows();
            }
        });

        form.addEventListener("change", event => {
            if (
                event.target.name === "dist_biobank_id[]" ||
                event.target.name === "dist_quantity[]" ||
                event.target.name === "aliquot_count"
            ) {
                updatePositionRows();
            }
        });

        form.addEventListener("click", () => {
            setTimeout(updatePositionRows, 0);
        });

        form.addEventListener("submit", event => {
            synchronize();

            if (mode.value !== "physical") return;

            const fields = Array.from(
                rows.querySelectorAll(
                    'input[name="storage_positions[]"]'
                )
            );

            const values = fields.map(field =>
                field.value.trim()
            );

            const validPosition = value =>
                value.length > 0 &&
                value.length <= 100 &&
                !/[>,;\x00-\x1f\x7f]/u.test(value);

            if (
                input.value.trim() ||
                fields.length !== sampleCount() ||
                values.some(value => !validPosition(value)) ||
                new Set(
                    values.map(value => value.toLocaleLowerCase())
                ).size !== values.length ||
                (
                    Boolean(selectedSamplePosition) &&
                    values[0] !== selectedSamplePosition
                )
            ) {
                event.preventDefault();

                status.textContent =
                    "Complete one distinct position per Sample " +
                    "and press Enter to finish editing the path.";
            }
        });

        document.addEventListener(
            "b3:storage-child-created-v8146",
            event => {
                const anchor = event.detail?.anchor;

                if (
                    !anchor ||
                    !Number.isSafeInteger(Number(anchor.id)) ||
                    Number(anchor.id) <= 0
                ) return;

                anchors = anchors.filter(
                    item => String(item.id) !== String(anchor.id)
                );
                anchors.push(anchor);

                if (eligible(anchor)) {
                    const position = event.detail?.samplePosition
                        ? event.detail.position
                        : "";
                    choose(anchor, position);
                }
            }
        );

        synchronize();

        fetch(container.dataset.anchorCatalogUrl, {
            credentials: "same-origin",
            headers: {"Accept": "application/json"}
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error("Storage catalog unavailable");
                }
                return response.json();
            })
            .then(payload => {
                const fetchedAnchors =
                    Array.isArray(payload.anchors)
                        ? payload.anchors
                        : [];

                const newlyCreated = anchors.filter(
                    item => !fetchedAnchors.some(
                        serverItem =>
                            String(serverItem.id) === String(item.id)
                    )
                );

                anchors = fetchedAnchors.concat(newlyCreated);
                renderBrowse();
                setTimeout(renderBrowse, 700);

                if (!path.value.trim()) {
                    status.textContent = anchors.length
                        ? "Start typing to search registered storage."
                        : "No physical storage locations are registered.";
                }
            })
            .catch(error => {
                console.warn(
                    "Unable to load registered storage anchors",
                    error
                );

                status.textContent =
                    "Registered storage suggestions are unavailable. " +
                    "Text paths can still be saved as unverified.";
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
