/*
 * Sequence window for the independent tool pages.
 *
 * The record viewer gives the Digest, Primers, Cloning and Gel windows a
 * sequence to work on. On a tool page there is no open registry record, so
 * this holds a working sequence that can be pasted, taken from the registry or
 * taken from the Plasmid assembly window. It exposes the same small
 * BiobankMolecularWorkspace interface those windows already use.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("tw-sequence");
    const page = document.getElementById("tool-workbench");

    if (!root || !host || !page) return;

    const S = {name: "Working sequence", sequence: "", topology: "linear", selection: null, features: []};
    // The sequence of an RNA workbench is RNA (U), of a Protein workbench amino acids; elsewhere DNA.
    const KIND = page.dataset.tool === "rnafold" ? "rna" : page.dataset.tool === "protein3d" ? "protein" : "dna";
    const UNIT = KIND === "protein" ? "aa" : KIND === "rna" ? "nt" : "bp";
    const ACCEPT = {dna: ["dna", "plasmid", "insert", "primer", "other"], rna: ["rna", "dna", "insert"], protein: ["protein"]}[KIND];

    const clean = text => {
        const letters = String(text || "").replace(/^>.*$/gm, "").replace(/[^A-Za-z*]/g, "").toUpperCase();

        if (KIND === "protein") return letters;

        return KIND === "rna" ? letters.replace(/\*/g, "").replace(/T/g, "U") : letters.replace(/\*/g, "");
    };

    function emit() {
        root.dispatchEvent(new CustomEvent("biobank:molecular-workspace-change", {bubbles: false}));
        document.dispatchEvent(new CustomEvent("biobank:sequence-change"));
    }

    /* ---------- the interface the other windows use ---------- */

    const api = {
        getSnapshot: () => ({
            name: S.name,
            sequence: S.sequence,
            topology: S.topology,
            sequenceSelection: S.selection ? {start: S.selection.start, end: S.selection.end} : null,
            features: S.features.map(feature => Object.assign({}, feature)),
            canEdit: true,
        }),
        selectSequenceRange(start, end) {
            const a = Math.max(1, Math.min(S.sequence.length, Math.round(Number(start) || 1)));
            const b = Math.max(a, Math.min(S.sequence.length, Math.round(Number(end) || a)));

            S.selection = S.sequence.length ? {start: a, end: b} : null;
            showSelection();
            emit();
        },
        createFeatureFromSelection(options) {
            if (!S.selection) return false;

            const opts = options || {};

            S.features.push({
                name: String(opts.name || "feature"),
                type: String(opts.type || "custom"),
                start: S.selection.start,
                end: S.selection.end,
                strand: opts.strand === "-" ? "-" : "+",
            });
            render();
            emit();

            return true;
        },
        // `from`/`to` are 0-based slice positions, like String.slice.
        replaceRange(from, to, text) {
            const a = Math.max(0, Math.min(S.sequence.length, Number(from)));
            const b = Math.max(a, Math.min(S.sequence.length, Number(to)));
            const insert = clean(text);
            const delta = insert.length - (b - a);

            S.sequence = S.sequence.slice(0, a) + insert + S.sequence.slice(b);
            // Features after the edit move; features crossing it are dropped.
            S.features = S.features
                .filter(feature => feature.end <= a || feature.start > b)
                .map(feature => (feature.start > b ? Object.assign({}, feature, {start: feature.start + delta, end: feature.end + delta}) : feature));
            S.selection = null;
            render();
            emit();

            return true;
        },
    };

    window.BiobankMolecularWorkspace = api;

    /* ---------- window ---------- */

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

    function btn(text, title, onClick, className) {
        const node = el("button", "tw-btn" + (className ? " " + className : ""), text);

        node.type = "button";
        node.title = title || "";
        node.addEventListener("click", onClick);

        return node;
    }

    const nameInput = el("input");
    const topology = el("select");
    const box = el("textarea");
    const info = el("p", "tw-note");
    const sel = el("p", "tw-note");
    const results = el("div", "tw-results");
    const search = el("input");
    const note = el("p", "tw-note");

    [["linear", "Linear"], ["circular", "Circular"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        topology.append(option);
    });
    box.rows = 7;
    box.spellcheck = false;
    box.placeholder = KIND === "protein"
        ? "Paste the amino-acid sequence here (FASTA headers and spaces are ignored)"
        : KIND === "rna" ? "Paste RNA here; T is read as U (FASTA headers and spaces are ignored)" : "Paste DNA here, or use the buttons below (FASTA headers and spaces are ignored)";
    search.placeholder = KIND === "protein" ? "Search the registry (protein)…" : KIND === "rna" ? "Search the registry (RNA, DNA, insert)…" : "Search the registry (DNA, plasmid, insert)…";
    results.hidden = true;

    function gc(seq) {
        const acgt = seq.replace(/[^ACGTU]/g, "").length;

        return acgt ? Math.round((seq.split("").filter(base => base === "G" || base === "C").length / acgt) * 1000) / 10 : 0;
    }

    function showSelection() {
        sel.textContent = S.selection
            ? "Selected " + S.selection.start.toLocaleString("en-US") + "–" + S.selection.end.toLocaleString("en-US") + " (" + (S.selection.end - S.selection.start + 1).toLocaleString("en-US") + " " + UNIT + ")."
            : KIND === "dna" ? "Select a region in the box above to use it in Cloning, Primers or Digest." : "Select a region in the box above; the analysis windows can work on the selection.";
    }

    function render() {
        if (box.value !== S.sequence) box.value = S.sequence;

        nameInput.value = S.name;
        topology.value = S.topology;
        info.textContent = S.sequence
            ? S.sequence.length.toLocaleString("en-US") + " " + UNIT + (KIND === "protein" ? "" : " · GC " + gc(S.sequence) + "%") + (KIND === "dna" ? " · " + S.topology : "") + (S.features.length ? " · " + S.features.length + " feature" + (S.features.length === 1 ? "" : "s") : "")
            : "No sequence yet.";
        showSelection();
    }

    function setSequence(name, sequence, topo) {
        S.name = name || S.name;
        S.sequence = clean(sequence);
        S.topology = topo === "circular" ? "circular" : "linear";
        S.selection = null;
        S.features = [];
        render();
        emit();
        document.dispatchEvent(new CustomEvent("biobank:sequence-state"));
    }

    nameInput.addEventListener("change", () => {
        S.name = nameInput.value.trim() || S.name;
        emit();
        document.dispatchEvent(new CustomEvent("biobank:sequence-state"));
    });
    topology.addEventListener("change", () => {
        S.topology = topology.value;
        render();
        emit();
        document.dispatchEvent(new CustomEvent("biobank:sequence-state"));
    });
    box.addEventListener("change", () => {
        S.sequence = clean(box.value);
        S.selection = null;
        S.features = [];
        render();
        emit();
        document.dispatchEvent(new CustomEvent("biobank:sequence-state"));
    });
    // Selecting text in the box selects that region for the other windows.
    function syncSelection() {
        const from = box.selectionStart;
        const to = box.selectionEnd;

        if (S.sequence !== clean(box.value)) return;

        const text = box.value;
        const start = clean(text.slice(0, from)).length + 1;
        const end = clean(text.slice(0, to)).length;

        if (end >= start && to > from) {
            if (!S.selection || S.selection.start !== start || S.selection.end !== end) {
                S.selection = {start, end};
                showSelection();
                emit();
            }
        } else if (S.selection) {
            S.selection = null;
            showSelection();
            emit();
        }
    }

    ["mouseup", "keyup"].forEach(type => box.addEventListener(type, syncSelection));

    const useAssembly = btn("Use the assembly result", "Take the sequence built in the Plasmid assembly window", () => {
        if (!window.BiobankAssembly) return;

        const out = window.BiobankAssembly.assemble();

        if (!out.seq) {
            note.textContent = "The Plasmid assembly window has no parts yet.";

            return;
        }

        const circular = window.BiobankAssembly.getState().circular;

        setSequence((document.getElementById("tw-name").value || "Assembly"), out.seq, circular ? "circular" : "linear");
        note.textContent = "Loaded " + out.seq.length.toLocaleString("en-US") + " bp from the assembly.";
    }, "is-primary");
    const clear = btn("Clear", "Remove the working sequence", () => setSequence("Working sequence", "", "linear"));
    const actions = el("div", "tw-row");

    actions.append(useAssembly, clear);

    let timer = 0;

    search.addEventListener("input", () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(async () => {
            const query = search.value.trim();

            results.replaceChildren();

            if (!query) {
                results.hidden = true;

                return;
            }

            const response = await fetch(page.dataset.searchUrl + "?q=" + encodeURIComponent(query), {credentials: "same-origin"});
            const found = (response.ok ? (await response.json()).results || [] : []).filter(record => !record.sequence_type || ACCEPT.indexOf(record.sequence_type) !== -1);

            results.hidden = false;

            if (!found.length) results.append(el("p", "tw-note", "No records found."));

            found.forEach(record => {
                const row = el("button");

                row.type = "button";
                row.append(el("span", "", record.name), el("span", "tw-note", record.sequence_type || ""));
                row.addEventListener("click", async () => {
                    const detail = await fetch(page.dataset.recordUrl.replace("/0/", "/" + record.id + "/"), {credentials: "same-origin"});

                    if (!detail.ok) {
                        note.textContent = "That record could not be read.";

                        return;
                    }

                    const data = await detail.json();

                    setSequence(data.name, data.sequence, data.topology);
                    results.hidden = true;
                    search.value = "";
                    note.textContent = "Loaded " + data.name + ".";
                });
                results.append(row);
            });
        }, 250);
    });

    if (KIND !== "dna") useAssembly.hidden = true;

    host.append(field("Name", nameInput), KIND === "dna" ? field("Topology", topology) : document.createComment("no topology"), field("Sequence", box), info, sel, actions, field("Or load a registry record", search), results, note);

    window.BiobankToolSequence = {
        getState: () => ({name: S.name, sequence: S.sequence, topology: S.topology}),
        setState(state) {
            if (!state || typeof state !== "object") return;

            S.name = String(state.name || S.name);
            S.sequence = clean(state.sequence);
            S.topology = state.topology === "circular" ? "circular" : "linear";
            S.selection = null;
            S.features = [];
            render();
            emit();
        },
        set: setSequence,
    };

    render();
}());
