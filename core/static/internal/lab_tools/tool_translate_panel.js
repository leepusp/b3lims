/*
 * Translate window (RNA and Protein workbenches): the six reading frames of a
 * DNA/RNA text and its open reading frames. In the Protein workbench an ORF
 * can be sent to the Sequence window as a protein.
 */
(function () {
    "use strict";

    const host = document.getElementById("tw-translate");
    const page = document.getElementById("tool-workbench");
    const calc = window.BiobankBioCalc;

    if (!host || !page || !calc) return;

    const toProtein = page.dataset.tool === "protein3d";
    const S = {text: "", min: "30"};

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

    const box = el("textarea");
    const minInput = el("input");
    const frames = el("div");
    const orfs = el("div");
    const note = el("p", "tw-note");

    box.rows = 4;
    box.spellcheck = false;
    box.placeholder = "Paste DNA or RNA (FASTA header and spaces are ignored)";
    minInput.type = "number";
    minInput.min = "5";
    minInput.step = "5";

    function changed() {
        document.dispatchEvent(new CustomEvent("biobank:translate-change"));
    }

    function copy(text, what) {
        if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => { note.textContent = what + " copied."; });
    }

    function render() {
        frames.replaceChildren();
        orfs.replaceChildren();

        const dna = calc.toDna(S.text);

        if (!dna) {
            frames.append(el("p", "tw-note", "Paste a nucleotide sequence above."));

            return;
        }

        const rc = calc.reverseComplement(dna);
        const table = el("table", "tw-table");

        [["+", dna], ["−", rc]].forEach(([strand, seq]) => {
            for (let frame = 0; frame < 3; frame += 1) {
                const protein = calc.translate(seq, frame);
                const tr = el("tr");
                const td = el("td", "tw-mono tw-wrap", protein);

                tr.append(el("td", "", strand + (frame + 1)), td, el("td", "", ""));
                tr.lastChild.append(btn("Copy", "Copy this translation", () => copy(protein, "Translation")));
                table.append(tr);
            }
        });
        frames.append(table);

        const found = calc.findOrfs(dna, S.min);
        const list = el("table", "tw-table");
        const head = el("tr");

        ["Strand/frame", "Position", "Length", "Protein", ""].forEach(t => head.append(el("th", "", t)));
        list.append(head);
        found.slice(0, 30).forEach((orf, index) => {
            const tr = el("tr");
            const preview = orf.protein.length > 40 ? orf.protein.slice(0, 40) + "…" : orf.protein;

            tr.append(el("td", "", (orf.strand === "+" ? "+" : "−") + orf.frame), el("td", "tw-mono", orf.start + "–" + orf.end), el("td", "", orf.protein.length + " aa" + (orf.stop ? "" : " (no stop)")), el("td", "tw-mono", preview));

            const actions = el("td");

            actions.append(btn("Copy", "Copy the protein", () => copy(orf.protein, "Protein")));

            if (toProtein && window.BiobankToolSequence) {
                actions.append(btn("→ Sequence", "Use this protein in the Sequence window", () => {
                    window.BiobankToolSequence.set("ORF " + (index + 1) + " (" + orf.strand + orf.frame + ")", orf.protein, "linear");
                    note.textContent = "Sent to the Sequence window.";
                }, "is-primary"));
            }

            tr.append(actions);
            list.append(tr);
        });
        orfs.append(el("p", "tw-note", found.length ? found.length + " open reading frame" + (found.length === 1 ? "" : "s") + " of at least " + S.min + " aa" + (found.length > 30 ? " (the 30 longest are listed)" : "") + "." : "No open reading frames of at least " + S.min + " aa."));

        if (found.length) orfs.append(list);
    }

    box.addEventListener("input", () => { S.text = box.value; render(); changed(); });
    minInput.addEventListener("input", () => { S.min = minInput.value; render(); changed(); });

    const useSeq = btn("Use the Sequence window", "Take the nucleotide sequence of the Sequence window (RNA workbench)", () => {
        const seq = window.BiobankToolSequence ? window.BiobankToolSequence.getState().sequence : "";

        S.text = seq;
        box.value = seq;
        render();
        changed();
    });
    const actions = el("div", "tw-row");

    if (!toProtein) actions.append(useSeq);

    host.append(field("Nucleotide sequence to translate", box), actions, field("Minimum ORF length (aa)", minInput), el("h4", "tw-chem-subhead", "Six frames"), frames, el("h4", "tw-chem-subhead", "Open reading frames"), orfs, note);

    window.BiobankTranslate = {
        getState: () => Object.assign({}, S),
        setState(state) {
            if (!state || typeof state !== "object") return;

            if (typeof state.text === "string") S.text = state.text.slice(0, 200000);
            if (state.min !== undefined && isFinite(Number(state.min))) S.min = String(state.min);

            box.value = S.text;
            minInput.value = S.min;
            render();
        },
    };

    minInput.value = S.min;
    render();
}());
