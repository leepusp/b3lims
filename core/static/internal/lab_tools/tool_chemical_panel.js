/*
 * Chemical window: keep the structure of a compound (SMILES / MOL block),
 * its formula and its mass. The formula is read locally; the structure drawing
 * (Ketcher) is added in a later release and will edit the same fields.
 */
(function () {
    "use strict";

    const host = document.getElementById("tw-chemical");

    if (!host) return;

    // Average and monoisotopic masses of the common elements.
    const MASS = {
        H: [1.008, 1.00782503], C: [12.011, 12], N: [14.007, 14.0030740], O: [15.999, 15.9949146],
        F: [18.998, 18.9984032], Na: [22.990, 22.9897693], Mg: [24.305, 23.9850417], P: [30.974, 30.9737620],
        S: [32.06, 31.9720711], Cl: [35.45, 34.9688527], K: [39.098, 38.9637065], Ca: [40.078, 39.9625910],
        Mn: [54.938, 54.9380451], Fe: [55.845, 55.9349375], Co: [58.933, 58.9331950], Ni: [58.693, 57.9353429],
        Cu: [63.546, 62.9295975], Zn: [65.38, 63.9291422], Se: [78.971, 79.9165218], Br: [79.904, 78.9183376],
        I: [126.904, 126.904473], B: [10.81, 11.0093054], Si: [28.085, 27.9769265], Li: [6.94, 7.0160040],
    };
    const S = {smiles: "", mol: "", formula: "", cas: "", notes: ""};

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    // "C9H8O4", "Ca(OH)2", "CuSO4.5H2O" → {C: 9, H: 8, O: 4}; null when invalid.
    function parseFormula(text) {
        const source = String(text || "").replace(/\s+/g, "").replace(/[·•]/g, ".");

        if (!source) return null;

        function group(chunk) {
            const stack = [{}];
            let i = 0;

            while (i < chunk.length) {
                const ch = chunk[i];

                if (ch === "(") {
                    stack.push({});
                    i += 1;
                } else if (ch === ")") {
                    if (stack.length < 2) return null;

                    i += 1;

                    let digits = "";

                    while (/[0-9]/.test(chunk[i] || "")) digits += chunk[i++];

                    const top = stack.pop();
                    const times = digits ? Number(digits) : 1;

                    Object.keys(top).forEach(key => {
                        stack[stack.length - 1][key] = (stack[stack.length - 1][key] || 0) + top[key] * times;
                    });
                } else if (/[A-Z]/.test(ch)) {
                    let symbol = ch;

                    i += 1;

                    if (/[a-z]/.test(chunk[i] || "")) symbol += chunk[i++];

                    if (!MASS[symbol]) return null;

                    let digits = "";

                    while (/[0-9]/.test(chunk[i] || "")) digits += chunk[i++];

                    const count = digits ? Number(digits) : 1;

                    stack[stack.length - 1][symbol] = (stack[stack.length - 1][symbol] || 0) + count;
                } else {
                    return null;
                }
            }

            return stack.length === 1 ? stack[0] : null;
        }

        const total = {};

        for (const piece of source.split(".")) {
            const match = piece.match(/^([0-9]+)?(.*)$/);
            const factor = match[1] ? Number(match[1]) : 1;
            const counts = group(match[2]);

            if (!counts) return null;

            Object.keys(counts).forEach(key => {
                total[key] = (total[key] || 0) + counts[key] * factor;
            });
        }

        return total;
    }

    function masses(counts) {
        let average = 0;
        let exact = 0;

        Object.keys(counts).forEach(symbol => {
            average += MASS[symbol][0] * counts[symbol];
            exact += MASS[symbol][1] * counts[symbol];
        });

        return {average, exact};
    }

    function prettyFormula(counts) {
        const order = Object.keys(counts).sort((a, b) => (a === "C" ? -1 : b === "C" ? 1 : a === "H" ? -1 : b === "H" ? 1 : a.localeCompare(b)));

        return order.map(symbol => symbol + (counts[symbol] > 1 ? counts[symbol] : "")).join("");
    }

    function field(text, node) {
        const wrap = el("label", "tw-field");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    const smiles = el("textarea");
    const mol = el("textarea");
    const formula = el("input");
    const cas = el("input");
    const notes = el("textarea");
    const out = el("div");
    const hint = el("p", "tw-note", "Ketcher (structure drawing) is added in a later release; until then keep the structure as SMILES or a MOL block, or attach a structure file to this record.");

    smiles.rows = 2;
    mol.rows = 6;
    notes.rows = 3;
    smiles.spellcheck = mol.spellcheck = false;
    formula.placeholder = "e.g. C9H8O4 or CuSO4.5H2O";
    cas.placeholder = "e.g. 50-78-2";

    [[smiles, "smiles"], [mol, "mol"], [formula, "formula"], [cas, "cas"], [notes, "notes"]].forEach(([node, key]) => {
        node.addEventListener("input", () => {
            S[key] = node.value;
            render();
            document.dispatchEvent(new CustomEvent("biobank:chemical-change"));
        });
    });
    host.append(
        field("SMILES", smiles),
        field("MOL block", mol),
        field("Molecular formula", formula),
        out,
        field("CAS number", cas),
        field("Notes", notes),
        hint,
    );

    function render() {
        out.replaceChildren();

        if (!S.formula.trim()) return;

        const counts = parseFormula(S.formula);

        if (!counts) {
            out.append(el("p", "tw-note tw-bad", "The formula could not be read. Use element symbols and numbers, e.g. C9H8O4."));

            return;
        }

        const m = masses(counts);
        const table = el("table", "tw-table");

        [["Formula", prettyFormula(counts)], ["Molecular weight", m.average.toFixed(3) + " g/mol"], ["Monoisotopic mass", m.exact.toFixed(5) + " Da"]].forEach(([label, value]) => {
            const row = el("tr");

            row.append(el("td", "", label), el("td", "tw-mono", value));
            table.append(row);
        });
        out.append(table);
    }

    function sync() {
        smiles.value = S.smiles;
        mol.value = S.mol;
        formula.value = S.formula;
        cas.value = S.cas;
        notes.value = S.notes;
        render();
    }

    window.BiobankChemical = {
        getState: () => Object.assign({}, S),
        setState: state => {
            if (!state || typeof state !== "object") return;

            Object.keys(S).forEach(key => {
                if (typeof state[key] === "string") S[key] = state[key];
            });
            sync();
        },
        parseFormula,
        masses,
    };

    sync();
}());
