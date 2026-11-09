/*
 * ORFs window: open reading frames of the record, in full width.
 *
 * Six frame lanes (+1..+3, -1..-3) span the whole sequence; every ORF is a
 * clickable bar. Below, a table lists them with the actions that matter:
 * select on the map and in the sequence, make it a CDS annotation, copy or
 * download the protein.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const pane = document.getElementById("mw-orfs");
    const calc = window.BiobankMolecularCalc;

    if (!root || !pane || !calc) {
        return;
    }

    const NS = "http://www.w3.org/2000/svg";
    const LANES = ["+1", "+2", "+3", "−1", "−2", "−3"];
    const ui = {min: 50, strand: "both", sort: "length", limit: 40, all: false};
    let cache = {key: "", orfs: []};
    let frame = 0;

    const api = () => window.BiobankMolecularWorkspace || null;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function svg(tag, attributes, text) {
        const node = document.createElementNS(NS, tag);

        Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));

        if (text !== undefined) node.textContent = text;

        return node;
    }

    const head = el("div", "mwp-head");
    const title = el("strong", "mwp-title", "ORFs");
    const minLabel = el("label", "mwp-inline", "Min length ");
    const minInput = el("input", "mwp-num");
    const strandSelect = el("select", "mwp-select");
    const sortSelect = el("select", "mwp-select");
    const fastaButton = el("button", "mwp-btn", "Proteins FASTA");
    const csvButton = el("button", "mwp-btn", "CSV");
    const lanes = el("div", "mwp-lanes");
    const list = el("div", "mwp-scroll mwp-orflist");
    const note = el("p", "mwp-note");

    minInput.type = "number";
    minInput.min = "10";
    minInput.max = "2000";
    minInput.value = String(ui.min);
    minInput.setAttribute("aria-label", "Minimum ORF length in amino acids");
    minLabel.append(minInput, document.createTextNode(" aa"));
    [["both", "Both strands"], ["+", "Forward"], ["-", "Reverse"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        strandSelect.append(option);
    });
    [["length", "Longest first"], ["position", "By position"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        sortSelect.append(option);
    });
    fastaButton.type = csvButton.type = "button";
    head.append(title, minLabel, strandSelect, sortSelect, fastaButton, csvButton);
    pane.append(head, lanes, list, note);

    function protein(orf, sequence) {
        const piece = calc.slice(sequence, orf.start, orf.end);

        return calc.translate(orf.strand === "-" ? calc.reverseComplement(piece) : piece, 0).replace(/\*$/, "");
    }

    function compute(snapshot) {
        const key = [snapshot.sequence.length, snapshot.sequence.slice(0, 48), snapshot.sequence.slice(-48), ui.min, ui.strand].join("|");

        if (cache.key !== key || cache.sequence !== snapshot.sequence) {
            cache = {key, sequence: snapshot.sequence, orfs: calc.findOrfs(snapshot.sequence, ui.min, {strand: ui.strand})};
        }

        const orfs = cache.orfs.slice();

        return ui.sort === "position" ? orfs.sort((a, b) => a.start - b.start) : orfs;
    }

    function laneIndex(orf) {
        return (orf.strand === "-" ? 3 : 0) + orf.frame - 1;
    }

    function isSelected(orf, selection) {
        return Boolean(selection && selection.start === orf.start && selection.end === orf.end);
    }

    function selectOrf(orf) {
        const workspace = api();

        if (workspace) workspace.selectSequenceRange(orf.start, orf.end, {source: "orf-window"});
    }

    function renderLanes(orfs, snapshot) {
        const width = Math.max(420, Math.round(pane.clientWidth - 24));
        const left = 34;
        const laneH = 26;
        const top = 22;
        const length = snapshot.sequence.length;
        const height = top + LANES.length * laneH + 8;
        const x = position => left + (position - 1) / Math.max(1, length - 1) * (width - left - 8);
        const node = svg("svg", {viewBox: "0 0 " + width + " " + height, class: "mwp-svg", role: "img", "aria-label": "ORFs by reading frame"});
        const step = (() => {
            const raw = length / 8;
            const pow = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1))));

            return [1, 2, 5, 10].map(m => m * pow).find(value => value >= raw) || pow;
        })();

        for (let tick = 0; tick <= length; tick += step) {
            node.append(svg("line", {x1: x(Math.max(1, tick)), x2: x(Math.max(1, tick)), y1: top - 6, y2: top + LANES.length * laneH, class: "mwp-grid"}));
            node.append(svg("text", {x: x(Math.max(1, tick)), y: 12, "text-anchor": "middle", class: "mwp-tick"}, tick.toLocaleString()));
        }

        LANES.forEach((label, index) => {
            const y = top + index * laneH;

            node.append(svg("rect", {x: left, y, width: width - left - 8, height: laneH - 3, class: "mwp-lane" + (index >= 3 ? " is-reverse" : "")}));
            node.append(svg("text", {x: left - 6, y: y + laneH / 2, "text-anchor": "end", "dominant-baseline": "middle", class: "mwp-lanelabel"}, label));
        });

        const selection = snapshot.sequenceSelection;

        if (selection && selection.start <= selection.end) {
            node.append(svg("rect", {x: x(selection.start), y: top - 4, width: Math.max(2, x(selection.end) - x(selection.start)), height: LANES.length * laneH + 4, class: "mwp-selection"}));
        }

        orfs.forEach(orf => {
            const y = top + laneIndex(orf) * laneH;
            const bar = svg("rect", {
                x: x(orf.start), y: y + 2, width: Math.max(2, x(orf.end) - x(orf.start)), height: laneH - 7, rx: 3,
                class: "mwp-orf" + (orf.strand === "-" ? " is-reverse" : "") + (isSelected(orf, selection) ? " is-selected" : ""),
            });

            bar.append(svg("title", {}, orf.aminoAcids + " aa · " + orf.strand + orf.frame + " · " + orf.start.toLocaleString() + "–" + orf.end.toLocaleString()));
            bar.addEventListener("click", () => selectOrf(orf));
            node.append(bar);
        });

        const legend = el("div", "mwp-legend");

        legend.append(el("span", "mwp-key is-forward", "Forward ORF (ATG to stop)"), el("span", "mwp-key is-reverse", "Reverse ORF"), el("span", "mwp-key is-selected", "Selected"));
        lanes.replaceChildren(node, legend);
    }

    function row(orf, snapshot) {
        const workspace = api();
        const item = el("div", "mwp-orfrow" + (isSelected(orf, snapshot.sequenceSelection) ? " is-selected" : ""));
        const label = el("button", "mwp-orfmain");
        const copy = el("button", "mwp-btn", "Copy protein");
        const make = el("button", "mwp-btn", "Make CDS");

        label.type = copy.type = make.type = "button";
        label.append(
            el("b", "", orf.aminoAcids + " aa"),
            el("span", "mwp-orftag" + (orf.strand === "-" ? " is-reverse" : ""), orf.strand + orf.frame),
            el("span", "mwp-orfrange", orf.start.toLocaleString() + "–" + orf.end.toLocaleString()),
            el("span", "mwp-orfsize", (orf.end - orf.start + 1).toLocaleString() + " bp")
        );
        label.addEventListener("click", () => selectOrf(orf));
        copy.addEventListener("click", () => {
            if (navigator.clipboard) navigator.clipboard.writeText(protein(orf, snapshot.sequence)).catch(() => {});

            copy.textContent = "Copied";
            window.setTimeout(() => {
                copy.textContent = "Copy protein";
            }, 1500);
        });
        make.disabled = !snapshot.canEdit;
        make.title = snapshot.canEdit ? "Create a CDS annotation for this ORF" : "Read only record";
        make.addEventListener("click", () => {
            workspace.selectSequenceRange(orf.start, orf.end, {source: "orf-window"});
            workspace.createFeatureFromSelection({type: "cds", name: "ORF " + orf.aminoAcids + " aa", strand: orf.strand, focusEditor: false});
        });
        item.append(label, copy, make);

        return item;
    }

    function render() {
        frame = 0;

        const workspace = api();

        if (!workspace || pane.hidden) return;

        const snapshot = workspace.getSnapshot();
        const orfs = compute(snapshot);
        const shown = ui.all ? orfs : orfs.slice(0, ui.limit);

        title.textContent = "ORFs · " + orfs.length;
        renderLanes(orfs, snapshot);
        list.replaceChildren(...shown.map(orf => row(orf, snapshot)));

        if (!orfs.length) {
            list.append(el("p", "mwp-empty", "No ORF of " + ui.min + " aa or more with these settings. Lower the minimum length."));
        }

        if (orfs.length > shown.length) {
            const more = el("button", "mwp-btn", "Show all " + orfs.length);

            more.type = "button";
            more.addEventListener("click", () => {
                ui.all = true;
                render();
            });
            list.append(more);
        }

        note.textContent = "An ORF runs from ATG to the first stop codon in its frame. Frames −1 to −3 are read on the reverse strand; coordinates are always on the forward strand. ORFs that cross the origin of a circular record are not listed.";
    }

    function schedule() {
        if (!frame) frame = window.requestAnimationFrame(render);
    }

    function download(name, type, content) {
        const link = document.createElement("a");

        link.href = URL.createObjectURL(new Blob([content], {type}));
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
    }

    function baseName(snapshot) {
        return (snapshot.name || "record").replace(/[^A-Za-z0-9._-]+/g, "_");
    }

    fastaButton.addEventListener("click", () => {
        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const text = compute(snapshot).map((orf, index) => (
            ">" + baseName(snapshot) + "_ORF" + (index + 1) + " " + orf.strand + orf.frame + " " + orf.start + "-" + orf.end + " " + orf.aminoAcids + "aa\n" + protein(orf, snapshot.sequence) + "\n"
        )).join("");

        download(baseName(snapshot) + "_orfs.faa", "text/plain", text);
    });
    csvButton.addEventListener("click", () => {
        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const lines = ["start,end,strand,frame,amino_acids,length_bp"].concat(compute(snapshot).map(orf => [orf.start, orf.end, orf.strand, orf.frame, orf.aminoAcids, orf.end - orf.start + 1].join(",")));

        download(baseName(snapshot) + "_orfs.csv", "text/csv", lines.join("\n") + "\n");
    });
    minInput.addEventListener("change", () => {
        ui.min = Math.max(10, Math.min(2000, Number(minInput.value) || 50));
        minInput.value = String(ui.min);
        ui.all = false;
        render();
    });
    strandSelect.addEventListener("change", () => {
        ui.strand = strandSelect.value;
        ui.all = false;
        render();
    });
    sortSelect.addEventListener("change", () => {
        ui.sort = sortSelect.value;
        render();
    });
    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail.layout === "orfs") window.requestAnimationFrame(render);
    });
    root.addEventListener("biobank:molecular-workspace-change", schedule);
}());
