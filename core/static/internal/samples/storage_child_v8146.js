/*
 * B3 LIMS V8.14.6B3
 * Explicit child creation shared by New Sample and Edit Sample.
 * Never converts typed text into an implicit StorageLocation.
 */
(() => {
    "use strict";

    const EVENT_NAME = "b3:storage-child-created-v8146";

    function init() {
        const panel = document.querySelector(
            "[data-b3-storage-child-v8146]"
        );

        if (!panel) return;

        const parent = document.getElementById(
            "storageChildParentV8146"
        );
        const name = document.getElementById(
            "storageChildNameV8146"
        );
        const type = document.getElementById(
            "storageChildTypeV8146"
        );
        const create = document.getElementById(
            "storageChildCreateV8146"
        );
        const status = document.getElementById(
            "storageChildStatusV8146"
        );

        if (!parent || !name || !type || !create || !status) {
            return;
        }

        let busy = true;

        function update() {
            create.disabled = busy ||
                !parent.value ||
                !name.value.trim() ||
                !type.value;
        }

        function addOption(anchor) {
            if (!anchor || !anchor.id) return;

            const id = String(anchor.id);
            const exists = Array.from(parent.options)
                .some(option => option.value === id);

            if (exists) return;

            const option = document.createElement("option");
            option.value = id;
            option.textContent =
                anchor.full_path + " [" + anchor.location_type + "]";

            parent.add(option);
        }

        async function loadParents() {
            try {
                const response = await fetch(
                    panel.dataset.catalogUrl,
                    {
                        credentials: "same-origin",
                        headers: {
                            "Accept": "application/json"
                        }
                    }
                );

                if (!response.ok) {
                    throw new Error(
                        "Unable to load authorized storage locations."
                    );
                }

                const payload = await response.json();
                const anchors = Array.isArray(payload.anchors)
                    ? payload.anchors
                    : [];

                parent.replaceChildren();

                const placeholder = document.createElement("option");
                placeholder.value = "";
                placeholder.textContent = "Select an existing parent";
                parent.add(placeholder);

                for (const anchor of anchors) {
                    addOption(anchor);
                }

                status.textContent = anchors.length
                    ? "Choose a parent in the registered hierarchy."
                    : "No accessible storage parents are registered.";

            } catch (error) {
                status.textContent = error.message ||
                    "The physical storage catalog is unavailable.";
            } finally {
                busy = false;
                update();
            }
        }

        async function createChild() {
            if (create.disabled || busy) return;

            const csrf = document.querySelector(
                '#mainSampleForm input[name="csrfmiddlewaretoken"]'
            )?.value;

            if (!csrf) {
                status.textContent =
                    "CSRF token unavailable. Reload the form.";
                return;
            }

            const selectedParent = parent.value;
            const newName = name.value.trim();

            busy = true;
            update();
            status.textContent = "Creating the physical location...";

            try {
                const body = new URLSearchParams();
                body.set("parent_id", selectedParent);
                body.set("name", newName);
                body.set("location_type", type.value);

                const response = await fetch(
                    panel.dataset.createUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            "Accept": "application/json",
                            "Content-Type":
                                "application/x-www-form-urlencoded;charset=UTF-8",
                            "X-CSRFToken": csrf
                        },
                        body: body.toString()
                    }
                );

                const payload = await response.json();

                if (!response.ok || !payload.ok || !payload.anchor) {
                    throw new Error(
                        payload.error ||
                        "The location could not be created."
                    );
                }

                const anchor = payload.anchor;

                addOption(anchor);
                parent.value = String(anchor.id);
                name.value = "";

                document.dispatchEvent(
                    new CustomEvent(EVENT_NAME, {
                        detail: {anchor}
                    })
                );

                const host = ["box", "rack", "other"].includes(
                    String(anchor.location_type).toLowerCase()
                );

                status.textContent = host
                    ? "Location created: " + anchor.full_path +
                      ". You can now assign a Sample position."
                    : "Hierarchy level created: " +
                      anchor.full_path +
                      ". Select it as the parent to create another child.";

            } catch (error) {
                status.textContent = error.message ||
                    "Unable to create this location.";
            } finally {
                busy = false;
                update();
            }
        }

        for (const field of [parent, name, type]) {
            field.addEventListener("input", update);
            field.addEventListener("change", update);
        }

        create.addEventListener("click", createChild);

        loadParents();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
