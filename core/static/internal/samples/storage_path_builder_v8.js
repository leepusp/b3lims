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
        let renderedCount = -1;

        const eligible = anchor =>
            ["box", "rack"].includes(
                String(anchor.location_type).toLowerCase()
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
            panel.hidden = !physical;

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
                rows.querySelectorAll("input").forEach(node => {
                    node.disabled = false;
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
                field.value = existing[index] || "";

                wrapper.append(label, field);
                rows.append(wrapper);
            }

            renderedCount = count;
        }

        function synchronize() {
            if (
                selectedAnchor &&
                path.value.trim() !== selectedAnchor.full_path
            ) {
                selectedAnchor = null;
                anchorId.value = "";
            }

            if (selectedAnchor && eligible(selectedAnchor)) {
                mode.value = "physical";
                anchorId.value = String(selectedAnchor.id);
                status.textContent =
                    "Linked physical container: " +
                    selectedAnchor.full_path +
                    ". Occupancy is checked when saving.";
            } else {
                mode.value = path.value.trim()
                    ? "unverified"
                    : "unassigned";

                anchorId.value = "";

                status.textContent = path.value.trim()
                    ? "Unverified text path. No physical location " +
                      "will be created automatically."
                    : "No storage assigned. Select a registered " +
                      "Box or Rack to register physical positions.";
            }

            updatePositionRows();
        }

        function choose(anchor) {
            if (
                typeof window.setStorageLocationFromText !== "function"
            ) {
                status.textContent =
                    "The original Path Builder is unavailable.";
                return;
            }

            window.setStorageLocationFromText(anchor.full_path);
            input.value = "";
            selectedAnchor = eligible(anchor) ? anchor : null;
            suggestions.replaceChildren();
            synchronize();
        }

        function showSuggestions() {
            suggestions.replaceChildren();

            const query = input.value.trim().toLowerCase();

            if (!query || !anchors.length) return;

            const prefix = path.value.trim();

            const matches = anchors
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
                synchronize();
            };
        }

        input.addEventListener("input", showSuggestions);

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
                field.value.trim().toUpperCase()
            );

            if (
                input.value.trim() ||
                fields.length !== sampleCount() ||
                values.some(value => !/^[A-Z]+[0-9]+$/.test(value)) ||
                new Set(values).size !== values.length
            ) {
                event.preventDefault();

                status.textContent =
                    "Complete one distinct position per Sample " +
                    "and press Enter to finish editing the path.";
            }
        });

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
                anchors = Array.isArray(payload.anchors)
                    ? payload.anchors
                    : [];

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
