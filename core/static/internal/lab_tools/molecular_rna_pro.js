/*
 * RNA secondary structure workbench layer.
 *
 * Sits on top of molecular_rna_secondary_structure.js (stored structures,
 * Forna drawing, upload). It adds what that module lacks:
 *   - view tabs: Structure (2D, interactive) | 3D | Force layout | Arc | Circle | Dot-bracket | Pairs
 *   - statistics computed from the dot-bracket (pairs, stems, loops, GC/AU/GU)
 *   - structure comparison (shared / only-A / only-B base pairs)
 *   - export: SVG, CT, dot-bracket FASTA, pairs CSV
 *   - clicking a pair or a nucleotide selects it in the shared workspace
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const card = document.getElementById("mw-rna-secondary-structure");

    if (!root || !card || root.dataset.sequenceType !== "rna") return;

    const apiUrl = root.dataset.rnaSecondaryStructuresUrl || "";
    const NS = "http://www.w3.org/2000/svg";
    const COLORS = {GC: "#1d4ed8", AU: "#d97706", GU: "#15803d", other: "#dc2626"};
    const BASE = {A: "#e07a5f", U: "#3d85c6", T: "#3d85c6", G: "#5aa469", C: "#c9a227"};

    let structures = [];
    let current = null;
    let view = "2d";
    let compareId = "";
    let ui = null;

    const el = (tag, cls, text) => {
        const n = document.createElement(tag);

        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;

        return n;
    };
    const svg = (tag, attrs) => {
        const n = document.createElementNS(NS, tag);

        for (const k in attrs || {}) n.setAttribute(k, attrs[k]);

        return n;
    };

    function sequence() {
        const api = window.BiobankMolecularWorkspace;
        const snap = api && api.getSnapshot && api.getSnapshot();

        return String((snap && snap.sequence) || "").toUpperCase().replace(/T/g, "U");
    }

    // ---- dot-bracket maths -------------------------------------------------
    const OPEN = "([{<";
    const CLOSE = ")]}>";

    function pairsOf(db) {
        const stacks = {"(": [], "[": [], "{": [], "<": []};
        const out = [];

        for (let i = 0; i < db.length; i += 1) {
            const c = db[i];
            const o = OPEN.indexOf(c);

            if (o >= 0) stacks[c].push(i);
            else {
                const k = CLOSE.indexOf(c);

                if (k >= 0 && stacks[OPEN[k]].length) {
                    out.push([stacks[OPEN[k]].pop(), i, k > 0]);
                }
            }
        }

        return out.sort((a, b) => a[0] - b[0]);
    }

    function pairClass(a, b) {
        const p = (a || "") + (b || "");

        if (p === "GC" || p === "CG") return "GC";
        if (p === "AU" || p === "UA") return "AU";
        if (p === "GU" || p === "UG") return "GU";

        return "other";
    }

    function analyse(db, seq) {
        const pairs = pairsOf(db);
        const partner = new Array(db.length).fill(-1);

        pairs.forEach(([i, j]) => {
            partner[i] = j;
            partner[j] = i;
        });

        const counts = {GC: 0, AU: 0, GU: 0, other: 0};

        pairs.forEach(([i, j]) => {
            counts[pairClass(seq[i], seq[j])] += 1;
        });

        // Stems: runs of stacked pairs (i+1, j-1).
        const stems = [];
        const seen = new Set();

        pairs.forEach(([i, j]) => {
            if (seen.has(i)) return;

            let a = i;
            let b = j;
            let len = 1;

            seen.add(a);

            while (partner[a + 1] === b - 1 && a + 1 < b - 1) {
                a += 1;
                b -= 1;
                len += 1;
                seen.add(a);
            }

            stems.push({start: i, end: j, length: len});
        });

        // Loops: classify the unpaired region enclosed by each closing pair.
        let hairpins = 0;
        let internal = 0;
        let bulges = 0;
        let multi = 0;
        const loopSizes = [];

        for (const [i, j] of pairs) {
            let inner = 0;
            let branches = 0;
            let k = i + 1;
            let unp = 0;
            const gaps = [];

            while (k < j) {
                if (partner[k] === -1) {
                    unp += 1;
                    k += 1;
                } else if (partner[k] > k) {
                    branches += 1;
                    gaps.push(unp);
                    unp = 0;
                    k = partner[k] + 1;
                } else {
                    k += 1;
                }
            }

            gaps.push(unp);
            inner = gaps.reduce((s, v) => s + v, 0);

            if (branches === 0) {
                hairpins += 1;
                loopSizes.push(inner);
            } else if (branches === 1) {
                if (gaps[0] > 0 && gaps[1] > 0) internal += 1;
                else if (gaps[0] > 0 || gaps[1] > 0) bulges += 1;
            } else {
                multi += 1;
            }
        }

        const paired = pairs.length * 2;
        const longest = stems.reduce((m, s) => Math.max(m, s.length), 0);

        return {
            pairs, partner, counts, stems, hairpins, internal, bulges, multi,
            paired, unpaired: db.length - paired, longest, loopSizes,
            pseudoknot: pairs.some(p => p[2]),
        };
    }

    // ---- sources of data ---------------------------------------------------
    async function loadAll() {
        if (!apiUrl) return;

        try {
            const response = await fetch(apiUrl, {
                credentials: "same-origin",
                headers: {Accept: "application/json"},
            });
            const data = await response.json();

            structures = Array.isArray(data.secondary_structures) ? data.secondary_structures : [];
        } catch (error) {
            structures = [];
        }
    }

    function activeStructure() {
        const items = card.querySelectorAll(".mrss-list-item");

        for (let i = 0; i < items.length; i += 1) {
            if (items[i].classList.contains("is-active")) return structures[i] || null;
        }

        return structures[0] || null;
    }

    // ---- exports -----------------------------------------------------------
    function download(name, text, type) {
        const url = URL.createObjectURL(new Blob([text], {type: type || "text/plain"}));
        const a = document.createElement("a");

        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function baseName() {
        return String((current && current.name) || "structure").replace(/[^\w.-]+/g, "_");
    }

    function toCt(db, seq, name) {
        const partner = analyse(db, seq).partner;
        const lines = [`${db.length}\t${name}`];

        for (let i = 0; i < db.length; i += 1) {
            lines.push([
                i + 1, seq[i] || "N", i, i + 2 > db.length ? 0 : i + 2,
                partner[i] + 1, i + 1,
            ].join("\t"));
        }

        return lines.join("\n") + "\n";
    }

    function pairsCsv(db, seq) {
        const rows = ["i,j,base_i,base_j,type,stem_distance"];

        pairsOf(db).forEach(([i, j]) => {
            rows.push([i + 1, j + 1, seq[i] || "", seq[j] || "", pairClass(seq[i], seq[j]), j - i].join(","));
        });

        return rows.join("\n") + "\n";
    }

    // ---- drawings ----------------------------------------------------------
    function selectRange(a, b) {
        const api = window.BiobankMolecularWorkspace;

        if (api && api.selectSequenceRange) api.selectSequenceRange(a + 1, b + 1);
    }

    function tip(text) {
        ui.tip.textContent = text;
    }

    function otherStructure() {
        return structures.find(s => String(s.id) === String(compareId)) || null;
    }

    function drawArc(db, seq) {
        const n = db.length;
        const cell = Math.max(7, Math.min(16, Math.floor(1100 / Math.max(n, 1))));
        const width = n * cell + 40;
        const other = otherStructure();
        const otherSet = other ? new Set(pairsOf(other.structure).map(p => p[0] + ":" + p[1])) : null;
        const mine = pairsOf(db);
        const mineSet = new Set(mine.map(p => p[0] + ":" + p[1]));
        const all = other ? [...mine, ...pairsOf(other.structure).filter(p => !mineSet.has(p[0] + ":" + p[1]))] : mine;
        const maxSpan = all.reduce((m, p) => Math.max(m, p[1] - p[0]), 1);
        const height = Math.min(360, Math.max(120, (maxSpan * cell) / 2 + 40));
        const base = height + 8;
        const s = svg("svg", {
            viewBox: `0 0 ${width} ${base + 54}`, width, height: base + 54,
            class: "mrp-svg", role: "img", "aria-label": "Arc diagram",
        });

        all.forEach(([i, j]) => {
            const x1 = 20 + i * cell + cell / 2;
            const x2 = 20 + j * cell + cell / 2;
            const r = (x2 - x1) / 2;
            const key = i + ":" + j;
            let color = COLORS[pairClass(seq[i], seq[j])];
            let dash = null;

            if (other) {
                const inMine = mineSet.has(key);
                const inOther = otherSet.has(key);

                color = inMine && inOther ? "#64748b" : (inMine ? "#1d4ed8" : "#dc2626");
                dash = inMine && inOther ? null : (inMine ? null : "4 3");
            }

            const path = svg("path", {
                d: `M${x1},${base} A${r},${Math.min(r, height)} 0 0 1 ${x2},${base}`,
                fill: "none", stroke: color, "stroke-width": 1.6, opacity: 0.8, class: "mrp-arc",
            });

            if (dash) path.setAttribute("stroke-dasharray", dash);

            path.addEventListener("mouseenter", () => tip(
                `${seq[i] || "?"}${i + 1} – ${seq[j] || "?"}${j + 1} · ${pairClass(seq[i], seq[j])}`
            ));
            path.addEventListener("click", () => selectRange(i, j));
            s.appendChild(path);
        });

        const line = svg("line", {x1: 20, x2: 20 + n * cell, y1: base + 1, y2: base + 1, stroke: "#c5ced8"});

        s.appendChild(line);

        for (let i = 0; i < n; i += 1) {
            const x = 20 + i * cell + cell / 2;
            const paired = db[i] !== ".";
            const t = svg("text", {
                x, y: base + 16, "text-anchor": "middle", "font-size": Math.max(7, cell - 3),
                fill: BASE[seq[i]] || "#64748b", "font-family": "IBM Plex Mono,monospace",
                "font-weight": paired ? 700 : 400, class: "mrp-nt",
            });

            t.textContent = seq[i] || "·";
            t.addEventListener("click", () => selectRange(i, i));
            s.appendChild(t);

            if ((i + 1) % 10 === 0) {
                const tick = svg("text", {
                    x, y: base + 34, "text-anchor": "middle", "font-size": 9, fill: "#8896a6",
                });

                tick.textContent = String(i + 1);
                s.appendChild(tick);
            }
        }

        return s;
    }

    function drawCircle(db, seq) {
        const n = db.length;
        const size = 560;
        const c = size / 2;
        const r = size / 2 - 46;
        const s = svg("svg", {
            viewBox: `0 0 ${size} ${size}`, width: size, height: size, class: "mrp-svg mrp-circle", role: "img",
            "aria-label": "Circle plot",
        });
        const pt = (i, rad) => {
            const a = (i / n) * Math.PI * 2 - Math.PI / 2;

            return [c + Math.cos(a) * rad, c + Math.sin(a) * rad];
        };

        s.appendChild(svg("circle", {cx: c, cy: c, r, fill: "none", stroke: "#e3e8ee"}));

        pairsOf(db).forEach(([i, j]) => {
            const [x1, y1] = pt(i, r - 4);
            const [x2, y2] = pt(j, r - 4);
            const path = svg("path", {
                d: `M${x1},${y1} Q${c},${c} ${x2},${y2}`, fill: "none",
                stroke: COLORS[pairClass(seq[i], seq[j])], "stroke-width": 1.5, opacity: 0.75, class: "mrp-arc",
            });

            path.addEventListener("mouseenter", () => tip(
                `${seq[i] || "?"}${i + 1} – ${seq[j] || "?"}${j + 1} · ${pairClass(seq[i], seq[j])}`
            ));
            path.addEventListener("click", () => selectRange(i, j));
            s.appendChild(path);
        });

        for (let i = 0; i < n; i += 1) {
            const [x, y] = pt(i, r + 10);
            const t = svg("text", {
                x, y: y + 3, "text-anchor": "middle", "font-size": n > 120 ? 7 : 9,
                fill: BASE[seq[i]] || "#64748b", "font-family": "IBM Plex Mono,monospace", class: "mrp-nt",
            });

            t.textContent = seq[i] || "·";
            t.addEventListener("click", () => selectRange(i, i));
            s.appendChild(t);

            if ((i + 1) % 10 === 0) {
                const [tx, ty] = pt(i, r + 28);
                const tick = svg("text", {x: tx, y: ty + 3, "text-anchor": "middle", "font-size": 8, fill: "#8896a6"});

                tick.textContent = String(i + 1);
                s.appendChild(tick);
            }
        }

        return s;
    }

    function drawDotBracket(db, seq) {
        const wrap = el("div", "mrp-db");
        const info = analyse(db, seq);

        for (let start = 0; start < db.length; start += 60) {
            const row = el("div", "mrp-db-row");
            const num = el("span", "mrp-db-num", String(start + 1));
            const sq = el("div", "mrp-db-seq");
            const st = el("div", "mrp-db-str");

            for (let i = start; i < Math.min(db.length, start + 60); i += 1) {
                const a = el("span", "mrp-db-nt", seq[i] || "·");

                a.style.color = BASE[seq[i]] || "#64748b";
                a.title = `${seq[i] || "?"}${i + 1}` + (info.partner[i] >= 0 ? ` ↔ ${info.partner[i] + 1}` : "");
                a.addEventListener("click", () => selectRange(i, info.partner[i] >= 0 ? info.partner[i] : i));
                sq.appendChild(a);
                st.appendChild(el("span", "mrp-db-ch" + (db[i] === "." ? "" : " is-paired"), db[i]));
            }

            const block = el("div", "mrp-db-block");

            block.append(sq, st);
            row.append(num, block);
            wrap.appendChild(row);
        }

        return wrap;
    }

    function drawPairs(db, seq) {
        const table = el("table", "mrp-table");
        const head = el("thead");
        const hr = el("tr");

        ["#", "i", "j", "Pair", "Type", "Span"].forEach(h => hr.appendChild(el("th", "", h)));
        head.appendChild(hr);
        table.appendChild(head);

        const body = el("tbody");

        pairsOf(db).forEach(([i, j], k) => {
            const tr = el("tr");
            const type = pairClass(seq[i], seq[j]);
            const cells = [k + 1, i + 1, j + 1, `${seq[i] || "?"}–${seq[j] || "?"}`, type, j - i];

            cells.forEach((v, idx) => {
                const td = el("td", "", String(v));

                if (idx === 4) td.style.color = COLORS[type];

                tr.appendChild(td);
            });
            tr.addEventListener("click", () => selectRange(i, j));
            body.appendChild(tr);
        });

        table.appendChild(body);

        const box = el("div", "mrp-table-wrap");

        box.appendChild(table);

        return box;
    }

    // ---- composition -------------------------------------------------------
    function stat(label, value, hint) {
        const tile = el("div", "mrp-stat");

        tile.append(el("span", "", label), el("strong", "", String(value)));

        if (hint) tile.title = hint;

        return tile;
    }

    function renderStats(db, seq) {
        const info = analyse(db, seq);
        const total = db.length || 1;
        const mfe = current && current.minimum_free_energy;
        const mfeNum = mfe === null || mfe === undefined ? null : Number(mfe);

        ui.stats.replaceChildren(
            stat("Length", `${db.length} nt`),
            stat("Base pairs", info.pairs.length),
            stat("Paired", `${Math.round((info.paired / total) * 100)}%`, `${info.paired} paired / ${info.unpaired} unpaired`),
            stat("MFE", mfeNum === null ? "—" : `${mfeNum} kcal/mol`),
            stat("MFE / nt", mfeNum === null ? "—" : (mfeNum / total).toFixed(3)),
            stat("Stems", info.stems.length, `Longest ${info.longest} bp`),
            stat("Hairpins", info.hairpins),
            stat("Internal / bulge", `${info.internal} / ${info.bulges}`),
            stat("Multiloops", info.multi),
            stat("GC · AU · GU", `${info.counts.GC} · ${info.counts.AU} · ${info.counts.GU}`,
                `Non-canonical: ${info.counts.other}`),
            stat("Pseudoknot", info.pseudoknot ? "Yes" : "No"),
        );

        const legend = [
            ["GC", COLORS.GC], ["AU", COLORS.AU], ["GU", COLORS.GU], ["Non-canonical", COLORS.other],
        ];

        ui.legend.replaceChildren(...legend.map(([name, color]) => {
            const chip = el("span", "mrp-chip");
            const dot = el("i");

            dot.style.background = color;
            chip.append(dot, document.createTextNode(` ${name}`));

            return chip;
        }));
    }

    function renderCompareSummary(db) {
        const other = otherStructure();

        ui.compareInfo.textContent = "";

        if (!other) return;

        const a = new Set(pairsOf(db).map(p => p[0] + ":" + p[1]));
        const b = new Set(pairsOf(other.structure).map(p => p[0] + ":" + p[1]));
        let shared = 0;

        a.forEach(k => {
            if (b.has(k)) shared += 1;
        });

        const union = a.size + b.size - shared;
        const jaccard = union ? shared / union : 1;

        ui.compareInfo.textContent = `${shared} shared · ${a.size - shared} only in this · ${b.size - shared} only in `
            + `“${other.name}” · similarity ${Math.round(jaccard * 100)}%`;
    }

    // ---- interactive 2D / 3D ----------------------------------------------
    const layoutLib = () => window.BiobankRnaLayout;
    const SCHEMES = [["base", "Nucleotide"], ["pair", "Pair type"], ["position", "Position"], ["none", "None"]];
    let scheme = "base";
    let editDb = null;
    let editFor = null;
    let editMode = false;
    let anchor = null;
    let lastPick = null;
    let hist = [];
    let vb2 = null;
    const cam = {yaw: 0.6, pitch: -0.35, zoom: 1, spin: false};
    let redraw3d = null;
    let model3d = false;

    function activeDb() {
        if (!current) return "";
        if (editDb !== null && editFor === current.id) return editDb;

        return String(current.structure || "");
    }

    function selection() {
        const api = window.BiobankMolecularWorkspace;
        const snap = api && api.getSnapshot && api.getSnapshot();
        const r = snap && snap.sequenceSelection;

        if (!r) return null;

        const a = Number(r.start);
        const b = Number(r.end);

        return Number.isFinite(a) && Number.isFinite(b) ? [Math.min(a, b) - 1, Math.max(a, b) - 1] : null;
    }

    function fillFor(i, seq, partner, n) {
        if (scheme === "pair") {
            return partner[i] >= 0 ? COLORS[pairClass(seq[i], seq[partner[i]])] : "#cbd5e1";
        }
        if (scheme === "position") return `hsl(${Math.round((i / Math.max(n, 1)) * 300)},65%,62%)`;
        if (scheme === "none") return "#e2e8f0";

        return BASE[seq[i]] || "#94a3b8";
    }

    function pick(i, shift) {
        if (shift && lastPick !== null) selectRange(Math.min(lastPick, i), Math.max(lastPick, i));
        else selectRange(i, i);

        lastPick = i;
    }

    function editClick(i, db) {
        const lib = layoutLib();
        const partner = lib.partnersOf(db, false);

        if (partner[i] >= 0) {
            hist.push(db);
            editDb = lib.removePair(db, i);
            editFor = current.id;
            anchor = null;
            renderView();

            return;
        }
        if (anchor === null) {
            anchor = i;
            tip(`Position ${i + 1} chosen — click the nucleotide to pair it with.`);
            renderView();

            return;
        }

        const a = anchor;

        anchor = null;

        if (a === i || Math.abs(a - i) < 4) {
            tip("A pair needs at least 3 nucleotides between its bases.");
        } else if (partner[a] >= 0 || lib.crosses(db, a, i)) {
            tip("That pair would cross an existing pair (pseudoknot) — not supported in the editor.");
        } else {
            hist.push(db);
            editDb = lib.setPair(db, a, i);
            editFor = current.id;
        }

        renderView();
    }

    async function saveEdited() {
        const db = activeDb();
        const seq = sequence();

        if (!current || seq.length !== db.length) {
            tip("Cannot save: sequence length differs from the structure.");

            return;
        }

        const name = `${current.name || "Structure"} (edited)`;
        const data = new FormData();

        data.append("action", "save");
        data.append("source_text", `>${name}\n${seq}\n${db}\n`);
        data.append("name", name);
        data.append("source_method", "Manual edit of base pairs");
        data.append("source_note", "Edited in the interactive structure view");

        try {
            const response = await fetch(apiUrl, {
                method: "POST", credentials: "same-origin", body: data,
                headers: {"X-CSRFToken": root.dataset.csrfToken || "", Accept: "application/json"},
            });
            const payload = await response.json();

            if (!response.ok || payload.status === "error") {
                tip(payload.message || "Could not save the edited structure.");

                return;
            }

            editDb = null;
            hist = [];
            tip("Saved as a new structure. Reloading…");
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            tip("Could not save the edited structure.");
        }
    }

    function toolButton(label, title, onClick, active) {
        const b = el("button", "mrp-btn mrp-btn-sm" + (active ? " is-on" : ""), label);

        b.type = "button";
        b.title = title;
        b.addEventListener("click", onClick);

        return b;
    }

    function figureTools(kind) {
        const bar = el("div", "mrp-figtools");
        const sel = document.createElement("select");

        sel.className = "mrp-select";
        sel.setAttribute("aria-label", "Colour bases by");
        SCHEMES.forEach(([k, label]) => sel.appendChild(new Option(`Colour: ${label}`, k)));
        sel.value = scheme;
        sel.addEventListener("change", () => {
            scheme = sel.value;
            renderView();
        });
        bar.appendChild(sel);

        if (kind === "2d") {
            bar.appendChild(toolButton("Fit", "Fit the whole structure", () => {
                vb2 = null;
                renderView();
            }));
            bar.appendChild(toolButton(editMode ? "Editing pairs ✓" : "Edit pairs",
                "Click a paired base to remove its pair; click two free bases to add one", () => {
                    editMode = !editMode;
                    anchor = null;
                    renderView();
                }, editMode));

            if (editMode) {
                const undo = toolButton("Undo", "Undo last edit", () => {
                    if (hist.length) {
                        editDb = hist.pop();
                        renderView();
                    }
                });

                undo.disabled = !hist.length;
                bar.appendChild(undo);

                const reset = toolButton("Reset", "Discard edits", () => {
                    editDb = null;
                    hist = [];
                    anchor = null;
                    renderView();
                });

                reset.disabled = editDb === null;
                bar.appendChild(reset);

                const save = toolButton("Save as new structure", "Store the edited pairs as a new structure", saveEdited);

                save.disabled = editDb === null;
                bar.appendChild(save);
            }
        } else {
            if (window.BiobankRnaStructure3D) {
                bar.appendChild(toolButton("3D structure (PDB)", "Back to the attached PDB / mmCIF structure", () => {
                    model3d = false;
                    renderView();
                }));
            }

            bar.appendChild(toolButton(cam.spin ? "Stop rotation" : "Rotate", "Toggle automatic rotation", () => {
                cam.spin = !cam.spin;
                renderView();
            }, cam.spin));
            bar.appendChild(toolButton("Reset view", "Reset the camera", () => {
                Object.assign(cam, {yaw: 0.6, pitch: -0.35, zoom: 1});
                if (redraw3d) redraw3d();
            }));
        }

        return bar;
    }

    function draw2d(db, seq) {
        const lib = layoutLib();
        const wrap = el("div", "mrp-figure");

        wrap.appendChild(figureTools("2d"));

        if (!lib) {
            wrap.appendChild(el("div", "mrp-empty", "Layout module not loaded."));

            return wrap;
        }

        const n = db.length;
        const lay = lib.layout(db, {loop: 1, pair: 1, rise: 1, closed: true});

        if (lay.pos.some(p => !p)) {
            wrap.appendChild(el("div", "mrp-empty", "This structure cannot be laid out; use the Arc or Circle view."));

            return wrap;
        }

        const S = 24;
        const R = 9;
        const pos = lay.pos.map(p => [p[0] * S, p[1] * S]);
        const b = lib.bounds(pos);
        const pad = 44;
        const full = {x: b.x0 - pad, y: b.y0 - pad, w: Math.max(b.x1 - b.x0 + 2 * pad, 120), h: Math.max(b.y1 - b.y0 + 2 * pad, 120)};

        if (!vb2 || vb2.n !== n) vb2 = {...full, n};

        const s = svg("svg", {class: "mrp-svg mrp-2d", role: "img", "aria-label": "RNA secondary structure drawing", preserveAspectRatio: "xMidYMid meet"});
        const setVb = () => s.setAttribute("viewBox", `${vb2.x} ${vb2.y} ${vb2.w} ${vb2.h}`);
        const partner = lay.partner;
        const sel = selection();
        const inSel = i => Boolean(sel) && i >= sel[0] && i <= sel[1];
        const gBack = svg("g");
        const gPairs = svg("g");
        const gNodes = svg("g");
        const gNums = svg("g");

        for (let i = 0; i < n - 1; i += 1) {
            gBack.appendChild(svg("line", {x1: pos[i][0], y1: pos[i][1], x2: pos[i + 1][0], y2: pos[i + 1][1], stroke: "#9aa5b1", "stroke-width": 2.2, "stroke-linecap": "round"}));
        }

        lib.pairsOf(db).forEach(([i, j, knot]) => {
            if (!knot && !(pos[i] && pos[j])) return;

            const line = svg("line", {
                x1: pos[i][0], y1: pos[i][1], x2: pos[j][0], y2: pos[j][1],
                stroke: knot ? "#9333ea" : "#3b82f6", "stroke-width": knot ? 1.6 : 2.2,
                "stroke-dasharray": knot ? "4 3" : "", class: "mrp-pairline",
            });

            line.addEventListener("mouseenter", () => tip(`${seq[i] || "?"}${i + 1} – ${seq[j] || "?"}${j + 1} · ${pairClass(seq[i], seq[j])}${knot ? " · pseudoknot" : ""}`));
            line.addEventListener("click", () => {
                if (editMode) editClick(i, db);
                else selectRange(i, j);
            });
            gPairs.appendChild(line);
        });

        for (let i = 0; i < n; i += 1) {
            const [x, y] = pos[i];
            const g = svg("g", {class: "mrp-node", "data-i": i});
            const circle = svg("circle", {
                cx: x, cy: y, r: R, fill: fillFor(i, seq, partner, n),
                stroke: anchor === i ? "#dc2626" : (inSel(i) ? "#111827" : "#64748b"),
                "stroke-width": anchor === i || inSel(i) ? 2.6 : 1,
            });
            const t = svg("text", {x, y: y + 3.2, "text-anchor": "middle", "font-size": 9.5, "font-weight": 600, fill: "#1f2937", "font-family": "IBM Plex Mono,monospace", "pointer-events": "none"});

            t.textContent = seq[i] || "·";
            g.append(circle, t);
            g.addEventListener("mouseenter", () => tip(
                `${seq[i] || "?"}${i + 1}` + (partner[i] >= 0 ? ` paired with ${seq[partner[i]] || "?"}${partner[i] + 1}` : " unpaired")
            ));
            g.addEventListener("click", event => {
                if (editMode) editClick(i, db);
                else pick(i, event.shiftKey);
            });
            gNodes.appendChild(g);

            if ((i + 1) % 10 === 0 || i === 0) {
                const prev = pos[Math.max(i - 1, 0)];
                const next = pos[Math.min(i + 1, n - 1)];
                let vx = x - (prev[0] + next[0]) / 2;
                let vy = y - (prev[1] + next[1]) / 2;
                const len = Math.hypot(vx, vy);

                if (len < 0.5) {
                    vx = 0;
                    vy = -1;
                } else {
                    vx /= len;
                    vy /= len;
                }

                gNums.appendChild(svg("line", {x1: x + vx * R, y1: y + vy * R, x2: x + vx * (R + 7), y2: y + vy * (R + 7), stroke: "#94a3b8", "stroke-width": 1}));

                const label = svg("text", {x: x + vx * (R + 16), y: y + vy * (R + 16) + 3, "text-anchor": "middle", "font-size": 9, fill: "#64748b"});

                label.textContent = String(i + 1);
                gNums.appendChild(label);
            }
        }

        s.append(gBack, gPairs, gNums, gNodes);
        setVb();

        const scaleOf = () => Math.max(vb2.w / (s.clientWidth || 800), vb2.h / (s.clientHeight || 520));
        let drag = null;

        s.addEventListener("pointerdown", event => {
            if (event.target.closest(".mrp-node, .mrp-pairline")) return;

            drag = {x: event.clientX, y: event.clientY};
            s.setPointerCapture(event.pointerId);
            s.classList.add("is-grabbing");
        });
        s.addEventListener("pointermove", event => {
            if (!drag) return;

            const k = scaleOf();

            vb2.x -= (event.clientX - drag.x) * k;
            vb2.y -= (event.clientY - drag.y) * k;
            drag = {x: event.clientX, y: event.clientY};
            setVb();
        });
        const end = () => {
            drag = null;
            s.classList.remove("is-grabbing");
        };

        s.addEventListener("pointerup", end);
        s.addEventListener("pointercancel", end);
        s.addEventListener("wheel", event => {
            event.preventDefault();

            const rect = s.getBoundingClientRect();
            const k = scaleOf();
            const mx = vb2.x + (event.clientX - rect.left - (rect.width - vb2.w / k) / 2) * k;
            const my = vb2.y + (event.clientY - rect.top - (rect.height - vb2.h / k) / 2) * k;
            const f = event.deltaY < 0 ? 0.88 : 1.14;

            vb2.x = mx - (mx - vb2.x) * f;
            vb2.y = my - (my - vb2.y) * f;
            vb2.w *= f;
            vb2.h *= f;
            setVb();
        }, {passive: false});

        const hint = el("div", "mrp-figure-hint", editMode
            ? "Edit mode: click a paired base to remove its pair, or two free bases to create one."
            : "Drag to move · scroll to zoom · click a base (Shift for a range) to select it in the sequence.");

        wrap.append(s, hint);

        return wrap;
    }

    function draw3dReal(db, seq) {
        const lib = window.BiobankRnaStructure3D;

        if (!lib || model3d) return draw3d(db, seq);

        const holder = el("div", "mrp-figure");

        lib.mount(() => {
            model3d = true;
            renderView();
        }).then(host => {
            if (view === "3d" && !model3d && holder.isConnected) holder.appendChild(host);
        });

        return holder;
    }

    function draw3d(db, seq) {
        const lib = layoutLib();
        const wrap = el("div", "mrp-figure");

        wrap.appendChild(figureTools("3d"));

        if (!lib) {
            wrap.appendChild(el("div", "mrp-empty", "Layout module not loaded."));

            return wrap;
        }

        const n = db.length;
        const model = lib.build3d(db);
        const pts = model.pts;

        if (pts.some(p => !p || p.some(v => !Number.isFinite(v)))) {
            wrap.appendChild(el("div", "mrp-empty", "This structure cannot be modelled in 3D; use the Arc or Circle view."));

            return wrap;
        }

        const c = [0, 1, 2].map(k => pts.reduce((a, p) => a + p[k], 0) / n);
        const ext = Math.max(1, ...pts.map(p => Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2])));
        const canvas = document.createElement("canvas");

        canvas.className = "mrp-3d";
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", "Illustrative 3D RNA model");
        wrap.appendChild(canvas);
        wrap.appendChild(el("div", "mrp-figure-hint",
            "Illustrative model built from the base pairs (idealised A-form helices, flat loops), not a predicted tertiary structure. Drag to rotate · scroll to zoom · click a base to select it."));

        const sel = selection();
        let hits = [];

        redraw3d = () => {
            const dpr = window.devicePixelRatio || 1;
            const w = canvas.clientWidth || 800;
            const h = canvas.clientHeight || 520;

            if (canvas.width !== Math.round(w * dpr)) {
                canvas.width = Math.round(w * dpr);
                canvas.height = Math.round(h * dpr);
            }

            const ctx = canvas.getContext("2d");

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);

            const cy = Math.cos(cam.yaw);
            const sy = Math.sin(cam.yaw);
            const cp = Math.cos(cam.pitch);
            const sp = Math.sin(cam.pitch);
            const k = (Math.min(w, h) / (ext * 2.3)) * cam.zoom;
            const P = pts.map(p => {
                const x0 = p[0] - c[0];
                const y0 = p[1] - c[1];
                const z0 = p[2] - c[2];
                const x1 = x0 * cy + z0 * sy;
                const z1 = -x0 * sy + z0 * cy;
                const y1 = y0 * cp - z1 * sp;
                const z2 = y0 * sp + z1 * cp;

                return {x: w / 2 + x1 * k, y: h / 2 + y1 * k, z: z2};
            });
            const items = [];

            for (let i = 0; i < n - 1; i += 1) items.push({t: "bond", a: i, b: i + 1, z: (P[i].z + P[i + 1].z) / 2});
            lib.pairsOf(db).forEach(([i, j, knot]) => {
                if (!knot) items.push({t: "rung", a: i, b: j, z: (P[i].z + P[j].z) / 2});
            });
            for (let i = 0; i < n; i += 1) items.push({t: "nt", a: i, z: P[i].z});
            items.sort((a, b) => a.z - b.z);
            hits = [];

            const depth = z => 0.62 + 0.38 * Math.max(-1, Math.min(1, z / ext));

            items.forEach(it => {
                if (it.t === "bond") {
                    ctx.strokeStyle = "#7d8998";
                    ctx.globalAlpha = depth(it.z);
                    ctx.lineWidth = Math.max(1.5, 1.5 * k * 0.55);
                    ctx.lineCap = "round";
                    ctx.beginPath();
                    ctx.moveTo(P[it.a].x, P[it.a].y);
                    ctx.lineTo(P[it.b].x, P[it.b].y);
                    ctx.stroke();
                } else if (it.t === "rung") {
                    ctx.strokeStyle = COLORS[pairClass(seq[it.a], seq[it.b])];
                    ctx.globalAlpha = 0.55 * depth(it.z);
                    ctx.lineWidth = Math.max(1, k * 0.7);
                    ctx.beginPath();
                    ctx.moveTo(P[it.a].x, P[it.a].y);
                    ctx.lineTo(P[it.b].x, P[it.b].y);
                    ctx.stroke();
                } else {
                    const i = it.a;
                    const r = Math.max(3.2, 2.4 * k * (0.85 + 0.3 * depth(it.z)));
                    const color = fillFor(i, seq, model.partner, n);
                    const selected = Boolean(sel) && i >= sel[0] && i <= sel[1];

                    ctx.globalAlpha = 1;

                    if (n <= 1500) {
                        const grad = ctx.createRadialGradient(P[i].x - r * 0.35, P[i].y - r * 0.4, r * 0.1, P[i].x, P[i].y, r);

                        grad.addColorStop(0, "#ffffff");
                        grad.addColorStop(0.35, color);
                        grad.addColorStop(1, color);
                        ctx.fillStyle = grad;
                    } else ctx.fillStyle = color;

                    ctx.beginPath();
                    ctx.arc(P[i].x, P[i].y, r, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.lineWidth = selected ? 2.5 : 0.8;
                    ctx.strokeStyle = selected ? "#111827" : "rgba(71,85,105,.7)";
                    ctx.stroke();
                    hits.push({i, x: P[i].x, y: P[i].y, r, z: it.z});
                }
            });
            ctx.globalAlpha = 1;
        };

        let drag = null;
        let moved = 0;

        canvas.addEventListener("pointerdown", event => {
            drag = {x: event.clientX, y: event.clientY};
            moved = 0;
            canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener("pointermove", event => {
            if (!drag) return;

            const dx = event.clientX - drag.x;
            const dy = event.clientY - drag.y;

            moved += Math.abs(dx) + Math.abs(dy);
            cam.yaw += dx * 0.008;
            cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + dy * 0.008));
            drag = {x: event.clientX, y: event.clientY};
            if (redraw3d) redraw3d();
        });
        canvas.addEventListener("pointerup", event => {
            drag = null;

            if (moved > 4) return;

            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            let best = null;

            hits.forEach(h => {
                const d = Math.hypot(h.x - x, h.y - y);

                if (d <= h.r + 3 && (!best || h.z > best.z)) best = h;
            });

            if (best) pick(best.i, event.shiftKey);
        });
        canvas.addEventListener("pointermove", event => {
            if (drag) return;

            const rect = canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            let best = null;

            hits.forEach(h => {
                if (Math.hypot(h.x - x, h.y - y) <= h.r + 2 && (!best || h.z > best.z)) best = h;
            });

            if (best) {
                const i = best.i;

                tip(`${seq[i] || "?"}${i + 1}` + (model.partner[i] >= 0 ? ` paired with ${seq[model.partner[i]] || "?"}${model.partner[i] + 1}` : " unpaired"));
            }
        });
        canvas.addEventListener("wheel", event => {
            event.preventDefault();
            cam.zoom = Math.max(0.3, Math.min(6, cam.zoom * (event.deltaY < 0 ? 1.12 : 0.89)));
            if (redraw3d) redraw3d();
        }, {passive: false});

        const spin = () => {
            if (!canvas.isConnected || !cam.spin) return;

            cam.yaw += 0.01;
            if (redraw3d) redraw3d();
            requestAnimationFrame(spin);
        };

        requestAnimationFrame(() => {
            if (redraw3d) redraw3d();
            if (cam.spin) spin();
        });

        return wrap;
    }

    function renderView() {
        if (!ui) return;

        current = activeStructure();

        const fornaShell = card.querySelector(".mrss-viewer-shell");
        const legacyDb = card.querySelector(".mrss-structure-code-wrap");

        card.dataset.mrpView = view;
        ui.tabs.forEach(t => t.classList.toggle("is-active", t.dataset.view === view));

        if (fornaShell) fornaShell.hidden = view !== "forna";

        ui.stage.hidden = view === "forna";
        ui.panel.hidden = !current;
        ui.empty.hidden = Boolean(current);

        if (legacyDb) legacyDb.hidden = view !== "forna";

        ui.compareRow.hidden = !(view === "arc" && structures.length > 1);

        if (!current) return;

        const seq = sequence();
        const db = activeDb();
        const safe = seq.length === db.length;

        renderStats(db, seq);
        renderCompareSummary(db);
        ui.exportBtn.disabled = false;

        if (view === "forna") return;

        ui.stage.replaceChildren();
        ui.tip.textContent = safe ? "Hover a pair for details; click to select it in the sequence." : (
            "Sequence differs from the stored structure length; nucleotides may not match."
        );

        if (view === "2d") {
            ui.stage.appendChild(draw2d(db, safe ? seq : ""));
        } else if (view === "3d") {
            ui.stage.appendChild(draw3dReal(db, safe ? seq : ""));
        } else if (view === "arc") {
            const box = el("div", "mrp-scroll");

            box.appendChild(drawArc(db, safe ? seq : ""));
            ui.stage.appendChild(box);
        } else if (view === "circle") {
            const box = el("div", "mrp-center");

            box.appendChild(drawCircle(db, safe ? seq : ""));
            ui.stage.appendChild(box);
        } else if (view === "dot") {
            ui.stage.appendChild(drawDotBracket(db, safe ? seq : ""));
        } else if (view === "pairs") {
            ui.stage.appendChild(drawPairs(db, safe ? seq : ""));
        }
    }

    function exportMenu(event) {
        const seq = sequence();
        const db = activeDb();

        if (!db) return;

        const name = baseName();
        const items = [
            ["Dot-bracket FASTA", () => download(`${name}.dbn`, `>${current.name || name}\n${seq}\n${db}\n`)],
            ["CT file", () => download(`${name}.ct`, toCt(db, seq, current.name || name))],
            ["Pairs CSV", () => download(`${name}_pairs.csv`, pairsCsv(db, seq), "text/csv")],
        ];

        const svgNode = ui.stage.querySelector("svg.mrp-svg");

        if (svgNode) {
            items.push(["SVG image", () => {
                const clone = svgNode.cloneNode(true);

                clone.setAttribute("xmlns", NS);
                download(`${name}_${view}.svg`, new XMLSerializer().serializeToString(clone), "image/svg+xml");
            }]);
        }

        ui.menu.replaceChildren(...items.map(([label, run]) => {
            const b = el("button", "mrp-menu-item", label);

            b.type = "button";
            b.addEventListener("click", () => {
                run();
                ui.menu.hidden = true;
            });

            return b;
        }));
        ui.menu.hidden = !ui.menu.hidden;
        event.stopPropagation();
    }

    function build() {
        const main = card.querySelector(".mrss-main");

        if (!main || card.querySelector(".mrp-bar")) return Boolean(card.querySelector(".mrp-bar"));

        const bar = el("div", "mrp-bar");
        const tabsBox = el("div", "mrp-tabs");
        const tabs = [];

        [["2d", "Structure"], ["3d", "3D"], ["forna", "Force layout"], ["arc", "Arc"], ["circle", "Circle"], ["dot", "Dot-bracket"], ["pairs", "Pairs"]]
            .forEach(([key, label]) => {
                const b = el("button", "mrp-tab" + (key === view ? " is-active" : ""), label);

                b.type = "button";
                b.dataset.view = key;
                b.addEventListener("click", () => {
                    view = key;
                    renderView();
                });
                tabs.push(b);
                tabsBox.appendChild(b);
            });

        const compareRow = el("div", "mrp-compare");
        const sel = document.createElement("select");

        sel.className = "mrp-select";
        sel.addEventListener("change", () => {
            compareId = sel.value;
            renderView();
        });

        const compareInfo = el("span", "mrp-compare-info");

        compareRow.append(el("label", "", "Compare with"), sel, compareInfo);
        compareRow.hidden = true;

        const exportWrap = el("div", "mrp-export");
        const exportBtn = el("button", "mrp-btn", "Export ▾");

        exportBtn.type = "button";
        exportBtn.disabled = true;
        exportBtn.addEventListener("click", exportMenu);

        const menu = el("div", "mrp-menu");

        menu.hidden = true;
        exportWrap.append(exportBtn, menu);
        document.addEventListener("click", () => {
            menu.hidden = true;
        });

        bar.append(tabsBox, compareRow, exportWrap);

        const panel = el("div", "mrp-panel");
        const stats = el("div", "mrp-stats");
        const legend = el("div", "mrp-legend");
        const stage = el("div", "mrp-stage");
        const tipNode = el("div", "mrp-tip");
        const empty = el("div", "mrp-empty", "Add a structure (dot-bracket, CT or FASTA with structure line) to see statistics and views.");

        stage.hidden = true;
        panel.append(stats, legend);

        // Insert before the legacy toolbar so metadata/stats come first.
        const first = main.firstElementChild;

        main.insertBefore(bar, first);
        main.insertBefore(panel, first);
        main.insertBefore(stage, first);
        main.insertBefore(tipNode, first);
        main.insertBefore(empty, first);

        ui = {tabs, stage, panel, stats, legend, tip: tipNode, empty, menu, exportBtn, compareRow, compareInfo, select: sel};

        return true;
    }

    function fillCompare() {
        if (!ui) return;

        const keep = compareId;

        ui.select.replaceChildren(new Option("— none —", ""));

        structures.forEach(s => {
            if (current && s.id === current.id) return;

            ui.select.appendChild(new Option(s.name || `Structure ${s.id}`, String(s.id)));
        });

        ui.select.value = [...ui.select.options].some(o => o.value === keep) ? keep : "";
        compareId = ui.select.value;
    }

    async function refresh() {
        await loadAll();

        if (!build()) return;

        current = activeStructure();
        fillCompare();
        renderView();
    }

    // The legacy module rebuilds its DOM asynchronously and re-renders the
    // list on every selection, so follow its list instead of polling timers.
    let queued = false;
    const observer = new MutationObserver(() => {
        // Debounced so our own DOM updates can never re-enter synchronously.
        if (queued) return;

        queued = true;
        setTimeout(() => {
            queued = false;
            onCardChange();
        }, 60);
    });

    function onCardChange() {
        if (!card.querySelector(".mrss-main")) return;

        if (!ui || !card.contains(ui.stage)) {
            ui = null;
            refresh();

            return;
        }

        const active = activeStructure();

        if (active && (!current || active.id !== current.id)) {
            current = active;
            fillCompare();
            renderView();
        }
    }

    observer.observe(card, {subtree: true, childList: true, attributes: true, attributeFilter: ["class"]});

    // Structures can be added or removed by the legacy form; reload the list.
    card.addEventListener("click", event => {
        if (event.target.closest(".mrss-form button, .mrss-list button, button")) {
            setTimeout(() => {
                loadAll().then(() => {
                    current = activeStructure();
                    fillCompare();
                    renderView();
                });
            }, 900);
        }
    });

    root.addEventListener("biobank:molecular-workspace-change", () => {
        if (!ui || view === "forna") return;

        // The Mol* viewer follows the selection by itself; rebuilding it here would reset the camera.
        if (view === "3d" && !model3d && window.BiobankRnaStructure3D) return;

        renderView();
    });

    // One layout: the structure card is always shown under the sequence, so
    // ask the stored-structure module to load without a view switch.
    const boot = () => root.dispatchEvent(new CustomEvent("biobank:molecular-view-change", {
        detail: {view: "secondary-structure", requestedView: "secondary-structure", unified: true},
    }));

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(boot, 0));
    else setTimeout(boot, 0);
})();
