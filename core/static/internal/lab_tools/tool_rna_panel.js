/*
 * RNA workbench windows: Analysis (composition, mass, conversions) and
 * Structure (secondary structure: predicted with a simplified energy model or
 * typed as dot-bracket, drawn with the vendored fornac). They work on the
 * sequence of the Sequence window, or on its selection.
 */
(function () {
    "use strict";

    const propsHost = document.getElementById("tw-rna-props");
    const foldHost = document.getElementById("tw-fold");
    const calc = window.BiobankBioCalc;

    if ((!propsHost && !foldHost) || !calc) return;

    const S = {scope: "all", structure: "", scheme: "structure"};

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
        document.dispatchEvent(new CustomEvent("biobank:rna-change"));
    }

    function whenShown(host, callback) {
        const pane = host.closest("[data-tw-pane]");

        if (!pane) return;

        if (!pane.hidden) callback();

        if (typeof MutationObserver !== "undefined") {
            new MutationObserver(() => { if (!pane.hidden) callback(); }).observe(pane, {attributes: true, attributeFilter: ["hidden"]});
        }
    }

    // The sequence the windows work on: all of it or the selected region.
    function current() {
        const seq = window.BiobankToolSequence ? window.BiobankToolSequence.getState().sequence : "";
        const snap = window.BiobankMolecularWorkspace ? window.BiobankMolecularWorkspace.getSnapshot() : null;
        const sel = snap && snap.sequenceSelection;

        if (S.scope === "selection" && sel) return {seq: seq.slice(sel.start - 1, sel.end), region: sel.start + "–" + sel.end};

        return {seq, region: ""};
    }

    function scopeSelect() {
        const select = el("select");

        [["all", "Whole sequence"], ["selection", "Selection only"]].forEach(([value, label]) => {
            const option = el("option", "", label);

            option.value = value;
            select.append(option);
        });
        select.addEventListener("change", () => {
            S.scope = select.value;
            renderProps();
            renderFold(true);
            changed();
        });

        return select;
    }

    const scopeA = scopeSelect();
    const scopeB = scopeSelect();

    /* ---------- Analysis window ---------- */

    const propsOut = el("div");
    const propsNote = el("p", "tw-note");

    function row(label, value) {
        const tr = el("tr");

        tr.append(el("td", "", label), el("td", "tw-mono", value));

        return tr;
    }

    function sendSequence(text, name) {
        if (!window.BiobankToolSequence) return;

        window.BiobankToolSequence.set(name, text, "linear");
        propsNote.textContent = "Sent to the Sequence window.";
    }

    function copy(text, what) {
        if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => { propsNote.textContent = what + " copied."; });
    }

    function renderProps() {
        if (!propsHost) return;

        propsOut.replaceChildren();
        scopeA.value = S.scope;

        const {seq, region} = current();

        if (!seq) {
            propsOut.append(el("p", "tw-note", "Add an RNA sequence in the Sequence window."));

            return;
        }

        const r = calc.rnaReport(seq);
        const table = el("table", "tw-table");
        const pct = n => (r.length ? (n / r.length * 100).toFixed(1) : "0") + "%";

        table.append(
            row("Length", r.length.toLocaleString("en-US") + " nt" + (region ? " (" + region + ")" : "")),
            row("GC content", r.gc.toFixed(1) + "%"),
            row("A / C / G / U", [r.counts.A, r.counts.C, r.counts.G, r.counts.U].join(" / ") + "  (" + pct(r.counts.A) + " " + pct(r.counts.C) + " " + pct(r.counts.G) + " " + pct(r.counts.U) + ")"),
            row("Molecular weight", (r.mass / 1000).toFixed(3) + " kDa  (" + r.mass.toFixed(1) + " g/mol, 5′-OH)"),
            row("ε260 (additive)", r.epsilon260.toLocaleString("en-US") + " M⁻¹cm⁻¹"),
        );

        if (r.counts.other) table.append(row("Other symbols", String(r.counts.other)));

        const bar = el("div", "tw-compbar");

        [["A", r.counts.A, "#2b8a3e"], ["C", r.counts.C, "#1d4ed8"], ["G", r.counts.G, "#b35c00"], ["U", r.counts.U, "#c92a2a"]].forEach(([label, n, color]) => {
            if (!n) return;

            const part = el("span", "", label);

            part.style.width = (n / r.length * 100) + "%";
            part.style.background = color;
            part.title = label + ": " + n;
            bar.append(part);
        });

        const actions = el("div", "tw-row");

        actions.append(
            btn("Copy as DNA", "Copy the sequence with T instead of U", () => copy(calc.toDna(seq), "DNA sequence")),
            btn("Copy reverse complement", "Copy the reverse complement (RNA)", () => copy(calc.reverseComplement(seq, true), "Reverse complement")),
            btn("Reverse complement → Sequence", "Replace the Sequence window with the reverse complement", () => sendSequence(calc.reverseComplement(seq, true), "Reverse complement")),
        );
        propsOut.append(table, bar, actions);
    }

    if (propsHost) propsHost.append(field("Analyse", scopeA), propsOut, propsNote);

    /* ---------- Structure window ---------- */

    const structure = el("textarea");
    const scheme = el("select");
    const info = el("p", "tw-note");
    const canvas = el("div", "tw-fold-canvas");
    const foldNote = el("p", "tw-note");
    let drawTimer = 0;
    let fornacPromise = null;
    let lastEnergy = null;

    structure.rows = 3;
    structure.spellcheck = false;
    structure.placeholder = "Dot-bracket, e.g. ((((...)))) — or press Predict";
    [["structure", "Colour by structure"], ["sequence", "Colour by base"], ["positions", "Colour by position"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        scheme.append(option);
    });
    scheme.addEventListener("change", () => {
        S.scheme = scheme.value;
        draw();
        changed();
    });
    structure.addEventListener("input", () => {
        S.structure = structure.value.replace(/\s+/g, "");
        lastEnergy = null;
        window.clearTimeout(drawTimer);
        drawTimer = window.setTimeout(draw, 500);
        changed();
    });

    function loadFornac() {
        if (window.fornac && window.fornac.FornaContainer) return Promise.resolve(window.fornac);

        if (fornacPromise) return fornacPromise;

        fornacPromise = new Promise((resolve, reject) => {
            const script = el("script");

            script.src = foldHost.dataset.fornacUrl;
            script.async = true;
            script.addEventListener("load", () => (window.fornac && window.fornac.FornaContainer ? resolve(window.fornac) : reject(new Error("The RNA drawing library did not start."))));
            script.addEventListener("error", () => reject(new Error("The RNA drawing library could not be loaded.")));
            document.head.append(script);
        });
        fornacPromise.catch(() => { fornacPromise = null; });

        return fornacPromise;
    }

    async function draw() {
        if (!foldHost) return;

        const pane = foldHost.closest("[data-tw-pane]");
        const {seq} = current();
        const text = S.structure;

        canvas.replaceChildren();

        if (!text) {
            info.textContent = seq ? "Press Predict, or type a dot-bracket structure." : "Add an RNA sequence in the Sequence window.";

            return;
        }

        const parsed = calc.parseDotBracket(text, seq);

        if (parsed.error) {
            info.textContent = parsed.error;
            info.className = "tw-note tw-bad";

            return;
        }

        info.className = "tw-note";

        const bad = parsed.pairs.filter(([a, b]) => !calc.pairType(seq[a], seq[b])).length;

        info.textContent = parsed.pairs.length + " base pairs · " + seq.length + " nt"
            + (lastEnergy !== null ? " · ΔG ≈ " + lastEnergy.toFixed(1) + " kcal/mol (simplified model)" : "")
            + (bad ? " · " + bad + " pair(s) are not A–U, G–C or G–U" : "");

        if (pane && pane.hidden) return;

        try {
            const library = await loadFornac();
            const mount = el("div", "tw-fold-mount");

            mount.id = "tw-fold-mount";
            canvas.replaceChildren(mount);

            const container = new library.FornaContainer("#tw-fold-mount", {applyForce: false, allowPanningAndZooming: true, resizeSvgOnResize: true, transitionDuration: 0});

            container.deaf = true;
            container.addRNA(text, {sequence: seq, name: nameOf(), avoidOthers: true});
            container.changeColorScheme(S.scheme);
            container.setSize();
        } catch (error) {
            foldNote.textContent = String(error && error.message ? error.message : error);
        }
    }

    function nameOf() {
        const node = document.getElementById("tw-name");

        return node && node.value ? node.value : "RNA";
    }

    const predict = btn("Predict (simplified model)", "Minimum free energy structure with a simplified nearest-neighbour model", () => {
        const {seq} = current();

        if (!seq) {
            foldNote.textContent = "Add an RNA sequence in the Sequence window first.";

            return;
        }

        foldNote.textContent = "Folding…";
        window.setTimeout(() => {
            try {
                const result = calc.foldRna(seq);

                S.structure = result.structure;
                structure.value = S.structure;
                lastEnergy = result.energy;
                foldNote.textContent = "Predicted with a simplified energy model: a quick guide, not a replacement for RNAfold or experimental data. Edit the dot-bracket to refine.";
                draw();
                changed();
            } catch (error) {
                foldNote.textContent = String(error && error.message ? error.message : error);
            }
        }, 20);
    }, "is-primary");
    const clearBtn = btn("Clear", "Remove the structure", () => {
        S.structure = "";
        structure.value = "";
        lastEnergy = null;
        draw();
        changed();
    });
    const copyBtn = btn("Copy dot-bracket", "Copy the structure", () => {
        if (S.structure && navigator.clipboard) navigator.clipboard.writeText(S.structure).then(() => { foldNote.textContent = "Dot-bracket copied."; });
    });
    const svgBtn = btn("Download SVG", "Download the drawing", () => {
        const svg = canvas.querySelector("svg");

        if (!svg) {
            foldNote.textContent = "Nothing is drawn yet.";

            return;
        }

        const text = new XMLSerializer().serializeToString(svg);
        const url = URL.createObjectURL(new Blob([text], {type: "image/svg+xml"}));
        const a = el("a");

        a.href = url;
        a.download = nameOf().replace(/[^\w.-]+/g, "_") + ".svg";
        a.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    const foldActions = el("div", "tw-row");

    foldActions.append(predict, clearBtn, copyBtn, svgBtn);

    if (foldHost) foldHost.append(field("Fold", scopeB), field("Structure (dot-bracket)", structure), foldActions, info, foldNote, field("Colours", scheme), canvas);

    function renderFold(redraw) {
        scopeB.value = S.scope;
        structure.value = S.structure;
        scheme.value = S.scheme;

        if (redraw) draw();
    }

    document.addEventListener("biobank:sequence-state", () => {
        renderProps();
        window.clearTimeout(drawTimer);
        drawTimer = window.setTimeout(draw, 300);
    });
    document.addEventListener("biobank:viewer-layout", () => window.setTimeout(draw, 100));
    document.addEventListener("biobank:tool-layout", () => window.setTimeout(draw, 100));
    // A new selection in the Sequence window re-reads when the scope is "selection".
    document.getElementById("molecular-workspace").addEventListener("biobank:molecular-workspace-change", () => {
        if (S.scope === "selection") {
            renderProps();
            window.clearTimeout(drawTimer);
            drawTimer = window.setTimeout(draw, 300);
        }
    });

    window.BiobankRna = {
        getState: () => Object.assign({}, S),
        setState(state) {
            if (!state || typeof state !== "object") return;

            if (state.scope === "selection" || state.scope === "all") S.scope = state.scope;
            if (typeof state.structure === "string") S.structure = state.structure;
            if (["structure", "sequence", "positions"].indexOf(state.scheme) !== -1) S.scheme = state.scheme;

            renderProps();
            renderFold(false);
            draw();
        },
    };

    renderProps();
    renderFold(false);

    if (propsHost) whenShown(propsHost, renderProps);
    if (foldHost) whenShown(foldHost, draw);
}());
