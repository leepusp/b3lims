/*
 * RNA 3D structure (PDB / mmCIF) in Mol*.
 *
 * Stored structure files are attached to the RNA record through the same
 * structures endpoint the Protein record uses. The viewer is created once and
 * kept alive while the user moves between tabs: the sequence selection is
 * pushed into it instead of rebuilding it.
 *
 * Exposes window.BiobankRnaStructure3D.mount(onFallback) -> element.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");

    if (!root || root.dataset.sequenceType !== "rna") return;

    const url = root.dataset.proteinStructuresUrl || "";
    const state = {items: [], selectedId: null, viewer: null, host: null, numbering: 1, loaded: null, busy: false};
    const ui = {};

    const el = (tag, cls, text) => {
        const n = document.createElement(tag);

        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;

        return n;
    };

    const rawUrl = id => `${url}${url.includes("?") ? "&" : "?"}structure_id=${id}&raw=1`;
    const csrf = () => root.dataset.csrfToken || "";

    function status(text, kind) {
        if (!ui.status) return;

        ui.status.textContent = text || "";
        ui.status.dataset.kind = kind || "";
    }

    function viewerReady() {
        return Boolean(window.molstar && window.molstar.Viewer && typeof window.molstar.Viewer.create === "function");
    }

    async function loadList() {
        try {
            const response = await fetch(url, {credentials: "same-origin", headers: {Accept: "application/json"}});
            const data = await response.json();

            state.items = Array.isArray(data.structures) ? data.structures : [];
        } catch (error) {
            state.items = [];
        }

        if (!state.items.some(i => i.id === state.selectedId)) state.selectedId = state.items.length ? state.items[0].id : null;
    }

    function disposeViewer() {
        if (state.viewer && state.viewer.plugin && typeof state.viewer.plugin.dispose === "function") {
            try {
                state.viewer.plugin.dispose();
            } catch (error) {
                console.warn("Could not dispose the Mol* viewer", error);
            }
        }

        state.viewer = null;
        state.loaded = null;

        if (ui.stage) ui.stage.replaceChildren();
    }

    async function showSelected() {
        const item = state.items.find(i => i.id === state.selectedId);

        ui.empty.hidden = Boolean(item);
        ui.stage.hidden = !item;
        ui.remove.disabled = !item;
        ui.download.hidden = !item;

        if (!item) {
            disposeViewer();
            status("");

            return;
        }

        ui.download.href = `${url}${url.includes("?") ? "&" : "?"}structure_id=${item.id}&download=1`;

        if (state.loaded === item.id && state.viewer) return;

        if (!viewerReady()) {
            status("The Mol* viewer is not available on this page.", "error");

            return;
        }

        state.busy = true;
        status("Loading structure…");

        try {
            const response = await fetch(rawUrl(item.id), {credentials: "same-origin"});

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const text = await response.text();

            disposeViewer();
            state.viewer = await window.molstar.Viewer.create(ui.stage, {
                layoutIsExpanded: false, layoutShowControls: true, layoutShowRemoteState: false,
                layoutShowSequence: false, layoutShowLog: false, layoutShowLeftPanel: false,
                viewportShowExpand: true, viewportShowSelectionMode: true, viewportShowControls: true,
                viewportShowAnimation: false, viewportBackgroundColor: "#111318",
            });

            const label = item.label || item.original_filename || "RNA structure";

            await state.viewer.loadStructureFromData(text, String(item.source_format).toLowerCase() === "pdb" ? "pdb" : "mmcif", {dataLabel: label});
            state.loaded = item.id;
            window.BiobankRnaStructureViewer = state.viewer;
            status(`${label} loaded. Select nucleotides in the sequence to highlight them here.`, "ok");
            syncSelection();
        } catch (error) {
            console.error("RNA structure failed to load", error);
            status("Could not load this structure file.", "error");
        } finally {
            state.busy = false;
        }
    }

    function currentSelection() {
        const api = window.BiobankMolecularWorkspace;
        const snap = api && api.getSnapshot && api.getSnapshot();
        const r = snap && snap.sequenceSelection;

        if (!r || !Number.isFinite(Number(r.start)) || !Number.isFinite(Number(r.end))) return null;

        return [Math.min(Number(r.start), Number(r.end)), Math.max(Number(r.start), Number(r.end))];
    }

    function syncSelection(focus) {
        const viewer = state.viewer;

        if (!viewer || typeof viewer.structureInteractivity !== "function") return;

        const sel = currentSelection();
        const shift = Number(state.numbering) - 1;

        try {
            viewer.structureInteractivity({action: "select"});

            if (!sel) return;

            const elements = {beg_auth_seq_id: sel[0] + shift, end_auth_seq_id: sel[1] + shift};

            viewer.structureInteractivity({elements, action: "select"});

            if (focus) viewer.structureInteractivity({elements, action: "focus", focusOptions: {extraRadius: 4}});
        } catch (error) {
            console.warn("Could not select residues in the structure", error);
        }
    }

    async function upload(file) {
        if (!file) return;

        const data = new FormData();

        data.append("action", "upload");
        data.append("file", file);
        data.append("label", file.name.replace(/\.[^.]+$/, ""));
        status("Uploading…");

        try {
            const response = await fetch(url, {method: "POST", credentials: "same-origin", body: data, headers: {"X-CSRFToken": csrf(), Accept: "application/json"}});
            const payload = await response.json();

            if (!response.ok) {
                status(payload.message || "Upload failed.", "error");

                return;
            }

            await loadList();
            state.selectedId = payload.structure ? payload.structure.id : state.selectedId;
            fillSelect();
            await showSelected();
        } catch (error) {
            status("Upload failed.", "error");
        }
    }

    async function removeSelected() {
        const item = state.items.find(i => i.id === state.selectedId);

        if (!item || !window.confirm(`Remove ${item.label || item.original_filename}?`)) return;

        const data = new FormData();

        data.append("action", "delete");
        data.append("structure_id", String(item.id));

        try {
            await fetch(url, {method: "POST", credentials: "same-origin", body: data, headers: {"X-CSRFToken": csrf(), Accept: "application/json"}});
        } catch (error) {
            status("Could not remove the structure.", "error");

            return;
        }

        state.loaded = null;
        await loadList();
        fillSelect();
        disposeViewer();
        await showSelected();
    }

    function fillSelect() {
        ui.select.replaceChildren(...state.items.map(i => new Option(`${i.label || i.original_filename} · ${i.source_format_label}`, String(i.id))));
        ui.select.hidden = state.items.length < 1;

        if (state.selectedId !== null) ui.select.value = String(state.selectedId);
    }

    function build(onFallback) {
        const wrap = el("div", "mrp3d");
        const bar = el("div", "mrp-figtools");
        const fileInput = document.createElement("input");

        fileInput.type = "file";
        fileInput.accept = ".pdb,.ent,.cif,.mmcif";
        fileInput.hidden = true;
        fileInput.addEventListener("change", () => {
            upload(fileInput.files && fileInput.files[0]);
            fileInput.value = "";
        });

        ui.select = document.createElement("select");
        ui.select.className = "mrp-select";
        ui.select.setAttribute("aria-label", "Stored 3D structures");
        ui.select.addEventListener("change", () => {
            state.selectedId = Number(ui.select.value);
            showSelected();
        });

        const uploadBtn = el("button", "mrp-btn mrp-btn-sm", "Upload 3D structure");

        uploadBtn.type = "button";
        uploadBtn.title = "Attach a PDB or mmCIF file to this RNA record";
        uploadBtn.addEventListener("click", () => fileInput.click());

        ui.download = el("a", "mrp-btn mrp-btn-sm", "Download");
        ui.download.hidden = true;
        ui.remove = el("button", "mrp-btn mrp-btn-sm", "Remove");
        ui.remove.type = "button";
        ui.remove.addEventListener("click", removeSelected);

        const numbering = document.createElement("input");

        numbering.type = "number";
        numbering.min = "-999";
        numbering.value = String(state.numbering);
        numbering.className = "mrp-select mrp3d-number";
        numbering.title = "Residue number of the first nucleotide in the structure file";
        numbering.setAttribute("aria-label", "Residue numbering starts at");
        numbering.addEventListener("change", () => {
            state.numbering = Number(numbering.value) || 1;
            syncSelection(true);
        });

        const numLabel = el("label", "mrp3d-numlabel");

        numLabel.append(document.createTextNode("Numbering starts at "), numbering);

        const focusBtn = el("button", "mrp-btn mrp-btn-sm", "Focus selection");

        focusBtn.type = "button";
        focusBtn.addEventListener("click", () => syncSelection(true));

        const model = el("button", "mrp-btn mrp-btn-sm", "Illustrative model");

        model.type = "button";
        model.title = "Show the idealised model drawn from the base pairs";
        model.addEventListener("click", () => onFallback && onFallback());

        bar.append(ui.select, uploadBtn, ui.download, ui.remove, numLabel, focusBtn, model, fileInput);

        ui.empty = el("div", "mrp3d-empty");
        ui.empty.append(
            el("strong", "", "No 3D structure attached yet"),
            el("p", "", "Upload a PDB or mmCIF file of this RNA (for example from the PDB, RNAcomposer or a modelling run) to inspect it here, with the sequence selection highlighted in 3D."),
        );

        const emptyBtn = el("button", "mrp-btn", "Upload 3D structure");

        emptyBtn.type = "button";
        emptyBtn.addEventListener("click", () => fileInput.click());
        ui.empty.appendChild(emptyBtn);

        ui.stage = el("div", "mrp3d-stage");
        ui.stage.hidden = true;
        ui.status = el("div", "mrp-figure-hint mrp3d-status");
        wrap.append(bar, ui.empty, ui.stage, ui.status);

        return wrap;
    }

    window.BiobankRnaStructure3D = {
        async mount(onFallback) {
            if (!state.host) {
                state.host = build(onFallback);
                await loadList();
                fillSelect();
                await showSelected();
            } else {
                // Same host re-attached: Mol* needs a resize after being re-inserted.
                window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
            }

            return state.host;
        },
        syncSelection,
        isActive: () => Boolean(state.viewer),
    };

    root.addEventListener("biobank:molecular-workspace-change", () => syncSelection(false));
})();
