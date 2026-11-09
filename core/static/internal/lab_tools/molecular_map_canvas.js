/*
 * Molecular map canvas: one interactive map for every nucleotide record.
 *
 * Circular records are drawn as a ring, linear ones as a track. Both share the
 * same tools (Select, Pan, Zoom, Add), the same selection and the same
 * selection bar, and talk to the workspace only through
 * window.BiobankMolecularWorkspace and its change event, so the inspector,
 * Tracks rail and Digest stay in sync without extra wiring.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("mmc");

    if (!root || !host) {
        return;
    }

    const NS = "http://www.w3.org/2000/svg";
    const TOOLS = [
        {id: "select", key: "V", label: "Select", hint: "Click a feature or drag across the map to select a region", icon: "M5 3l12 8-5 1-2 5z"},
        {id: "pan", key: "P", label: "Pan", hint: "Drag to move the map", icon: "M12 3v18M3 12h18M12 3l-3 3m3-3l3 3M12 21l-3-3m3 3l3-3M3 12l3-3m-3 3l3 3M21 12l-3-3m3 3l-3 3"},
        {id: "zoom", key: "Z", label: "Zoom", hint: "Click to zoom in (Shift to zoom out) or drag a region to zoom to it", icon: "M10 4a6 6 0 100 12 6 6 0 000-12zm5 11l5 5M8 10h4M10 8v4"},
        {id: "add", key: "A", label: "Add feature", hint: "Drag across a region to create a feature from it", icon: "M4 4h10l6 6v10H4zM12 9v6M9 12h6"},
        {id: "cut", key: "X", label: "Cut", hint: "Cut sites arrive with Digest on the map", icon: "M6 6l12 12M6 18L18 6M6 6a2 2 0 100-.1M6 18a2 2 0 100-.1", disabled: true},
    ];

    const state = {
        tool: "select",
        zoom: 1,
        centre: 0.5,
        tx: 0,
        ty: 0,
        drag: null,
        preview: null,
        active: false,
        frame: 0,
    };

    const api = () => window.BiobankMolecularWorkspace || null;
    const snap = () => (api() ? api().getSnapshot() : null);

    function svg(name, attrs, children) {
        const node = document.createElementNS(NS, name);

        Object.entries(attrs || {}).forEach(([key, value]) => {
            if (value !== null && value !== undefined) {
                node.setAttribute(key, String(value));
            }
        });
        (children || []).forEach(child => node.append(child));

        return node;
    }

    function html(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    const color = value => (/^#[0-9a-f]{6}$/i.test(value || "") ? value : "#868E96");

    function niceStep(length) {
        const target = length / 8;
        const power = Math.pow(10, Math.floor(Math.log10(Math.max(target, 1))));

        for (const m of [1, 2, 5, 10]) {
            if (m * power >= target) return m * power;
        }

        return power * 10;
    }

    function segmentsOf(feature, length) {
        const start = clamp(Number(feature.start) || 1, 1, length);
        const end = clamp(Number(feature.end) || start, 1, length);

        return start <= end
            ? [[start, end]]
            : [[start, length], [1, end]];
    }

    function assignLanes(features, length) {
        const order = features
            .map((feature, index) => ({feature, index}))
            .sort((a, b) => (a.feature.start - b.feature.start) || (b.feature.end - a.feature.end));
        const laneEnds = [];
        const lanes = new Map();

        order.forEach(({feature, index}) => {
            const [first] = segmentsOf(feature, length);
            const last = segmentsOf(feature, length).slice(-1)[0];
            const from = first[0];
            const to = feature.start > feature.end ? length : last[1];
            let lane = laneEnds.findIndex(end => end < from - 1);

            if (lane < 0) {
                lane = laneEnds.length;
                laneEnds.push(0);
            }

            laneEnds[lane] = to;
            lanes.set(index, lane);
        });

        return {lanes, count: Math.max(1, laneEnds.length)};
    }

    /* ---------- chrome: tool rail, canvas, selection bar ---------- */

    const rail = html("div", "mmc-rail");
    const stage = html("div", "mmc-stage");
    const bar = html("div", "mmc-selbar");
    const tip = html("div", "mmc-tip");
    const hint = html("div", "mmc-hint");

    rail.setAttribute("role", "toolbar");
    rail.setAttribute("aria-label", "Map tools");
    rail.setAttribute("aria-orientation", "vertical");
    bar.hidden = true;
    tip.hidden = true;
    stage.append(bar, tip, hint);
    host.append(rail, stage);

    TOOLS.forEach(tool => {
        const button = html("button", "mmc-tool");

        button.type = "button";
        button.dataset.tool = tool.id;
        button.title = tool.label + " (" + tool.key + ") - " + tool.hint;
        button.setAttribute("aria-label", tool.label);
        button.disabled = Boolean(tool.disabled);
        button.append(svg("svg", {viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor", "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true"}, [svg("path", {d: tool.icon})]));
        button.addEventListener("click", () => setTool(tool.id));
        rail.append(button);
    });

    function setTool(id) {
        const tool = TOOLS.find(item => item.id === id);

        if (!tool || tool.disabled) return;

        state.tool = id;
        rail.querySelectorAll(".mmc-tool").forEach(button => {
            const on = button.dataset.tool === id;

            button.classList.toggle("is-active", on);
            button.setAttribute("aria-pressed", String(on));
        });
        hint.textContent = tool.hint;
        stage.dataset.tool = id;
    }

    /* ---------- geometry helpers ---------- */

    function view(length) {
        const span = length / state.zoom;
        const half = span / 2;
        const centre = clamp(state.centre * length, half, length - half);

        return {from: centre - half, to: centre + half, span};
    }

    function canvasSize() {
        const rect = stage.getBoundingClientRect();

        return {w: Math.max(300, rect.width), h: Math.max(320, rect.height)};
    }

    function coordinateAt(event, node, length, circular) {
        const rect = node.getBoundingClientRect();

        if (circular) {
            const size = canvasSize();
            const scale = Math.min(size.w, size.h) / 1000;
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            const dx = (event.clientX - cx) / scale - state.tx;
            const dy = (event.clientY - cy) / scale - state.ty;
            const angle = Math.atan2(dy / state.zoom, dx / state.zoom) + Math.PI / 2;
            const fraction = ((angle / (2 * Math.PI)) % 1 + 1) % 1;

            return clamp(Math.floor(fraction * length) + 1, 1, length);
        }

        const v = view(length);
        const pad = 56;
        const frac = clamp((event.clientX - rect.left - pad) / (rect.width - pad * 2), 0, 1);

        return clamp(Math.floor(v.from + frac * v.span) + 1, 1, length);
    }

    /* ---------- rendering ---------- */

    function selectionOf(s) {
        const sel = s.sequenceSelection;

        if (!sel || !s.sequence.length) return null;

        return {start: sel.start, end: sel.end};
    }

    function render() {
        state.frame = 0;

        if (!state.active) return;

        const s = snap();

        if (!s || !s.sequence || !s.sequence.length) {
            stage.querySelector("svg")?.remove();
            return;
        }

        const circular = s.topology === "circular";
        const size = canvasSize();
        const node = circular ? drawCircular(s, size) : drawLinear(s, size);

        stage.querySelector("svg")?.remove();
        stage.prepend(node);
        node.addEventListener("pointerdown", onDown);
        node.addEventListener("pointermove", onMove);
        node.addEventListener("pointerup", onUp);
        node.addEventListener("pointercancel", onUp);
        node.addEventListener("wheel", onWheel, {passive: false});
        renderBar(s);
        notifyZoom();
    }

    function schedule() {
        if (!state.frame) {
            state.frame = window.requestAnimationFrame(render);
        }
    }

    function drawLinear(s, size) {
        const length = s.sequence.length;
        const v = view(length);
        const pad = 56;
        const width = size.w - pad * 2;
        const laneInfo = assignLanes(s.features, length);
        const laneH = 38;
        const axisY = Math.max(Math.round(size.h * 0.58), 90 + laneInfo.count * laneH);
        const height = Math.max(size.h, axisY + 120);
        const x = bp => pad + (bp - v.from) / v.span * width;
        const out = svg("svg", {class: "mmc-svg", width: size.w, height, viewBox: "0 0 " + size.w + " " + height, role: "img", "aria-label": "Linear map of " + (s.name || "record")});
        const g = svg("g");
        const sel = selectionOf(s);

        out.append(g);

        const step = niceStep(v.span);
        const first = Math.ceil(v.from / step) * step;

        g.append(svg("line", {x1: pad, x2: pad + width, y1: axisY, y2: axisY, class: "mmc-axis"}));

        for (let tick = first; tick <= v.to; tick += step) {
            const px = x(tick);

            g.append(svg("line", {x1: px, x2: px, y1: axisY - 5, y2: axisY + 5, class: "mmc-axis"}));
            g.append(svg("text", {x: px, y: axisY + 22, class: "mmc-tick", "text-anchor": "middle"}, [document.createTextNode(Math.round(tick).toLocaleString())]));
        }

        if (sel) {
            drawLinearSelection(g, sel, length, x, axisY, laneInfo.count * laneH + 40);
        }

        if (state.preview) {
            drawLinearSelection(g, state.preview, length, x, axisY, laneInfo.count * laneH + 40, "mmc-preview");
        }

        const labelEnds = new Map();
        const ordered = s.features.map((feature, index) => ({feature, index}))
            .sort((a, b) => a.feature.start - b.feature.start);

        ordered.forEach(({feature, index}) => {
            const lane = laneInfo.lanes.get(index) || 0;
            const y = axisY - 34 - lane * laneH;
            const selected = index === s.selectedFeature;
            const group = svg("g", {class: "mmc-feature" + (selected ? " is-selected" : ""), "data-index": index, tabindex: 0, role: "button", "aria-label": feature.name + ", " + feature.start + " to " + feature.end});

            segmentsOf(feature, length).forEach(([a, b]) => {
                const x1 = clamp(x(a - 1), pad - 20, pad + width + 20);
                const x2 = clamp(x(b), pad - 20, pad + width + 20);

                if (x2 < pad - 20 || x1 > pad + width + 20 || x2 - x1 < 0.5) return;

                const w = Math.max(x2 - x1, 3);
                const arrow = feature.strand === "-" ? "left" : feature.strand === "+" ? "right" : "";
                const body = arrow
                    ? svg("path", {d: arrowPath(x1, y, w, 18, arrow), fill: color(feature.color)})
                    : svg("rect", {x: x1, y, width: w, height: 18, rx: 3, fill: color(feature.color)});

                group.append(body);

                const text = feature.name || "";
                const approx = text.length * 6.6;
                const natural = Math.max(pad, Math.min(x1, pad + width - approx));
                const last = labelEnds.get(lane) || -1e9;
                const lx = Math.max(natural, last + 8);
                const fits = lx === natural || lx + approx <= x1 + w;

                if (!group.querySelector("text") && fits) {
                    group.append(svg("text", {x: lx, y: y - 5, class: "mmc-label"}, [document.createTextNode(text)]));
                    labelEnds.set(lane, lx + approx);
                }
            });

            group.append(svg("title", {}, [document.createTextNode(feature.name + " (" + feature.start + ".." + feature.end + ", " + (Math.abs(feature.end - feature.start) + 1) + " bp)")]));
            g.append(group);
        });

        return out;
    }

    function arrowPath(x, y, w, h, dir) {
        const head = Math.min(10, w / 2);

        return dir === "right"
            ? "M" + x + " " + y + "H" + (x + w - head) + "L" + (x + w) + " " + (y + h / 2) + "L" + (x + w - head) + " " + (y + h) + "H" + x + "Z"
            : "M" + (x + w) + " " + y + "H" + (x + head) + "L" + x + " " + (y + h / 2) + "L" + (x + head) + " " + (y + h) + "H" + (x + w) + "Z";
    }

    function drawLinearSelection(g, sel, length, x, axisY, depth, cls) {
        segmentsOf({start: sel.start, end: sel.end}, length).forEach(([a, b]) => {
            g.prepend(svg("rect", {x: x(a - 1), y: axisY - depth, width: Math.max(x(b) - x(a - 1), 2), height: depth + 8, class: cls || "mmc-selection"}));
        });
    }

    function drawCircular(s, size) {
        const length = s.sequence.length;
        const side = Math.min(size.w, size.h);
        const out = svg("svg", {class: "mmc-svg", width: size.w, height: size.h, viewBox: "0 0 " + size.w + " " + size.h, role: "img", "aria-label": "Circular map of " + (s.name || "record")});
        const k = side / 1000;
        const g = svg("g", {transform: "translate(" + size.w / 2 + " " + size.h / 2 + ") scale(" + k + ") translate(" + state.tx + " " + state.ty + ") scale(" + state.zoom + ")"});
        const R = 330;
        const laneInfo = assignLanes(s.features, length);
        const sel = selectionOf(s);
        const angle = pos => (pos / length) * 2 * Math.PI - Math.PI / 2;
        const point = (pos, r) => [Math.cos(angle(pos)) * r, Math.sin(angle(pos)) * r];
        const arc = (a, b, r) => {
            const [x1, y1] = point(a - 1, r);
            const [x2, y2] = point(b, r);
            const large = (b - a + 1) / length > 0.5 ? 1 : 0;

            return "M" + x1.toFixed(2) + " " + y1.toFixed(2) + "A" + r + " " + r + " 0 " + large + " 1 " + x2.toFixed(2) + " " + y2.toFixed(2);
        };

        out.append(g);
        g.append(svg("circle", {r: R, class: "mmc-ring", fill: "none"}));

        const step = niceStep(length);

        for (let tick = 0; tick < length; tick += step) {
            const [x1, y1] = point(tick, R - 8);
            const [x2, y2] = point(tick, R + 8);
            const [tx, ty] = point(tick, R - 30);

            g.append(svg("line", {x1, y1, x2, y2, class: "mmc-axis"}));
            g.append(svg("text", {x: tx, y: ty, class: "mmc-tick", "text-anchor": "middle", "dominant-baseline": "middle", "font-size": 13 / state.zoom + 6}, [document.createTextNode(tick ? tick.toLocaleString() : "1")]));
        }

        [sel, state.preview].forEach((region, i) => {
            if (!region) return;

            segmentsOf({start: region.start, end: region.end}, length).forEach(([a, b]) => {
                g.prepend(svg("path", {d: arc(a, b, R), class: i ? "mmc-arc-preview" : "mmc-arc-selection", fill: "none"}));
            });
        });

        const labels = [];

        s.features.forEach((feature, index) => {
            const lane = laneInfo.lanes.get(index) || 0;
            const r = R + 26 + lane * 20;
            const selected = index === s.selectedFeature;
            const group = svg("g", {class: "mmc-feature" + (selected ? " is-selected" : ""), "data-index": index, tabindex: 0, role: "button", "aria-label": feature.name});

            segmentsOf(feature, length).forEach(([a, b]) => {
                group.append(svg("path", {d: arc(a, b, r), fill: "none", stroke: color(feature.color), "stroke-width": 15, "stroke-linecap": "butt"}));
            });

            group.append(svg("title", {}, [document.createTextNode(feature.name + " (" + feature.start + ".." + feature.end + ")")]));
            g.append(group);

            const mid = feature.start <= feature.end
                ? (feature.start + feature.end) / 2
                : ((feature.start + feature.end + length) / 2) % length;

            labels.push({feature, index, mid, r});
        });

        placeCircularLabels(g, labels, point, length, R + 26 + laneInfo.count * 20 + 26);

        g.append(svg("text", {x: 0, y: -10, class: "mmc-centre-name", "text-anchor": "middle"}, [document.createTextNode(s.name || "")]));
        g.append(svg("text", {x: 0, y: 24, class: "mmc-centre-sub", "text-anchor": "middle"}, [document.createTextNode(length.toLocaleString() + " bp")]));

        return out;
    }

    function placeCircularLabels(g, labels, point, length, labelRadius) {
        const sides = {right: [], left: []};

        labels.forEach(item => {
            const [x, y] = point(item.mid, labelRadius);

            (x >= 0 ? sides.right : sides.left).push({...item, x, y});
        });

        Object.entries(sides).forEach(([name, list]) => {
            list.sort((a, b) => a.y - b.y);

            let last = -1e9;

            list.forEach(item => {
                item.y = Math.max(item.y, last + 22);
                last = item.y;
            });

            list.forEach(item => {
                const [ax, ay] = point(item.mid, item.r + 9);
                const tx = (name === "right" ? 1 : -1) * (Math.abs(item.x) + 14);
                const group = svg("g", {class: "mmc-feature", "data-index": item.index});
                const pts = [[ax, ay], [item.x, item.y], [tx, item.y]]
                    .map(pair => pair[0].toFixed(1) + "," + pair[1].toFixed(1))
                    .join(" ");

                group.append(svg("polyline", {points: pts, class: "mmc-leader", fill: "none"}));
                group.append(svg("text", {x: tx + (name === "right" ? 4 : -4), y: item.y, class: "mmc-label", "text-anchor": name === "right" ? "start" : "end", "dominant-baseline": "middle"}, [document.createTextNode(item.feature.name)]));
                g.append(group);
            });
        });
    }

    /* ---------- selection bar ---------- */

    function renderBar(s) {
        const sel = selectionOf(s);

        bar.replaceChildren();
        bar.hidden = !sel;

        if (!sel) return;

        const length = s.sequence.length;
        const size = sel.start <= sel.end ? sel.end - sel.start + 1 : length - sel.start + sel.end + 1;
        const feature = s.selectedFeature >= 0 ? s.features[s.selectedFeature] : null;

        bar.append(html("strong", "", feature ? feature.name : sel.start + ".." + sel.end));
        bar.append(html("span", "mmc-selbar-meta", (feature ? sel.start + ".." + sel.end + " · " : "") + size.toLocaleString() + " bp"));

        const actions = [
            ["Copy", () => copy(sequenceOf(s, sel))],
            ["Copy reverse complement", () => copy(reverseComplement(sequenceOf(s, sel)))],
        ];

        if (s.canEdit && !feature) {
            actions.unshift(["Create feature", () => createFeature()]);
        }

        actions.push(["Clear", () => clearSelection()]);
        actions.forEach(([label, handler]) => {
            const button = html("button", "mmc-selbar-btn", label);

            button.type = "button";
            button.addEventListener("click", handler);
            bar.append(button);
        });
    }

    function sequenceOf(s, sel) {
        const text = s.sequence;

        return sel.start <= sel.end
            ? text.slice(sel.start - 1, sel.end)
            : text.slice(sel.start - 1) + text.slice(0, sel.end);
    }

    function reverseComplement(seq) {
        const map = {A: "T", T: "A", G: "C", C: "G", U: "A", N: "N"};

        return seq.split("").reverse().map(base => map[base] || base).join("");
    }

    function copy(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).catch(() => {});
        }
    }

    function createFeature() {
        const workspace = api();

        if (!workspace) return;

        const created = workspace.createFeatureFromSelection({name: "New feature", type: "custom"});
        const after = snap();

        if (created !== null && after && after.features.length) {
            workspace.selectFeature(after.features.length - 1);
        }
    }

    function clearSelection() {
        const workspace = api();
        const s = snap();

        if (workspace && s) {
            workspace.selectFeature(-1);
            window.setTimeout(schedule, 0);
        }
    }

    /* ---------- pointer interaction ---------- */

    function featureIndexAt(event) {
        const target = event.target.closest ? event.target.closest(".mmc-feature") : null;

        return target ? Number(target.dataset.index) : -1;
    }

    /* ---------- dragging an annotation ---------- */

    function wrapCoordinate(value, length) {
        return ((Math.round(value) - 1) % length + length) % length + 1;
    }

    function featureLength(feature, length) {
        return feature.start <= feature.end
            ? feature.end - feature.start + 1
            : length - feature.start + feature.end + 1;
    }

    function gap(a, b, length, circular) {
        const d = Math.abs(a - b);

        return circular ? Math.min(d, length - d) : d;
    }

    /* "start", "end" near the ends of the annotation, "move" along its body. */
    function gripAt(feature, at, s) {
        const length = s.sequence.length;
        const circular = s.topology === "circular";
        const span = circular ? length / state.zoom : view(length).span;
        const tolerance = Math.min(Math.max(1, Math.round(span / 45)), Math.floor(featureLength(feature, length) / 3));

        if (tolerance < 1) return "move";

        const toStart = gap(at, feature.start, length, circular);
        const toEnd = gap(at, feature.end, length, circular);

        if (toStart > tolerance && toEnd > tolerance) return "move";

        return toStart <= toEnd ? "start" : "end";
    }

    function draggedRange(drag, at, s) {
        const length = s.sequence.length;
        const circular = s.topology === "circular";

        if (drag.grip === "start") {
            return {start: circular ? at : Math.min(at, drag.end), end: drag.end};
        }

        if (drag.grip === "end") {
            return {start: drag.start, end: circular ? at : Math.max(at, drag.start)};
        }

        let delta = at - drag.anchor;

        if (circular) {
            if (delta > length / 2) delta -= length;
            if (delta < -length / 2) delta += length;

            return {start: wrapCoordinate(drag.start + delta, length), end: wrapCoordinate(drag.end + delta, length)};
        }

        const low = Math.min(drag.start, drag.end);
        const high = Math.max(drag.start, drag.end);

        delta = Math.max(1 - low, Math.min(length - high, delta));

        return {start: drag.start + delta, end: drag.end + delta};
    }

    function onDown(event) {
        const s = snap();

        if (!s || !s.sequence.length || event.button !== 0) return;

        const circular = s.topology === "circular";
        const node = event.currentTarget;

        node.setPointerCapture(event.pointerId);

        if (state.tool === "select" || state.tool === "add") {
            const index = state.tool === "select" ? featureIndexAt(event) : -1;

            if (index >= 0) {
                const feature = s.features[index];

                if (s.canEdit && feature) {
                    const at = coordinateAt(event, node, s.sequence.length, circular);

                    state.drag = {
                        kind: "feature-edit", index, anchor: at, grip: gripAt(feature, at, s),
                        start: feature.start, end: feature.end, moved: false, began: false,
                    };
                } else {
                    state.drag = {kind: "click-feature", index};
                }

                return;
            }

            const at = coordinateAt(event, node, s.sequence.length, circular);

            state.drag = {kind: "range", anchor: at, moved: false};
            state.preview = {start: at, end: at};
        } else if (state.tool === "pan") {
            state.drag = {kind: "pan", x: event.clientX, y: event.clientY, centre: state.centre, tx: state.tx, ty: state.ty};
            stage.classList.add("is-grabbing");
        } else if (state.tool === "zoom") {
            const at = coordinateAt(event, node, s.sequence.length, circular);

            state.drag = {kind: "zoom", anchor: at, x: event.clientX, y: event.clientY, moved: false};
            state.preview = {start: at, end: at};
        }
    }

    function onMove(event) {
        const s = snap();
        const drag = state.drag;

        if (!s || !drag) {
            showTip(event, s);

            if (s && state.tool === "select" && s.canEdit) {
                const index = featureIndexAt(event);
                const feature = index >= 0 ? s.features[index] : null;
                const grip = feature
                    ? gripAt(feature, coordinateAt(event, event.currentTarget, s.sequence.length, s.topology === "circular"), s)
                    : null;

                event.currentTarget.style.cursor = !feature ? "" : grip === "move" ? "grab" : "ew-resize";
            }

            return;
        }

        const length = s.sequence.length;
        const circular = s.topology === "circular";

        if (drag.kind === "feature-edit") {
            const at = coordinateAt(event, event.currentTarget, length, circular);
            const workspace = api();

            if (!drag.moved && at === drag.anchor) return;

            if (!drag.began) {
                drag.began = true;
                workspace.selectFeature(drag.index);
                workspace.editFeature("begin", drag.index);
            }

            drag.moved = true;
            drag.last = draggedRange(drag, at, s);
            workspace.editFeature("move", drag.index, drag.last.start, drag.last.end, {source: "map-canvas"});
            event.currentTarget.style.cursor = drag.grip === "move" ? "grabbing" : "ew-resize";

            return;
        }

        if (drag.kind === "range" || drag.kind === "zoom") {
            const at = coordinateAt(event, event.currentTarget, length, circular);

            drag.moved = drag.moved || at !== drag.anchor;
            state.preview = {start: Math.min(drag.anchor, at), end: Math.max(drag.anchor, at)};

            if (circular && Math.abs(at - drag.anchor) > length / 2) {
                state.preview = {start: Math.max(drag.anchor, at), end: Math.min(drag.anchor, at)};
            }

            schedule();
        } else if (drag.kind === "pan") {
            const dx = event.clientX - drag.x;
            const dy = event.clientY - drag.y;

            if (circular) {
                const k = Math.min(canvasSize().w, canvasSize().h) / 1000;

                state.tx = drag.tx + dx / k;
                state.ty = drag.ty + dy / k;
            } else {
                const v = view(length);

                state.centre = clamp(drag.centre - dx / (canvasSize().w - 112) * v.span / length, 0, 1);
            }

            schedule();
        }
    }

    function onUp(event) {
        const s = snap();
        const drag = state.drag;

        state.drag = null;
        stage.classList.remove("is-grabbing");

        if (!s || !drag) return;

        const workspace = api();
        const preview = state.preview;

        state.preview = null;

        if (drag.kind === "feature-edit") {
            if (drag.began && drag.last) {
                workspace.editFeature("end", drag.index, drag.last.start, drag.last.end, {source: "map-canvas"});
            } else {
                workspace.selectFeature(drag.index);
            }
        } else if (drag.kind === "click-feature") {
            workspace.selectFeature(drag.index);
        } else if (drag.kind === "range" && preview) {
            const single = preview.start === preview.end && !drag.moved;

            if (single && state.tool === "select") {
                workspace.selectFeature(-1);
            } else if (single) {
                /* A click with Add does nothing: a region is needed. */
            } else {
                workspace.selectSequenceRange(preview.start, preview.end, {source: "map-canvas"});

                if (state.tool === "add" && s.canEdit) {
                    createFeature();
                    setTool("select");
                }
            }
        } else if (drag.kind === "zoom" && preview) {
            if (preview.end - preview.start > 3) {
                zoomToRegion(s, preview.start, preview.end);
            } else {
                zoomBy(event.shiftKey ? 1 / 1.6 : 1.6, event);
            }
        }

        schedule();
    }

    function onWheel(event) {
        event.preventDefault();
        zoomBy(event.deltaY < 0 ? 1.18 : 1 / 1.18, event);
    }

    function zoomToRegion(s, start, end) {
        const length = s.sequence.length;

        if (s.topology === "circular") {
            state.zoom = clamp(length / Math.max(end - start + 1, length / 8), 1, 8);
            const mid = (start + end) / 2 / length * 2 * Math.PI - Math.PI / 2;

            state.tx = -Math.cos(mid) * 330 * (state.zoom - 1) / state.zoom;
            state.ty = -Math.sin(mid) * 330 * (state.zoom - 1) / state.zoom;
        } else {
            state.zoom = clamp(length / Math.max(end - start + 1, 20), 1, length / 20);
            state.centre = ((start + end) / 2) / length;
        }
    }

    function zoomBy(factor, event) {
        const s = snap();

        if (!s || !s.sequence.length) return;

        const length = s.sequence.length;
        const before = state.zoom;
        const max = s.topology === "circular" ? 8 : Math.max(2, length / 20);

        state.zoom = clamp(before * factor, 1, max);

        if (s.topology !== "circular" && event && event.currentTarget && event.currentTarget.getBoundingClientRect) {
            const rect = event.currentTarget.getBoundingClientRect();
            const frac = clamp((event.clientX - rect.left - 56) / (rect.width - 112), 0, 1);
            const v0 = view(length);
            const anchor = v0.from + frac * v0.span;
            const span = length / state.zoom;

            state.centre = (anchor - frac * span + span / 2) / length;
        }

        if (state.zoom === 1) {
            state.centre = 0.5;
            state.tx = 0;
            state.ty = 0;
        }

        schedule();
    }

    function fit() {
        state.zoom = 1;
        state.centre = 0.5;
        state.tx = 0;
        state.ty = 0;
        schedule();
    }

    function showTip(event, s) {
        const index = featureIndexAt(event);

        if (!s || index < 0 || !s.features[index]) {
            tip.hidden = true;
            return;
        }

        const feature = s.features[index];
        const rect = stage.getBoundingClientRect();

        tip.textContent = feature.name + " · " + feature.start + ".." + feature.end + " · " + (Math.abs(feature.end - feature.start) + 1) + " bp";
        tip.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 220) + "px";
        tip.style.top = event.clientY - rect.top + 14 + "px";
        tip.hidden = false;
    }

    function notifyZoom() {
        host.dispatchEvent(new CustomEvent("mmc:zoom", {bubbles: true, detail: {percent: Math.round(state.zoom * 100)}}));
    }

    /* ---------- keyboard ---------- */

    host.addEventListener("keydown", event => {
        if (event.target.matches && event.target.matches("input,textarea,select")) return;

        const key = event.key.toLowerCase();
        const tool = TOOLS.find(item => item.key.toLowerCase() === key && !item.disabled);

        if (tool && !event.ctrlKey && !event.metaKey) {
            setTool(tool.id);
        } else if (key === "+" || key === "=") {
            zoomBy(1.4);
        } else if (key === "-") {
            zoomBy(1 / 1.4);
        } else if (key === "0") {
            fit();
        } else if (key === "escape") {
            clearSelection();
        } else if ((key === "enter" || key === " ") && event.target.classList && event.target.classList.contains("mmc-feature")) {
            api().selectFeature(Number(event.target.dataset.index));
            event.preventDefault();
        }
    });

    host.tabIndex = 0;

    root.addEventListener("biobank:molecular-workspace-change", schedule);

    if (window.ResizeObserver) {
        new ResizeObserver(schedule).observe(stage);
    }

    setTool("select");

    window.BiobankMapCanvas = {
        active: () => state.active,
        setActive(on) {
            state.active = Boolean(on);
            host.hidden = !state.active;
            schedule();
        },
        zoomIn: () => zoomBy(1.4),
        zoomOut: () => zoomBy(1 / 1.4),
        fit,
        zoomPercent: () => Math.round(state.zoom * 100),
    };

    host.hidden = true;
}());
