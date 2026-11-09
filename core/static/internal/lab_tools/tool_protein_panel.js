/*
 * Protein workbench windows: Properties (mass, pI, charge, extinction,
 * hydropathy plot, composition) and Structure 3D (Mol*, vendored): a PDB
 * entry, an AlphaFold model by UniProt accession, or the record's own file.
 */
(function () {
    "use strict";

    const propsHost = document.getElementById("tw-prot-props");
    const structHost = document.getElementById("tw-struct3d");
    const calc = window.BiobankBioCalc;
    const page = document.getElementById("tool-workbench");

    if ((!propsHost && !structHost) || !calc || !page) return;

    const S = {scope: "all", ph: "7.4", win: "9", source: "pdb", id: "", loaded: null};
    const NS = "http://www.w3.org/2000/svg";

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function field(text, node) {
        const wrap = el("label", "tw-field");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    function btn(text, title, onClick, cls) {
        const node = el("button", "tw-btn" + (cls ? " " + cls : ""), text);

        node.type = "button";
        node.title = title || "";
        node.addEventListener("click", onClick);

        return node;
    }

    function changed() {
        document.dispatchEvent(new CustomEvent("biobank:protein-change"));
    }

    function whenShown(host, callback) {
        const pane = host.closest("[data-tw-pane]");

        if (!pane) return;

        if (!pane.hidden) callback();

        if (typeof MutationObserver !== "undefined") {
            new MutationObserver(() => { if (!pane.hidden) callback(); }).observe(pane, {attributes: true, attributeFilter: ["hidden"]});
        }
    }

    function current() {
        const seq = window.BiobankToolSequence ? window.BiobankToolSequence.getState().sequence : "";
        const snap = window.BiobankMolecularWorkspace ? window.BiobankMolecularWorkspace.getSnapshot() : null;
        const sel = snap && snap.sequenceSelection;

        if (S.scope === "selection" && sel) return {seq: seq.slice(sel.start - 1, sel.end), offset: sel.start - 1, region: sel.start + "–" + sel.end};

        return {seq, offset: 0, region: ""};
    }

    /* ---------- Properties ---------- */

    const scope = el("select");
    const phInput = el("input");
    const winInput = el("input");
    const out = el("div");
    const plot = el("div", "tw-plot");
    const comp = el("div", "tw-aabars");
    const note = el("p", "tw-note");

    [["all", "Whole sequence"], ["selection", "Selection only"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        scope.append(option);
    });
    phInput.type = "number";
    phInput.min = "0";
    phInput.max = "14";
    phInput.step = "0.1";
    winInput.type = "number";
    winInput.min = "3";
    winInput.max = "41";
    winInput.step = "2";
    scope.addEventListener("change", () => { S.scope = scope.value; renderProps(); changed(); });
    phInput.addEventListener("input", () => { S.ph = phInput.value; renderProps(); changed(); });
    winInput.addEventListener("input", () => { S.win = winInput.value; renderProps(); changed(); });

    function row(label, value) {
        const tr = el("tr");

        tr.append(el("td", "", label), el("td", "tw-mono", value));

        return tr;
    }

    function drawPlot(seq, offset) {
        plot.replaceChildren();

        const values = calc.hydropathy(seq, S.win);
        const finite = values.filter(v => v !== null);

        if (!finite.length) {
            plot.append(el("p", "tw-note", "The sequence is shorter than the window."));

            return;
        }

        const W = 520;
        const H = 150;
        const padL = 30;
        const padB = 18;
        const svg = document.createElementNS(NS, "svg");

        svg.setAttribute("viewBox", "0 0 " + W + " " + H);
        svg.setAttribute("class", "tw-plot-svg");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Kyte–Doolittle hydropathy plot");

        const lo = Math.min(-4.5, Math.min(...finite));
        const hi = Math.max(4.5, Math.max(...finite));
        const x = i => padL + (i / Math.max(1, values.length - 1)) * (W - padL - 6);
        const y = v => 6 + (hi - v) / (hi - lo) * (H - padB - 6);

        function line(x1, y1, x2, y2, stroke, dash) {
            const node = document.createElementNS(NS, "line");

            node.setAttribute("x1", x1);
            node.setAttribute("y1", y1);
            node.setAttribute("x2", x2);
            node.setAttribute("y2", y2);
            node.setAttribute("stroke", stroke);
            node.setAttribute("stroke-width", "1");

            if (dash) node.setAttribute("stroke-dasharray", "3 3");

            svg.append(node);
        }

        function label(text, px, py, anchor) {
            const node = document.createElementNS(NS, "text");

            node.setAttribute("x", px);
            node.setAttribute("y", py);
            node.setAttribute("font-size", "9");
            node.setAttribute("fill", "#667085");
            node.setAttribute("text-anchor", anchor || "end");
            node.textContent = text;
            svg.append(node);
        }

        line(padL, y(0), W - 6, y(0), "#98a2b3");
        line(padL, y(1.6), W - 6, y(1.6), "#c92a2a", true);
        label("0", padL - 4, y(0) + 3);
        label("1.6", padL - 4, y(1.6) + 3);
        label("1", padL, H - 4, "start");
        label(String(values.length + offset), W - 6, H - 4);

        let d = "";

        values.forEach((v, i) => {
            if (v !== null) d += (d ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
        });

        const path = document.createElementNS(NS, "path");

        path.setAttribute("d", d);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "#1d4ed8");
        path.setAttribute("stroke-width", "1.4");
        svg.append(path);

        // Clicking the plot selects that stretch in the Sequence window.
        svg.addEventListener("click", event => {
            const box = svg.getBoundingClientRect();
            const frac = ((event.clientX - box.left) / box.width * W - padL) / (W - padL - 6);
            const centre = Math.max(0, Math.min(values.length - 1, Math.round(frac * (values.length - 1))));
            const half = (Math.max(3, Number(S.win) || 9) - 1) / 2;

            if (window.BiobankMolecularWorkspace) window.BiobankMolecularWorkspace.selectSequenceRange(offset + centre - half + 1, offset + centre + half + 1);
        });
        plot.append(svg, el("p", "tw-note", "Kyte–Doolittle, window " + S.win + ". Above the dashed line (1.6) suggests a transmembrane segment. Click the plot to select that region in the Sequence window."));
    }

    function renderProps() {
        if (!propsHost) return;

        out.replaceChildren();
        comp.replaceChildren();
        scope.value = S.scope;
        phInput.value = S.ph;
        winInput.value = S.win;

        const {seq, offset, region} = current();
        const r = seq ? calc.proteinReport(seq, S.ph) : null;

        if (!r) {
            out.append(el("p", "tw-note", "Add a protein sequence in the Sequence window."));
            plot.replaceChildren();

            return;
        }

        const table = el("table", "tw-table");

        table.append(
            row("Length", r.length.toLocaleString("en-US") + " aa" + (region ? " (" + region + ")" : "")),
            row("Molecular weight", (r.mass / 1000).toFixed(3) + " kDa"),
            row("Isoelectric point (pI)", r.pI.toFixed(2)),
            row("Charge at pH " + r.ph, r.charge.toFixed(1)),
            row("ε280 (folded / reduced)", r.epsilon280.toLocaleString("en-US") + " / " + r.epsilon280Reduced.toLocaleString("en-US") + " M⁻¹cm⁻¹"),
            row("Abs 0.1% (1 mg/mL)", (r.epsilon280 / r.mass).toFixed(3)),
            row("GRAVY", r.gravy.toFixed(3)),
            row("Aliphatic index", r.aliphatic.toFixed(1)),
        );
        out.append(table);

        const max = Math.max(1, ...r.composition.map(c => c[1]));

        r.composition.forEach(([aa, n]) => {
            const col = el("div", "tw-aabar");
            const bar = el("span");

            bar.style.height = (n / max * 100) + "%";
            bar.title = aa + ": " + n + " (" + (n / r.known * 100).toFixed(1) + "%)";
            col.append(bar, el("em", "", aa));
            comp.append(col);
        });
        drawPlot(seq, offset);
    }

    if (propsHost) {
        const settings = el("div", "tw-row");

        settings.append(field("Analyse", scope), field("pH", phInput), field("Hydropathy window", winInput));
        propsHost.append(settings, out, el("p", "tw-note", "Amino-acid composition"), comp, plot, note);
    }

    /* ---------- Structure 3D ---------- */

    const source = el("select");
    const idInput = el("input");
    const status = el("p", "tw-note");
    const mount = el("div", "tw-mol-mount");
    let viewer = null;
    let molPromise = null;

    [["pdb", "PDB entry (RCSB)"], ["alphafold", "AlphaFold model (UniProt)"], ["file", "The record's attached file"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        source.append(option);
    });
    idInput.spellcheck = false;
    source.addEventListener("change", () => { S.source = source.value; idInput.disabled = S.source === "file"; changed(); });
    idInput.addEventListener("input", () => { S.id = idInput.value.trim(); changed(); });
    idInput.addEventListener("keydown", event => { if (event.key === "Enter") loadStructure(); });
    idInput.placeholder = "e.g. 1EMA, or P42212";

    function loadMolstar() {
        if (window.molstar && window.molstar.Viewer) return Promise.resolve(window.molstar);

        if (molPromise) return molPromise;

        molPromise = new Promise((resolve, reject) => {
            const css = el("link");

            css.rel = "stylesheet";
            css.href = structHost.dataset.molstarCss;
            document.head.append(css);

            const script = el("script");

            script.src = structHost.dataset.molstarJs;
            script.async = true;
            script.addEventListener("load", () => (window.molstar && window.molstar.Viewer ? resolve(window.molstar) : reject(new Error("The 3D viewer did not start."))));
            script.addEventListener("error", () => reject(new Error("The 3D viewer could not be loaded.")));
            document.head.append(script);
        });
        molPromise.catch(() => { molPromise = null; });

        return molPromise;
    }

    async function ensureViewer() {
        const library = await loadMolstar();

        if (viewer) return viewer;

        viewer = await library.Viewer.create(mount, {
            layoutIsExpanded: false,
            layoutShowControls: true,
            layoutShowRemoteState: false,
            layoutShowSequence: false,
            layoutShowLog: false,
            layoutShowLeftPanel: false,
            viewportShowExpand: true,
            viewportShowSelectionMode: true,
            viewportShowControls: true,
            viewportShowAnimation: false,
            viewportBackgroundColor: "#111318",
        });

        return viewer;
    }

    async function fetchText(url) {
        const response = await fetch(url, url.indexOf(page.dataset.fileUrl || "\u0000") === 0 ? {credentials: "same-origin"} : {});

        if (!response.ok) throw new Error(response.status === 404 ? "Not found (" + url.split("/").slice(-1)[0] + ")." : "The server answered " + response.status + ".");

        return response.text();
    }

    async function loadStructure() {
        const src = S.source;
        const id = S.id.trim();

        try {
            let data;
            let format = "mmcif";
            let label;

            if (src === "file") {
                if (page.dataset.hasFile !== "1" && !window.__twHasFile) throw new Error("This record has no attached structure file yet (use Attach file).");

                const name = (window.__twFilename || page.dataset.filename || "").toLowerCase();

                data = await fetchText(page.dataset.fileUrl + "?t=" + Date.now());
                format = /\.(pdb|ent)$/.test(name) ? "pdb" : "mmcif";
                label = name || "attached file";
            } else if (src === "pdb") {
                if (!/^[0-9][A-Za-z0-9]{3}$/.test(id)) throw new Error("A PDB id has four characters, e.g. 1EMA.");

                status.textContent = "Fetching " + id.toUpperCase() + " from RCSB…";
                data = await fetchText("https://files.rcsb.org/download/" + id.toUpperCase() + ".cif");
                label = id.toUpperCase();
            } else {
                if (!/^[A-Za-z0-9_-]{4,12}$/.test(id)) throw new Error("Type a UniProt accession, e.g. P42212.");

                status.textContent = "Asking AlphaFold DB about " + id.toUpperCase() + "…";

                const meta = JSON.parse(await fetchText("https://alphafold.ebi.ac.uk/api/prediction/" + id.toUpperCase()));
                const entry = Array.isArray(meta) ? meta[0] : meta;
                const url = entry && (entry.cifUrl || entry.pdbUrl);

                if (!url) throw new Error("AlphaFold DB has no model for " + id.toUpperCase() + ".");

                format = entry.cifUrl ? "mmcif" : "pdb";
                data = await fetchText(url);
                label = "AlphaFold " + id.toUpperCase();
            }

            status.textContent = "Loading the viewer…";

            const instance = await ensureViewer();

            if (instance.plugin && instance.plugin.clear) await instance.plugin.clear();

            await instance.loadStructureFromData(data, format, {dataLabel: label});
            S.loaded = {source: src, id};
            status.textContent = label + " loaded.";
            status.className = "tw-note tw-ok";
            changed();
            fit();
        } catch (error) {
            status.className = "tw-note tw-bad";
            status.textContent = String(error && error.message ? error.message : error).replace(/^TypeError: Failed to fetch/, "The browser could not reach the server");
        }
    }

    function fit() {
        if (viewer && typeof viewer.handleResize === "function") viewer.handleResize();
    }

    if (structHost) {
        const row2 = el("div", "tw-row");
        const go = btn("Load", "Load the structure", loadStructure, "is-primary");

        row2.append(field("Source", source), field("Identifier", idInput), go);
        structHost.append(row2, status, mount, el("p", "tw-note", "Mol* viewer (vendored). Public structures are fetched by your browser from RCSB PDB or AlphaFold DB; nothing is sent from this server. Attach a .pdb or .cif file to this record to keep your own structure."));
    }

    document.addEventListener("biobank:sequence-state", renderProps);
    document.addEventListener("biobank:tool-layout", () => window.setTimeout(fit, 100));
    document.getElementById("molecular-workspace").addEventListener("biobank:molecular-workspace-change", () => {
        if (S.scope === "selection") renderProps();
    });
    // The workbench announces file changes; a new attached file is shown at once.
    document.addEventListener("biobank:tool-file", event => {
        window.__twHasFile = !!event.detail.hasFile;
        window.__twFilename = event.detail.filename || "";

        if (event.detail.hasFile && structHost && /\.(pdb|ent|cif|mmcif)$/i.test(event.detail.filename || "")) {
            S.source = "file";
            source.value = "file";
            idInput.disabled = true;
            loadStructure();
        }
    });

    window.BiobankProtein = {
        getState: () => Object.assign({}, S),
        setState(state) {
            if (!state || typeof state !== "object") return;

            if (state.scope === "selection" || state.scope === "all") S.scope = state.scope;
            if (state.ph !== undefined && isFinite(Number(state.ph))) S.ph = String(state.ph);
            if (state.win !== undefined && isFinite(Number(state.win))) S.win = String(state.win);
            if (["pdb", "alphafold", "file"].indexOf(state.source) !== -1) S.source = state.source;
            if (typeof state.id === "string") S.id = state.id;
            if (state.loaded && typeof state.loaded === "object") S.loaded = state.loaded;

            source.value = S.source;
            idInput.value = S.id;
            idInput.disabled = S.source === "file";
            renderProps();
        },
    };

    source.value = S.source;
    renderProps();

    if (propsHost) whenShown(propsHost, renderProps);

    // A structure that was open when the record was saved comes back when its window is shown.
    if (structHost) {
        let restored = false;

        whenShown(structHost, () => {
            fit();

            if (!restored && S.loaded && (S.loaded.source === "file" || S.loaded.id)) {
                restored = true;
                loadStructure();
            }
        });
    }
}());
