/*
 * Storage Designer V7: contextual navigation to existing transfer
 * previews. Never submits a form or executes a movement.
 */
(() => {
    "use strict";

    const controls = document.querySelector(".b3-v5-controls");
    const transfersTab = document.querySelector(
        '[data-b3-v6-tab="transfers"]'
    );
    const containerSelect = document.getElementById(
        "preview-container"
    );
    const sampleSelect = document.getElementById(
        "preview-sample-assignment"
    );

    if (!controls || !transfersTab) {
        console.warn("Storage V7: spatial workspace unavailable.");
        return;
    }

    const panel = document.createElement("div");
    panel.className = "b3-v7-actions";
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", "Contextual storage transfers");

    const boxButton = document.createElement("button");
    boxButton.type = "button";
    boxButton.className = "btn btn-sm btn-outline-primary";
    boxButton.textContent = "Move entire box";
    boxButton.disabled = true;

    const sampleButton = document.createElement("button");
    sampleButton.type = "button";
    sampleButton.className = "btn btn-sm btn-outline-primary";
    sampleButton.textContent = "Move this Sample";
    sampleButton.disabled = true;
    sampleButton.hidden = true;

    const message = document.createElement("span");
    message.className = "b3-v7-action-message";
    message.setAttribute("aria-live", "polite");
    message.textContent = "Select a box or Sample to inspect available actions.";

    panel.append(boxButton, sampleButton, message);
    controls.append(panel);

    let mode = null;
    let box = null;
    let samples = [];
    let sample = null;

    function availableOptions(select) {
        return select
            ? Array.from(select.options).filter(option => option.value)
            : [];
    }

    function containerOption() {
        if (mode !== "live" || !box || !containerSelect) {
            return null;
        }

        return availableOptions(containerSelect).find(
            option => option.value === String(box.id)
        ) || null;
    }

    function sampleOptions() {
        if (
            mode !== "live" ||
            !sample ||
            sample.legacy ||
            sample.id == null ||
            !box ||
            !sampleSelect
        ) {
            return [];
        }

        const prefix = String(box.path || "") + " > ";

        return availableOptions(sampleSelect).filter(option => {
            if (option.dataset.b3SamplePk !== String(sample.id)) {
                return false;
            }

            const path = option.dataset.b3LocationPath || "";

            // Never select an assignment merely because its Sample
            // has the same identity. Its physical origin must match
            // the selected box or a descendant of that box.
            return Boolean(box.path) && (
                path === box.path ||
                path.startsWith(prefix)
            );
        });
    }

    function render() {
        const registeredBox = containerOption();
        const assignments = sampleOptions();

        boxButton.disabled = !registeredBox;
        sampleButton.hidden = !sample;
        sampleButton.disabled = assignments.length !== 1;

        if (mode === "demo") {
            message.textContent =
                "Example model: transfers are unavailable.";
        } else if (!box) {
            message.textContent =
                "Select a registered box to manage transfers.";
        } else if (!registeredBox) {
            message.textContent =
                "Historical or unavailable container: reconcile its physical registration first.";
        } else if (sample && assignments.length === 0) {
            message.textContent =
                "This Sample has no matching editable physical assignment in the selected box.";
        } else if (sample && assignments.length > 1) {
            message.textContent =
                "Multiple assignments match; choose the specific assignment in Transfers.";
        } else if (sample) {
            message.textContent =
                "Choose a transfer type. Preview and confirmation are required.";
        } else {
            message.textContent =
                "Move the entire box with its registered contents.";
        }
    }

    function sampleKey(item) {
        if (!item) {
            return "";
        }

        if (item.key != null) {
            return String(item.key);
        }

        if (item.id != null) {
            return String(item.id);
        }

        return "";
    }

    function selectSample(key) {
        sample = null;

        if (key == null) {
            return;
        }

        sample = samples.find(
            item => sampleKey(item) === String(key)
        ) || null;
    }

    document.addEventListener("b3-spatial-v5-box", event => {
        const detail = event.detail || {};

        mode = detail.mode || null;
        box = detail.box || null;
        samples = Array.isArray(detail.samples)
            ? detail.samples
            : [];

        selectSample(detail.picked);
        render();
    });

    document.addEventListener("b3-spatial-v5-pick", event => {
        const detail = event.detail || {};

        if (
            detail.mode !== mode ||
            !box ||
            detail.box == null ||
            String(detail.box) !== String(box.id)
        ) {
            return;
        }

        selectSample(detail.key);
        render();
    });

    function openTransfer(select, option) {
        if (!select || !option || !option.value) {
            return;
        }

        // V6 owns the workspace tab state. Never modify panels
        // or submit transfer forms independently.
        transfersTab.click();

        select.value = option.value;

        select.dispatchEvent(new Event("change", {
            bubbles: true
        }));

        const form = select.closest("form");
        const destination = form || select;

        if (typeof destination.scrollIntoView === "function") {
            destination.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        }

        select.focus({preventScroll: true});
    }

    boxButton.addEventListener("click", () => {
        const option = containerOption();

        if (!boxButton.disabled && option) {
            openTransfer(containerSelect, option);
        }
    });

    sampleButton.addEventListener("click", () => {
        const assignments = sampleOptions();

        if (!sampleButton.disabled && assignments.length === 1) {
            openTransfer(sampleSelect, assignments[0]);
        }
    });

    render();
})();
