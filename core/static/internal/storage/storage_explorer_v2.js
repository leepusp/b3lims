(() => {
    "use strict";

    function initializeStorageExplorer() {
        const root = document.getElementById("storage-location-explorer");
        const data = document.getElementById("storage-explorer-data");
        const assignmentData = document.getElementById(
            "storage-explorer-assignment-data"
        );

        if (!root || !data || !assignmentData) return;

        const tree = document.getElementById("storage-explorer-tree");
        const search = document.getElementById("storage-explorer-search");
        const details = document.getElementById("storage-explorer-details");
        const list = document.getElementById(
            "storage-explorer-assignments"
        );
        const count = document.getElementById("storage-explorer-count");
        const assignmentCount = document.getElementById(
            "storage-explorer-assignment-count"
        );
        const positionList = document.getElementById(
            "storage-explorer-positions"
        );
        const positionCount = document.getElementById(
            "storage-explorer-position-count"
        );
        const clearPosition = document.getElementById(
            "storage-explorer-clear-position"
        );

        const locations = Array.from(
            data.content.querySelectorAll("[data-location-id]")
        ).map((node) => ({
            id: node.dataset.locationId,
            parent: node.dataset.parentId,
            name: node.dataset.locationName,
            type: node.dataset.locationType,
            path: node.dataset.locationPath,
            active: node.dataset.locationActive === "1"
        }));

        const assignments = Array.from(
            assignmentData.content.querySelectorAll(
                "[data-assignment-location]"
            )
        ).map((node) => ({
            location: node.dataset.assignmentLocation,
            sample: node.dataset.assignmentSample,
            position: node.dataset.assignmentPosition,
            status: node.dataset.assignmentStatus
        })).filter((item) => item.status === "active");

        const byId = new Map(locations.map((item) => [item.id, item]));
        const children = new Map();
        const expanded = new Set();
        let selectedId = null;
        let selectedPosition = null;

        locations.forEach((location) => {
            if (!children.has(location.parent)) {
                children.set(location.parent, []);
            }
            children.get(location.parent).push(location);
        });

        const compare = (a, b) =>
            a.name.localeCompare(b.name, undefined, {
                numeric: true,
                sensitivity: "base"
            });

        children.forEach((items) => items.sort(compare));

        function element(tag, className, text) {
            const node = document.createElement(tag);
            if (className) node.className = className;
            if (text !== undefined) node.textContent = text;
            return node;
        }

        function field(label, value) {
            const wrapper = element("div", "b3-storage-detail-field");
            wrapper.append(
                element("span", "b3-storage-detail-label", label),
                element("span", "b3-storage-detail-value", value)
            );
            return wrapper;
        }

        function showDetails(location) {
            details.replaceChildren();
            positionList.replaceChildren();
            list.replaceChildren();

            positionCount.textContent = "0";
            assignmentCount.textContent = "0";
            clearPosition.hidden = true;

            if (!location) {
                details.append(element(
                    "p", "small text-muted", "Select a location."
                ));
                return;
            }

            const assigned = assignments.filter(
                item => item.location === location.id
            );

            details.append(
                field("Name", location.name),
                field("Type", location.type || "Unspecified"),
                field("Full path", location.path || location.name),
                field("Status", location.active ? "Active" : "Inactive"),
                field("Direct active assignments", String(assigned.length))
            );

            const groups = new Map();

            assigned.forEach(item => {
                const key = item.position.trim();
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push(item);
            });

            const positions = Array.from(groups.keys())
                .filter(Boolean)
                .sort((a, b) => a.localeCompare(b, undefined, {
                    numeric: true,
                    sensitivity: "base"
                }));

            positionCount.textContent = String(positions.length);

            function positionButton(key, label) {
                const button = element(
                    "button", "b3-storage-position", label
                );
                button.type = "button";
                button.dataset.positionKey = key;
                button.setAttribute(
                    "aria-pressed", String(selectedPosition === key)
                );
                if (selectedPosition === key) {
                    button.classList.add("is-selected");
                }

                button.addEventListener("click", () => {
                    selectedPosition =
                        selectedPosition === key ? null : key;
                    showDetails(location);

                    const next = Array.from(
                        positionList.querySelectorAll("button")
                    ).find(node => node.dataset.positionKey === key);
                    if (next) next.focus();
                });

                positionList.append(button);
            }

            positions.forEach(position => {
                const total = groups.get(position).length;
                positionButton(
                    position,
                    total > 1 ? `${position} (${total})` : position
                );
            });

            if (groups.has("")) {
                positionButton(
                    "",
                    `Unpositioned (${groups.get("").length})`
                );
            }

            if (!groups.size) {
                positionList.append(element(
                    "p",
                    "small text-muted mb-0",
                    "No recorded assignments."
                ));
            }

            const filtered = selectedPosition === null
                ? assigned
                : assigned.filter(
                    item => item.position.trim() === selectedPosition
                );

            clearPosition.hidden = selectedPosition === null;
            assignmentCount.textContent = String(filtered.length);

            if (!filtered.length) {
                list.append(element(
                    "p",
                    "small text-muted",
                    "No visible Samples in this selection."
                ));
                return;
            }

            filtered.slice(0, 40).forEach(item => {
                const card = element(
                    "div", "b3-storage-assignment"
                );
                card.append(
                    element("strong", "", item.sample || "Sample"),
                    element(
                        "small",
                        "",
                        item.position
                            ? `Position: ${item.position}`
                            : "Position not recorded"
                    )
                );
                list.append(card);
            });

            if (filtered.length > 40) {
                list.append(element(
                    "p",
                    "small text-muted",
                    `Showing 40 of ${filtered.length} assignments.`
                ));
            }
        }

        function selectLocation(id) {
            selectedId = id;
            selectedPosition = null;
            showDetails(byId.get(id));
            renderTree();

            document.dispatchEvent(
                new CustomEvent(
                    "b3-storage-location-selected",
                    { detail: { id } }
                )
            );

            const replacement = Array.from(
                tree.querySelectorAll(".b3-storage-tree-item")
            ).find((node) => node.dataset.locationId === id);

            if (replacement) replacement.focus();
        }

        function renderTree() {
            tree.replaceChildren();

            const query = search.value.trim().toLocaleLowerCase();
            const rendered = new Set();

            function draw(location, depth) {
                if (rendered.has(location.id)) return;
                rendered.add(location.id);

                const branch = element("div", "b3-storage-tree-branch");
                const row = element("div", "b3-storage-tree-row");

                const descendants = children.get(location.id) || [];
                const toggle = element(
                    "button",
                    "b3-storage-tree-toggle",
                    !query && descendants.length
                        ? (expanded.has(location.id) ? "▾" : "▸")
                        : "·"
                );
                toggle.type = "button";
                toggle.dataset.locationId = location.id;
                toggle.disabled = Boolean(query) || !descendants.length;
                toggle.setAttribute(
                    "aria-label",
                    `Toggle ${location.name}`
                );

                if (descendants.length) {
                    toggle.setAttribute(
                        "aria-expanded",
                        String(expanded.has(location.id))
                    );
                }

                const button = element(
                    "button",
                    "b3-storage-tree-item",
                    `${location.name} · ${location.type || "Location"}`
                );
                button.type = "button";
                button.dataset.locationId = location.id;

                if (selectedId === location.id) {
                    button.classList.add("is-selected");
                    button.setAttribute("aria-current", "true");
                }

                button.addEventListener("click", () => {
                    selectLocation(location.id);
                });

                row.append(toggle, button);
                branch.append(row);

                const nested = element(
                    "div",
                    "b3-storage-tree-children"
                );

                if (!query) {
                    descendants.forEach((child) => {
                        const childBranch = draw(child, depth + 1);
                        if (childBranch) nested.append(childBranch);
                    });

                    nested.hidden = !expanded.has(location.id);
                    branch.append(nested);

                    toggle.addEventListener("click", () => {
                        if (expanded.has(location.id)) {
                            expanded.delete(location.id);
                        } else {
                            expanded.add(location.id);
                        }
                        renderTree();

                        const replacement = Array.from(
                            tree.querySelectorAll(
                                ".b3-storage-tree-toggle"
                            )
                        ).find(
                            (node) =>
                                node.dataset.locationId === location.id
                        );

                        if (replacement) replacement.focus();
                    });
                }

                return branch;
            }

            if (query) {
                const matches = locations.filter((location) =>
                    [location.name, location.path, location.type]
                        .join(" ")
                        .toLocaleLowerCase()
                        .includes(query)
                );

                count.textContent = `${matches.length} found`;

                matches.sort(compare).forEach((location) => {
                    const branch = draw(location, 0);
                    if (branch) tree.append(branch);
                });

                if (!matches.length) {
                    tree.append(
                        element(
                            "p",
                            "small text-muted p-2 mb-0",
                            "No matching locations."
                        )
                    );
                }

                return;
            }

            count.textContent = String(locations.length);

            const roots = locations.filter(
                (location) =>
                    !location.parent ||
                    !byId.has(location.parent) ||
                    location.parent === location.id
            ).sort(compare);

            roots.forEach((location) => {
                const branch = draw(location, 0);
                if (branch) tree.append(branch);
            });

            // Also display orphaned or malformed hierarchy records safely.
            locations.forEach((location) => {
                if (!rendered.has(location.id)) {
                    const branch = draw(location, 0);
                    if (branch) tree.append(branch);
                }
            });

            if (!locations.length) {
                tree.append(
                    element(
                        "p",
                        "small text-muted p-2 mb-0",
                        "No visible storage locations."
                    )
                );
            }
        }

        locations
            .filter((location) => !location.parent)
            .forEach((location) => expanded.add(location.id));

        clearPosition.addEventListener("click", () => {
            selectedPosition = null;
            showDetails(byId.get(selectedId));
            search.focus();
        });

        document.addEventListener(
            "b3-storage-select-request",
            event => {
                const value = event.detail?.id;
                const id = value == null ? null : String(value);

                if (id !== null && !byId.has(id)) return;

                search.value = "";

                const visited = new Set();
                let ancestor = id ? byId.get(id)?.parent : null;

                while (ancestor && !visited.has(ancestor)) {
                    visited.add(ancestor);
                    expanded.add(ancestor);
                    ancestor = byId.get(ancestor)?.parent;
                }

                selectLocation(id);
            }
        );

        search.addEventListener("input", renderTree);

        showDetails(null);
        renderTree();
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            initializeStorageExplorer,
            { once: true }
        );
    } else {
        initializeStorageExplorer();
    }
})();
