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

        if (!workspace || !display || !button ||
            !status || !path || !input || !chips) return;

        let busy = true;
        let available = 0;

        function update() {
            const value = path.value.trim();
            display.textContent = value || "No path entered";

            button.disabled = (
                busy ||
                available === 0 ||
                !workspace.value ||
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
                empty.textContent = "Select workspace";
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

                status.textContent = rows.length
                    ? "Finish entering your path, then register it."
                    : "No manageable workspace is available. " +
                      "Open Storage management.";

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

            const body = new URLSearchParams({
                workspace_id: workspace.value,
                path: hierarchyPath
            });

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

                if (path.value.trim() !== submittedPath) {
                    status.textContent =
                        "Path registered, but the editor changed. " +
                        "Select the registered destination again.";
                    return;
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

        workspace.addEventListener("change", update);
        input.addEventListener("input", update);
        input.addEventListener("keydown", () =>
            setTimeout(update, 0)
        );
        chips.addEventListener("click", () =>
            setTimeout(update, 0)
        );

        button.addEventListener("click", registerPath);

        loadWorkspaces();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
