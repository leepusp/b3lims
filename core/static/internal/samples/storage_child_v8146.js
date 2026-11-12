/*
 * V8.14.6C1 — Register the existing chip-based Path Builder.
 * No predefined type selection and no implicit creation on typing.
 */
(() => {
    "use strict";

    function init() {
        const panel = document.querySelector(
            "[data-b3-storage-child-v8146]"
        );
        if (!panel) return;

        const workspace = document.getElementById(
            "storageChildWorkspaceV8146"
        );
        const display = document.getElementById(
            "storageChildCurrentPathV8146"
        );
        const button = document.getElementById(
            "storageChildCreateV8146"
        );
        const status = document.getElementById(
            "storageChildStatusV8146"
        );
        const path = document.getElementById(
            "storage_location_hidden"
        );
        const input = document.getElementById(
            "storageInputVisual"
        );
        const chips = document.getElementById(
            "dynamicStorageContainer"
        );

        const prefix = document.getElementById(
            "storageChildWorkspacePrefixV8146"
        );
        const separator = document.getElementById(
            "storageChildWorkspaceSeparatorV8146"
        );

        if (!workspace || !display || !button ||
            !status || !path || !input || !chips ||
            !prefix || !separator) return;

        const layoutBox = document.getElementById("storageChildLayoutV8146");
        const orgSelect = document.getElementById("storageChildOrgV8146");
        const gridBox = document.getElementById("storageChildGridV8146");
        const slotsBox = document.getElementById("storageChildSlotsV8146");

        let busy = true;
        let available = 0;

        const preview = document.getElementById("storageChildPreviewV8146");

        function clampInt(id, low, high, fallback) {
            const value = parseInt(document.getElementById(id).value, 10);

            return Math.min(high, Math.max(low, Number.isFinite(value) ? value : fallback));
        }

        let lastSignature = "";

        function pathParts() {
            return path.value.split(">").map(x => x.trim()).filter(Boolean);
        }

        function pickPosition(name) {
            if (typeof window.setStorageLocationFromText !== "function") return;

            const parts = pathParts();

            // In Sample intake the last level is the Sample position: the click replaces it.
            if (parts.length >= 2) parts.pop();

            parts.push(name);
            window.setStorageLocationFromText(parts.join(" > "));
            update();
        }

        function drawPreview() {
            if (!preview) return;

            preview.hidden = layoutBox.hidden || orgSelect.value === "free";

            if (preview.hidden) {
                preview.replaceChildren();
                lastSignature = "";

                return;
            }

            const interactive = Boolean(document.getElementById("storagePositionPanelV8"));
            const parts = pathParts();
            const chosen = interactive && parts.length >= 2 ? parts[parts.length - 1].toLowerCase() : "";
            const host = interactive && parts.length >= 2 ? parts[parts.length - 2] : (parts[parts.length - 1] || "");
            const board = document.createElement("div");

            board.className = "b3-child-board";

            let labels = [];
            let signature = orgSelect.value;
            let caption = "";

            if (orgSelect.value === "grid") {
                const rows = clampInt("storageChildRowsV8146", 1, 26, 9);
                const cols = clampInt("storageChildColsV8146", 1, 24, 9);
                const size = Math.max(14, Math.min(28, Math.floor(340 / cols)));

                signature += rows + "x" + cols;
                board.style.gridTemplateColumns = "18px repeat(" + cols + ", " + size + "px)";
                board.append(document.createElement("span"));

                for (let c = 1; c <= cols; c += 1) {
                    const head = document.createElement("span");

                    head.className = "b3-child-axis";
                    head.textContent = size >= 18 ? c : "";
                    board.append(head);
                }

                for (let r = 0; r < rows; r += 1) {
                    const head = document.createElement("span");

                    head.className = "b3-child-axis";
                    head.textContent = String.fromCharCode(65 + r);
                    board.append(head);

                    for (let c = 0; c < cols; c += 1) {
                        const name = String.fromCharCode(65 + r) + (c + 1);
                        const cell = document.createElement("button");

                        cell.type = "button";
                        cell.className = "b3-child-cell" + (chosen === name.toLowerCase() ? " is-chosen" : "");
                        cell.style.width = cell.style.height = size + "px";
                        cell.style.animationDelay = ((r + c) * 18) + "ms";
                        cell.title = name;
                        cell.disabled = !interactive;
                        cell.addEventListener("click", () => pickPosition(name));
                        board.append(cell);
                    }
                }

                caption = rows + " × " + cols + " = " + (rows * cols) + " positions";
            } else {
                const names = document.getElementById("storageChildSlotNamesV8146").value
                    .split(/[,\n]/).map(x => x.trim()).filter(Boolean);

                labels = names.length ? names : ["Compartment 1", "Compartment 2", "Compartment 3"];
                signature += labels.join("|") + document.getElementById("storageChildDirV8146").value;

                const sideBySide = document.getElementById("storageChildDirV8146").value === "row";

                board.classList.add("is-slots");
                board.style.gridTemplateColumns = sideBySide ? "repeat(" + labels.length + ", 1fr)" : "1fr";

                labels.forEach((label, index) => {
                    const slot = document.createElement("button");

                    slot.type = "button";
                    slot.className = "b3-child-slot" + (chosen === label.toLowerCase() ? " is-chosen" : "");
                    slot.style.animationDelay = (index * 70) + "ms";
                    slot.textContent = label;
                    slot.disabled = !interactive;
                    slot.addEventListener("click", () => pickPosition(label));
                    board.append(slot);
                });

                caption = labels.length + " compartment" + (labels.length === 1 ? "" : "s")
                    + (names.length ? "" : " (example, type the names above)");
            }

            // Only a new drawing animates; picking a position just moves the highlight.
            if (signature === lastSignature) board.classList.add("is-static");

            lastSignature = signature;

            const title = document.createElement("div");

            title.className = "b3-child-title";
            title.textContent = interactive
                ? (host ? "Drawing of " + host : "Drawing") + " · click a position to choose where the Sample goes"
                : "Drawing preview";

            preview.replaceChildren(title, board);
            preview.dataset.caption = caption;
        }

        function syncLayout() {
            if (!layoutBox) return;

            layoutBox.hidden = !path.value.trim();
            gridBox.hidden = orgSelect.value !== "grid";
            slotsBox.hidden = orgSelect.value !== "slots";
            drawPreview();
        }

        ["storageChildRowsV8146", "storageChildColsV8146", "storageChildSlotNamesV8146", "storageChildDirV8146"]
            .forEach(id => {
                const node = document.getElementById(id);

                if (node) {
                    node.addEventListener("input", drawPreview);
                    node.addEventListener("change", drawPreview);
                }
            });

        function layoutFields(body) {
            if (!orgSelect || layoutBox.hidden) return;

            body.set("organization", orgSelect.value);

            if (orgSelect.value === "grid") {
                body.set("rows", document.getElementById("storageChildRowsV8146").value);
                body.set("columns", document.getElementById("storageChildColsV8146").value);
            }

            if (orgSelect.value === "slots") {
                document.getElementById("storageChildSlotNamesV8146").value
                    .split(/[,\n]/).map(x => x.trim()).filter(Boolean)
                    .forEach(label => body.append("slot_label", label));
                body.set("slot_direction", document.getElementById("storageChildDirV8146").value);
            }
        }

        function update() {
            const value = path.value.trim();
            const option = workspace.selectedOptions[0];
            const name = workspace.value && option
                ? option.textContent.trim()
                : "";

            prefix.textContent = name
                ? "Workspace: " + name
                : "";

            prefix.hidden = !name;
            prefix.style.display = name ? "" : "none";

            separator.hidden = !(name && value);
            separator.style.display =
                name && value ? "" : "none";

            display.textContent =
                [name, value].filter(Boolean).join(" > ") ||
                "No path entered";

            syncLayout();

            button.disabled = (
                busy ||
                !value ||
                Boolean(input.value.trim())
            );
        }

        async function loadWorkspaces() {
            try {
                const response = await fetch(
                    panel.dataset.catalogUrl,
                    {
                        credentials: "same-origin",
                        headers: {"Accept": "application/json"}
                    }
                );

                if (!response.ok) {
                    throw new Error(
                        "Cannot load authorized workspaces."
                    );
                }

                const data = await response.json();
                const rows = Array.isArray(data.workspaces)
                    ? data.workspaces : [];

                available = rows.length;
                workspace.replaceChildren();

                const empty = document.createElement("option");
                empty.value = "";
                empty.textContent = "New workspace from the first level of the path";
                workspace.add(empty);

                for (const item of rows) {
                    const option = document.createElement("option");
                    option.value = String(item.id);
                    option.textContent = item.name;
                    workspace.add(option);
                }

                if (rows.length === 1) {
                    workspace.value = String(rows[0].id);
                }

                status.textContent = "Finish entering your path, then register it.";

                if (rows.length === 1) {
                    workspace.dispatchEvent(new Event("change"));
                }

            } catch (error) {
                status.textContent = error.message;
            } finally {
                busy = false;
                update();
            }
        }

        async function registerPath() {
            update();
            if (busy || button.disabled) return;

            const token = document.querySelector(
                '#mainSampleForm input[name="csrfmiddlewaretoken"]'
            )?.value;

            if (!token) {
                status.textContent = "CSRF token unavailable.";
                return;
            }

            const submittedPath = path.value.trim();
            const submittedWorkspace = workspace.value;
            const sampleIntake = Boolean(
                document.getElementById("storagePositionPanelV8")
            );

            let hierarchyPath = submittedPath;
            let samplePosition = "";

            if (sampleIntake) {
                const parts = submittedPath.split(">")
                    .map(part => part.trim());

                if (
                    submittedPath.includes(";") ||
                    parts.length < 2 ||
                    parts.some(part => !part)
                ) {
                    status.textContent =
                        "Enter a physical location followed by " +
                        "the Sample position as the final level.";
                    return;
                }

                samplePosition = parts.pop();
                hierarchyPath = parts.join(" > ");
            }

            if (!submittedWorkspace && hierarchyPath.split(">").length < 2) {
                status.textContent =
                    "Without a workspace the first level becomes the workspace: " +
                    "type workspace, location and then the Sample position " +
                    "(for example Lab A > Freezer 1 > A4).";
                return;
            }

            const body = new URLSearchParams({
                workspace_id: submittedWorkspace,
                path: hierarchyPath
            });

            layoutFields(body);

            busy = true;
            update();
            status.textContent = "Registering physical hierarchy...";

            try {
                const response = await fetch(
                    panel.dataset.createUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            "Accept": "application/json",
                            "Content-Type":
                                "application/x-www-form-urlencoded;charset=UTF-8",
                            "X-CSRFToken": token
                        },
                        body: body.toString()
                    }
                );

                const result = await response.json();

                if (!response.ok || !result.ok || !result.anchor) {
                    throw new Error(
                        result.error ||
                        "Unable to register this path."
                    );
                }

                if (
                    path.value.trim() !== submittedPath ||
                    workspace.value !== submittedWorkspace
                ) {
                    status.textContent =
                        "Path registered, but the editor changed. " +
                        "Select the registered destination again.";
                    return;
                }

                if (!submittedWorkspace && result.workspace) {
                    const id = String(result.workspace.id);

                    if (![...workspace.options].some(o => o.value === id)) {
                        workspace.add(new Option(result.workspace.name, id));
                    }

                    workspace.value = id;
                    available += 1;
                }

                document.dispatchEvent(
                    new CustomEvent(
                        "b3:storage-child-created-v8146",
                        {
                            detail: {
                                anchor: result.anchor,
                                samplePosition: sampleIntake,
                                position: samplePosition
                            }
                        }
                    )
                );

                status.textContent = sampleIntake
                    ? "Physical destination registered: " +
                      result.anchor.full_path +
                      ". Sample position: " + samplePosition +
                      ". The position will be occupied when " +
                      "you save the Sample."
                    : "Physical path registered: " +
                      result.anchor.full_path +
                      ". New levels: " + result.created_count +
                      "; existing levels: " + result.reused_count + ".";

            } catch (error) {
                status.textContent = error.message;
            } finally {
                busy = false;
                update();
            }
        }

        workspace.addEventListener("change", () => {
            if (path.value.trim()) {
                if (
                    typeof window.setStorageLocationFromText !==
                    "function"
                ) {
                    status.textContent =
                        "Path Builder unavailable. Reload this page.";
                    return;
                }

                window.setStorageLocationFromText("");
                input.value = "";
            }

            update();
        });
        input.addEventListener("input", update);
        input.addEventListener("keydown", () =>
            setTimeout(update, 0)
        );
        chips.addEventListener("click", () =>
            setTimeout(update, 0)
        );

        button.addEventListener("click", registerPath);
        orgSelect?.addEventListener("change", syncLayout);

        loadWorkspaces();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
