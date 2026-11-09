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
            renderFiles(step);
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

    function nodeHeight(step) {
        const el = document.querySelector(".wf-node[data-id='" + step.id + "']");

        return el ? el.offsetHeight : NODE_H;
    }
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

    function miniMap(m) {
        const total = Math.max(1, m.length || 1);
        const color = (f) => /^#[0-9a-fA-F]{3,8}$/.test(f.c) ? f.c : "#868e96";

        if (m.topology === "circular") {
            const R = 34, C = 44;
            const point = (pos, r) => {
                const angle = (pos / total) * 2 * Math.PI - Math.PI / 2;

                return [C + r * Math.cos(angle), C + r * Math.sin(angle)];
            };
            const arcs = m.features.map((f) => {
                const [x1, y1] = point(Math.max(0, f.s - 1), R);
                const [x2, y2] = point(Math.min(total, f.e), R);
                const large = (f.e - f.s) / total > 0.5 ? 1 : 0;

                return "<path d='M" + x1.toFixed(1) + "," + y1.toFixed(1) + " A" + R + "," + R + " 0 " + large + " 1 " + x2.toFixed(1) + "," + y2.toFixed(1)
                    + "' fill='none' stroke='" + color(f) + "' stroke-width='7'><title>" + esc(f.n) + "</title></path>";
            }).join("");

            return "<svg class='wf-map' viewBox='0 0 88 88' aria-hidden='true'><circle cx='" + C + "' cy='" + C + "' r='" + R + "' fill='none' stroke='#ced4da' stroke-width='2'/>" + arcs
                + "<text x='" + C + "' y='" + (C + 3) + "' text-anchor='middle' font-size='9' fill='#495057'>" + esc(String(m.length)) + " bp</text></svg>";
        }

        const bars = m.features.map((f) => {
            const x = (Math.max(0, f.s - 1) / total) * 176;
            const w = Math.max(2, ((f.e - f.s + 1) / total) * 176);

            return "<rect x='" + x.toFixed(1) + "' y='8' width='" + w.toFixed(1) + "' height='10' rx='2' fill='" + color(f) + "'><title>" + esc(f.n) + "</title></rect>";
        }).join("");

        return "<svg class='wf-map wf-map-line' viewBox='0 0 176 26' aria-hidden='true'><line x1='0' y1='13' x2='176' y2='13' stroke='#ced4da' stroke-width='2'/>" + bars + "</svg>";
    }

    function previewHtml(step) {
        const p = step.preview || {};
        const out = [];

        if (p.molecule) {
            const m = p.molecule;

            out.push("<div class='wf-prev'><div class='wf-prev-title'><i class='bi bi-bezier2'></i> " + esc(m.name) + "</div><div class='wf-prev-sub'>" + esc(m.type) + " · "
                + esc(m.topology) + " · " + esc(String(m.length)) + " bp" + (m.gc !== null ? " · GC " + m.gc + "%" : "") + "</div>" + (m.length ? miniMap(m) : "") + "</div>");
        }
        if (p.sample) out.push("<div class='wf-prev'><div class='wf-prev-title'><i class='bi bi-eyedropper'></i> " + esc(p.sample.id) + "</div><div class='wf-prev-sub'>" + esc([p.sample.type, p.sample.organism].filter(Boolean).join(" · ")) + "</div></div>");
        if (p.entry) {
            const e = p.entry;

            out.push("<div class='wf-prev'><div class='wf-prev-title'><i class='bi bi-journal-bookmark'></i> " + esc(e.title) + "</div>"
                + (e.steps_total ? "<div class='wf-prev-sub'>" + e.steps_done + " / " + e.steps_total + " ELN steps done</div>" : "") + "</div>");
        }

        return out.join("");
    }

    function tableHtml(step) {
        const table = step.run && step.run.tables && step.run.tables[0];

        if (!table || !table.length) return "";

        const rows = table.slice(0, 4).map((row, i) => "<tr>" + row.slice(0, 4).map((cell) => (i === 0 ? "<th>" : "<td>") + esc(cell) + (i === 0 ? "</th>" : "</td>")).join("") + "</tr>").join("");

        return "<div class='wf-table-wrap'><table class='wf-table'>" + rows + "</table>" + (table.length > 4 ? "<div class='wf-prev-sub'>+ " + (table.length - 4) + " more rows</div>" : "") + "</div>";
    }

    function renderNodes() {
        const layer = $("wf-nodes");

        layer.innerHTML = "";
        wf.steps.forEach((step) => {
            const node = document.createElement("div");
            const note = step.kind === "note";

            node.className = "wf-node" + (note ? " wf-note" : "") + (step.id === selected ? " selected" : "");
            node.dataset.id = step.id;
            node.dataset.status = note ? "note" : step.status;
            node.dataset.kind = step.kind;
            node.style.left = step.x + "px";
            node.style.top = step.y + "px";

            if (note) {
                node.innerHTML = "<div class='wf-node-title'><i class='bi bi-sticky'></i> " + esc(step.title) + "</div>"
                    + (step.notes ? "<div class='wf-note-text'>" + esc(step.notes.slice(0, 400)) + "</div>" : "");
                layer.appendChild(node);

                return;
            }

            const thumb = thumbOf(step) || (step.files && step.files.length ? step.files[0].url : "");

                        node.innerHTML = "<div class='wf-node-title'>" + esc(step.title) + "</div>" + runBadge(step)
                + (thumb ? "<img class='wf-thumb' alt='Figure' src='" + esc(thumb) + "'>" : "") + tableHtml(step) + previewHtml(step)
                + "<div class='wf-node-meta'><span>" + STATUS_LABEL[step.status] + "</span>"
                + (step.assignee_name ? "<span><i class='bi bi-person'></i> " + esc(step.assignee_name) + "</span>" : "") + dueHtml(step)
                + (step.files && step.files.length ? "<span title='Attached images'><i class='bi bi-images'></i> " + step.files.length + "</span>" : "")
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

    function applyKindLayout(kind) {
        const note = kind === "note";

        root.querySelectorAll(".wf-work-only").forEach((el) => { el.hidden = note; });
        $("wf-jupyter").hidden = kind !== "jupyter";
        $("wf-f-notes-label").textContent = note ? "Annotation" : "Notes";
        $("wf-f-notes").rows = note ? 8 : 3;
    }

    function renderFiles(step) {
        const list = $("wf-files-list");

        list.innerHTML = (step.files || []).map((f) => "<span class='wf-file'><a href='" + esc(f.url) + "' target='_blank' rel='noopener'><img class='wf-fig' alt='" + esc(f.name) + "' title='" + esc(f.name) + "' src='" + esc(f.url) + "'></a>"
            + (canEdit ? "<button type='button' class='btn btn-sm btn-link text-danger p-0 wf-file-del' data-id='" + f.id + "' aria-label='Remove " + esc(f.name) + "'>Remove</button>" : "") + "</span>").join("");
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
        applyKindLayout(step.kind);
        renderFiles(step);
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
        $("wf-run-tables").innerHTML = (run && run.tables ? run.tables : []).map((table) => "<div class='wf-table-wrap'><table class='wf-table'>"
            + table.map((row, i) => "<tr>" + row.map((cell) => (i === 0 ? "<th>" : "<td>") + esc(cell) + (i === 0 ? "</th>" : "</td>")).join("") + "</tr>").join("") + "</table></div>").join("");
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

    $("wf-f-kind").addEventListener("change", () => applyKindLayout($("wf-f-kind").value));

    $("wf-files-list").addEventListener("click", async (event) => {
        const button = event.target.closest(".wf-file-del");

        if (!button || !canEdit || !window.confirm("Remove this image?")) return;

        await act({action: "delete_file", file_id: Number(button.dataset.id)});
    });

    const fileInput = $("wf-file-input");

    if (fileInput) {
        fileInput.addEventListener("change", async () => {
            const file = fileInput.files[0];

            if (!file || !selected) return;

            showError("");

            const body = new FormData();

            body.append("file", file);

            const response = await fetch(apiUrl.replace(/api\/$/, "steps/" + selected + "/files/"), {method: "POST", headers: {"X-CSRFToken": csrf()}, body});
            const data = await response.json().catch(() => ({status: "error", message: "Unexpected response."}));

            fileInput.value = "";

            if (data.status === "success") {
                wf = data.workflow;
                renderQuiet();
                renderFiles(stepById(selected));
            } else {
                showError(data.message || "Could not upload the image.");
            }
        });
    }

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

    // --- layout ---------------------------------------------------------------

    function bottomY() {
        return wf.steps.reduce((m, s) => Math.max(m, s.y + nodeHeight(s)), 0);
    }

    // Columns by depth in the flow, stacked with the real card heights; notes go to the right.
    async function arrange() {
        const work = wf.steps.filter((s) => s.kind !== "note");
        const notes = wf.steps.filter((s) => s.kind === "note");
        const incoming = {};
        const level = {};

        wf.edges.forEach((e) => { (incoming[e.target] = incoming[e.target] || []).push(e.source); });

        const depth = (id, seen) => {
            if (level[id] !== undefined) return level[id];
            if (seen.has(id)) return 0;

            seen.add(id);
            level[id] = (incoming[id] || []).reduce((m, src) => Math.max(m, depth(src, seen) + 1), 0);

            return level[id];
        };

        work.forEach((s) => depth(s.id, new Set()));

        const columns = {};

        work.forEach((s) => { (columns[level[s.id]] = columns[level[s.id]] || []).push(s); });

        const positions = [];
        const widest = Math.max(-1, ...Object.keys(columns).map(Number));

        Object.keys(columns).forEach((key) => {
            let y = 40;

            columns[key].sort((a, b) => a.y - b.y).forEach((s) => {
                s.x = 40 + Number(key) * 260;
                s.y = y;
                y += nodeHeight(s) + 24;
                positions.push({id: s.id, x: s.x, y: s.y});
            });
        });

        let noteY = 40;

        notes.forEach((s) => {
            s.x = 40 + (widest + 1) * 260;
            s.y = noteY;
            noteY += nodeHeight(s) + 24;
            positions.push({id: s.id, x: s.x, y: s.y});
        });

        renderNodes();
        renderEdges();

        // Heights are real now: stack again with them.
        let moved = false;

        Object.keys(columns).forEach((key) => {
            let y = 40;

            columns[key].forEach((s) => {
                const height = nodeHeight(s);

                if (s.y !== y) { s.y = y; moved = true; }

                y += height + 24;
            });
        });

        if (moved) { renderNodes(); renderEdges(); }

        await call({action: "move_steps", positions: wf.steps.map((s) => ({id: s.id, x: s.x, y: s.y}))});
    }

    // --- header actions -------------------------------------------------------

    if (canEdit) {
        $("wf-name").addEventListener("change", () => act({action: "update", name: $("wf-name").value}));
        $("wf-status").addEventListener("change", () => act({action: "update", status: $("wf-status").value}));
        $("wf-add").addEventListener("click", async () => {
            const data = await act({action: "add_step", step: {title: "New step", x: 40, y: wf.steps.length ? bottomY() + 24 : 40}});

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

        $("wf-arrange").addEventListener("click", arrange);
        $("wf-add-note").addEventListener("click", async () => {
            const data = await act({action: "add_step", step: {title: "Note", kind: "note", x: 40, y: wf.steps.length ? bottomY() + 24 : 40}});

            if (data && data.step_id) {
                selected = data.step_id;
                render();
                $("wf-f-notes").focus();
            }
        });

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
