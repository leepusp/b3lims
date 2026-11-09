/*
 * Molecular sequence canvas: the sequence view as one editor.
 *
 * Drawn on a <canvas> so that long records stay fast. It shows the ruler,
 * the annotations (clickable), the sequence, its complement and the
 * translation of every CDS. The caret, the selection and typing work like in
 * a text editor, and every edit goes through window.BiobankMolecularWorkspace
 * (replaceRange / undo / redo), which moves the annotations with the text.
 *
 * Ctrl (or Cmd) + scroll zooms around the pointer; plain scroll moves
 * through the rows. The map canvas, Tracks and the inspector follow the
 * selection through the workspace change event.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("msc");

    if (!root || !host) {
        return;
    }

    const LEFT = 62;
    const RIGHT = 14;
    const RULER = 18;
    const LANE = 19;
    const TRANS = 17;
    const GAP = 20;
    const DEFAULT_CHAR = 12;
    const MIN_CHAR = 4;
    const MAX_CHAR = 34;
    const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';
    const BASE_COLOR = {A: "#2B8A3E", T: "#C92A2A", U: "#C92A2A", G: "#E67700", C: "#1971C2"};
    const COMPLEMENT = {A: "T", T: "A", U: "A", G: "C", C: "G", R: "Y", Y: "R", K: "M", M: "K", B: "V", V: "B", D: "H", H: "D", S: "S", W: "W", N: "N"};
    const NUCLEOTIDE_KEYS = /^[ACGTUNRYKMSWBDHV]$/i;
    const CODONS = (() => {
        const bases = "TCAG";
        const aa = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG";
        const table = {};
        let i = 0;

        for (const a of bases) for (const b of bases) for (const c of bases) table[a + b + c] = aa[i++];

        return table;
    })();

    const st = {
        active: false,
        charW: DEFAULT_CHAR,
        showComp: true,
        showTrans: true,
        caret: 0,
        selA: 0,
        selB: 0,
        pending: false,
        pendingTimer: 0,
        drag: null,
        hover: -1,
        layout: null,
        layoutKey: "",
        frame: 0,
        lastFeature: -2,
        focused: false,
        query: "",
        matches: [],
        matchAt: -1,
    };

    const api = () => window.BiobankMolecularWorkspace || null;
    const snap = () => (api() ? api().getSnapshot() : null);
    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    /* ---------- DOM ---------- */

    host.textContent = "";

    const bar = el("div", "msc-bar");
    const undoBtn = el("button", "msc-btn", "Undo");
    const redoBtn = el("button", "msc-btn", "Redo");
    const compLabel = el("label", "msc-check");
    const compInput = document.createElement("input");
    const transLabel = el("label", "msc-check");
    const transInput = document.createElement("input");
    const find = document.createElement("input");
    const found = el("span", "msc-found");
    const info = el("span", "msc-info");
    const viewport = el("div", "msc-viewport");
    const inner = el("div", "msc-inner");
    const canvas = el("canvas", "msc-canvas");
    const tip = el("div", "msc-tip");
    const hint = el("div", "msc-hint", "Click to place the cursor · drag to select · type to edit · Ctrl + scroll to zoom");

    undoBtn.type = redoBtn.type = "button";
    undoBtn.title = "Undo (Ctrl+Z)";
    redoBtn.title = "Redo (Ctrl+Shift+Z)";
    compInput.type = transInput.type = "checkbox";
    compInput.checked = true;
    transInput.checked = true;
    compLabel.append(compInput, document.createTextNode(" Complement"));
    transLabel.append(transInput, document.createTextNode(" Translations"));
    find.type = "search";
    find.className = "msc-find";
    find.placeholder = "Find motif (Enter = next)";
    find.setAttribute("aria-label", "Find a sequence motif on both strands");
    bar.append(undoBtn, redoBtn, compLabel, transLabel, find, found, info);
    inner.append(canvas);
    viewport.append(inner);
    viewport.tabIndex = 0;
    tip.hidden = true;
    host.append(bar, viewport, tip, hint);

    const ctx = canvas.getContext("2d");

    /* ---------- layout ---------- */

    function segmentsOf(features, length, circular) {
        const out = [];

        features.forEach((feature, index) => {
            const start = clamp(feature.start - 1, 0, length);
            const end = clamp(feature.end, 0, length);

            if (feature.start > feature.end && circular) {
                out.push({f: index, a: start, b: length, tipEnd: false, tipStart: false});
                out.push({f: index, a: 0, b: end, tipEnd: true, tipStart: false});
            } else if (end > start) {
                out.push({f: index, a: start, b: end, tipEnd: true, tipStart: true});
            }
        });

        return out;
    }

    function translationOf(sequence, feature) {
        const start = feature.start - 1;
        const end = feature.end;
        const out = [];

        if (feature.start > feature.end || end - start < 3) return out;

        if (feature.strand === "-") {
            for (let i = end - 3; i >= start; i -= 3) {
                const codon = sequence.slice(i, i + 3).split("").reverse().map(b => COMPLEMENT[b] || "N").join("");

                out.push({mid: i + 1, aa: CODONS[codon] || "X"});
            }
        } else {
            for (let i = start; i + 3 <= end; i += 3) {
                out.push({mid: i + 1, aa: CODONS[sequence.slice(i, i + 3)] || "X"});
            }
        }

        return out;
    }

    function buildLayout(s, width) {
        const length = s.sequence.length;
        const circular = s.topology === "circular";
        const avail = Math.max(120, width - LEFT - RIGHT);
        let bpr = Math.floor(avail / st.charW);

        bpr = bpr >= 20 ? Math.floor(bpr / 10) * 10 : Math.max(5, bpr);

        const rows = Math.max(1, Math.ceil(length / bpr));
        const lineH = Math.max(20, Math.round(st.charW * 1.7));
        const perRow = Array.from({length: rows}, () => []);
        const transRow = Array.from({length: rows}, () => []);
        const canTrans = st.showTrans && st.charW >= 9 && s.sequenceType !== "protein";

        segmentsOf(s.features, length, circular).forEach(seg => {
            for (let r = Math.floor(seg.a / bpr); r <= Math.floor((seg.b - 1) / bpr) && r < rows; r += 1) {
                perRow[r].push({
                    f: seg.f,
                    a: Math.max(seg.a, r * bpr),
                    b: Math.min(seg.b, (r + 1) * bpr),
                    tipStart: seg.tipStart && seg.a >= r * bpr,
                    tipEnd: seg.tipEnd && seg.b <= (r + 1) * bpr,
                });
            }
        });

        if (canTrans) {
            s.features.forEach((feature, index) => {
                if (feature.type !== "cds") return;

                translationOf(s.sequence, feature).forEach(codon => {
                    const r = Math.floor((codon.mid - 1) / bpr);

                    if (r >= 0 && r < rows) transRow[r].push({...codon, f: index});
                });
            });
        }

        const list = [];
        let y = 0;

        for (let r = 0; r < rows; r += 1) {
            const segs = perRow[r].sort((p, q) => p.a - q.a || q.b - p.b);
            const laneEnds = [];

            segs.forEach(seg => {
                let lane = laneEnds.findIndex(end => end <= seg.a);

                if (lane < 0) {
                    lane = laneEnds.length;
                    laneEnds.push(0);
                }

                laneEnds[lane] = seg.b;
                seg.lane = lane;
            });

            const cdsOrder = [...new Set(transRow[r].map(c => c.f))].sort((p, q) => p - q);

            transRow[r].forEach(codon => {
                codon.lane = cdsOrder.indexOf(codon.f);
            });

            const lanes = laneEnds.length;
            const transLanes = cdsOrder.length;
            const laneTop = 6 + RULER;
            const seqTop = laneTop + (lanes ? lanes * LANE + 4 : 2);
            const compTop = seqTop + lineH;
            const transTop = compTop + (st.showComp ? lineH - 2 : 0) + 2;
            const height = transTop + transLanes * TRANS + GAP;

            list.push({
                r, y, h: height, start: r * bpr, end: Math.min(length, (r + 1) * bpr),
                segs, trans: transRow[r], lanes, transLanes, laneTop, seqTop, compTop, transTop, lineH,
            });
            y += height;
        }

        return {rows: list, bpr, total: y + 8, length, circular};
    }

    function layoutFor(s) {
        const width = Math.max(320, viewport.clientWidth);
        const key = [
            s.sequence.length, s.sequence.slice(0, 40), s.sequence.slice(-40), s.topology, width, st.charW,
            st.showComp, st.showTrans,
            s.features.map(f => [f.start, f.end, f.strand, f.type].join(":")).join("|"),
        ].join("/");

        if (key !== st.layoutKey || !st.layout) {
            st.layout = buildLayout(s, width);
            st.layoutKey = key;
            inner.style.height = st.layout.total + "px";
        }

        return st.layout;
    }

    function rowAt(layout, y) {
        let lo = 0;
        let hi = layout.rows.length - 1;

        while (lo < hi) {
            const mid = (lo + hi + 1) >> 1;

            if (layout.rows[mid].y <= y) lo = mid;
            else hi = mid - 1;
        }

        return layout.rows[lo];
    }

    const rowOfIndex = (layout, index) => layout.rows[clamp(Math.floor(index / layout.bpr), 0, layout.rows.length - 1)];

    /* ---------- find ---------- */

    const IUPAC = {A: "A", C: "C", G: "G", T: "T", U: "T", R: "[AG]", Y: "[CT]", K: "[GT]", M: "[AC]", S: "[CG]", W: "[AT]", B: "[CGT]", D: "[AGT]", H: "[ACT]", V: "[ACG]", N: "[ACGT]"};

    function reverseComplement(text) {
        return text.split("").reverse().map(base => COMPLEMENT[base] || base).join("");
    }

    function findMatches(sequence, motif, protein) {
        const query = motif.toUpperCase().replace(/\s+/g, "");

        if (!query) return [];

        const out = [];
        const scan = (text, strand) => {
            const pattern = protein
                ? text.replace(/[^A-Z*]/g, "")
                : text.split("").map(base => IUPAC[base] || "").join("");

            if (!pattern) return;

            const regex = new RegExp("(?=(" + pattern + "))", "g");
            let hit;

            while ((hit = regex.exec(sequence)) !== null) {
                out.push({a: hit.index, b: hit.index + hit[1].length, strand});
                regex.lastIndex = hit.index + 1;
            }
        };

        scan(query, "+");

        if (!protein) {
            const reverse = reverseComplement(query);

            if (reverse !== query) scan(reverse, "-");
        }

        return out.sort((p, q) => p.a - q.a);
    }

    function refreshMatches() {
        const s = snap();

        st.matchedLength = s ? s.sequence.length : 0;
        st.matches = s && st.query ? findMatches(s.sequence, st.query, s.sequenceType === "protein") : [];
        st.matchAt = -1;
        found.textContent = st.query
            ? (st.matches.length ? st.matches.length.toLocaleString() + " match" + (st.matches.length === 1 ? "" : "es") : "No match")
            : "";
        schedule();
    }

    function gotoMatch(step) {
        if (!st.matches.length) return;

        const here = Math.min(st.selA, st.selB);
        let next = st.matchAt >= 0 ? st.matchAt + step : st.matches.findIndex(m => m.a >= here + (step > 0 ? 1 : 0));

        if (step < 0 && st.matchAt < 0) next = st.matches.length - 1;

        next = ((next % st.matches.length) + st.matches.length) % st.matches.length;
        st.matchAt = next;

        const match = st.matches[next];

        st.selA = match.a;
        st.selB = st.caret = match.b;
        publishNow();
        reveal(match.a, "centre");
        found.textContent = (next + 1) + " of " + st.matches.length.toLocaleString();
        schedule();
    }

    /* ---------- drawing ---------- */

    function selectedRanges(s) {
        const a = Math.min(st.selA, st.selB);
        const b = Math.max(st.selA, st.selB);
        const out = [];

        if (b > a) {
            out.push([a, b]);
        } else if (s.sequenceSelection && st.pending === false && s.sequenceSelection.start > s.sequenceSelection.end) {
            out.push([s.sequenceSelection.start - 1, s.sequence.length], [0, s.sequenceSelection.end]);
        }

        return out;
    }

    function draw() {
        st.frame = 0;

        if (!st.active) return;

        const s = snap();

        if (!s || !s.sequence) return;

        const layout = layoutFor(s);
        const w = viewport.clientWidth;
        const h = viewport.clientHeight;
        const dpr = window.devicePixelRatio || 1;

        if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
            canvas.width = Math.round(w * dpr);
            canvas.height = Math.round(h * dpr);
            canvas.style.width = w + "px";
            canvas.style.height = h + "px";
        }

        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);

        const top = viewport.scrollTop;
        const charW = st.charW;
        const fontPx = Math.max(8, Math.round(charW * 1.12));
        const ranges = selectedRanges(s);
        const first = rowAt(layout, top).r;
        const x = i => LEFT + i * charW;

        ctx.textBaseline = "middle";

        for (let r = first; r < layout.rows.length; r += 1) {
            const row = layout.rows[r];

            if (row.y - top > h) break;

            const oy = row.y - top;
            const count = row.end - row.start;

            ctx.fillStyle = "#EEF1F5";
            ctx.fillRect(LEFT, oy + 6 + RULER - 2, count * charW, 1);

            // selection background behind the letters
            ranges.forEach(([a, b]) => {
                const from = Math.max(a, row.start);
                const to = Math.min(b, row.end);

                if (to > from) {
                    ctx.fillStyle = "rgba(29,78,216,.16)";
                    ctx.fillRect(x(from - row.start), oy + row.seqTop - 1, (to - from) * charW, row.lineH * (st.showComp ? 2 : 1) - 1);
                    ctx.fillStyle = "rgba(29,78,216,.08)";
                    ctx.fillRect(x(from - row.start), oy + 6, (to - from) * charW, RULER + (row.lanes ? row.lanes * LANE + 4 : 2));
                }
            });

            // row label and ruler ticks
            ctx.font = "11px " + MONO;
            ctx.textAlign = "right";
            ctx.fillStyle = "#8795A6";
            ctx.fillText(String(row.start + 1), LEFT - 10, oy + row.seqTop + row.lineH / 2);
            ctx.textAlign = "center";

            for (let i = row.start; i < row.end; i += 1) {
                const pos = i + 1;

                if (pos % 10 === 0 || (charW >= 14 && pos % 5 === 0)) {
                    const major = pos % 10 === 0;

                    ctx.fillStyle = major ? "#6B7A8C" : "#B6C0CC";
                    ctx.fillRect(x(i - row.start) + charW / 2 - 0.5, oy + 6 + RULER - (major ? 6 : 4), 1, major ? 6 : 4);

                    if (major) ctx.fillText(String(pos), x(i - row.start) + charW / 2, oy + 6 + 5);
                }
            }

            // annotations
            row.segs.forEach(seg => {
                const feature = s.features[seg.f];
                const x0 = x(seg.a - row.start);
                const x1 = x(seg.b - row.start);
                const y0 = oy + row.laneTop + seg.lane * LANE;
                const tip = Math.min(7, (x1 - x0) / 2);
                const forward = feature.strand !== "-";
                const selected = s.selectedFeature === seg.f;

                ctx.beginPath();

                if (feature.strand === "." || (!seg.tipEnd && forward) || (!seg.tipStart && !forward)) {
                    ctx.rect(x0, y0, x1 - x0, LANE - 5);
                } else if (forward) {
                    ctx.moveTo(x0, y0);
                    ctx.lineTo(x1 - tip, y0);
                    ctx.lineTo(x1, y0 + (LANE - 5) / 2);
                    ctx.lineTo(x1 - tip, y0 + LANE - 5);
                    ctx.lineTo(x0, y0 + LANE - 5);
                } else {
                    ctx.moveTo(x1, y0);
                    ctx.lineTo(x0 + tip, y0);
                    ctx.lineTo(x0, y0 + (LANE - 5) / 2);
                    ctx.lineTo(x0 + tip, y0 + LANE - 5);
                    ctx.lineTo(x1, y0 + LANE - 5);
                }

                ctx.closePath();
                ctx.fillStyle = feature.color || "#868E96";
                ctx.globalAlpha = st.hover === seg.f ? 0.82 : 1;
                ctx.fill();
                ctx.globalAlpha = 1;

                if (selected) {
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = "#1B2733";
                    ctx.stroke();
                }

                ctx.font = "600 11px system-ui, sans-serif";

                if (ctx.measureText(feature.name).width + 10 < x1 - x0) {
                    ctx.fillStyle = "#fff";
                    ctx.fillText(feature.name, (x0 + x1) / 2 - (forward ? 2 : -2), y0 + (LANE - 5) / 2 + 0.5);
                }
            });

            // motif matches
            if (st.matches.length) {
                st.matches.forEach((match, index) => {
                    const from = Math.max(match.a, row.start);
                    const to = Math.min(match.b, row.end);

                    if (to > from) {
                        ctx.fillStyle = index === st.matchAt ? "rgba(255,193,7,.75)" : "rgba(255,224,102,.55)";
                        ctx.fillRect(x(from - row.start), oy + row.seqTop, (to - from) * charW, row.lineH - 2);
                    }
                });
            }

            // sequence and complement
            ctx.font = fontPx + "px " + MONO;

            for (let i = row.start; i < row.end; i += 1) {
                const base = s.sequence[i];
                const cx = x(i - row.start) + charW / 2;

                if (charW < 6.5) {
                    ctx.fillStyle = BASE_COLOR[base] || "#868E96";
                    ctx.fillRect(cx - charW / 2 + 0.5, oy + row.seqTop + 3, charW - 1, row.lineH - 8);
                } else {
                    ctx.fillStyle = s.sequenceType === "protein" ? "#1B2733" : (BASE_COLOR[base] || "#566474");
                    ctx.fillText(base, cx, oy + row.seqTop + row.lineH / 2);
                }

                if (st.showComp && s.sequenceType !== "protein") {
                    if (charW < 6.5) {
                        ctx.fillStyle = "#DDE3EA";
                        ctx.fillRect(cx - charW / 2 + 0.5, oy + row.compTop + 3, charW - 1, row.lineH - 8);
                    } else {
                        ctx.fillStyle = "#AEB9C6";
                        ctx.fillText(COMPLEMENT[base] || "N", cx, oy + row.compTop + row.lineH / 2 - 1);
                    }
                }
            }

            // translations of CDS features
            ctx.font = "600 " + Math.max(9, Math.round(charW * 0.9)) + "px " + MONO;

            row.trans.forEach(codon => {
                const cx = x(codon.mid - 1 - row.start) + charW / 2;
                const y0 = oy + row.transTop + codon.lane * TRANS;

                ctx.fillStyle = codon.aa === "*" ? "#F8D7DA" : (s.features[codon.f].color || "#868E96") + "33";
                ctx.fillRect(cx - charW * 1.5 + 1, y0, charW * 3 - 2, TRANS - 3);
                ctx.fillStyle = codon.aa === "*" ? "#B02A37" : "#1B2733";
                ctx.fillText(codon.aa, cx, y0 + (TRANS - 3) / 2 + 0.5);
            });

            // caret
            if (st.focused && st.selA === st.selB) {
                const at = st.caret;
                const inRow = at >= row.start && (at < row.end || (at === row.end && r === layout.rows.length - 1));

                if (inRow) {
                    ctx.fillStyle = "#1D4ED8";
                    ctx.fillRect(x(at - row.start) - 1, oy + row.seqTop, 2, row.lineH * (st.showComp ? 2 : 1) - 2);
                }
            }
        }

        updateChrome(s);
    }

    function schedule() {
        if (!st.frame) {
            st.frame = window.requestAnimationFrame(draw);
        }
    }

    function updateChrome(s) {
        const a = Math.min(st.selA, st.selB);
        const b = Math.max(st.selA, st.selB);
        const unit = s.sequenceType === "protein" ? "aa" : "bp";
        const history = api() && api().history ? api().history() : {undo: 0, redo: 0};

        info.textContent = b > a
            ? "Selected " + (a + 1) + "–" + b + " · " + (b - a).toLocaleString() + " " + unit
            : "Cursor after " + st.caret.toLocaleString() + " of " + s.sequence.length.toLocaleString() + " " + unit;
        undoBtn.disabled = !s.canEdit || !history.undo;
        redoBtn.disabled = !s.canEdit || !history.redo;
        undoBtn.hidden = redoBtn.hidden = !s.canEdit;
        hint.textContent = s.canEdit
            ? "Click to place the cursor · drag to select · type to edit · Ctrl + scroll to zoom"
            : "Click to place the cursor · drag to select · Ctrl + scroll to zoom · this record is read only";
    }

    /* ---------- geometry and hits ---------- */

    function local(event) {
        const rect = viewport.getBoundingClientRect();

        return {x: event.clientX - rect.left, y: event.clientY - rect.top + viewport.scrollTop, cy: event.clientY - rect.top};
    }

    function boundaryAt(layout, point) {
        const row = rowAt(layout, point.y);
        const offset = Math.round((point.x - LEFT) / st.charW);

        return row.start + clamp(offset, 0, row.end - row.start);
    }

    function featureAt(layout, point) {
        const row = rowAt(layout, point.y);
        const rel = point.y - row.y - row.laneTop;
        const lane = Math.floor(rel / LANE);

        if (!row.lanes || lane < 0 || lane >= row.lanes) return -1;

        const index = row.start + Math.floor((point.x - LEFT) / st.charW);
        const seg = row.segs.find(item => item.lane === lane && index >= item.a && index < item.b);

        return seg ? seg.f : -1;
    }

    function reveal(index, mode) {
        const s = snap();

        if (!s || !st.layout) return;

        const row = rowOfIndex(layoutFor(s), index);
        const top = viewport.scrollTop;
        const bottom = top + viewport.clientHeight;

        if (mode === "centre" || row.y < top || row.y + row.h > bottom) {
            viewport.scrollTop = Math.max(0, row.y - viewport.clientHeight / 3);
        }
    }

    /* ---------- selection ---------- */

    function publishNow() {
        window.clearTimeout(st.pendingTimer);
        st.pending = false;

        const a = Math.min(st.selA, st.selB);
        const b = Math.max(st.selA, st.selB);
        const workspace = api();

        if (!workspace) return;

        if (b > a) workspace.selectSequenceRange(a + 1, b, {source: "seqcanvas"});
        else if (workspace.getSnapshot().sequenceSelection) workspace.clearSelection();
    }

    function publishSoon() {
        st.pending = true;
        window.clearTimeout(st.pendingTimer);
        st.pendingTimer = window.setTimeout(publishNow, 160);
    }

    function setCaret(index, extend, publish) {
        const s = snap();
        const next = clamp(index, 0, s ? s.sequence.length : 0);

        if (!extend) st.selA = next;

        st.caret = next;
        st.selB = next;

        if (publish) publishSoon();

        reveal(next);
        schedule();
    }

    /* ---------- editing ---------- */

    function selectionBounds() {
        return [Math.min(st.selA, st.selB), Math.max(st.selA, st.selB)];
    }

    function edit(from, to, text) {
        const workspace = api();
        const s = snap();

        if (!workspace || !s || !s.canEdit) return false;

        publishNow();

        const added = workspace.replaceRange(from, to, text, {source: "seqcanvas"});

        if (added === false) return false;

        st.caret = from + added;
        st.selA = st.selB = st.caret;
        reveal(st.caret);
        schedule();

        return true;
    }

    function typeText(text) {
        const [a, b] = selectionBounds();
        const at = b > a ? a : st.caret;

        edit(at, b > a ? b : at, text);
    }

    function removeBack(forward) {
        const [a, b] = selectionBounds();
        const s = snap();

        if (b > a) {
            edit(a, b, "");
        } else if (forward) {
            if (st.caret < s.sequence.length) edit(st.caret, st.caret + 1, "");
        } else if (st.caret > 0) {
            edit(st.caret - 1, st.caret, "");
        }
    }

    function selectedText() {
        const s = snap();
        const [a, b] = selectionBounds();

        return s && b > a ? s.sequence.slice(a, b) : "";
    }

    function history(kind) {
        const workspace = api();

        if (!workspace) return;

        if (kind === "undo") workspace.undo();
        else workspace.redo();

        const s = snap();

        st.caret = clamp(st.caret, 0, s.sequence.length);
        st.selA = st.selB = st.caret;
        schedule();
    }

    /* ---------- zoom ---------- */

    function setCharWidth(next, pointerY, pointerX) {
        const s = snap();
        const value = clamp(next, MIN_CHAR, MAX_CHAR);

        if (!s || value === st.charW) return;

        const layout = layoutFor(s);
        const probe = {x: pointerX === undefined ? LEFT : pointerX, y: viewport.scrollTop + (pointerY === undefined ? viewport.clientHeight / 2 : pointerY)};
        const anchor = boundaryAt(layout, probe);
        const offset = pointerY === undefined ? viewport.clientHeight / 2 : pointerY;

        st.charW = value;
        st.layoutKey = "";

        const next2 = layoutFor(s);
        const row = rowOfIndex(next2, anchor);

        viewport.scrollTop = Math.max(0, row.y - offset + row.h / 2);
        viewport.dispatchEvent(new CustomEvent("msc:zoom", {bubbles: true, detail: {percent: zoomPercent()}}));
        host.dispatchEvent(new CustomEvent("msc:zoom", {bubbles: true, detail: {percent: zoomPercent()}}));
        schedule();
    }

    const zoomPercent = () => Math.round(st.charW / DEFAULT_CHAR * 100);

    /* ---------- events ---------- */

    canvas.addEventListener("pointerdown", event => {
        if (event.button !== 0) return;

        const s = snap();

        if (!s) return;

        const layout = layoutFor(s);
        const point = local(event);
        const feature = featureAt(layout, point);

        viewport.focus({preventScroll: true});

        if (feature >= 0) {
            st.drag = {kind: "feature", feature, x: event.clientX, y: event.clientY};
        } else {
            const at = boundaryAt(layout, point);

            if (event.shiftKey) {
                st.caret = at;
                st.selB = at;
            } else {
                st.selA = st.selB = st.caret = at;
            }

            st.drag = {kind: "select"};
            canvas.setPointerCapture(event.pointerId);
        }

        schedule();
    });

    canvas.addEventListener("pointermove", event => {
        const s = snap();

        if (!s) return;

        const layout = layoutFor(s);
        const point = local(event);

        if (st.drag && st.drag.kind === "select") {
            const at = boundaryAt(layout, point);

            st.caret = at;
            st.selB = at;

            if (point.cy < 24) viewport.scrollTop -= 24;
            else if (point.cy > viewport.clientHeight - 24) viewport.scrollTop += 24;

            schedule();

            return;
        }

        const feature = featureAt(layout, point);

        canvas.style.cursor = feature >= 0 ? "pointer" : "text";

        if (feature !== st.hover) {
            st.hover = feature;
            schedule();
        }

        if (feature >= 0 && s.features[feature]) {
            const item = s.features[feature];
            const rect = host.getBoundingClientRect();

            tip.textContent = item.name + " · " + item.start + ".." + item.end + " · " + (Math.abs(item.end - item.start) + 1) + " bp";
            tip.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 220) + "px";
            tip.style.top = event.clientY - rect.top + 16 + "px";
            tip.hidden = false;
        } else {
            tip.hidden = true;
        }
    });

    canvas.addEventListener("pointerleave", () => {
        tip.hidden = true;

        if (st.hover !== -1) {
            st.hover = -1;
            schedule();
        }
    });

    function endDrag(event) {
        const drag = st.drag;

        st.drag = null;

        if (!drag) return;

        if (drag.kind === "feature") {
            if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 5 && api()) {
                api().selectFeature(drag.feature);
            }

            return;
        }

        publishNow();
        schedule();
    }

    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);

    viewport.addEventListener("wheel", event => {
        if (!(event.ctrlKey || event.metaKey)) return;

        event.preventDefault();

        const point = local(event);

        setCharWidth(st.charW * (event.deltaY < 0 ? 1.12 : 1 / 1.12), point.cy, point.x);
    }, {passive: false});

    viewport.addEventListener("scroll", schedule);
    viewport.addEventListener("focus", () => {
        st.focused = true;
        schedule();
    });
    viewport.addEventListener("blur", () => {
        st.focused = false;
        schedule();
    });

    viewport.addEventListener("keydown", event => {
        const s = snap();

        if (!s) return;

        const mod = event.ctrlKey || event.metaKey;
        const key = event.key;
        const bpr = st.layout ? st.layout.bpr : 60;
        let handled = true;

        if (mod && key.toLowerCase() === "z") {
            history(event.shiftKey ? "redo" : "undo");
        } else if (mod && key.toLowerCase() === "y") {
            history("redo");
        } else if (mod && key.toLowerCase() === "a") {
            st.selA = 0;
            st.selB = st.caret = s.sequence.length;
            publishSoon();
            schedule();
        } else if (mod && (key === "+" || key === "=")) {
            setCharWidth(st.charW * 1.25);
        } else if (mod && key === "-") {
            setCharWidth(st.charW / 1.25);
        } else if (mod && key === "0") {
            setCharWidth(DEFAULT_CHAR);
        } else if (mod) {
            handled = false;
        } else if (key === "ArrowLeft") {
            setCaret(st.caret - 1, event.shiftKey, true);
        } else if (key === "ArrowRight") {
            setCaret(st.caret + 1, event.shiftKey, true);
        } else if (key === "ArrowUp") {
            setCaret(st.caret - bpr, event.shiftKey, true);
        } else if (key === "ArrowDown") {
            setCaret(st.caret + bpr, event.shiftKey, true);
        } else if (key === "Home") {
            setCaret(Math.floor(st.caret / bpr) * bpr, event.shiftKey, true);
        } else if (key === "End") {
            setCaret(Math.min(s.sequence.length, (Math.floor(st.caret / bpr) + 1) * bpr), event.shiftKey, true);
        } else if (key === "Escape") {
            st.selA = st.selB = st.caret;
            publishNow();
            schedule();
        } else if (key === "Backspace" || key === "Delete") {
            removeBack(key === "Delete");
        } else if (key.length === 1 && s.canEdit) {
            const allowed = s.sequenceType === "protein" ? /^[A-Za-z*]$/ : NUCLEOTIDE_KEYS;

            if (allowed.test(key)) typeText(key);
            else handled = false;
        } else {
            handled = false;
        }

        if (handled) event.preventDefault();
    });

    viewport.addEventListener("copy", event => {
        const text = selectedText();

        if (text) {
            event.clipboardData.setData("text/plain", text);
            event.preventDefault();
        }
    });

    viewport.addEventListener("cut", event => {
        const text = selectedText();

        if (text && snap().canEdit) {
            event.clipboardData.setData("text/plain", text);
            event.preventDefault();
            removeBack(false);
        }
    });

    viewport.addEventListener("paste", event => {
        const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";

        if (text && snap().canEdit) {
            event.preventDefault();
            typeText(text);
        }
    });

    let findTimer = 0;

    find.addEventListener("input", () => {
        st.query = find.value;
        window.clearTimeout(findTimer);
        findTimer = window.setTimeout(refreshMatches, 140);
    });
    find.addEventListener("keydown", event => {
        if (event.key === "Enter") {
            event.preventDefault();
            window.clearTimeout(findTimer);

            if (st.query && !st.matches.length) refreshMatches();

            gotoMatch(event.shiftKey ? -1 : 1);
        } else if (event.key === "Escape") {
            find.value = "";
            st.query = "";
            refreshMatches();
            viewport.focus({preventScroll: true});
        }

        event.stopPropagation();
    });

    undoBtn.addEventListener("click", () => {
        history("undo");
        viewport.focus({preventScroll: true});
    });
    redoBtn.addEventListener("click", () => {
        history("redo");
        viewport.focus({preventScroll: true});
    });
    compInput.addEventListener("change", () => {
        st.showComp = compInput.checked;
        st.layoutKey = "";
        schedule();
    });
    transInput.addEventListener("change", () => {
        st.showTrans = transInput.checked;
        st.layoutKey = "";
        schedule();
    });

    /* ---------- workspace sync ---------- */

    function onWorkspace(event) {
        const detail = event.detail || {};
        const s = detail.snapshot || snap();

        if (!s || !st.active) return;

        st.caret = clamp(st.caret, 0, s.sequence.length);

        if (st.query && (detail.reason === "sequence-edit" || st.matchedLength !== s.sequence.length)) {
            st.matchedLength = s.sequence.length;
            window.clearTimeout(findTimer);
            findTimer = window.setTimeout(refreshMatches, 200);
        }

        if (!st.pending && !st.drag) {
            const sel = s.sequenceSelection;

            if (sel && sel.start <= sel.end) {
                const a = sel.start - 1;
                const b = sel.end;

                if (st.selA !== a || st.selB !== b) {
                    st.selA = a;
                    st.selB = st.caret = b;

                    if (detail.source !== "seqcanvas") reveal(a, "centre");
                }
            } else if (!sel) {
                st.selA = st.selB = st.caret;
            }
        }

        st.selA = clamp(st.selA, 0, s.sequence.length);
        st.selB = clamp(st.selB, 0, s.sequence.length);
        schedule();
    }

    root.addEventListener("biobank:molecular-workspace-change", onWorkspace);

    if (window.ResizeObserver) {
        new ResizeObserver(() => {
            st.layoutKey = "";
            schedule();
        }).observe(viewport);
    }

    window.BiobankSeqCanvas = {
        active: () => st.active,
        setActive(on) {
            st.active = Boolean(on);
            host.hidden = !st.active;

            if (st.active) {
                st.layoutKey = "";
                schedule();
            }
        },
        zoomIn: () => setCharWidth(st.charW * 1.25),
        zoomOut: () => setCharWidth(st.charW / 1.25),
        fit: () => setCharWidth(DEFAULT_CHAR),
        zoomPercent,
        state: () => ({caret: st.caret, selA: st.selA, selB: st.selB, charW: st.charW}),
        // Viewport position of the sequence line at a base (used by tests and tours).
        pointOf(index, lane) {
            const s = snap();

            if (!s || !st.layout) return null;

            const row = rowOfIndex(layoutFor(s), index);
            const rect = canvas.getBoundingClientRect();

            return {
                x: rect.left + LEFT + (index - row.start) * st.charW + st.charW / 2,
                y: Number.isInteger(lane)
                    ? rect.top + row.y - viewport.scrollTop + row.laneTop + lane * LANE + LANE / 2
                    : rect.top + row.y - viewport.scrollTop + row.seqTop + row.lineH / 2,
            };
        },
    };

    host.hidden = true;
}());
