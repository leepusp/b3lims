/*
 * Chemical window: compound card (identifiers, structure, calculated properties,
 * hazards), SMILES / MOL reading, PubChem lookup, and a reaction stoichiometry
 * table. Everything is computed in the browser; PubChem is queried by the
 * browser only when the user asks. The Ketcher editor (vendored, loaded in an
 * iframe) edits the same smiles / mol fields.
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
    const VALENCE = {B: [3], C: [4], N: [3, 5], O: [2], P: [3, 5], S: [2, 4, 6], F: [1], Cl: [1], Br: [1], I: [1], Si: [4], Se: [2]};

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


    // ---- structure reading -------------------------------------------------
    // Molecule: {atoms: [{el, charge, h (explicit count or null), x, y, arom}], bonds: [{a, b, order}]}
    function implicitH(atom, sum) {
        if (atom.h !== null && atom.h !== undefined) return atom.h;

        const options = VALENCE[atom.el];

        if (!options) return 0;

        const used = Math.round(sum) + (atom.el === "N" || atom.el === "P" ? Math.max(0, -atom.charge) * 0 : 0);
        let valence = options.find(v => v >= used);

        if (valence === undefined) valence = options[options.length - 1];

        // Charged atoms shift valence: N+ / O+ gain one, B- / O- / N- lose one.
        const shift = atom.el === "N" || atom.el === "P" || atom.el === "O" || atom.el === "S" ? atom.charge : atom.el === "B" ? -atom.charge : 0;

        return Math.max(0, valence + shift - used);
    }

    function formulaOf(mol) {
        const sums = mol.atoms.map(() => 0);

        mol.bonds.forEach(bond => {
            sums[bond.a] += bond.order;
            sums[bond.b] += bond.order;
        });

        const counts = {};
        let charge = 0;

        mol.atoms.forEach((atom, index) => {
            counts[atom.el] = (counts[atom.el] || 0) + 1;
            charge += atom.charge || 0;

            const h = implicitH(atom, sums[index]);

            if (h) counts.H = (counts.H || 0) + h;
        });

        return {counts, charge};
    }

    function parseSmiles(text) {
        const s = String(text || "").trim().split(/\s+/)[0];

        if (!s) return null;

        const atoms = [];
        const bonds = [];
        const rings = {};
        const stack = [];
        let prev = -1;
        let order = 0;
        let i = 0;

        function add(atom) {
            const index = atoms.length;

            atoms.push(atom);

            if (prev >= 0) {
                const o = order || (atom.arom && atoms[prev].arom ? 1.5 : 1);

                bonds.push({a: prev, b: index, order: o});
            }

            prev = index;
            order = 0;
        }

        while (i < s.length) {
            const ch = s[i];

            if (ch === "[") {
                const end = s.indexOf("]", i);

                if (end < 0) return null;

                const m = s.slice(i + 1, end).match(/^(\d+)?([A-Z][a-z]?|[a-z]{1,2})(@{0,2})(?:H(\d*))?([+-]+\d*)?(?::\d+)?$/);

                if (!m) return null;

                const arom = /^[a-z]/.test(m[2]);
                const el = arom ? m[2][0].toUpperCase() + m[2].slice(1) : m[2];

                if (!MASS[el]) return null;

                let charge = 0;

                if (m[5]) {
                    const sign = m[5][0] === "+" ? 1 : -1;
                    const digits = m[5].replace(/[+-]/g, "");

                    charge = digits ? sign * Number(digits) : sign * m[5].length;
                }

                add({el, charge, h: m[4] === undefined ? (/H/.test(s.slice(i, end)) ? 1 : 0) : (m[4] === "" ? 1 : Number(m[4])), arom});
                i = end + 1;
            } else if (/[A-Z]/.test(ch) || /[bcnops]/.test(ch)) {
                let sym = ch;

                if (ch === "C" && s[i + 1] === "l") sym = "Cl";
                else if (ch === "B" && s[i + 1] === "r") sym = "Br";

                const arom = /[a-z]/.test(ch);
                const el = arom ? ch.toUpperCase() : sym;

                if (!VALENCE[el]) return null;

                add({el, charge: 0, h: null, arom});
                i += sym.length;
            } else if (ch === "(") {
                stack.push(prev);
                i += 1;
            } else if (ch === ")") {
                if (!stack.length) return null;

                prev = stack.pop();
                i += 1;
            } else if (ch === ".") {
                prev = -1;
                order = 0;
                i += 1;
            } else if ("-=#$:/\\".includes(ch)) {
                order = ch === "=" ? 2 : ch === "#" ? 3 : ch === ":" ? 1.5 : ch === "$" ? 4 : 1;
                i += 1;
            } else if (/[0-9%]/.test(ch)) {
                let label = ch;

                i += 1;

                if (ch === "%") {
                    label = s.slice(i, i + 2);
                    i += 2;
                }

                if (prev < 0) return null;

                if (rings[label] !== undefined) {
                    const other = rings[label];
                    const o = order || (atoms[other].arom && atoms[prev].arom ? 1.5 : 1);

                    bonds.push({a: other, b: prev, order: o});
                    delete rings[label];
                } else {
                    rings[label] = prev;
                }

                order = 0;
            } else {
                return null;
            }
        }

        if (stack.length || Object.keys(rings).length || !atoms.length) return null;

        return {atoms, bonds};
    }

    // MDL V2000 (.mol or first record of an .sdf).
    function parseMol(text) {
        const lines = String(text || "").replace(/\r/g, "").split("\n");
        const countsAt = lines.findIndex((line, index) => index >= 3 && /V2000/.test(line));

        if (countsAt < 0) return null;

        const nAtoms = parseInt(lines[countsAt].slice(0, 3), 10);
        const nBonds = parseInt(lines[countsAt].slice(3, 6), 10);

        if (!(nAtoms > 0)) return null;

        const atoms = [];
        const bonds = [];

        for (let k = 0; k < nAtoms; k += 1) {
            const line = lines[countsAt + 1 + k] || "";
            const el = line.slice(31, 34).trim();

            if (!MASS[el]) return null;

            atoms.push({el, charge: 0, h: null, x: parseFloat(line.slice(0, 10)), y: parseFloat(line.slice(10, 20))});
        }

        for (let k = 0; k < nBonds; k += 1) {
            const line = lines[countsAt + 1 + nAtoms + k] || "";
            const a = parseInt(line.slice(0, 3), 10) - 1;
            const b = parseInt(line.slice(3, 6), 10) - 1;
            const t = parseInt(line.slice(6, 9), 10);

            if (!(a >= 0 && b >= 0 && a < nAtoms && b < nAtoms)) return null;

            bonds.push({a, b, order: t === 4 ? 1.5 : t >= 1 && t <= 3 ? t : 1});
        }

        lines.slice(countsAt + 1 + nAtoms + nBonds).forEach(line => {
            const m = line.match(/^M {2}CHG {2}?(\d+)(.*)$/);

            if (!m) return;

            const parts = m[2].trim().split(/\s+/);

            for (let k = 0; k + 1 < parts.length; k += 2) {
                const atom = atoms[Number(parts[k]) - 1];

                if (atom) atom.charge = Number(parts[k + 1]);
            }
        });

        return {atoms, bonds};
    }

    function ringCount(mol) {
        const parent = mol.atoms.map((_, index) => index);
        const find = x => (parent[x] === x ? x : (parent[x] = find(parent[x])));
        let comps = mol.atoms.length;

        mol.bonds.forEach(bond => {
            const ra = find(bond.a);
            const rb = find(bond.b);

            if (ra !== rb) {
                parent[ra] = rb;
                comps -= 1;
            }
        });

        return mol.bonds.length - mol.atoms.length + comps;
    }

    const NS = "http://www.w3.org/2000/svg";

    function drawMol(mol) {
        if (!mol || !mol.atoms.length || mol.atoms.some(a => !isFinite(a.x) || !isFinite(a.y))) return null;

        const xs = mol.atoms.map(a => a.x);
        const ys = mol.atoms.map(a => a.y);
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        const span = Math.max(maxX - minX, maxY - minY, 1);
        const scale = 200 / span;
        const pad = 24;
        const px = a => pad + (a.x - minX) * scale;
        const py = a => pad + (maxY - a.y) * scale;
        const svg = document.createElementNS(NS, "svg");

        svg.setAttribute("viewBox", "0 0 " + (2 * pad + (maxX - minX) * scale) + " " + (2 * pad + (maxY - minY) * scale));
        svg.setAttribute("class", "tw-chem-svg");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Structure drawing");

        function line(x1, y1, x2, y2, dash) {
            const node = document.createElementNS(NS, "line");

            node.setAttribute("x1", x1);
            node.setAttribute("y1", y1);
            node.setAttribute("x2", x2);
            node.setAttribute("y2", y2);
            node.setAttribute("stroke", "#1b2a3a");
            node.setAttribute("stroke-width", "1.6");

            if (dash) node.setAttribute("stroke-dasharray", "4 3");

            svg.appendChild(node);
        }

        mol.bonds.forEach(bond => {
            const a = mol.atoms[bond.a];
            const b = mol.atoms[bond.b];
            const dx = py(b) - py(a);
            const dy = px(a) - px(b);
            const len = Math.hypot(dx, dy) || 1;
            const n = bond.order === 1.5 ? 2 : bond.order;
            const gap = 3.2;

            for (let k = 0; k < n; k += 1) {
                const off = (k - (n - 1) / 2) * gap;
                const ox = dx / len * off;
                const oy = dy / len * off;

                line(px(a) + ox, py(a) + oy, px(b) + ox, py(b) + oy, bond.order === 1.5 && k === 1);
            }
        });

        mol.atoms.forEach(atom => {
            if (atom.el === "C" && !atom.charge) return;

            const text = document.createElementNS(NS, "text");

            text.setAttribute("x", px(atom));
            text.setAttribute("y", py(atom) + 4);
            text.setAttribute("text-anchor", "middle");
            text.setAttribute("font-size", "13");
            text.setAttribute("font-weight", "700");
            text.setAttribute("fill", {O: "#c92a2a", N: "#1d4ed8", S: "#b35c00", Cl: "#2b8a3e", Br: "#8a4b0a", F: "#2b8a3e"}[atom.el] || "#1b2a3a");
            text.textContent = atom.el + (atom.charge ? (atom.charge > 0 ? "+" : "−") : "");

            const bg = document.createElementNS(NS, "circle");

            bg.setAttribute("cx", px(atom));
            bg.setAttribute("cy", py(atom));
            bg.setAttribute("r", 8);
            bg.setAttribute("fill", "#fff");
            svg.appendChild(bg);
            svg.appendChild(text);
        });

        return svg;
    }

    function descriptors(counts, charge) {
        const m = masses(counts);
        const electron = 0.00054858;
        const total = Object.keys(counts).reduce((sum, key) => sum + counts[key], 0);
        const heavy = total - (counts.H || 0);

        return {
            formula: prettyFormula(counts),
            average: m.average,
            exact: m.exact,
            heavy,
            mh: m.exact + 1.00727646 - (charge ? charge * electron : 0),
            mminus: m.exact - 1.00727646 + (charge ? -charge * electron : 0),
            composition: Object.keys(counts).map(symbol => [symbol, MASS[symbol][0] * counts[symbol] / m.average * 100]),
        };
    }

    // ---- state -------------------------------------------------------------
    const HAZARDS = [
        ["flammable", "Flammable"], ["oxidising", "Oxidising"], ["explosive", "Explosive"], ["corrosive", "Corrosive"],
        ["toxic", "Toxic"], ["health", "Health hazard"], ["irritant", "Irritant"], ["environment", "Environment"], ["gas", "Gas under pressure"],
    ];
    const TEXT_KEYS = ["name", "iupac", "cid", "inchikey", "smiles", "mol", "formula", "cas", "notes", "hazards"];
    const S = {reaction: []};

    TEXT_KEYS.forEach(key => { S[key] = ""; });

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function changed() {
        document.dispatchEvent(new CustomEvent("biobank:chemical-change"));
    }

    function recordName() {
        const node = document.getElementById("tw-name");

        return node && node.value ? node.value.trim() : "";
    }

    // Best available composition: structure first, typed formula second.
    function current() {
        const mol = parseSmiles(S.smiles) || parseMol(S.mol);

        if (mol) {
            const r = formulaOf(mol);

            return {mol, counts: r.counts, charge: r.charge, source: parseSmiles(S.smiles) ? "SMILES" : "MOL block"};
        }

        const counts = parseFormula(S.formula);

        return counts ? {mol: null, counts, charge: 0, source: "formula"} : null;
    }

    function molarMass() {
        const c = current();

        return c ? masses(c.counts).average : 0;
    }

    // ---- UI ----------------------------------------------------------------
    function field(text, node) {
        const wrap = el("label", "tw-field");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    function input(key, placeholder, tag) {
        const node = el(tag || "input");

        if (placeholder) node.placeholder = placeholder;

        node.spellcheck = false;
        node.dataset.chemKey = key;
        node.addEventListener("input", () => {
            S[key] = node.value;
            renderResult();
            changed();

            if (key === "smiles" || key === "mol") {
                kSource = key;
                pushIfOpen();
            }
        });

        return node;
    }

    const nodes = {};

    nodes.name = input("name", "Compound name");
    nodes.cas = input("cas", "e.g. 50-78-2");
    nodes.cid = input("cid", "PubChem CID");
    nodes.iupac = input("iupac", "IUPAC name");
    nodes.inchikey = input("inchikey", "InChIKey");
    nodes.formula = input("formula", "e.g. C9H8O4 or CuSO4.5H2O");
    nodes.smiles = input("smiles", "e.g. CC(=O)Oc1ccccc1C(=O)O", "textarea");
    nodes.mol = input("mol", "Paste a MOL block (V2000) or load a .mol / .sdf file", "textarea");
    nodes.notes = input("notes", "", "textarea");
    nodes.smiles.rows = 2;
    nodes.mol.rows = 5;
    nodes.notes.rows = 3;

    const status = el("p", "tw-note");
    const result = el("div", "tw-chem-result");
    const lookupBtn = el("button", "tw-btn is-primary", "Look up in PubChem");
    const stockLink = el("a", "tw-btn", "Find in Chemicals stock");
    const addStock = el("a", "tw-btn", "Add to Chemicals stock");
    const svgBtn = el("button", "tw-btn", "Download SVG");
    const kBox = el("div", "tw-chem-ketcher");
    const kNote = el("p", "tw-note");
    const csvBtn = el("button", "tw-btn", "Copy table (TSV)");
    const molFile = el("input");
    const molBtn = el("button", "tw-btn", "Load .mol / .sdf");
    const molDownload = el("button", "tw-btn", "Download .mol");
    const copySmiles = el("button", "tw-btn", "Copy SMILES");
    const hazardBox = el("div", "tw-row");
    const reactionBox = el("div");

    svgBtn.type = csvBtn.type = "button";
    lookupBtn.type = molBtn.type = molDownload.type = copySmiles.type = "button";
    molFile.type = "file";
    molFile.accept = ".mol,.sdf,.txt";
    molFile.hidden = true;
    stockLink.target = "_blank";
    stockLink.rel = "noopener";
    stockLink.href = host.dataset.stockUrl || "#";
    addStock.target = "_blank";
    addStock.rel = "noopener";
    addStock.href = host.dataset.stockAddUrl || "#";

    HAZARDS.forEach(([key, label]) => {
        const wrap = el("label", "tw-chip");
        const box = el("input");

        box.type = "checkbox";
        box.dataset.hazard = key;
        box.addEventListener("change", () => {
            const set = new Set(S.hazards.split(",").filter(Boolean));

            if (box.checked) set.add(key); else set.delete(key);

            S.hazards = HAZARDS.map(h => h[0]).filter(k => set.has(k)).join(",");
            changed();
        });
        wrap.append(box, document.createTextNode(" " + label));
        hazardBox.append(wrap);
    });

    function setStatus(text, cls) {
        status.textContent = text || "";
        status.className = "tw-note" + (cls ? " " + cls : "");
    }

    // GHS pictograms from PubChem PUG View → our hazard flags.
    const GHS_MAP = {
        flammable: "flammable", oxidizer: "oxidising", oxidising: "oxidising", explosive: "explosive", "exploding bomb": "explosive",
        corrosive: "corrosive", toxic: "toxic", "skull and crossbones": "toxic", "health hazard": "health", irritant: "irritant",
        "exclamation mark": "irritant", environment: "environment", "environmental hazard": "environment", "compressed gas": "gas", "gas cylinder": "gas",
    };

    async function importGhs(cid) {
        const response = await fetch("https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/" + encodeURIComponent(cid) + "/JSON?heading=GHS+Classification");

        if (!response.ok) return false;

        const found = new Set(S.hazards.split(",").filter(Boolean));
        const before = found.size;

        (function walk(node) {
            if (!node || typeof node !== "object") return;

            if (Array.isArray(node)) {
                node.forEach(walk);

                return;
            }

            if (node.Name === "Pictogram(s)" && node.Value && node.Value.StringWithMarkup) {
                node.Value.StringWithMarkup.forEach(item => (item.Markup || []).forEach(mark => {
                    const key = GHS_MAP[String(mark.Extra || "").toLowerCase()];

                    if (key) found.add(key);
                }));
            }

            Object.keys(node).forEach(key => walk(node[key]));
        }(await response.json()));

        S.hazards = HAZARDS.map(h => h[0]).filter(k => found.has(k)).join(",");

        return found.size > before;
    }

    async function pubchem() {
        const cid = S.cid.trim();
        const query = cid || S.cas.trim() || S.name.trim();

        if (!query) {
            setStatus("Type a name, a CAS number or a CID first.", "tw-warn");

            return;
        }

        const base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/";
        const how = /^\d+$/.test(query) && cid ? "cid/" : "name/";
        const props = "Title,IUPACName,MolecularFormula,MolecularWeight,SMILES,InChIKey";

        lookupBtn.disabled = true;
        setStatus("Asking PubChem…");

        try {
            const response = await fetch(base + how + encodeURIComponent(query) + "/property/" + props + "/JSON");

            if (!response.ok) throw new Error(response.status === 404 ? "PubChem has no compound for “" + query + "”." : "PubChem answered " + response.status + ".");

            const p = ((await response.json()).PropertyTable || {}).Properties;

            if (!p || !p[0]) throw new Error("PubChem returned no data.");

            const d = p[0];

            S.cid = String(d.CID);
            S.iupac = d.IUPACName || S.iupac;
            S.formula = d.MolecularFormula || S.formula;
            S.smiles = d.SMILES || d.ConnectivitySMILES || S.smiles;
            S.inchikey = d.InChIKey || S.inchikey;

            if (!S.name.trim()) S.name = d.Title || "";

            // 2D structure is optional; ignore failures.
            try {
                const sdf = await fetch(base + "cid/" + S.cid + "/SDF");

                if (sdf.ok) S.mol = (await sdf.text()).split("$$$$")[0];
            } catch (error) { /* keep SMILES only */ }

            let ghs = false;

            try {
                ghs = await importGhs(S.cid);
            } catch (error) { /* hazards stay as they are */ }

            sync();
            changed();
            pushIfOpen();
            setStatus("Filled from PubChem CID " + S.cid + (ghs ? ", including GHS pictograms" : "") + ". Review before saving.", "tw-ok");
        } catch (error) {
            setStatus(String(error && error.message ? error.message : error).replace(/^TypeError: /, "The browser could not reach PubChem: "), "tw-bad");
        } finally {
            lookupBtn.disabled = false;
        }
    }

    function stockHref() {
        const q = S.name.trim() || S.cas.trim();

        return (host.dataset.stockUrl || "#") + (q ? "?q=" + encodeURIComponent(q) : "");
    }

    lookupBtn.addEventListener("click", pubchem);
    molBtn.addEventListener("click", () => molFile.click());
    molFile.addEventListener("change", () => {
        const file = molFile.files[0];

        if (!file) return;

        file.text().then(text => {
            S.mol = text.split("$$$$")[0];

            if (!parseMol(S.mol)) setStatus("That file is not a V2000 MOL block.", "tw-bad");
            else setStatus("Structure loaded from " + file.name + ".", "tw-ok");

            if (!S.name.trim()) S.name = file.name.replace(/\.[^.]+$/, "");

            sync();
            changed();
            pushIfOpen();
            molFile.value = "";
        });
    });
    molDownload.addEventListener("click", () => {
        if (!S.mol.trim()) {
            setStatus("There is no MOL block to download.", "tw-warn");

            return;
        }

        const url = URL.createObjectURL(new Blob([S.mol], {type: "chemical/x-mdl-molfile"}));
        const a = el("a");

        a.href = url;
        a.download = (S.name.trim() || "structure").replace(/[^\w.-]+/g, "_") + ".mol";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    copySmiles.addEventListener("click", () => {
        if (S.smiles.trim() && navigator.clipboard) navigator.clipboard.writeText(S.smiles.trim()).then(() => setStatus("SMILES copied.", "tw-ok"));
    });
    stockLink.addEventListener("click", () => { stockLink.href = stockHref(); });
    addStock.addEventListener("click", () => {
        const c = current();
        const params = new URLSearchParams();
        const labels = HAZARDS.filter(h => S.hazards.split(",").includes(h[0])).map(h => h[1]);

        params.set("name", S.name.trim() || recordName());
        params.set("formula", c ? prettyFormula(c.counts) : S.formula.trim());
        params.set("cas_number", S.cas.trim());

        if (labels.length) params.set("hazard_notes", labels.join(", "));

        addStock.href = (host.dataset.stockAddUrl || "#") + "?" + params.toString();
    });

    function row(label, value) {
        const tr = el("tr");

        tr.append(el("td", "", label), el("td", "tw-mono", value));

        return tr;
    }

    function renderResult() {
        result.replaceChildren();

        const c = current();

        if (!S.smiles.trim() && !S.mol.trim() && !S.formula.trim()) return;

        if (!c) {
            result.append(el("p", "tw-note tw-bad", "Nothing could be read. Check the SMILES, the MOL block (V2000) or the formula (element symbols and numbers)."));

            return;
        }

        const d = descriptors(c.counts, c.charge);
        const table = el("table", "tw-table");

        table.append(
            row("Formula (from " + c.source + ")", d.formula + (c.charge ? " (" + (c.charge > 0 ? "+" : "") + c.charge + ")" : "")),
            row("Molecular weight", d.average.toFixed(3) + " g/mol"),
            row("Monoisotopic mass", d.exact.toFixed(5) + " Da"),
            row("[M+H]+  /  [M−H]−", d.mh.toFixed(4) + "  /  " + d.mminus.toFixed(4)),
            row("Heavy atoms", String(d.heavy)),
        );

        if (c.mol) table.append(row("Rings", String(ringCount(c.mol))));

        table.append(row("Composition", d.composition.map(([s, pct]) => s + " " + pct.toFixed(1) + "%").join("  ")));

        const grid = el("div", "tw-chem-grid");

        grid.append(table);

        const molForDraw = parseMol(S.mol);
        const drawing = molForDraw ? drawMol(molForDraw) : null;

        if (drawing) grid.prepend(drawing);
        else if (S.cid.trim()) {
            const img = el("img", "tw-chem-svg");

            img.alt = "Structure from PubChem";
            img.src = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/" + encodeURIComponent(S.cid.trim()) + "/PNG?image_size=240x240";
            grid.prepend(img);
        } else if (S.smiles.trim()) {
            grid.prepend(el("p", "tw-note", "Drawing needs a MOL block or a PubChem CID; Ketcher will draw from SMILES."));
        }

        result.append(grid);

        if (S.formula.trim() && c.source !== "formula") {
            const typed = parseFormula(S.formula);

            if (typed && prettyFormula(typed) !== d.formula) {
                result.append(el("p", "tw-note tw-warn", "The typed formula (" + prettyFormula(typed) + ") differs from the structure (" + d.formula + ")."));
            }
        }
    }

    // ---- Ketcher editor (vendored, same-origin iframe) --------------------
    let kApi = null;
    let kFrame = null;
    let kMute = false;
    let kPushTimer = null;
    let kPullTimer = null;
    let kSource = "";

    function ketcherReady(frame) {
        return new Promise((resolve, reject) => {
            let tries = 0;
            const timer = setInterval(() => {
                const w = frame.contentWindow;

                if (w && w.ketcher) {
                    clearInterval(timer);
                    resolve(w.ketcher);
                } else if ((tries += 1) > 240) {
                    clearInterval(timer);
                    reject(new Error("The structure editor did not start."));
                }
            }, 150);
        });
    }

    async function pushToKetcher() {
        if (!kApi) return;

        const source = kSource;
        // A MOL block starts with a (possibly blank) title line: never trim it.
        const text = source === "smiles" ? S.smiles.trim() : source === "mol" ? S.mol : (S.mol.trim() ? S.mol : S.smiles.trim());

        kSource = "";
        kMute = true;

        try {
            if (text) await kApi.setMolecule(text);
            else if (kApi.editor && kApi.editor.clear) kApi.editor.clear();
        } catch (error) {
            kNote.textContent = "The editor could not read this structure: " + (error && error.message ? error.message : error);
        }

        setTimeout(() => { kMute = false; }, 600);

        // The field the user typed stays as typed; the other one follows the drawing.
        if (source && text) setTimeout(() => pullFromKetcher(source), 700);
    }

    function pushIfOpen() {
        if (!kApi) return;

        clearTimeout(kPushTimer);
        kPushTimer = setTimeout(pushToKetcher, 400);
    }

    async function pullFromKetcher(keep) {
        if (!kApi) return;

        try {
            const mol = await kApi.getMolfile();
            const empty = /V2000/.test(mol) ? /^\s*0\s+0\s/.test((mol.split("\n")[3] || "")) : /"atoms":\s*\[\s*\]/.test(mol);

            if (keep !== "mol") S.mol = empty ? "" : mol;
            if (keep !== "smiles") S.smiles = empty ? "" : (await kApi.getSmiles());

            if (!empty) {
                try { S.inchikey = (await kApi.getInChIKey()) || S.inchikey; } catch (error) { /* optional */ }
            }

            nodes.mol.value = S.mol;
            nodes.smiles.value = S.smiles;
            nodes.inchikey.value = S.inchikey;
            renderResult();
            changed();
        } catch (error) {
            kNote.textContent = "Could not read the drawing: " + (error && error.message ? error.message : error);
        }
    }

    let kStarting = false;

    // Starts the editor the first time the Structure window is on screen.
    async function ensureKetcher() {
        if (kFrame) {
            if (kApi) pushToKetcher();

            return;
        }

        if (kStarting) return;

        const url = host.dataset.ketcherUrl;

        if (!url) {
            kNote.textContent = "The structure editor is not installed.";

            return;
        }

        kStarting = true;
        kNote.textContent = "Loading the structure editor (about 30 MB, cached after the first time)…";
        kFrame = el("iframe", "tw-chem-frame");
        kFrame.title = "Structure editor";
        kFrame.src = url;
        kBox.prepend(kFrame);

        try {
            kApi = await ketcherReady(kFrame);

            // The editor object exists a moment before it accepts a structure:
            // load it, check it took, and try again if not.
            for (let attempt = 0; attempt < 8; attempt += 1) {
                await new Promise(resolve => setTimeout(resolve, attempt ? 700 : 300));
                await pushToKetcher();

                if (!(S.mol.trim() || S.smiles.trim())) break;

                await new Promise(resolve => setTimeout(resolve, 500));

                let loaded = "";

                try { loaded = await kApi.getSmiles(); } catch (error) { loaded = ""; }

                if (loaded) break;
            }

            kApi.editor.subscribe("change", () => {
                if (kMute) return;

                clearTimeout(kPullTimer);
                kPullTimer = setTimeout(pullFromKetcher, 500);
            });
            kNote.textContent = "Draw here: the properties, SMILES and MOL block follow. Save the record to keep it.";
        } catch (error) {
            kNote.textContent = String(error && error.message ? error.message : error);
        } finally {
            kStarting = false;
        }
    }

    function structureShown() {
        const pane = host.closest ? host.closest("[data-tw-pane]") : null;

        return !pane || !pane.hidden;
    }

    function watchStructure() {
        const pane = host.closest ? host.closest("[data-tw-pane]") : null;

        if (structureShown()) ensureKetcher();

        if (pane && typeof MutationObserver !== "undefined") {
            new MutationObserver(() => { if (!pane.hidden) ensureKetcher(); }).observe(pane, {attributes: true, attributeFilter: ["hidden"]});
        }
    }

    svgBtn.addEventListener("click", async () => {
        if (!S.mol.trim() && !S.smiles.trim()) {
            setStatus("Draw or paste a structure first.", "tw-warn");

            return;
        }

        try {
            let api = kApi;

            if (!api) {
                await ensureKetcher();
                api = kApi;
            }

            const blob = await api.generateImage(S.mol.trim() ? S.mol : S.smiles.trim(), {outputFormat: "svg"});
            const url = URL.createObjectURL(blob);
            const a = el("a");

            a.href = url;
            a.download = (S.name.trim() || "structure").replace(/[^\w.-]+/g, "_") + ".svg";
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) {
            setStatus("Could not make the image: " + (error && error.message ? error.message : error), "tw-bad");
        }
    });

    // ---- reaction table ----------------------------------------------------
    const ROLES = ["reactant", "reagent", "solvent", "product"];

    function newRow(name, mw) {
        return {name: name || "", mw: mw || "", eq: "1", role: "reactant", limiting: false, mmol: "", actual: "", density: ""};
    }

    function limitingRow() {
        return S.reaction.find(r => r.limiting) || S.reaction.find(r => r.role === "reactant");
    }

    function computeRow(r, lim) {
        const mw = Number(r.mw);
        const eq = Number(r.eq);
        const base = lim ? Number(lim.mmol) : NaN;
        const mmol = r === lim ? Number(r.mmol) : base * eq;

        return {mw, mmol: isFinite(mmol) ? mmol : NaN, mg: isFinite(mmol) && mw ? mmol * mw : NaN};
    }

    function fmt(n, digits) {
        return isFinite(n) ? String(Number(n.toFixed(digits))) : "";
    }

    function renderReaction() {
        reactionBox.replaceChildren();

        const lim = limitingRow();
        const table = el("table", "tw-table tw-chem-rx");
        const head = el("tr");

        ["Role", "Name", "MW", "Equiv.", "mmol", "mg", "Limiting", "Actual mg", "Yield %", ""].forEach(t => head.append(el("th", "", t)));
        table.append(head);

        S.reaction.forEach((r, index) => {
            const tr = el("tr");
            const calc = computeRow(r, lim);
            const isLim = lim === r;

            function cell(node) {
                const td = el("td");

                td.append(node);
                tr.append(td);

                return node;
            }

            function bind(key, value, opts) {
                const node = el("input");

                node.value = value;
                node.setAttribute("aria-label", key);

                if (opts && opts.readonly) node.readOnly = true;

                node.addEventListener("change", () => {
                    r[key] = node.value;
                    renderReaction();
                    changed();
                });

                return cell(node);
            }

            const role = el("select");

            ROLES.forEach(name => {
                const option = el("option", "", name);

                option.value = name;
                option.selected = name === r.role;
                role.append(option);
            });
            role.addEventListener("change", () => {
                r.role = role.value;

                if (r.role !== "reactant" && r.limiting) r.limiting = false;

                renderReaction();
                changed();
            });
            cell(role);
            bind("name", r.name);
            bind("mw", r.mw);
            bind("eq", r.eq);

            if (isLim) {
                bind("mmol", r.mmol);
                const mg = bind("mg", fmt(calc.mg, 3));

                mg.addEventListener("change", () => {
                    const v = Number(mg.value);

                    if (v > 0 && Number(r.mw) > 0) r.mmol = fmt(v / Number(r.mw), 5);

                    renderReaction();
                    changed();
                });
            } else {
                cell(el("span", "tw-mono", fmt(calc.mmol, 4)));
                cell(el("span", "tw-mono", fmt(calc.mg, 3)));
            }

            const radio = el("input");

            radio.type = "radio";
            radio.name = "chem-limiting";
            radio.checked = isLim;
            radio.disabled = r.role !== "reactant";
            radio.addEventListener("change", () => {
                S.reaction.forEach(x => { x.limiting = false; });
                r.limiting = true;
                renderReaction();
                changed();
            });
            cell(radio);

            if (r.role === "product") {
                bind("actual", r.actual);
                cell(el("span", "tw-mono", calc.mg > 0 && Number(r.actual) > 0 ? fmt(Number(r.actual) / calc.mg * 100, 1) : ""));
            } else {
                cell(el("span"));
                cell(el("span"));
            }

            const del = el("button", "tw-btn is-danger", "×");

            del.type = "button";
            del.title = "Remove row";
            del.addEventListener("click", () => {
                S.reaction.splice(index, 1);
                renderReaction();
                changed();
            });
            cell(del);
            table.append(tr);
        });

        const actions = el("div", "tw-row");
        const addCurrent = el("button", "tw-btn", "Add current compound");
        const addBlank = el("button", "tw-btn", "Add blank row");

        addCurrent.type = addBlank.type = "button";
        addCurrent.addEventListener("click", () => {
            const mw = molarMass();

            S.reaction.push(newRow(S.name.trim() || recordName() || S.formula.trim() || "compound", mw ? mw.toFixed(3) : ""));
            renderReaction();
            changed();
        });
        addBlank.addEventListener("click", () => {
            S.reaction.push(newRow());
            renderReaction();
            changed();
        });
        actions.append(addCurrent, addBlank);

        reactionBox.append(table, actions, el("p", "tw-note", "Set the amount of the limiting reagent (mmol or mg); the other rows follow from their equivalents. For products, “Actual mg” gives the yield."));
    }

    // ---- solution calculator -------------------------------------------------
    const calc = {conc: el("input"), vol: el("input"), out: el("span", "tw-mono")};

    calc.conc.placeholder = "mM";
    calc.vol.placeholder = "mL";
    calc.conc.addEventListener("input", recalc);
    calc.vol.addEventListener("input", recalc);

    function recalc() {
        const mw = molarMass();
        const mg = Number(calc.conc.value) * Number(calc.vol.value) * mw / 1000;

        calc.out.textContent = mw && mg > 0 ? fmt(mg, 3) + " mg to make " + calc.vol.value + " mL at " + calc.conc.value + " mM" : (mw ? "" : "needs a formula or structure");
    }

    const calcRow = el("div", "tw-row");

    calcRow.append(field("Concentration (mM)", calc.conc), field("Volume (mL)", calc.vol), calc.out);

    // C1·V1 = C2·V2
    const dil = {c1: el("input"), c2: el("input"), v2: el("input"), out: el("span", "tw-mono")};

    dil.c1.placeholder = "stock";
    dil.c2.placeholder = "final";
    dil.v2.placeholder = "final volume";
    [dil.c1, dil.c2, dil.v2].forEach(node => node.addEventListener("input", () => {
        const c1 = Number(dil.c1.value);
        const c2 = Number(dil.c2.value);
        const v2 = Number(dil.v2.value);

        if (c1 > 0 && c2 > 0 && v2 > 0 && c2 <= c1) {
            const v1 = c2 * v2 / c1;

            dil.out.textContent = fmt(v1, 4) + " of stock + " + fmt(v2 - v1, 4) + " of diluent";
        } else {
            dil.out.textContent = c2 > c1 ? "final must not exceed stock" : "";
        }
    }));

    const dilRow = el("div", "tw-row");

    dilRow.append(field("Stock concentration", dil.c1), field("Final concentration (same unit)", dil.c2), field("Final volume", dil.v2), dil.out);

    csvBtn.addEventListener("click", () => {
        const lim = limitingRow();
        const lines = [["role", "name", "MW", "equiv", "mmol", "mg", "limiting", "actual_mg", "yield_pct"].join("\t")];

        S.reaction.forEach(r => {
            const c = computeRow(r, lim);

            lines.push([r.role, r.name, r.mw, r.eq, fmt(c.mmol, 4), fmt(c.mg, 3), lim === r ? "yes" : "", r.actual || "",
                r.role === "product" && c.mg > 0 && Number(r.actual) > 0 ? fmt(Number(r.actual) / c.mg * 100, 1) : ""].join("\t"));
        });

        if (navigator.clipboard) navigator.clipboard.writeText(lines.join("\n")).then(() => setStatus("Reaction table copied (paste into a spreadsheet or the notebook).", "tw-ok"));
    });

    function section(title, ...children) {
        const box = el("section", "tw-chem-section");

        box.append(el("h4", "", title), ...children);

        return box;
    }

    // Each part goes to its own workbench window when the page has one; on a
    // page without those windows everything stays in the single host.
    const MOUNTS = {
        compound: document.getElementById("tw-chem-compound"),
        props: document.getElementById("tw-chem-props"),
        hazards: document.getElementById("tw-chem-hazards"),
        reaction: document.getElementById("tw-chem-reaction"),
        calc: document.getElementById("tw-chem-calc"),
    };

    function mount(key, title, ...children) {
        if (MOUNTS[key]) MOUNTS[key].append(...children);
        else host.append(section(title, ...children));
    }

    const idRow = el("div", "tw-row");
    const ids = el("div", "tw-row");
    const smilesActions = el("div", "tw-row");
    const molActions = el("div", "tw-row");
    const textBox = el("details", "tw-chem-text");

    idRow.append(field("Name", nodes.name), field("CAS number", nodes.cas), field("PubChem CID", nodes.cid));
    ids.append(field("IUPAC name", nodes.iupac), field("InChIKey", nodes.inchikey));
    smilesActions.append(lookupBtn, stockLink, addStock);
    molActions.append(molBtn, molDownload, svgBtn, copySmiles, molFile);
    textBox.append(el("summary", "", "SMILES and MOL block (text)"), field("SMILES", nodes.smiles), field("MOL block", nodes.mol));

    host.append(molActions, kBox, kNote, textBox);
    mount("compound", "Compound", idRow, smilesActions, status, ids, field("Molecular formula (used when there is no structure)", nodes.formula), field("Notes", nodes.notes));
    mount("props", "Properties", result);
    mount("hazards", "Hazards", hazardBox, el("p", "tw-note", "Mark what applies and check the supplier's safety data sheet before use."));
    mount("calc", "Solution calculator", calcRow, el("p", "tw-note", "Dilution (C1·V1 = C2·V2):"), dilRow);
    mount("reaction", "Reaction stoichiometry", reactionBox, csvBtn);

    function sync() {
        TEXT_KEYS.forEach(key => {
            if (nodes[key]) nodes[key].value = S[key];
        });
        document.querySelectorAll("#tw-chem-hazards [data-hazard], #tw-chemical [data-hazard]").forEach(box => {
            box.checked = S.hazards.split(",").includes(box.dataset.hazard);
        });
        renderResult();
        renderReaction();
        recalc();
    }

    window.BiobankChemical = {
        getState: () => Object.assign({}, S, {reaction: S.reaction.map(r => Object.assign({}, r))}),
        setState: state => {
            if (!state || typeof state !== "object") return;

            TEXT_KEYS.forEach(key => {
                if (typeof state[key] === "string") S[key] = state[key];
            });

            if (Array.isArray(state.reaction)) {
                S.reaction = state.reaction.filter(r => r && typeof r === "object").map(r => Object.assign(newRow(), r));
            }

            sync();
        },
        parseFormula,
        parseSmiles,
        parseMol,
        formulaOf,
        masses,
        prettyFormula,
    };


    sync();
    watchStructure();
}());
