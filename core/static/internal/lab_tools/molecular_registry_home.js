/*
 * Registry home: drop a file, see what it is and whether the same sequence is
 * already registered, then continue into the existing create form.
 *
 * The preview endpoint and the create form (with its own import flow) already
 * exist; this only puts the first step on the front page.
 */
(() => {
    "use strict";

    const drop = document.getElementById("mr-home-drop");
    const input = document.getElementById("mr-home-file");
    const result = document.getElementById("mr-home-result");
    const form = document.getElementById("molecular-registry-create-form");

    if (!drop || !input || !result || !form) return;

    const url = form.dataset.importPreviewUrl;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function csrf() {
        const field = form.querySelector("[name=csrfmiddlewaretoken]");

        return field ? field.value : "";
    }

    function showMessage(text) {
        result.hidden = false;
        result.replaceChildren(el("div", "mr-detect-warn", text));
    }

    function continueToForm(file) {
        const toggle = document.querySelector(
            '[data-bs-target="#new-molecular-record"]'
        );
        const panel = document.getElementById("new-molecular-record");

        if (toggle && panel && !panel.classList.contains("show")) toggle.click();

        const target = document.getElementById("molecular-registry-file");

        if (target && window.DataTransfer) {
            const transfer = new DataTransfer();

            transfer.items.add(file);
            target.files = transfer.files;
            target.dispatchEvent(new Event("change", {bubbles: true}));
        }

        if (panel) panel.scrollIntoView({behavior: "smooth", block: "start"});
    }

    function render(record, file) {
        const duplicates = record.duplicates || [];
        const head = el("div", "mr-detect-head");
        const kind = record.detected_content_label || record.sequence_type || "Sequence";
        const unit = record.sequence_type === "protein" ? "aa" : "bp";

        head.append(
            el("b", "", record.name || file.name),
            el("span", "badge text-bg-primary", kind),
            el("span", "badge text-bg-light border", record.topology || "linear"),
            el("span", "badge text-bg-light border",
                Number(record.length || 0).toLocaleString("en-US") + " " + unit),
            el("span", "badge text-bg-light border",
                (record.feature_count || 0) + " feature" +
                (record.feature_count === 1 ? "" : "s"))
        );

        const actions = el("div", "mr-detect-actions");

        duplicates.forEach(match => {
            const link = el("a", "btn btn-sm btn-primary", "Open " + match.name);

            link.href = match.url;
            actions.append(link);
        });

        const register = el(
            "button",
            "btn btn-sm " + (duplicates.length ? "btn-outline-secondary" : "btn-primary"),
            duplicates.length ? "Register anyway" : "Register this file"
        );

        register.type = "button";
        register.addEventListener("click", () => continueToForm(file));

        const dismiss = el("button", "btn btn-sm btn-outline-secondary", "Dismiss");

        dismiss.type = "button";
        dismiss.addEventListener("click", () => {
            result.hidden = true;
            result.replaceChildren();
        });
        actions.append(register, dismiss);

        const nodes = [head];

        if (duplicates.length) {
            nodes.push(el(
                "div", "mr-detect-warn",
                "The same sequence is already registered as " +
                duplicates.map(match => match.name).join(", ") +
                ". Open the existing record, or register this file anyway."
            ));
        }

        nodes.push(actions);
        result.hidden = false;
        result.replaceChildren(...nodes);
    }

    // Files that belong to an independent tool open that tool with the file.
    const TOOL_FILES = [
        {tool: "gel", label: "Gel", pattern: /\.(png|jpe?g|gif|webp|bmp)$/i},
        {tool: "chemical", label: "Chemical", pattern: /\.(mol|sdf|smi|cdxml)$/i},
        {tool: "protein3d", label: "Protein workbench", pattern: /\.(pdb|ent|cif|mmcif)$/i},
        {tool: "rnafold", label: "RNA workbench", pattern: /\.(dbn|ct)$/i},
    ];

    function toolFor(file) {
        return TOOL_FILES.find(entry => entry.pattern.test(file.name || "")) || null;
    }

    function renderTool(entry, file) {
        const head = el("div", "mr-detect-head");
        const actions = el("div", "mr-detect-actions");
        const open = el("button", "btn btn-sm btn-primary", "Open in " + entry.label);
        const dismiss = el("button", "btn btn-sm btn-outline-secondary", "Dismiss");
        const base = (file.name || entry.label).replace(/\.[^.]+$/, "");

        head.append(el("b", "", file.name), el("span", "badge text-bg-primary", entry.label));
        open.type = dismiss.type = "button";
        open.addEventListener("click", async () => {
            open.disabled = true;
            open.textContent = "Creating…";

            const data = new FormData();

            data.append("tool", entry.tool);
            data.append("name", base);
            data.append("file", file, file.name);
            data.append("csrfmiddlewaretoken", csrf());

            try {
                const response = await fetch(form.dataset.toolCreateUrl, {
                    method: "POST",
                    body: data,
                    credentials: "same-origin",
                    headers: {"X-CSRFToken": csrf()},
                });

                if (response.redirected && /\/tools\/\d+\//.test(response.url)) {
                    window.location.href = response.url;

                    return;
                }
            } catch (error) {
                // fall through to the message below
            }

            open.disabled = false;
            open.textContent = "Open in " + entry.label;
            showMessage("The " + entry.label + " could not be created from this file.");
        });
        dismiss.addEventListener("click", () => {
            result.hidden = true;
            result.replaceChildren();
        });
        actions.append(open, dismiss);
        result.hidden = false;
        result.replaceChildren(head, actions);
    }

    async function inspect(file) {
        const entry = toolFor(file);

        if (entry) {
            renderTool(entry, file);

            return;
        }

        showMessage("Reading " + file.name + "…");

        const data = new FormData();

        data.append("file", file);

        try {
            const response = await fetch(url, {
                method: "POST",
                body: data,
                headers: {"X-CSRFToken": csrf()},
                credentials: "same-origin",
            });
            const payload = await response.json();

            if (!response.ok || payload.status !== "ok") {
                showMessage(payload.message || "This file could not be read.");
                return;
            }

            render(payload.record, file);
        } catch (error) {
            showMessage("The file could not be checked. Try again.");
        }
    }

    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            input.click();
        }
    });
    input.addEventListener("change", () => {
        if (input.files && input.files[0]) inspect(input.files[0]);
    });
    ["dragenter", "dragover"].forEach(name => {
        drop.addEventListener(name, event => {
            event.preventDefault();
            drop.classList.add("is-over");
        });
    });
    ["dragleave", "drop"].forEach(name => {
        drop.addEventListener(name, event => {
            event.preventDefault();
            drop.classList.remove("is-over");
        });
    });
    drop.addEventListener("drop", event => {
        const file = event.dataTransfer && event.dataTransfer.files[0];

        if (file) inspect(file);
    });

    /* Independent tools (Gel, Plasmid assembly, Chemical, ...) are created from
     * the same form: picking one of them hides the sequence fields and posts
     * the form to the tool endpoint instead. */
    (() => {
        const select = document.getElementById("molecule-type");
        const sequence = document.getElementById("molecule-sequence");
        const toolUrl = form.dataset.toolCreateUrl;

        if (!select || !toolUrl) return;

        const originalAction = form.getAttribute("action") || "";
        const seqOnly = form.querySelectorAll("[data-seq-only]");
        const toolOnly = form.querySelectorAll("[data-tool-only]");
        const hidden = document.createElement("input");

        hidden.type = "hidden";
        hidden.name = "tool";

        function apply() {
            const isTool = select.value.indexOf("tool:") === 0;

            seqOnly.forEach(node => {
                node.hidden = isTool;
            });
            toolOnly.forEach(node => {
                node.hidden = !isTool;
            });

            if (sequence) sequence.required = !isTool;

            if (isTool) {
                hidden.value = select.value.slice(5);
                form.append(hidden);
                form.setAttribute("action", toolUrl);
            } else {
                hidden.remove();

                if (originalAction) form.setAttribute("action", originalAction);
                else form.removeAttribute("action");
            }
        }

        select.addEventListener("change", apply);
        apply();
    })();
})();
