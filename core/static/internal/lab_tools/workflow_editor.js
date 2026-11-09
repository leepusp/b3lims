/* Workflow editor: a canvas of steps and connections, backed by the workflow JSON API. */
(function () {
    "use strict";

    const root = document.getElementById("workflow-editor");

    if (!root) return;

    const $ = (id) => document.getElementById(id);
    const apiUrl = root.dataset.apiUrl;
    const lookupUrl = root.dataset.lookupUrl;
    const canEdit = root.dataset.canEdit === "1";
    const csrf = () => (root.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
    const NODE_W = 200;
    const NODE_H = 64;
    const STATUS_LABEL = {todo: "To do", doing: "In progress", done: "Done", blocked: "Blocked"};

    let wf = JSON.parse($("wf-data").textContent);
    let selected = null;
    let connectFrom = null;
    let pickerKind = null;
    let draft = {};

    function esc(text) {
        const el = document.createElement("div");

        el.textContent = text == null ? "" : String(text);

        return el.innerHTML;
    }

    function showError(message) {
        const box = $("wf-error");

        box.textContent = message || "";
        box.hidden = !message;
    }

    async function call(payload) {
        showError("");

        const response = await fetch(apiUrl, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({status: "error", message: "Unexpected response."}));

        if (data.status !== "success") {
            showError(data.message || "Could not save.");

            return null;
        }

        return data;
    }

    async function act(payload) {
        const data = await call(payload);

        if (data && data.workflow) {
            wf = data.workflow;
            render();
        }

        return data;
    }

    // Redraw everything except the form fields, so typing is never interrupted.
    function renderQuiet() {
        renderHeader();
        renderNodes();
        renderEdges();

        const step = selected ? stepById(selected) : null;

        if (step) {
            if (document.activeElement !== $("wf-f-status")) $("wf-f-status").value = step.status;

            renderRun(step);
        }
    }

    function setSaved(text) {
        const el = $("wf-saved");

        if (el) el.textContent = text;
    }

    function stepPayload() {
        const jupyter = $("wf-f-kind").value === "jupyter";

        return {
            title: $("wf-f-title").value, status: $("wf-f-status").value, kind: $("wf-f-kind").value,
            assignee: $("wf-f-assignee").value || null, due_date: $("wf-f-due").value, notes: $("wf-f-notes").value,
            entry: draft.eln || null, molecule: draft.molecule || null, sample: draft.sample || null,
            jupyter_notebook: jupyter ? (draft.jupyter || null) : null,
            parameters: jupyter ? $("wf-f-params").value : "",
            result_note: $("wf-f-result").value,
        };
    }

    let saveTimer = null;
    let saving = Promise.resolve(true);

    // The payload is read now, so switching steps right after typing still saves the right one.
    function saveNow() {
        clearTimeout(saveTimer);
        saveTimer = null;

        if (!canEdit || !selected) return Promise.resolve(true);

        const payload = {action: "update_step", step_id: selected, step: stepPayload()};

        setSaved("Saving…");
        saving = saving.then(async () => {
            const data = await call(payload);

            if (data && data.workflow) {
                wf = data.workflow;
                renderQuiet();
                setSaved("Saved");

                return true;
            }

            setSaved("Not saved");

            return false;
        });

        return saving;
    }

    function scheduleSave() {
        if (!canEdit || !selected) return;

        setSaved("Editing…");
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveNow, 700);
    }

    // --- canvas ---------------------------------------------------------------

    function stepById(id) { return wf.steps.find((s) => s.id === id); }

    const THUMB_H = 96;

    function thumbOf(step) { return step.run && step.run.images && step.run.images.length ? step.run.images[0] : ""; }
    function nodeHeight(step) { return NODE_H + (thumbOf(step) ? THUMB_H : 0); }
    function runBadge(step) {
        const run = step.run;

        if (!run) return "";

        const label = {submitted: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled"}[run.state] || run.state;
        const extra = [];

        if (run.duration !== null && run.duration !== undefined) extra.push(run.duration + " s");
        if (run.resources && run.resources.partition) extra.push(esc(run.resources.partition) + (run.resources.node && run.resources.node !== "auto" ? "/" + esc(run.resources.node) : ""));

        return "<div class='wf-run wf-run-" + esc(run.state) + "'><span class='wf-run-pill'>" + label + "</span>" + (extra.length ? "<span>" + extra.join(" · ") + "</span>" : "") + "</div>";
    }

    function dueHtml(step) {
        if (!step.due_date) return "";

        const late = step.status !== "done" && new Date(step.due_date) < new Date();

        return "<span class='" + (late ? "overdue" : "") + "'><i class='bi bi-calendar-event'></i> " + esc(step.due_date.replace("T", " ")) + "</span>";
    }

    function renderNodes() {
        const layer = $("wf-nodes");

        layer.innerHTML = "";
        wf.steps.forEach((step) => {
            const node = document.createElement("div");

            node.className = "wf-node" + (step.id === selected ? " selected" : "");
            node.dataset.id = step.id;
            node.dataset.status = step.status;
            node.style.left = step.x + "px";
            node.style.top = step.y + "px";
            node.dataset.kind = step.kind;
            node.style.minHeight = nodeHeight(step) + "px";
            node.innerHTML = "<div class='wf-node-title'>" + esc(step.title) + "</div>" + runBadge(step)
                + (thumbOf(step) ? "<img class='wf-thumb' alt='Figure from the last run' src='" + esc(thumbOf(step)) + "'>" : "")
                + "<div class='wf-node-meta'><span>" + STATUS_LABEL[step.status] + "</span>"
                + (step.assignee_name ? "<span><i class='bi bi-person'></i> " + esc(step.assignee_name) + "</span>" : "") + dueHtml(step)
                + (step.entry ? "<span title='ELN entry'><i class='bi bi-journal-bookmark'></i></span>" : "")
                + (step.molecule ? "<span title='Molecular record'><i class='bi bi-bezier2'></i></span>" : "")
                + (step.sample ? "<span title='Sample'><i class='bi bi-eyedropper'></i></span>" : "")
                + (step.kind === "jupyter" ? "<span title='Jupyter notebook step'><i class='bi bi-code-square'></i></span>" : "") + "</div>"
                + (canEdit ? "<button type='button' class='wf-port' aria-label='Connect from this step'></button>" : "");
            layer.appendChild(node);
        });
        $("wf-empty").hidden = wf.steps.length > 0;
    }

    function renderEdges() {
        const svg = $("wf-edges");

        svg.querySelectorAll("path.wf-edge").forEach((p) => p.remove());
        wf.edges.forEach((edge) => {
            const a = stepById(edge.source);
            const b = stepById(edge.target);

            if (!a || !b) return;

            const x1 = a.x + NODE_W;
            const y1 = a.y + nodeHeight(a) / 2;
            const x2 = b.x;
            const y2 = b.y + nodeHeight(b) / 2;
            const dx = Math.max(40, Math.abs(x2 - x1) / 2);
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

            path.setAttribute("class", "wf-edge");
            path.setAttribute("d", "M" + x1 + "," + y1 + " C" + (x1 + dx) + "," + y1 + " " + (x2 - dx) + "," + y2 + " " + x2 + "," + y2);
            path.setAttribute("marker-end", "url(#wf-arrow)");
            path.dataset.id = edge.id;
            path.innerHTML = "<title>Click to remove this connection</title>";
            svg.appendChild(path);
        });
    }

    function renderHeader() {
        const c = wf.counts;
        const total = wf.steps.length;

        if (document.activeElement !== $("wf-name")) $("wf-name").value = wf.name;

        $("wf-status").value = wf.status;
        $("wf-summary").textContent = total ? c.done + " of " + total + " done" + (c.blocked ? " · " + c.blocked + " blocked" : "") : "No steps yet";

        const select = $("wf-members-select");

        Array.from(select.options).forEach((o) => { o.selected = wf.members.some((m) => String(m.id) === o.value); });
    }

    function render() {
        renderHeader();
        renderNodes();
        renderEdges();
        renderPanel();
    }

    // --- side panel -----------------------------------------------------------

    const LINKS = {
        eln: {id: "entry", label: "entry_label", url: "entry_url"},
        molecule: {id: "molecule", label: "molecule_label", url: "molecule_url"},
        sample: {id: "sample", label: "sample_label", url: "sample_url"},
        jupyter: {id: "jupyter_notebook", label: "jupyter_label", url: "jupyter_url"},
    };

    function setLink(kind, step) {
        const box = root.querySelector(".wf-link[data-kind='" + kind + "']");
        const label = box.querySelector(".wf-link-label");
        const id = draft[kind];
        const map = LINKS[kind];
        const text = step[map.label];
        const url = step[map.url];
        const unchanged = String(id || "") === String(step[map.id] || "");

        if (id && unchanged && url) label.innerHTML = "<a href='" + esc(url) + "'>" + esc(text) + "</a>";
        else if (id && unchanged) label.textContent = text;
        else if (id) label.textContent = draft[kind + "_label"] || "Selected";
        else label.innerHTML = "<span class='text-muted'>None</span>";

        label.classList.toggle("muted", !id);
        box.querySelector(".wf-link-set").hidden = !canEdit;
    }

    function renderPanel() {
        const step = selected ? stepById(selected) : null;

        $("wf-form").hidden = !step;
        $("wf-panel-empty").hidden = !!step;

        if (!step) return;

        $("wf-f-title").value = step.title;
        $("wf-f-status").value = step.status;
        $("wf-f-kind").value = step.kind;
        $("wf-f-assignee").value = step.assignee || "";
        $("wf-f-due").value = step.due_date || "";
        $("wf-f-notes").value = step.notes;
        draft = {eln: step.entry, molecule: step.molecule, sample: step.sample, jupyter: step.jupyter_notebook};
        ["eln", "molecule", "sample", "jupyter"].forEach((k) => setLink(k, step));
        $("wf-jupyter").hidden = step.kind !== "jupyter";
        $("wf-f-params").value = step.parameters || "";
        $("wf-f-result").value = step.result_note || "";
        const saved = step.run_resources || {};

        $("wf-run-partition").value = saved.partition || "basic";
        $("wf-run-node").value = saved.node || "auto";
        $("wf-run-cpus").value = saved.cpus || 2;
        $("wf-run-mem").value = saved.memory_mb || 4096;
        $("wf-run-min").value = saved.minutes || 60;
        renderRun(step);
        $("wf-form").querySelectorAll("input,select,textarea").forEach((el) => { if (!canEdit) el.disabled = true; });
    }

    function renderRun(step) {
        const run = step.run;
        const active = !!run && (run.state === "submitted" || run.state === "running");
        const parts = run ? [run.state + (run.job_id ? " · job " + run.job_id : ""), run.created_at] : ["No run yet"];

        if (run && run.result && run.result.seconds !== undefined) parts.push(run.result.seconds + " s");
        if (run && run.error) parts.push(run.error);

        $("wf-run-state").textContent = parts.join(" · ");
        const text = run ? (run.output_text || (run.state === "failed" ? run.log_tail : "")) : "";

        $("wf-run-log").hidden = !text;
        $("wf-run-log").textContent = text;
        $("wf-run-figs").innerHTML = run && run.images ? run.images.map((url) => "<a href='" + esc(url) + "' target='_blank' rel='noopener'><img class='wf-fig' alt='Figure' src='" + esc(url) + "'></a>").join("") : "";
        $("wf-run-start").hidden = !canEdit || active;
        $("wf-run-refresh").hidden = !active;
        $("wf-run-cancel").hidden = !canEdit || !active;
        $("wf-run-start").disabled = !draft.jupyter;
    }

    $("wf-run-start").addEventListener("click", async () => {
        if (!selected || !(await saveNow())) return;

        act({action: "run_step", step_id: selected, resources: {
            partition: $("wf-run-partition").value, node: $("wf-run-node").value, cpus: $("wf-run-cpus").value, memory_mb: $("wf-run-mem").value, minutes: $("wf-run-min").value,
        }});
    });
    $("wf-run-refresh").addEventListener("click", () => {
        const run = stepById(selected).run;
        if (run) act({action: "refresh_run", run_id: run.id});
    });
    $("wf-run-cancel").addEventListener("click", () => {
        const run = stepById(selected).run;
        if (run && window.confirm("Cancel this run?")) act({action: "cancel_run", run_id: run.id});
    });

    $("wf-f-kind").addEventListener("change", () => { $("wf-jupyter").hidden = $("wf-f-kind").value !== "jupyter"; });

    $("wf-form").addEventListener("submit", (event) => { event.preventDefault(); saveNow(); });
    $("wf-form").addEventListener("input", scheduleSave);
    $("wf-form").addEventListener("change", scheduleSave);

    $("wf-step-delete").addEventListener("click", async () => {
        if (!selected || !window.confirm("Delete this step and its connections?")) return;

        const id = selected;

        selected = null;
        await act({action: "delete_step", step_id: id});
    });

    // --- canvas interaction ---------------------------------------------------

    const board = $("wf-board");
    let drag = null;

    board.addEventListener("pointerdown", (event) => {
        const port = event.target.closest(".wf-port");
        const node = event.target.closest(".wf-node");

        if (!node) return;

        const id = Number(node.dataset.id);

        if (port) {
            event.preventDefault();
            connectFrom = connectFrom === id ? null : id;
            board.querySelectorAll(".wf-node").forEach((n) => n.classList.toggle("wf-connecting", Number(n.dataset.id) === connectFrom));

            return;
        }

        if (connectFrom && connectFrom !== id) {
            const source = connectFrom;

            connectFrom = null;
            act({action: "add_edge", source, target: id});

            return;
        }

        if (saveTimer) saveNow();

        selected = id;
        board.querySelectorAll(".wf-node").forEach((n) => n.classList.toggle("selected", Number(n.dataset.id) === id));
        renderPanel();
        setSaved("");

        if (!canEdit) return;

        const step = stepById(id);

        drag = {id, node, startX: event.clientX, startY: event.clientY, x: step.x, y: step.y, moved: false};
        node.setPointerCapture(event.pointerId);
        node.style.cursor = "grabbing";
    });

    board.addEventListener("pointermove", (event) => {
        if (!drag) return;

        const dx = event.clientX - drag.startX;
        const dy = event.clientY - drag.startY;

        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;

        const step = stepById(drag.id);

        step.x = Math.max(0, Math.round((drag.x + dx) / 10) * 10);
        step.y = Math.max(0, Math.round((drag.y + dy) / 10) * 10);
        drag.node.style.left = step.x + "px";
        drag.node.style.top = step.y + "px";
        renderEdges();
    });

    board.addEventListener("pointerup", async () => {
        if (!drag) return;

        const finished = drag;
        const step = stepById(finished.id);

        drag = null;
        finished.node.style.cursor = "";

        if (finished.moved) await call({action: "move_steps", positions: [{id: step.id, x: step.x, y: step.y}]});
    });

    board.addEventListener("click", (event) => {
        const path = event.target.closest && event.target.closest("path.wf-edge");

        if (path && canEdit) act({action: "delete_edge", edge_id: Number(path.dataset.id)});
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && connectFrom) {
            connectFrom = null;
            board.querySelectorAll(".wf-node").forEach((n) => n.classList.remove("wf-connecting"));
        }
    });

    // --- header actions -------------------------------------------------------

    if (canEdit) {
        $("wf-name").addEventListener("change", () => act({action: "update", name: $("wf-name").value}));
        $("wf-status").addEventListener("change", () => act({action: "update", status: $("wf-status").value}));
        $("wf-add").addEventListener("click", async () => {
            const maxY = wf.steps.reduce((m, s) => Math.max(m, s.y), 0);
            const data = await act({action: "add_step", step: {title: "New step", x: 40, y: wf.steps.length ? maxY + 110 : 40}});

            if (data && data.step_id) {
                selected = data.step_id;
                render();
                $("wf-f-title").focus();
                $("wf-f-title").select();
            }
        });

        const del = $("wf-delete");

        if (del) {
            del.addEventListener("click", async () => {
                if (!window.confirm("Delete this workflow and all its steps?")) return;

                const data = await call({action: "delete"});

                if (data) window.location.href = root.dataset.listUrl;
            });
        }

        $("wf-import").addEventListener("click", () => openPicker("eln", async (id) => {
            if (id) await act({action: "import_eln", entry: id});
        }, "Import steps from an ELN entry"));

        $("wf-share").addEventListener("click", () => bootstrap.Modal.getOrCreateInstance($("wf-members")).show());

        const save = $("wf-members-save");

        if (save) {
            save.addEventListener("click", async () => {
                const ids = Array.from($("wf-members-select").selectedOptions).map((o) => Number(o.value));

                await act({action: "update", members: ids});
                bootstrap.Modal.getOrCreateInstance($("wf-members")).hide();
            });
        }
    }

    // --- link picker ----------------------------------------------------------

    let pickerCallback = null;
    let pickerTimer = null;

    function openPicker(kind, callback, title) {
        pickerKind = kind;
        pickerCallback = callback;
        $("wf-picker-title").textContent = title;
        $("wf-picker-q").value = "";
        $("wf-picker-clear").hidden = kind === "eln" && title.indexOf("Import") === 0;
        bootstrap.Modal.getOrCreateInstance($("wf-picker")).show();
        search();
    }

    async function search() {
        const list = $("wf-picker-results");
        const response = await fetch(lookupUrl + "?" + new URLSearchParams({kind: pickerKind, q: $("wf-picker-q").value}));
        const data = response.ok ? await response.json() : {results: []};

        list.innerHTML = data.results.length ? "" : "<div class='small text-muted p-2'>Nothing found.</div>";
        data.results.forEach((item) => {
            const button = document.createElement("button");

            button.type = "button";
            button.className = "list-group-item list-group-item-action small";
            button.textContent = item.label;
            button.addEventListener("click", () => {
                bootstrap.Modal.getOrCreateInstance($("wf-picker")).hide();
                pickerCallback(item.id, item.label);
            });
            list.appendChild(button);
        });
    }

    $("wf-picker-q").addEventListener("input", () => {
        clearTimeout(pickerTimer);
        pickerTimer = setTimeout(search, 250);
    });
    $("wf-picker-clear").addEventListener("click", () => {
        bootstrap.Modal.getOrCreateInstance($("wf-picker")).hide();
        pickerCallback(null, "");
    });

    root.querySelectorAll(".wf-link-set").forEach((button) => {
        button.addEventListener("click", () => {
            const kind = button.closest(".wf-link").dataset.kind;
            const names = {eln: "Choose an ELN entry", molecule: "Choose a molecular record", sample: "Choose a sample", jupyter: "Choose a Jupyter notebook"};

            openPicker(kind, (id, label) => {
                draft[kind] = id;
                draft[kind + "_label"] = label;
                setLink(kind, stepById(selected));
                if (kind === "jupyter") $("wf-run-start").disabled = !draft.jupyter;
                scheduleSave();
            }, names[kind]);
        });
    });

    // Follow active runs without a Refresh click.
    setInterval(async () => {
        if (document.hidden || drag) return;

        const active = wf.steps.filter((s) => s.run && (s.run.state === "submitted" || s.run.state === "running"));

        for (const step of active) {
            const data = await call({action: "refresh_run", run_id: step.run.id});

            if (data && data.workflow) {
                wf = data.workflow;
                renderQuiet();
            }
        }
    }, 6000);

    render();
})();
