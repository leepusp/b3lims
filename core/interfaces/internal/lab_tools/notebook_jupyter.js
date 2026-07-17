(function () {
    "use strict";

    const root = document.getElementById("eln-jupyter-workspace");
    if (!root) return;

    const canEdit = root.dataset.canEdit === "true";
    const canExecute = root.dataset.canExecute === "true";
    const documentUrl = root.dataset.documentUrl;
    const submitUrl = root.dataset.submitUrl;
    const statusUrlTemplate = root.dataset.statusUrlTemplate;
    const cancelUrlTemplate = root.dataset.cancelUrlTemplate;
    const downloadUrl = root.dataset.downloadUrl;
    const workspaceUrl = root.dataset.workspaceUrl;
    const notebookUrl = root.dataset.notebookUrl;
    const standalone = root.dataset.standalone === "true";

    const state = {
        documentId: null,
        title: "ELN analysis",
        notebook: emptyNotebook(),
        execution: null,
        dirty: false,
        pollingTimer: null,
    };

    function emptyNotebook() {
        return {
            cells: [],
            metadata: {
                kernelspec: {
                    display_name: "Python 3",
                    language: "python",
                    name: "python3",
                },
                language_info: {
                    name: "python",
                },
            },
            nbformat: 4,
            nbformat_minor: 5,
        };
    }

    function csrfValue() {
        if (typeof csrfToken !== "undefined" && csrfToken) {
            return csrfToken;
        }
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function requestJson(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-CSRFToken": csrfValue(),
                ...(options && options.headers ? options.headers : {}),
            },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.status === "error") {
            throw new Error(payload.message || `Request failed (${response.status}).`);
        }
        return payload;
    }

    function uniqueCellId() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return window.crypto.randomUUID().replaceAll("-", "").slice(0, 12);
        }
        return `cell${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
    }

    function newCell(cellType) {
        const cell = {
            cell_type: cellType,
            id: uniqueCellId(),
            metadata: {},
            source: "",
        };
        if (cellType === "code") {
            cell.execution_count = null;
            cell.outputs = [];
        }
        return cell;
    }

    function actionButton(label, action, icon, className) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = className || "btn btn-sm btn-outline-secondary";
        button.dataset.action = action;
        button.innerHTML = `<i class="bi ${icon} me-1"></i>${label}`;
        return button;
    }

    function setStatus(message, tone) {
        const element = root.querySelector("[data-jupyter-status]");
        if (!element) return;
        element.textContent = message;
        element.className = `eln-jupyter-status badge ${tone || "bg-secondary"}`;
    }

    function statusTone(status) {
        if (status === "completed") return "bg-success";
        if (status === "failed" || status === "cancelled") return "bg-danger";
        if (status === "running") return "bg-primary";
        if (status === "pending" || status === "submitted") return "bg-warning text-dark";
        return "bg-secondary";
    }

    function renderOutput(output, container) {
        const block = document.createElement("div");
        block.className = "eln-jupyter-output";

        if (output.output_type === "stream") {
            const pre = document.createElement("pre");
            pre.textContent = output.text || "";
            block.appendChild(pre);
        } else if (output.output_type === "error") {
            block.classList.add("eln-jupyter-output-error");
            const pre = document.createElement("pre");
            pre.textContent = (output.traceback || []).join("\n") ||
                `${output.ename || "Error"}: ${output.evalue || ""}`;
            block.appendChild(pre);
        } else if (["display_data", "execute_result"].includes(output.output_type)) {
            const data = output.data || {};
            if (data["text/plain"]) {
                const pre = document.createElement("pre");
                pre.textContent = Array.isArray(data["text/plain"])
                    ? data["text/plain"].join("")
                    : data["text/plain"];
                block.appendChild(pre);
            }
            for (const mimeType of ["image/png", "image/jpeg"]) {
                if (!data[mimeType]) continue;
                const image = document.createElement("img");
                image.alt = "Jupyter cell output";
                image.src = `data:${mimeType};base64,${data[mimeType]}`;
                block.appendChild(image);
            }
        }

        if (block.childNodes.length) container.appendChild(block);
    }

    function cellElement(cell, index) {
        const wrapper = document.createElement("section");
        wrapper.className = "eln-jupyter-cell";
        wrapper.dataset.cellId = cell.id;
        wrapper.dataset.cellType = cell.cell_type;

        const gutter = document.createElement("div");
        gutter.className = "eln-jupyter-gutter";
        gutter.textContent = cell.cell_type === "code"
            ? `In [${cell.execution_count ?? " "}]:`
            : "MD";

        const main = document.createElement("div");
        main.className = "eln-jupyter-cell-main";

        const header = document.createElement("div");
        header.className = "eln-jupyter-cell-header";

        const typeBadge = document.createElement("span");
        typeBadge.className = "badge bg-light text-dark border me-auto";
        typeBadge.textContent = cell.cell_type === "code" ? "Python" : "Markdown";
        header.appendChild(typeBadge);

        if (canExecute && cell.cell_type === "code") {
            header.appendChild(actionButton(
                "Run through",
                "run-through",
                "bi-play-fill",
                "btn btn-sm btn-outline-success",
            ));
        }

        if (canEdit) {
            header.appendChild(actionButton("Up", "move-up", "bi-arrow-up"));
            header.appendChild(actionButton("Down", "move-down", "bi-arrow-down"));
            header.appendChild(actionButton(
                "Remove",
                "remove",
                "bi-trash",
                "btn btn-sm btn-outline-danger",
            ));
        }

        const source = document.createElement("textarea");
        source.className = "eln-jupyter-cell-source";
        source.value = Array.isArray(cell.source) ? cell.source.join("") : (cell.source || "");
        source.readOnly = !canEdit;
        source.spellcheck = cell.cell_type !== "code";
        source.dataset.source = "";
        source.setAttribute(
            "aria-label",
            `${cell.cell_type === "code" ? "Python" : "Markdown"} cell ${index + 1}`,
        );
        source.addEventListener("input", markDirty);
        source.addEventListener("focus", () => wrapper.classList.add("is-active"));
        source.addEventListener("blur", () => wrapper.classList.remove("is-active"));
        source.addEventListener("keydown", (event) => {
            if (event.key === "Tab" && canEdit) {
                event.preventDefault();
                const start = source.selectionStart;
                const end = source.selectionEnd;
                source.value = `${source.value.slice(0, start)}    ${source.value.slice(end)}`;
                source.selectionStart = source.selectionEnd = start + 4;
                markDirty();
            }
            if (event.shiftKey && event.key === "Enter" && canExecute && cell.cell_type === "code") {
                event.preventDefault();
                runNotebook(index);
            }
        });

        main.append(header, source);
        for (const output of cell.outputs || []) renderOutput(output, main);
        wrapper.append(gutter, main);

        wrapper.addEventListener("click", (event) => {
            const button = event.target.closest("[data-action]");
            if (!button) return;
            handleCellAction(button.dataset.action, index);
        });
        return wrapper;
    }

    function collectNotebook() {
        const cells = [];
        root.querySelectorAll(".eln-jupyter-cell").forEach((element) => {
            const previous = state.notebook.cells.find(
                (cell) => cell.id === element.dataset.cellId,
            ) || {};
            const cell = {
                cell_type: element.dataset.cellType,
                id: element.dataset.cellId,
                metadata: {},
                source: element.querySelector("[data-source]").value,
            };
            if (cell.cell_type === "code") {
                cell.execution_count = previous.execution_count ?? null;
                cell.outputs = previous.outputs || [];
            }
            cells.push(cell);
        });
        state.notebook.cells = cells;
        return state.notebook;
    }

    function renderCells() {
        const container = root.querySelector("[data-jupyter-cells]");
        if (!container) return;
        container.replaceChildren();

        if (!state.notebook.cells.length) {
            const empty = document.createElement("div");
            empty.className = "eln-jupyter-empty";
            empty.innerHTML = canEdit
                ? '<i class="bi bi-code-square fs-2 d-block mb-2"></i>Add a Python or Markdown cell to begin the analysis.'
                : "No Jupyter cells have been saved for this ELN entry.";
            container.appendChild(empty);
            return;
        }

        state.notebook.cells.forEach((cell, index) => {
            container.appendChild(cellElement(cell, index));
        });
    }

    function renderWorkspace() {
        root.innerHTML = `
            <div class="eln-jupyter-toolbar">
                <input type="text" class="form-control form-control-sm eln-jupyter-title" data-jupyter-title aria-label="Jupyter notebook title">
                <button type="button" class="btn btn-sm btn-outline-primary" data-global-action="add-code"><i class="bi bi-plus-lg me-1"></i>Code</button>
                <button type="button" class="btn btn-sm btn-outline-secondary" data-global-action="add-markdown"><i class="bi bi-markdown me-1"></i>Markdown</button>
                <button type="button" class="btn btn-sm btn-primary" data-global-action="save"><i class="bi bi-floppy me-1"></i>Save</button>
                <button type="button" class="btn btn-sm btn-success" data-global-action="run-all"><i class="bi bi-play-fill me-1"></i>Run all</button>
                <a class="btn btn-sm btn-outline-dark" data-jupyter-download><i class="bi bi-download me-1"></i>.ipynb</a>
                <a class="btn btn-sm btn-outline-primary" data-open-workspace><i class="bi bi-window me-1"></i><span data-workspace-label>Open workspace</span></a>
                <button type="button" class="btn btn-sm btn-outline-primary" data-global-action="expand"><i class="bi bi-arrows-fullscreen me-1"></i><span data-expand-label>Expand</span></button>
                <button type="button" class="btn btn-sm btn-outline-danger d-none" data-global-action="cancel"><i class="bi bi-stop-fill me-1"></i>Cancel</button>
                <span class="eln-jupyter-status badge bg-secondary" data-jupyter-status>Ready</span>
            </div>
            <div data-execution-message class="small text-muted mb-3"></div>
            <div data-jupyter-cells></div>
            <div class="eln-jupyter-history small text-muted" data-jupyter-history>No persistent Slurm session recorded yet.</div>
        `;

        const title = root.querySelector("[data-jupyter-title]");
        title.value = state.title;
        title.readOnly = !canEdit;
        title.addEventListener("input", markDirty);

        root.querySelectorAll('[data-global-action="add-code"], [data-global-action="add-markdown"], [data-global-action="save"]').forEach((button) => {
            button.classList.toggle("d-none", !canEdit);
        });
        root.querySelector('[data-global-action="run-all"]').classList.toggle("d-none", !canExecute);
        root.querySelector("[data-jupyter-download]").href = downloadUrl;
        const workspaceLink = root.querySelector("[data-open-workspace]");
        workspaceLink.href = standalone ? notebookUrl : workspaceUrl;
        workspaceLink.querySelector("[data-workspace-label]").textContent = standalone
            ? "Back to ELN"
            : "Open workspace";
        root.addEventListener("click", handleGlobalAction);
        renderCells();
        renderExecution(state.execution);
        setStatus(state.dirty ? "Unsaved" : "Saved", state.dirty ? "bg-warning text-dark" : "bg-secondary");
    }

    function markDirty() {
        state.dirty = true;
        setStatus("Unsaved", "bg-warning text-dark");
    }

    function handleCellAction(action, index) {
        collectNotebook();
        if (action === "run-through") {
            runNotebook(index);
            return;
        }
        if (action === "remove") {
            state.notebook.cells.splice(index, 1);
        } else if (action === "move-up" && index > 0) {
            [state.notebook.cells[index - 1], state.notebook.cells[index]] =
                [state.notebook.cells[index], state.notebook.cells[index - 1]];
        } else if (action === "move-down" && index < state.notebook.cells.length - 1) {
            [state.notebook.cells[index + 1], state.notebook.cells[index]] =
                [state.notebook.cells[index], state.notebook.cells[index + 1]];
        }
        markDirty();
        renderCells();
    }

    function handleGlobalAction(event) {
        const button = event.target.closest("[data-global-action]");
        if (!button || !root.contains(button)) return;
        const action = button.dataset.globalAction;
        if (action === "add-code" || action === "add-markdown") {
            collectNotebook();
            state.notebook.cells.push(newCell(action === "add-code" ? "code" : "markdown"));
            markDirty();
            renderCells();
            const sources = root.querySelectorAll("[data-source]");
            if (sources.length) sources[sources.length - 1].focus();
        } else if (action === "save") {
            saveDocument();
        } else if (action === "run-all") {
            runNotebook(null);
        } else if (action === "cancel") {
            cancelExecution();
        } else if (action === "expand") {
            toggleExpanded();
        }
    }

    function toggleExpanded(forceExpanded) {
        const nextExpanded = typeof forceExpanded === "boolean"
            ? forceExpanded
            : !root.classList.contains("is-expanded");
        root.classList.toggle("is-expanded", nextExpanded);
        document.body.classList.toggle(
            "eln-jupyter-expanded-open",
            nextExpanded,
        );

        const button = root.querySelector('[data-global-action="expand"]');
        if (!button) return;
        button.querySelector("i").className = nextExpanded
            ? "bi bi-fullscreen-exit me-1"
            : "bi bi-arrows-fullscreen me-1";
        button.querySelector("[data-expand-label]").textContent = nextExpanded
            ? "Exit full screen"
            : "Expand";
        button.setAttribute("aria-pressed", String(nextExpanded));
    }

    async function saveDocument() {
        if (!canEdit) return;
        collectNotebook();
        state.title = root.querySelector("[data-jupyter-title]").value.trim() || "ELN analysis";
        setStatus("Saving…", "bg-primary");
        const payload = await requestJson(documentUrl, {
            method: "POST",
            body: JSON.stringify({ title: state.title, notebook: state.notebook }),
        });
        state.documentId = payload.document.id;
        state.notebook = payload.document.notebook;
        state.title = payload.document.title;
        state.dirty = false;
        setStatus("Saved", "bg-success");
        return payload.document;
    }

    async function runNotebook(cellIndex) {
        if (!canExecute) return;
        try {
            await saveDocument();
            setStatus("Submitting…", "bg-primary");
            const payload = await requestJson(submitUrl, {
                method: "POST",
                body: JSON.stringify({
                    cell_index: cellIndex,
                }),
            });
            state.execution = payload.execution;
            renderExecution(state.execution);
            schedulePoll(1500);
        } catch (error) {
            setStatus("Execution error", "bg-danger");
            alert(error.message);
        }
    }

    function executionUrl(template, executionId) {
        return template.replace("/0/", `/${executionId}/`);
    }

    function renderExecution(execution) {
        const history = root.querySelector("[data-jupyter-history]");
        const message = root.querySelector("[data-execution-message]");
        const cancel = root.querySelector('[data-global-action="cancel"]');
        if (!history || !message || !cancel) return;

        if (!execution) {
            history.textContent = "No persistent Slurm session recorded yet.";
            cancel.classList.add("d-none");
            return;
        }

        const resourceText = `${execution.cpus} CPU · ${Math.round(execution.memory_mb / 1024)} GB · ${execution.time_minutes} min`;
        const scopeText = execution.requested_cell_index === null
            ? "all cells"
            : `through cell ${execution.requested_cell_index + 1}`;
        history.textContent = `Job ${execution.job_id} · ${execution.status} · ${scopeText} · ${resourceText} · submitted by ${execution.submitted_by}`;
        message.textContent = ["submitted", "pending", "running"].includes(execution.status)
            ? "The persistent kernel runs as the Biobank Slurm service account and remains available until the session time limit ends."
            : "";
        cancel.classList.toggle(
            "d-none",
            !canExecute || !["submitted", "pending", "running"].includes(execution.status),
        );
        setStatus(execution.status, statusTone(execution.status));
    }

    function schedulePoll(delay) {
        window.clearTimeout(state.pollingTimer);
        state.pollingTimer = window.setTimeout(pollExecution, delay);
    }

    async function pollExecution() {
        if (!state.execution) return;
        try {
            const payload = await requestJson(
                executionUrl(statusUrlTemplate, state.execution.id),
                { method: "GET" },
            );
            state.execution = payload.execution;
            if (payload.document && !state.dirty) {
                state.notebook = payload.document;
                renderCells();
            } else if (payload.document && state.dirty) {
                const message = root.querySelector(
                    "[data-execution-message]"
                );
                if (message) {
                    message.textContent = (
                        "Unsaved local changes were preserved "
                        + "while the Slurm session was refreshed."
                    );
                }
            }
            renderExecution(state.execution);
            if (["submitted", "pending", "running", "unknown"].includes(state.execution.status)) {
                schedulePoll(3000);
            }
            if (payload.warning) {
                root.querySelector("[data-execution-message]").textContent = payload.warning;
            }
        } catch (error) {
            root.querySelector("[data-execution-message]").textContent = error.message;
            schedulePoll(5000);
        }
    }

    async function cancelExecution() {
        if (!state.execution || !canExecute) return;
        if (!window.confirm(`Stop persistent Slurm session ${state.execution.job_id}?`)) return;
        try {
            const payload = await requestJson(
                executionUrl(cancelUrlTemplate, state.execution.id),
                { method: "POST", body: "{}" },
            );
            state.execution = payload.execution;
            renderExecution(state.execution);
        } catch (error) {
            alert(error.message);
        }
    }

    async function loadDocument() {
        try {
            const payload = await requestJson(documentUrl, { method: "GET" });
            if (payload.document) {
                state.documentId = payload.document.id;
                state.title = payload.document.title;
                state.notebook = payload.document.notebook || emptyNotebook();
                state.execution = payload.document.latest_execution;
            }
            renderWorkspace();
            if (state.execution && ["submitted", "pending", "running", "unknown"].includes(state.execution.status)) {
                schedulePoll(1000);
            }
        } catch (error) {
            root.innerHTML = `<div class="alert alert-danger" role="alert"></div>`;
            root.firstElementChild.textContent = error.message;
        }
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && root.classList.contains("is-expanded")) {
            toggleExpanded(false);
            return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && canEdit) {
            const pane = document.getElementById("jupyter-pane");
            if (standalone || (pane && pane.classList.contains("active"))) {
                event.preventDefault();
                saveDocument().catch((error) => alert(error.message));
            }
        }
    });


    window.addEventListener("beforeunload", (event) => {
        if (!state.dirty) return;

        event.preventDefault();
        event.returnValue = "";
    });

    loadDocument();
})();
