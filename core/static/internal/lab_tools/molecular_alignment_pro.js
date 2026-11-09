/*
 * Protein alignment workbench layer.
 *
 * molecular_protein_alignment.js stores, lists and uploads alignments. This
 * layer replaces its plain text rendering with a viewer that matches the
 * sequence views: colour schemes, conservation, consensus, reference
 * selection, motif search, identity table, jump-to-position, export and
 * two-way selection with the protein record.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");

    if (!root || root.dataset.sequenceType !== "protein") return;

    const apiUrl = root.dataset.proteinAlignmentsUrl || "";
    const NAME_W = 140;
    const CELL_W = 11;

    const GROUPS = ["ILVM", "FYW", "KRH", "DE", "NQ", "ST", "AG", "C", "P"];
    const CLUSTAL = {
        A: "#80a0f0", V: "#80a0f0", F: "#80a0f0", P: "#80a0f0", M: "#80a0f0", I: "#80a0f0", L: "#80a0f0", W: "#80a0f0",
        K: "#f01505", R: "#f01505", D: "#c048c0", E: "#c048c0",
        N: "#15c015", Q: "#15c015", S: "#15c015", T: "#15c015",
        C: "#f08080", G: "#f09048", H: "#15a4a4", Y: "#15a4a4",
    };
    const KD = {
        A: 1.8, R: -4.5, N: -3.5, D: -3.5, C: 2.5, Q: -3.5, E: -3.5, G: -0.4, H: -3.2, I: 4.5,
        L: 3.8, K: -3.9, M: 1.9, F: 2.8, P: -1.6, S: -0.8, T: -0.7, W: -0.9, Y: -1.3, V: 4.2,
    };

    const state = {
        id: null, key: "", rows: [], len: 0, ref: 0, scheme: "clustal", width: "auto", showCons: true,
        showBar: true, motif: "", payload: null,
        sel: null, base: 0, orig: null,
    };

    let shell = null;
    let proRoot = null;
    let metrics = null;

    const el = (tag, cls, text) => {
        const n = document.createElement(tag);

        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;

        return n;
    };

    const groupOf = c => GROUPS.findIndex(g => g.includes(c));

    function sameClass(a, b) {
        if (a === b) return true;

        const g = groupOf(a);

        return g >= 0 && g === groupOf(b);
    }

    const isGap = ch => ch === "-" || ch === "." || ch === undefined;

    function ungappedIndex(seq) {
        const map = new Array(seq.length);
        let n = 0;

        for (let i = 0; i < seq.length; i += 1) {
            if (!isGap(seq[i])) {
                n += 1;
                map[i] = n + state.base;
            } else {
                map[i] = 0;
            }
        }

        return map;
    }

    function compute() {
        const rows = state.rows;
        const len = state.len;
        const cons = new Array(len).fill(0);
        const consensus = new Array(len).fill("-");
        let fully = 0;
        let gapCells = 0;

        for (let c = 0; c < len; c += 1) {
            const counts = {};
            let total = 0;

            for (const r of rows) {
                const ch = r.seq[c];

                if (isGap(ch)) {
                    gapCells += 1;
                    continue;
                }

                counts[ch] = (counts[ch] || 0) + 1;
                total += 1;
            }

            let best = "-";
            let top = 0;

            for (const k in counts) {
                if (counts[k] > top) {
                    top = counts[k];
                    best = k;
                }
            }

            cons[c] = rows.length ? top / rows.length : 0;
            consensus[c] = !total ? "-" : (top / rows.length >= 0.5 ? best : best.toLowerCase());

            if (top === rows.length && rows.length > 1) fully += 1;
        }

        const ref = rows[state.ref] || rows[0];
        const table = rows.map(r => {
            let ident = 0;
            let sim = 0;
            let aligned = 0;
            let gaps = 0;
            let residues = 0;

            for (let c = 0; c < len; c += 1) {
                const a = r.seq[c];
                const b = ref && ref.seq[c];

                if (isGap(a)) gaps += 1;
                else residues += 1;

                if (!isGap(a) && !isGap(b)) {
                    aligned += 1;
                    if (a === b) ident += 1;
                    if (sameClass(a, b)) sim += 1;
                }
            }

            return {
                name: r.name, residues, gaps, aligned,
                identity: aligned ? ident / aligned : 0, similarity: aligned ? sim / aligned : 0,
            };
        });

        const others = table.filter((_, i) => i !== state.ref);

        metrics = {
            cons, consensus, fully, table,
            meanIdentity: others.length ? others.reduce((s, t) => s + t.identity, 0) / others.length : 1,
            gapFraction: rows.length * len ? gapCells / (rows.length * len) : 0,
        };
    }

    // ---- colours -----------------------------------------------------------
    function cellStyle(ch, col, rowIndex) {
        if (isGap(ch)) return null;

        const s = state.scheme;

        if (s === "clustal") return CLUSTAL[ch] ? [CLUSTAL[ch], "#fff"] : null;

        if (s === "hydro") {
            const v = KD[ch];

            if (v === undefined) return null;

            const t = (v + 4.5) / 9;

            return [`rgb(${Math.round(60 + t * 190)},${Math.round(120 + (0.5 - Math.abs(t - 0.5)) * 80)},${Math.round(230 - t * 190)})`, "#fff"];
        }

        if (s === "charge") {
            if ("KR".includes(ch)) return ["#2563eb", "#fff"];
            if (ch === "H") return ["#93b4f5", "#10233f"];
            if ("DE".includes(ch)) return ["#dc2626", "#fff"];

            return null;
        }

        if (s === "identity") {
            const ref = state.rows[state.ref];

            if (rowIndex === state.ref) return ["#64748b", "#fff"];

            const rc = ref && ref.seq[col];

            if (rc === ch) return ["#1d4ed8", "#fff"];
            if (rc && sameClass(rc, ch)) return ["#a9c1f5", "#10233f"];

            return null;
        }

        if (s === "conservation") {
            const f = metrics.cons[col];

            if (f >= 0.999) return ["#1e3a8a", "#fff"];
            if (f >= 0.75) return ["#3b82f6", "#fff"];
            if (f >= 0.5) return ["#bfdbfe", "#10233f"];
        }

        return null;
    }

    // ---- selection / helpers -----------------------------------------------
    function workspaceSelection() {
        const api = window.BiobankMolecularWorkspace;
        const snap = api && api.getSnapshot && api.getSnapshot();
        const sel = snap && (snap.sequenceSelection || snap.selection);

        return sel && sel.start ? sel : null;
    }

    function selectRef(pos) {
        const api = window.BiobankMolecularWorkspace;

        if (api && api.selectSequenceRange && pos > 0) api.selectSequenceRange(pos, pos);
    }

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

    function motifColumns(seq) {
        if (!state.motif) return new Set();

        let re;

        try {
            re = new RegExp(state.motif.toUpperCase(), "g");
        } catch (error) {
            return new Set();
        }

        const cols = [];
        let plain = "";

        for (let i = 0; i < seq.length; i += 1) {
            if (!isGap(seq[i])) {
                plain += seq[i];
                cols.push(i);
            }
        }

        const out = new Set();
        let m;

        while ((m = re.exec(plain)) !== null) {
            if (!m[0].length) {
                re.lastIndex += 1;
                continue;
            }

            for (let k = 0; k < m[0].length; k += 1) out.add(cols[m.index + k]);

            if (out.size > 5000) break;
        }

        return out;
    }

    // ---- rendering ---------------------------------------------------------
    function colsPerBlock() {
        if (state.width !== "auto") return Number(state.width);

        const avail = (proRoot.clientWidth || 700) - NAME_W - 40;

        return Math.max(20, Math.floor(avail / CELL_W / 10) * 10);
    }

    function renderBlock(blockStart, blockEnd, refMap, hitsByRow) {
        const block = el("section", "mpro-block");
        const ruler = el("div", "mpro-line mpro-ruler");
        const sel = workspaceSelection();

        ruler.appendChild(el("span", "mpro-name mpro-label", `${blockStart + 1}–${blockEnd}`));

        const rc = el("span", "mpro-seq");

        for (let c = blockStart; c < blockEnd; c += 1) {
            const tick = (c + 1) % 10 === 0;
            const cell = el("i", "mpro-c" + (tick ? " is-tick" : ""), tick ? String(c + 1) : "");

            cell.dataset.c = String(c);
            if (state.sel && c >= state.sel.a && c <= state.sel.b) cell.classList.add("is-colsel");
            rc.appendChild(cell);
        }

        ruler.appendChild(rc);
        block.appendChild(ruler);

        state.rows.forEach((row, ri) => {
            const line = el("div", "mpro-line" + (ri === state.ref ? " is-ref" : ""));
            const name = el("button", "mpro-name", row.name);

            name.type = "button";
            name.title = `${row.name}\nClick to use as reference`;
            name.addEventListener("click", () => {
                state.ref = ri;
                render();
            });

            const seq = el("span", "mpro-seq");
            const hits = hitsByRow[ri];

            for (let c = blockStart; c < blockEnd; c += 1) {
                const ch = row.seq[c];
                const cell = el("i", "mpro-c", isGap(ch) ? "-" : ch);
                const style = cellStyle(ch, c, ri);

                if (style) {
                    cell.style.background = style[0];
                    cell.style.color = style[1];
                } else if (isGap(ch)) {
                    cell.classList.add("is-gap");
                }

                if (hits.has(c)) cell.classList.add("is-hit");

                const pos = refMap[c];

                if (sel && pos && pos >= sel.start && pos <= sel.end) cell.classList.add("is-sel");

                if (state.sel && c >= state.sel.a && c <= state.sel.b) cell.classList.add("is-colsel");
                cell.dataset.c = String(c);
                cell.dataset.r = String(ri);
                seq.appendChild(cell);
            }

            line.append(name, seq);
            block.appendChild(line);
        });

        if (state.showBar) {
            const line = el("div", "mpro-line mpro-barline");

            line.appendChild(el("span", "mpro-name mpro-label", "Conservation"));

            const seq = el("span", "mpro-seq");

            for (let c = blockStart; c < blockEnd; c += 1) {
                const cell = el("i", "mpro-c");
                const bar = el("b");
                const f = metrics.cons[c];

                bar.style.height = `${Math.round(f * 100)}%`;
                bar.style.background = f >= 0.999 ? "#1e3a8a" : (f >= 0.5 ? "#60a5fa" : "#cbd5e1");
                cell.appendChild(bar);
                seq.appendChild(cell);
            }

            line.appendChild(seq);
            block.appendChild(line);
        }

        if (state.showCons) {
            const line = el("div", "mpro-line mpro-consensus");

            line.appendChild(el("span", "mpro-name mpro-label", "Consensus"));

            const seq = el("span", "mpro-seq");

            for (let c = blockStart; c < blockEnd; c += 1) seq.appendChild(el("i", "mpro-c", metrics.consensus[c]));

            line.appendChild(seq);
            block.appendChild(line);
        }

        return block;
    }

    function renderView(container) {
        container.replaceChildren();

        const ref = state.rows[state.ref];
        const refMap = ref ? ungappedIndex(ref.seq) : new Array(state.len).fill(0);
        const hitsByRow = state.rows.map(r => motifColumns(r.seq));
        const per = colsPerBlock();
        const large = state.rows.length * state.len > 60000;
        const io = large && "IntersectionObserver" in window ? new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;

                const holder = entry.target;
                const [a, b] = holder.__range;

                io.unobserve(holder);
                holder.replaceWith(renderBlock(a, b, refMap, hitsByRow));
            });
        }, {rootMargin: "400px"}) : null;

        for (let start = 0; start < state.len; start += per) {
            const end = Math.min(state.len, start + per);

            if (io) {
                const holder = el("div", "mpro-holder");

                holder.style.height = `${(state.rows.length + 3) * 20}px`;
                holder.__range = [start, end];
                container.appendChild(holder);
                io.observe(holder);
            } else {
                container.appendChild(renderBlock(start, end, refMap, hitsByRow));
            }
        }
    }

    function openExport(event, menu) {
        const fasta = state.rows.map(r => `>${r.name}\n${r.seq}\n`).join("");
        const consensus = `>consensus\n${metrics.consensus.join("").toUpperCase()}\n`;
        const ungapped = state.rows.map(r => `>${r.name}\n${r.seq.replace(/[-.]/g, "")}\n`).join("");
        const csv = ["name,residues,gaps,aligned,identity_pct,similarity_pct"]
            .concat(metrics.table.map(t => [
                `"${t.name.replace(/"/g, "'")}"`, t.residues, t.gaps, t.aligned,
                (t.identity * 100).toFixed(1), (t.similarity * 100).toFixed(1),
            ].join(","))).join("\n") + "\n";
        const items = [
            ["Aligned FASTA", () => download("alignment.fasta", fasta)],
            ["Ungapped FASTA", () => download("sequences.fasta", ungapped)],
            ["Consensus FASTA", () => download("consensus.fasta", consensus)],
            ["Identity table (CSV)", () => download("alignment_identity.csv", csv, "text/csv")],
        ];

        menu.replaceChildren(...items.map(([label, run]) => {
            const b = el("button", "mrp-menu-item", label);

            b.type = "button";
            b.addEventListener("click", () => {
                run();
                menu.hidden = true;
            });

            return b;
        }));
        menu.hidden = !menu.hidden;
        event.stopPropagation();
    }

    function selectField(label, options, value, onChange) {
        const wrap = el("label", "mpro-field");
        const sel = document.createElement("select");

        sel.className = "mrp-select";
        options.forEach(([v, t]) => sel.appendChild(new Option(t, v)));
        sel.value = value;
        sel.addEventListener("change", () => onChange(sel.value));
        wrap.append(el("span", "", label), sel);

        return wrap;
    }

    function checkField(label, value, onChange) {
        const wrap = el("label", "mpro-check");
        const input = document.createElement("input");

        input.type = "checkbox";
        input.checked = value;
        input.addEventListener("change", () => onChange(input.checked));
        wrap.append(input, document.createTextNode(" " + label));

        return wrap;
    }


    // ---- column selection, trim, annotate ----------------------------------
    function selectionInfo() {
        if (!state.sel) return null;

        const a = Math.min(state.sel.a, state.sel.b);
        const b = Math.max(state.sel.a, state.sel.b);
        const map = ungappedIndex(state.rows[state.ref].seq);
        let lo = 0;
        let hi = 0;

        for (let c = a; c <= b; c += 1) {
            if (map[c]) {
                if (!lo) lo = map[c];
                hi = map[c];
            }
        }

        return {a, b, n: b - a + 1, lo, hi};
    }

    function paintColumns() {
        if (!proRoot) return;

        const a = state.sel ? Math.min(state.sel.a, state.sel.b) : -1;
        const b = state.sel ? Math.max(state.sel.a, state.sel.b) : -2;

        proRoot.querySelectorAll(".mpro-c[data-c]").forEach(n => {
            const c = Number(n.dataset.c);
            const on = c >= a && c <= b;

            if (on !== n.classList.contains("is-colsel")) n.classList.toggle("is-colsel", on);
        });
    }

    function trimTo(a, b) {
        const ref = state.rows[state.ref].seq;
        let before = 0;

        for (let c = 0; c < a; c += 1) if (!isGap(ref[c])) before += 1;

        state.base += before;
        state.rows = state.rows.map(r => ({name: r.name, seq: r.seq.slice(a, b + 1)}));
        state.len = b - a + 1;
        state.sel = null;
        render();
    }

    function restoreFull() {
        if (!state.orig) return;

        state.rows = state.orig.rows.map(r => ({...r}));
        state.len = state.orig.len;
        state.base = 0;
        state.sel = null;
        render();
    }

    function sliceFasta(a, b) {
        return state.rows.map(r => `>${r.name}\n${r.seq.slice(a, b + 1)}\n`).join("");
    }

    function actionBar() {
        const bar = el("div", "mpro-actions");
        const info = selectionInfo();
        const trimmed = Boolean(state.orig) && (state.len !== state.orig.len || state.base > 0);

        bar.hidden = !info && !trimmed;

        if (info) {
            bar.appendChild(el("strong", "mpro-actions-title",
                `Columns ${info.a + 1}–${info.b + 1} (${info.n})` + (info.lo ? ` · reference ${info.lo}–${info.hi}` : " · gaps in the reference")));

            const api = window.BiobankMolecularWorkspace;
            const small = (label, title, run, disabled) => {
                const b = el("button", "mrp-btn mrp-btn-sm", label);

                b.type = "button";
                b.title = title;
                b.disabled = Boolean(disabled);
                b.addEventListener("click", run);
                bar.appendChild(b);

                return b;
            };

            small("Select in protein", "Select these reference residues in the sequence and the 3D structure", () => {
                if (api && api.selectSequenceRange) api.selectSequenceRange(info.lo, info.hi);
            }, !info.lo);

            const name = document.createElement("input");

            name.className = "mrp-select mpro-annot-name";
            name.placeholder = "Annotation name";
            name.value = `Alignment ${info.a + 1}-${info.b + 1}`;
            name.setAttribute("aria-label", "Annotation name");

            const types = document.createElement("select");

            types.className = "mrp-select";
            types.setAttribute("aria-label", "Annotation type");
            (api && api.featureTypes ? api.featureTypes() : [{value: "custom", label: "Custom"}])
                .forEach(t => types.appendChild(new Option(t.label, t.value)));
            const preferred = [...types.options].find(o => /domain/i.test(o.textContent)) || [...types.options].find(o => o.value === "custom");

            if (preferred) types.value = preferred.value;

            const canEdit = Boolean(api && api.getSnapshot && api.getSnapshot().canEdit);

            bar.append(name, types);

            const add = small("Add annotation", "Create a feature on the reference residues of this selection", () => {
                api.selectSequenceRange(info.lo, info.hi);

                const made = api.createFeatureFromSelection({name: name.value.trim() || "Alignment region", type: types.value});

                add.textContent = made === null ? "Cannot add here" : "Annotation added (unsaved)";
            }, !info.lo || !canEdit);

            small("Trim to selection", "Keep only these columns in the view and in the exports", () => trimTo(info.a, info.b));
            small("Export selection", "Download the selected columns as aligned FASTA", () => download(`alignment_${info.a + 1}-${info.b + 1}.fasta`, sliceFasta(info.a, info.b)));
            small("Clear", "Clear the column selection", () => {
                state.sel = null;
                paintColumns();
                actionBar.refresh();
            });
        }

        if (trimmed) {
            const b = el("button", "mrp-btn mrp-btn-sm", "Restore full alignment");

            b.type = "button";
            b.addEventListener("click", restoreFull);
            bar.appendChild(b);
            bar.appendChild(el("span", "mpro-actions-note", `Showing ${state.len} of ${state.orig.len} columns`));
        }

        return bar;
    }
    actionBar.refresh = () => {
        if (!proRoot) return;

        const old = proRoot.querySelector(".mpro-actions");
        const next = actionBar();

        if (old) old.replaceWith(next);
    };

    function render() {
        if (!proRoot || !state.rows.length) return;

        compute();
        proRoot.replaceChildren();

        const refName = state.rows[state.ref].name;
        const tiles = el("div", "mpro-summary");
        const chip = (label, value, hint) => {
            const c = el("span", "mpro-chip");

            c.append(el("em", "", label), el("strong", "", String(value)));
            if (hint) c.title = hint;

            return c;
        };

        tiles.append(
            chip("Sequences", state.rows.length),
            chip("Columns", state.len),
            chip("Identical", `${Math.round((metrics.fully / state.len) * 100)}%`,
                `${metrics.fully} columns with the same residue in every sequence`),
            chip("Mean identity", `${Math.round(metrics.meanIdentity * 100)}%`, `Against ${refName}`),
            chip("Gaps", `${Math.round(metrics.gapFraction * 100)}%`),
            chip("Reference", refName, "Click a sequence name to change it"),
        );

        const bar = el("div", "mpro-controls");

        bar.append(
            selectField("Colour", [
                ["clustal", "Clustal"], ["hydro", "Hydrophobicity"], ["charge", "Charge"],
                ["identity", "Identity to reference"], ["conservation", "Conservation"], ["none", "None"],
            ], state.scheme, v => {
                state.scheme = v;
                render();
            }),
            selectField("Columns / row", [["auto", "Fit width"], ["40", "40"], ["60", "60"], ["80", "80"], ["120", "120"]],
                state.width, v => {
                    state.width = v;
                    render();
                }),
            checkField("Conservation", state.showBar, v => {
                state.showBar = v;
                render();
            }),
            checkField("Consensus", state.showCons, v => {
                state.showCons = v;
                render();
            }),
        );

        const motif = document.createElement("input");

        motif.className = "mrp-select mpro-motif";
        motif.placeholder = "Motif (regex), e.g. G.G..G";
        motif.value = state.motif;
        motif.addEventListener("change", () => {
            state.motif = motif.value.trim();
            render();
        });

        const hitInfo = el("span", "mpro-hit-info");

        if (state.motif) {
            const n = state.rows.reduce((s, r) => s + motifColumns(r.seq).size, 0);

            hitInfo.textContent = n ? `${n} residues highlighted` : "No match";
        }

        const jump = document.createElement("input");

        jump.className = "mrp-select mpro-jump";
        jump.placeholder = "Go to position";
        jump.type = "number";
        jump.min = "1";
        jump.addEventListener("change", () => {
            const pos = Number(jump.value);
            const col = ungappedIndex(state.rows[state.ref].seq).findIndex(v => v === pos);

            if (col < 0) return;

            const cell = proRoot.querySelector(`.mpro-line.is-ref .mpro-c[data-c="${col}"]`);

            if (cell) {
                cell.scrollIntoView({block: "center", inline: "center", behavior: "smooth"});
                cell.classList.add("is-flash");
                setTimeout(() => cell.classList.remove("is-flash"), 1400);
            }

            selectRef(pos);
        });

        const exportWrap = el("div", "mrp-export");
        const exportBtn = el("button", "mrp-btn", "Export ▾");
        const menu = el("div", "mrp-menu");

        exportBtn.type = "button";
        menu.hidden = true;
        exportBtn.addEventListener("click", ev => openExport(ev, menu));
        exportWrap.append(exportBtn, menu);
        document.addEventListener("click", () => {
            menu.hidden = true;
        });

        bar.append(motif, hitInfo, jump, exportWrap);

        const table = el("details", "mpro-table");
        const tbl = el("table", "mrp-table");
        const head = el("tr");

        ["Sequence", "Residues", "Gaps", "Aligned", "Identity", "Similarity"].forEach(h => head.appendChild(el("th", "", h)));
        tbl.appendChild(el("thead")).appendChild(head);

        const tb = el("tbody");

        metrics.table.forEach((t, i) => {
            const tr = el("tr");

            if (i === state.ref) tr.classList.add("is-ref");

            [t.name, t.residues, t.gaps, t.aligned, `${(t.identity * 100).toFixed(1)}%`, `${(t.similarity * 100).toFixed(1)}%`]
                .forEach(v => tr.appendChild(el("td", "", String(v))));
            tr.addEventListener("click", () => {
                state.ref = i;
                render();
            });
            tb.appendChild(tr);
        });
        tbl.appendChild(tb);

        const tw = el("div", "mrp-table-wrap");

        tw.appendChild(tbl);
        table.append(el("summary", "", "Identity to reference (click a row to change the reference)"), tw);

        const view = el("div", "mpro-view");
        const tip = el("div", "mrp-tip", "Click a residue to select it in the protein; drag across columns to select a region to annotate, trim or export. Click a sequence name to make it the reference.");

        let dragStart = null;
        let moved = false;
        let frame = 0;

        view.addEventListener("mousedown", ev => {
            const c = ev.target.closest(".mpro-c[data-c]");

            if (!c || ev.button !== 0) return;

            dragStart = Number(c.dataset.c);
            moved = false;
            ev.preventDefault();
        });
        view.addEventListener("mouseover", ev => {
            if (dragStart === null) return;

            const c = ev.target.closest(".mpro-c[data-c]");

            if (!c) return;

            const col = Number(c.dataset.c);

            if (col !== dragStart) moved = true;

            state.sel = {a: dragStart, b: col};
            if (!frame) {
                frame = requestAnimationFrame(() => {
                    frame = 0;
                    paintColumns();
                });
            }
        });
        document.addEventListener("mouseup", () => {
            if (dragStart === null) return;

            if (moved) actionBar.refresh();
            dragStart = null;
        });
        view.addEventListener("mouseover", ev => {
            const c = ev.target.closest(".mpro-c[data-c][data-r]");

            if (!c) return;

            const col = Number(c.dataset.c);
            const row = state.rows[Number(c.dataset.r)];
            const refPos = ungappedIndex(state.rows[state.ref].seq)[col];

            tip.textContent = `${row.name} · column ${col + 1} · ${c.textContent}`
                + (refPos ? ` · reference position ${refPos}` : "")
                + ` · conservation ${Math.round(metrics.cons[col] * 100)}%`;
        });
        view.addEventListener("click", ev => {
            const c = ev.target.closest(".mpro-c[data-c]");

            if (!c || moved) {
                moved = false;

                return;
            }

            const col = Number(c.dataset.c);

            state.sel = {a: col, b: col};
            paintColumns();
            actionBar.refresh();

            if (c.dataset.r !== undefined) selectRef(ungappedIndex(state.rows[state.ref].seq)[col]);
        });

        proRoot.append(tiles, bar, tip, actionBar(), view, table);
        renderView(view);
    }

    // ---- data --------------------------------------------------------------
    function activeKey(host) {
        const legacy = host.querySelector(".mpa-text-msa");
        const active = host.querySelector(".mpa-list-item.is-active");

        return legacy ? `${legacy.dataset.sequenceCount}:${legacy.dataset.alignmentLength}:${(active && active.textContent) || ""}` : "";
    }

    async function fetchActive(host) {
        const items = host.querySelectorAll(".mpa-list-item");
        let index = -1;

        items.forEach((node, i) => {
            if (node.classList.contains("is-active")) index = i;
        });

        if (index < 0) return null;

        const opts = {credentials: "same-origin", headers: {Accept: "application/json"}};
        const listing = await (await fetch(apiUrl, opts)).json();
        const item = (listing.alignments || [])[index];

        if (!item) return null;

        const detail = await (await fetch(`${apiUrl}?alignment_id=${item.id}`, opts)).json();

        return detail.alignment || null;
    }

    let busy = false;

    async function sync(host) {
        shell = host.querySelector(".mpa-viewer-shell");

        if (!shell) return;

        const key = activeKey(host);

        if (!key) {
            // Touch the DOM only when there is something to undo: even a
            // no-op classList.remove() rewrites the attribute, which this
            // layer's own MutationObserver would see again (endless loop).
            if (proRoot || shell.classList.contains("is-pro")) {
                shell.classList.remove("is-pro");
                shell.querySelectorAll(".mpro-root").forEach(n => n.remove());
                proRoot = null;
                state.key = "";
            }

            return;
        }

        if (key === state.key && proRoot && shell.contains(proRoot)) return;

        if (busy) return;

        busy = true;

        try {
            const payload = await fetchActive(host);

            if (!payload || !Array.isArray(payload.rows) || !payload.rows.length) return;

            state.key = key;
            state.payload = payload;
            state.rows = payload.rows.map(r => ({
                name: String(r.name || "sequence"), seq: String(r.sequence || "").toUpperCase(),
            }));
            state.len = Math.max(Number(payload.alignment_length) || 0, ...state.rows.map(r => r.seq.length));
            state.ref = Math.min(
                state.rows.length - 1,
                Math.max(0, payload.query_match && Number.isInteger(payload.query_match.index) ? payload.query_match.index : 0),
            );
            state.id = payload.id;
            state.sel = null;
            state.base = 0;
            state.orig = {rows: state.rows.map(r => ({...r})), len: state.len};

            shell.classList.add("is-pro");
            shell.querySelectorAll(".mpro-root").forEach(n => n.remove());
            proRoot = el("div", "mpro-root");
            shell.appendChild(proRoot);
            render();
        } catch (error) {
            console.error("Alignment viewer failed", error);
        } finally {
            busy = false;
        }
    }

    function start() {
        const host = document.getElementById("mw-protein-alignment");

        if (!host) return;

        // Debounced: never re-enter synchronously from our own DOM changes.
        let queued = false;

        new MutationObserver(() => {
            if (queued) return;

            queued = true;
            setTimeout(() => {
                queued = false;
                sync(host);
            }, 60);
        }).observe(host, {
            subtree: true, childList: true, attributes: true, attributeFilter: ["class"],
        });
        sync(host);
    }

    root.addEventListener("biobank:molecular-workspace-change", () => {
        if (!proRoot || !state.rows.length) return;

        const sel = workspaceSelection();
        const map = ungappedIndex(state.rows[state.ref].seq);

        proRoot.querySelectorAll(".mpro-c.is-sel").forEach(n => n.classList.remove("is-sel"));

        if (!sel) return;

        proRoot.querySelectorAll(".mpro-c[data-c]").forEach(n => {
            const pos = map[Number(n.dataset.c)];

            if (pos && pos >= sel.start && pos <= sel.end) n.classList.add("is-sel");
        });
    });

    let resizeTimer = null;

    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (proRoot && state.width === "auto" && proRoot.clientWidth) render();
        }, 200);
    });

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})();
