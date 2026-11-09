/*
 * RNA secondary structure workbench layer.
 *
 * Sits on top of molecular_rna_secondary_structure.js (stored structures,
 * Forna drawing, upload). It adds what that module lacks:
 *   - view tabs: Forna | Arc | Circle | Dot-bracket | Pairs
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
    let view = "forna";
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
        const db = String(current.structure || "");
        const safe = seq.length === db.length;

        renderStats(db, seq);
        renderCompareSummary(db);
        ui.exportBtn.disabled = false;

        if (view === "forna") return;

        ui.stage.replaceChildren();
        ui.tip.textContent = safe ? "Hover a pair for details; click to select it in the sequence." : (
            "Sequence differs from the stored structure length; nucleotides may not match."
        );

        if (view === "arc") {
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
        const db = current ? String(current.structure || "") : "";

        if (!db) return;

        const name = baseName();
        const items = [
            ["Dot-bracket FASTA", () => download(`${name}.dbn`, `>${current.name || name}\n${seq}\n${db}\n`)],
            ["CT file", () => download(`${name}.ct`, toCt(db, seq, current.name || name))],
            ["Pairs CSV", () => download(`${name}_pairs.csv`, pairsCsv(db, seq), "text/csv")],
        ];

        const svgNode = ui.stage.querySelector("svg");

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

        [["forna", "Structure"], ["arc", "Arc"], ["circle", "Circle"], ["dot", "Dot-bracket"], ["pairs", "Pairs"]]
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
    const observer = new MutationObserver(() => {
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
    });

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
        if (ui && view !== "forna") renderView();
    });
})();
