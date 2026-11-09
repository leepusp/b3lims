/*
 * Gel window: read a photographed gel.
 *
 * Load a photo (or draw a simulated gel of the current digest), straighten it,
 * mark the lanes, click the bands of the size marker to calibrate, then click
 * the bands of the samples (or detect them) to read their size in bp. Each
 * lane can be compared with the expected fragments of the record or of the
 * enzymes picked in the Digest window. The annotated figure and the table are
 * exported from here. The photo never leaves the browser.
 */
(function () {
    "use strict";

    const pane = document.getElementById("mw-gel");
    const root = document.getElementById("molecular-workspace") || pane;
    const calc = window.BiobankDigestCalc;

    if (!root || !pane || !calc) {
        return;
    }

    const LADDERS = {
        "1 kb": calc.LADDER,
        "100 bp": [1500, 1200, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100],
        "λ HindIII": [23130, 9416, 6557, 4361, 2322, 2027, 564],
    };
    const COLORS = ["#1D4ED8", "#D9480F", "#2B8A3E", "#9C36B5", "#C2255C", "#0B7285", "#E67700", "#495057"];
    const MAX_SIDE = 2400;

    const S = {
        work: null, source: null, rot: 0, fine: 0, bright: 0, contrast: 0, invert: false, zoom: 1,
        lanes: [], bands: [], cal: [], calStep: 0, ladderName: "1 kb", ladderLane: null,
        mode: "lanes", sel: null, nextId: 1, sensitivity: 35, drag: null, hover: null,
        sim: {wells: 10, lanes: []},
    };
    let frame = 0;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function labelled(text, node) {
        const wrap = el("label", "mwg-item");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    function button(text, title, onClick, className) {
        const node = el("button", className || "mwp-btn", text);

        node.type = "button";
        node.title = title || "";
        node.addEventListener("click", onClick);

        return node;
    }

    /* ---------- skeleton ---------- */

    const head = el("div", "mwp-head");
    const fileInput = el("input");
    const ladderSelect = el("select", "mwp-select");
    const body = el("div", "mwg-body");
    const stage = el("div", "mwg-stage");
    const holder = el("div", "mwg-holder");
    const photo = el("canvas", "mwg-photo");
    const overlay = el("canvas", "mwg-overlay");
    const empty = el("div", "mwg-empty");
    const side = el("div", "mwg-side");
    const toolbar = el("div", "mwg-tools");
    const hint = el("p", "mwp-note mwg-hint");
    const lanesBox = el("div", "mwg-card");
    const calBox = el("div", "mwg-card");
    const bandsBox = el("div", "mwg-card");
    const adjustBox = el("div", "mwg-card");
    const simBox = el("div", "mwg-card");
    const modeButtons = {};
    const sliders = {};

    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.hidden = true;
    ladderSelect.setAttribute("aria-label", "Size marker");
    Object.keys(LADDERS).forEach(name => {
        const option = el("option", "", name + " ladder");

        option.value = name;
        ladderSelect.append(option);
    });
    overlay.tabIndex = 0;
    overlay.setAttribute("aria-label", "Gel photo: mark lanes and bands");

    empty.append(
        el("p", "mwg-emptytitle", "Load a gel photo to read band sizes"),
        el("p", "", "Drop an image here, paste it (Ctrl+V), or choose a file. The photo stays in your browser."),
    );
    const chooseButton = button("Choose photo…", "Open an image file", () => fileInput.click(), "mwp-btn is-primary");
    const demoButton = button("Draw a simulated gel", "Draw a gel from the record and the enzymes picked in Digest, to try the tool", () => demoGel(), "mwp-btn");

    empty.append(chooseButton, demoButton);
    holder.append(photo, overlay);
    stage.append(holder, empty);

    [["lanes", "Lanes", "Drag across the gel to draw a lane; drag a lane to move it, its edges to resize"],
        ["ladder", "Calibrate", "Click the bands of the size marker, from the largest to the smallest"],
        ["bands", "Bands", "Click to add a band, drag to move it, Delete removes it"]].forEach(([key, label, title]) => {
        const node = button(label, title, () => setMode(key), "mwp-btn mwg-mode");

        modeButtons[key] = node;
        toolbar.append(node);
    });
    toolbar.append(
        button("Detect bands", "Find the bands of every sample lane automatically", () => detectAll()),
        button("Clear bands", "Remove all band marks", () => {
            S.bands = [];
            S.sel = null;
            changed();
        }),
    );

    const exportRow = el("div", "mwg-exportrow");

    exportRow.append(
        button("Figure PNG", "Download the annotated gel", () => exportPng()),
        button("Table CSV", "Download the band sizes", () => exportCsv()),
        button("Copy table", "Copy the band table", copyTable),
    );

    function slider(key, text, min, max, step, onInput) {
        const input = el("input", "mwg-range");

        input.type = "range";
        input.min = String(min);
        input.max = String(max);
        input.step = String(step || 1);
        input.value = String(S[key]);
        input.addEventListener("input", () => {
            S[key] = Number(input.value);
            onInput();
        });
        sliders[key] = input;

        return labelled(text, input);
    }

    const invertBox = el("input");

    invertBox.type = "checkbox";
    invertBox.addEventListener("change", () => {
        S.invert = invertBox.checked;
        redraw(true);
    });
    adjustBox.append(
        el("div", "mwg-cardtitle", "Photo"),
        slider("bright", "Brightness", -100, 100, 1, () => redraw(true)),
        slider("contrast", "Contrast", -100, 100, 1, () => redraw(true)),
        slider("fine", "Straighten", -10, 10, 0.1, () => rebuild()),
        slider("zoom", "Zoom", 0.1, 3, 0.05, () => layout()),
        labelled("Invert", invertBox),
    );
    const adjustRow = el("div", "mwg-exportrow");

    adjustRow.append(
        button("⟲ 90°", "Rotate left", () => rotate(-90)),
        button("⟳ 90°", "Rotate right", () => rotate(90)),
        button("Fit", "Fit the photo to the window", () => fit()),
        button("New photo…", "Choose another photo", () => fileInput.click()),
    );
    adjustBox.append(adjustRow);

    head.append(el("strong", "mwp-title", "Gel"), button("Photo…", "Open an image file", () => fileInput.click()), button("Simulated gel", "Draw a gel from the record and the enzymes picked in Digest", () => demoGel()), labelled("Marker", ladderSelect), toolbar, exportRow, fileInput);
    side.append(lanesBox, calBox, bandsBox, adjustBox, simBox);
    body.append(stage, side);
    pane.append(head, hint, body);

    /* ---------- image ---------- */

    function newCanvas(width, height) {
        const canvas = document.createElement("canvas");

        canvas.width = Math.max(1, Math.round(width));
        canvas.height = Math.max(1, Math.round(height));

        return canvas;
    }

    function loadBitmap(source) {
        const scale = Math.min(1, MAX_SIDE / Math.max(source.width, source.height));
        const canvas = newCanvas(source.width * scale, source.height * scale);

        canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
        S.source = canvas;
        S.rot = 0;
        S.fine = 0;
        sliders.fine.value = "0";
        S.lanes = [];
        S.bands = [];
        S.cal = [];
        S.calStep = 0;
        S.ladderLane = null;
        S.sel = null;
        rebuild();
        fit();
        setMode("lanes");
    }

    function loadFile(file) {
        if (!file || !/^image\//.test(file.type)) return;

        document.dispatchEvent(new CustomEvent("biobank:gel-photo", {detail: {file}}));

        const url = URL.createObjectURL(file);
        const image = new Image();

        image.onload = () => {
            loadBitmap(image);
            URL.revokeObjectURL(url);
        };
        image.onerror = () => {
            URL.revokeObjectURL(url);
            hint.textContent = "That file could not be read as an image.";
        };
        image.src = url;
    }

    // Rotation (multiples of 90° plus the fine straightening angle) is baked into `work`.
    function rebuild() {
        if (!S.source) return;

        const quarter = ((S.rot % 360) + 360) % 360;
        const radians = (quarter + S.fine) * Math.PI / 180;
        const w = S.source.width;
        const h = S.source.height;
        const sin = Math.abs(Math.sin(radians));
        const cos = Math.abs(Math.cos(radians));
        const fineOnly = S.fine !== 0;
        const outW = fineOnly ? w * cos + h * sin : (quarter % 180 ? h : w);
        const outH = fineOnly ? w * sin + h * cos : (quarter % 180 ? w : h);
        const work = newCanvas(outW, outH);
        const ctx = work.getContext("2d");

        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, work.width, work.height);
        ctx.translate(work.width / 2, work.height / 2);
        ctx.rotate(radians);
        ctx.drawImage(S.source, -w / 2, -h / 2);
        S.work = work;
        redraw(true);
    }

    function rotate(delta) {
        S.rot += delta;
        S.lanes = [];
        S.bands = [];
        S.cal = [];
        S.calStep = 0;
        S.ladderLane = null;
        rebuild();
        fit();
    }

    function fit() {
        if (!S.work) return;

        S.zoom = Math.max(0.1, Math.min(3, Math.round((stage.clientWidth - 6) / S.work.width * 20) / 20 || 0.5));
        sliders.zoom.value = String(S.zoom);
        layout();
    }

    function adjusted(canvas) {
        const out = newCanvas(canvas.width, canvas.height);
        const ctx = out.getContext("2d");

        ctx.drawImage(canvas, 0, 0);

        if (!S.bright && !S.contrast && !S.invert) return out;

        const data = ctx.getImageData(0, 0, out.width, out.height);
        const pixels = data.data;
        const factor = (259 * (S.contrast * 2.55 + 255)) / (255 * (259 - S.contrast * 2.55));
        const shift = S.bright * 2.55;

        for (let i = 0; i < pixels.length; i += 4) {
            for (let c = 0; c < 3; c++) {
                let value = factor * (pixels[i + c] - 128) + 128 + shift;

                value = value < 0 ? 0 : value > 255 ? 255 : value;
                pixels[i + c] = S.invert ? 255 - value : value;
            }
        }

        ctx.putImageData(data, 0, 0);

        return out;
    }

    function redraw(photoToo) {
        if (!S.work) {
            empty.hidden = false;
            holder.hidden = true;
            updateSide();

            return;
        }

        empty.hidden = true;
        holder.hidden = false;

        if (photoToo) {
            photo.width = overlay.width = S.work.width;
            photo.height = overlay.height = S.work.height;
            photo.getContext("2d").drawImage(adjusted(S.work), 0, 0);
            layout();
        }

        drawOverlay(overlay.getContext("2d"), Math.max(11, 13 / S.zoom), Math.max(1, 1.5 / S.zoom));
        updateSide();
        document.dispatchEvent(new CustomEvent("biobank:gel-change"));
    }

    function layout() {
        if (!S.work) return;

        const width = Math.round(S.work.width * S.zoom);
        const height = Math.round(S.work.height * S.zoom);

        [photo, overlay].forEach(canvas => {
            canvas.style.width = width + "px";
            canvas.style.height = height + "px";
        });
        holder.style.width = width + "px";
        holder.style.height = height + "px";
        drawOverlay(overlay.getContext("2d"), Math.max(11, 13 / S.zoom), Math.max(1, 1.5 / S.zoom));
    }

    /* ---------- calibration ---------- */

    function sizes() {
        return LADDERS[S.ladderName];
    }

    function points() {
        return S.cal.slice().sort((a, b) => a.y - b.y);
    }

    function estimate(y) {
        const pts = points();

        if (pts.length < 2) return null;

        let a = pts[0];
        let b = pts[1];
        let extrapolated = true;

        if (y > pts[0].y && y < pts[pts.length - 1].y) {
            extrapolated = false;

            for (let i = 0; i + 1 < pts.length; i++) {
                if (y >= pts[i].y && y <= pts[i + 1].y) {
                    a = pts[i];
                    b = pts[i + 1];
                    break;
                }
            }
        } else if (y >= pts[pts.length - 1].y) {
            a = pts[pts.length - 2];
            b = pts[pts.length - 1];
        }

        const la = Math.log10(a.size);
        const lb = Math.log10(b.size);
        const log = la + (y - a.y) / (b.y - a.y || 1) * (lb - la);

        return {size: Math.max(1, Math.round(Math.pow(10, log))), extrapolated};
    }

    /* ---------- lanes, bands ---------- */

    const laneById = id => S.lanes.find(lane => lane.id === id);

    function laneAt(x) {
        return S.lanes.find(lane => x >= lane.x0 && x <= lane.x1) || null;
    }

    function expectedFor(lane) {
        if (!lane || lane.expect === "none") return [];

        const workspace = window.BiobankMolecularWorkspace;
        const snapshot = workspace ? workspace.getSnapshot() : null;

        if (lane.expect === "uncut") return snapshot ? [snapshot.sequence.length] : [];

        return window.BiobankDigest ? window.BiobankDigest.fragments().map(fragment => fragment.length) : [];
    }

    function readBand(band) {
        const lane = laneById(band.lane);
        const reading = estimate(band.y);
        const expected = expectedFor(lane);
        let match = null;

        if (reading && expected.length) {
            const nearest = expected.reduce((best, value) => (Math.abs(Math.log(value / reading.size)) < Math.abs(Math.log(best / reading.size)) ? value : best), expected[0]);

            match = {expected: nearest, delta: (reading.size - nearest) / nearest * 100};
        }

        return {lane, size: reading ? reading.size : null, extrapolated: reading ? reading.extrapolated : false, match};
    }

    function addBand(laneId, y) {
        const band = {id: S.nextId++, lane: laneId, y: Math.round(y * 10) / 10};

        S.bands.push(band);
        S.sel = {type: "band", id: band.id};

        return band;
    }

    function addLane(x0, x1) {
        const lane = {id: S.nextId++, name: String(S.lanes.length + 1), x0, x1, expect: "none"};

        S.lanes.push(lane);
        S.lanes.sort((a, b) => a.x0 - b.x0);
        S.lanes.forEach((item, index) => {
            if (/^\d+$/.test(item.name)) item.name = String(index + 1);
        });

        if (!S.ladderLane) S.ladderLane = lane.id;

        S.sel = {type: "lane", id: lane.id};

        return lane;
    }

    // Brightness profile down a lane, bright band = high value.
    function profile(lane) {
        const ctx = photo.getContext("2d");
        const x0 = Math.max(0, Math.round(lane.x0 + (lane.x1 - lane.x0) * 0.2));
        const x1 = Math.min(photo.width, Math.round(lane.x1 - (lane.x1 - lane.x0) * 0.2));
        const width = Math.max(1, x1 - x0);
        const data = ctx.getImageData(x0, 0, width, photo.height).data;
        const values = new Float32Array(photo.height);
        let sum = 0;

        for (let y = 0; y < photo.height; y++) {
            let row = 0;

            for (let x = 0; x < width; x++) {
                const i = (y * width + x) * 4;

                row += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
            }

            values[y] = row / width;
            sum += values[y];
        }

        // Bands are the bright part against the lane background; flip dark-on-light photos.
        if (sum / values.length > 140) {
            for (let y = 0; y < values.length; y++) values[y] = 255 - values[y];
        }

        const smooth = new Float32Array(values.length);

        for (let y = 0; y < values.length; y++) {
            let total = 0;
            let count = 0;

            for (let k = -2; k <= 2; k++) {
                if (values[y + k] !== undefined) {
                    total += values[y + k];
                    count += 1;
                }
            }

            smooth[y] = total / count;
        }

        const radius = Math.max(12, Math.round(photo.height / 25));
        const base = new Float32Array(values.length);

        for (let y = 0; y < values.length; y++) {
            let low = Infinity;

            for (let k = -radius; k <= radius; k++) {
                if (smooth[y + k] !== undefined && smooth[y + k] < low) low = smooth[y + k];
            }

            base[y] = smooth[y] - low;
        }

        return base;
    }

    function detect(lane) {
        const signal = profile(lane);
        const peak = signal.reduce((max, value) => Math.max(max, value), 0);

        if (peak < 4) return [];

        const threshold = peak * (1 - S.sensitivity / 100) * 0.6 + 2;
        const gap = Math.max(5, Math.round(photo.height / 120));
        const found = [];

        for (let y = 2; y < signal.length - 2; y++) {
            if (signal[y] >= threshold && signal[y] >= signal[y - 1] && signal[y] > signal[y + 1] && signal[y] >= signal[y - 2] && signal[y] > signal[y + 2]) {
                const last = found[found.length - 1];

                if (last && y - last.y < gap) {
                    if (signal[y] > last.value) {
                        last.y = y;
                        last.value = signal[y];
                    }
                } else {
                    found.push({y, value: signal[y]});
                }
            }
        }

        return found.map(item => item.y + 0.5);
    }

    function detectAll() {
        const lanes = S.lanes.filter(lane => lane.id !== S.ladderLane || S.cal.length < 2);
        let added = 0;

        S.bands = S.bands.filter(band => !band.auto);
        lanes.forEach(lane => {
            if (lane.id === S.ladderLane) return;

            detect(lane).forEach(y => {
                const band = addBand(lane.id, y);

                band.auto = true;
                added += 1;
            });
        });
        S.sel = null;
        hint.textContent = added ? added + " band" + (added > 1 ? "s" : "") + " found. Drag a mark to correct it, Delete removes it." : "No bands found. Mark the lanes first, or raise the sensitivity.";
        changed();
    }

    function detectLadder() {
        const lane = laneById(S.ladderLane);

        if (!lane) return;

        const ys = detect(lane);
        const list = sizes();

        S.cal = ys.slice(0, list.length).map((y, index) => ({y, size: list[index]}));
        S.calStep = S.cal.length;
        hint.textContent = ys.length === list.length
            ? "Marker bands matched to the " + S.ladderName + " ladder. Check the labels and drag any that are off."
            : ys.length + " bands found for " + list.length + " marker sizes. Check the labels, or calibrate by clicking.";
        changed();
    }

    /* ---------- drawing ---------- */

    function drawOverlay(ctx, font, line) {
        ctx.clearRect(0, 0, overlay.width, overlay.height);
        ctx.lineWidth = line;
        ctx.textBaseline = "middle";
        ctx.font = "600 " + font + "px sans-serif";

        S.lanes.forEach((lane, index) => {
            const color = lane.id === S.ladderLane ? "#F08C00" : COLORS[index % COLORS.length];
            const selected = S.sel && S.sel.type === "lane" && S.sel.id === lane.id;

            ctx.fillStyle = color + (selected ? "33" : "1A");
            ctx.fillRect(lane.x0, 0, lane.x1 - lane.x0, overlay.height);
            ctx.strokeStyle = color;
            ctx.setLineDash(selected ? [] : [font * 0.6, font * 0.4]);
            ctx.strokeRect(lane.x0, 0, lane.x1 - lane.x0, overlay.height);
            ctx.setLineDash([]);
            ctx.fillStyle = color;
            ctx.textAlign = "center";
            ctx.fillText((lane.id === S.ladderLane ? "M " : "") + lane.name, (lane.x0 + lane.x1) / 2, font * 0.9);
        });

        const ladder = laneById(S.ladderLane);

        S.cal.forEach(point => {
            const x0 = ladder ? ladder.x0 : 0;
            const x1 = ladder ? ladder.x1 : 40;

            ctx.strokeStyle = "#F08C00";
            ctx.beginPath();
            ctx.moveTo(x0, point.y);
            ctx.lineTo(x1, point.y);
            ctx.stroke();
            ctx.fillStyle = "#F08C00";
            ctx.textAlign = "right";
            ctx.fillText(point.size >= 1000 ? (point.size / 1000) + "k" : String(point.size), x0 - font * 0.3, point.y);
        });

        S.bands.forEach(band => {
            const lane = laneById(band.lane);

            if (!lane) return;

            const reading = readBand(band);
            const selected = S.sel && S.sel.type === "band" && S.sel.id === band.id;
            const color = selected ? "#C92A2A" : "#E03131";

            ctx.strokeStyle = color;
            ctx.lineWidth = line * (selected ? 2 : 1.4);
            ctx.beginPath();
            ctx.moveTo(lane.x0, band.y);
            ctx.lineTo(lane.x1, band.y);
            ctx.stroke();
            ctx.lineWidth = line;

            if (reading.size) {
                const text = reading.size.toLocaleString("en-US") + (reading.extrapolated ? "*" : "");
                const width = ctx.measureText(text).width + font * 0.6;

                ctx.fillStyle = "rgba(255,255,255,.88)";
                ctx.fillRect(lane.x1 + 2, band.y - font * 0.65, width, font * 1.3);
                ctx.fillStyle = reading.match ? matchColor(reading.match.delta) : "#1B2733";
                ctx.textAlign = "left";
                ctx.fillText(text, lane.x1 + 2 + font * 0.3, band.y);
            }
        });
    }

    function matchColor(delta) {
        const size = Math.abs(delta);

        return size <= 8 ? "#2B8A3E" : size <= 15 ? "#E67700" : "#C92A2A";
    }

    /* ---------- pointer ---------- */

    function point(event) {
        const box = overlay.getBoundingClientRect();

        return {x: (event.clientX - box.left) / box.width * overlay.width, y: (event.clientY - box.top) / box.height * overlay.height};
    }

    function bandNear(p) {
        const tolerance = 7 / S.zoom;

        return S.bands.find(band => {
            const lane = laneById(band.lane);

            return lane && p.x >= lane.x0 - tolerance && p.x <= lane.x1 + tolerance && Math.abs(band.y - p.y) <= tolerance;
        }) || null;
    }

    function edgeNear(p) {
        const tolerance = 6 / S.zoom;

        for (const lane of S.lanes) {
            if (Math.abs(p.x - lane.x0) <= tolerance) return {lane, edge: "x0"};
            if (Math.abs(p.x - lane.x1) <= tolerance) return {lane, edge: "x1"};
        }

        return null;
    }

    overlay.addEventListener("pointerdown", event => {
        if (!S.work) return;

        const p = point(event);

        overlay.setPointerCapture(event.pointerId);
        overlay.focus();

        if (S.mode === "lanes") {
            const edge = edgeNear(p);
            const lane = laneAt(p.x);

            if (edge) {
                S.drag = {kind: "edge", lane: edge.lane, edge: edge.edge};
            } else if (lane) {
                S.sel = {type: "lane", id: lane.id};
                S.drag = {kind: "move", lane, from: p.x, x0: lane.x0, x1: lane.x1};
            } else {
                S.drag = {kind: "new", from: p.x, to: p.x};
            }
        } else if (S.mode === "ladder") {
            const lane = laneById(S.ladderLane);

            if (!lane) {
                hint.textContent = "Draw the marker lane first, then mark it as the marker in the lane list.";
            } else if (S.calStep < sizes().length) {
                S.cal.push({y: Math.round(p.y * 10) / 10, size: sizes()[S.calStep]});
                S.calStep += 1;
                changed();
            }
        } else if (S.mode === "bands") {
            const hit = bandNear(p);

            if (hit) {
                S.sel = {type: "band", id: hit.id};
                S.drag = {kind: "band", band: hit};
            } else {
                const lane = laneAt(p.x);

                if (lane && lane.id !== S.ladderLane) {
                    const band = addBand(lane.id, p.y);

                    S.drag = {kind: "band", band};
                }
            }
        }

        redraw(false);
    });

    overlay.addEventListener("pointermove", event => {
        if (!S.work) return;

        const p = point(event);
        const drag = S.drag;

        if (!drag) {
            const near = S.mode === "lanes" ? (edgeNear(p) ? "ew-resize" : laneAt(p.x) ? "move" : "crosshair") : S.mode === "bands" ? (bandNear(p) ? "ns-resize" : "crosshair") : "crosshair";

            overlay.style.cursor = near;

            return;
        }

        if (drag.kind === "new") {
            drag.to = p.x;
            redraw(false);
            drawPreview(drag);
        } else if (drag.kind === "move") {
            const shift = p.x - drag.from;

            drag.lane.x0 = Math.max(0, drag.x0 + shift);
            drag.lane.x1 = Math.min(overlay.width, drag.x1 + shift);
            redraw(false);
        } else if (drag.kind === "edge") {
            drag.lane[drag.edge] = Math.max(0, Math.min(overlay.width, p.x));

            if (drag.lane.x1 - drag.lane.x0 < 6) drag.lane[drag.edge] = drag.edge === "x0" ? drag.lane.x1 - 6 : drag.lane.x0 + 6;

            redraw(false);
        } else if (drag.kind === "band") {
            drag.band.y = Math.max(0, Math.min(overlay.height, Math.round(p.y * 10) / 10));
            drag.band.auto = false;
            redraw(false);
        }
    });

    function drawPreview(drag) {
        const ctx = overlay.getContext("2d");
        const x0 = Math.min(drag.from, drag.to);

        ctx.fillStyle = "rgba(29,78,216,.18)";
        ctx.fillRect(x0, 0, Math.abs(drag.to - drag.from), overlay.height);
    }

    function endDrag() {
        const drag = S.drag;

        S.drag = null;

        if (!drag) return;

        if (drag.kind === "new") {
            const width = Math.abs(drag.to - drag.from);
            const typical = S.lanes.length ? S.lanes.reduce((sum, lane) => sum + lane.x1 - lane.x0, 0) / S.lanes.length : overlay.width / 14;
            const center = (drag.from + drag.to) / 2;
            const half = (width < 8 ? typical : width) / 2;

            addLane(Math.max(0, center - half), Math.min(overlay.width, center + half));
        }

        S.lanes.sort((a, b) => a.x0 - b.x0);
        changed();
    }

    overlay.addEventListener("pointerup", endDrag);
    overlay.addEventListener("pointercancel", endDrag);
    overlay.addEventListener("keydown", event => {
        if ((event.key === "Delete" || event.key === "Backspace") && S.sel) {
            event.preventDefault();
            removeSelected();
        }
    });

    function removeSelected() {
        if (!S.sel) return;

        if (S.sel.type === "band") {
            S.bands = S.bands.filter(band => band.id !== S.sel.id);
        } else {
            removeLane(S.sel.id);
        }

        S.sel = null;
        changed();
    }

    function removeLane(id) {
        S.lanes = S.lanes.filter(lane => lane.id !== id);
        S.bands = S.bands.filter(band => band.lane !== id);

        if (S.ladderLane === id) {
            S.ladderLane = null;
            S.cal = [];
            S.calStep = 0;
        }
    }

    /* ---------- side panel ---------- */

    function setMode(mode) {
        S.mode = mode;
        Object.entries(modeButtons).forEach(([key, node]) => {
            node.classList.toggle("is-active", key === mode);
            node.setAttribute("aria-pressed", String(key === mode));
        });
        hint.textContent = {
            lanes: S.work ? "Drag across the gel to draw a lane for each well. Drag a lane to move it, its edges to resize. Mark which lane holds the size marker." : "Load a photo or draw a simulated gel to start.",
            ladder: "Click the marker bands from the largest to the smallest. The next size is shown in the Marker card.",
            bands: "Click in a sample lane to read a band. Drag a mark to move it; Delete removes it.",
        }[mode];
        redraw(false);
    }

    function changed() {
        redraw(false);
    }

    function updateSide() {
        lanesBox.replaceChildren(el("div", "mwg-cardtitle", "Lanes · " + S.lanes.length));

        if (!S.lanes.length) {
            lanesBox.append(el("p", "mwg-muted", "No lanes yet. In Lanes mode, drag across the gel."));
        }

        S.lanes.forEach(lane => {
            const row = el("div", "mwg-lane" + (S.sel && S.sel.id === lane.id ? " is-selected" : ""));
            const name = el("input", "mwp-cell");
            const marker = el("input");
            const expect = el("select", "mwp-select");
            const remove = el("button", "mwp-icon", "✕");

            name.value = lane.name;
            name.addEventListener("change", () => {
                lane.name = name.value.trim() || lane.name;
                changed();
            });
            name.addEventListener("keydown", event => event.stopPropagation());
            marker.type = "radio";
            marker.name = "mwg-marker";
            marker.checked = lane.id === S.ladderLane;
            marker.title = "This lane holds the size marker";
            marker.addEventListener("change", () => {
                S.ladderLane = lane.id;
                S.bands = S.bands.filter(band => band.lane !== lane.id);
                S.cal = [];
                S.calStep = 0;
                changed();
            });
            [["none", "no comparison"], ["uncut", "expect uncut"], ["digest", "expect Digest"]].forEach(([value, text]) => {
                const option = el("option", "", text);

                option.value = value;
                expect.append(option);
            });
            expect.value = lane.expect;
            expect.disabled = lane.id === S.ladderLane;
            expect.addEventListener("change", () => {
                lane.expect = expect.value;
                changed();
            });
            remove.type = "button";
            remove.title = "Remove this lane";
            remove.addEventListener("click", () => {
                removeLane(lane.id);
                changed();
            });
            row.addEventListener("click", () => {
                S.sel = {type: "lane", id: lane.id};
                redraw(false);
            });
            row.append(labelled("Marker", marker), name, expect, remove);
            lanesBox.append(row);
        });

        const list = sizes();
        const next = list[S.calStep];

        calBox.replaceChildren(el("div", "mwg-cardtitle", "Marker · " + S.ladderName));
        calBox.append(el("p", "mwg-muted", S.cal.length >= 2
            ? S.cal.length + " of " + list.length + " bands marked. Sizes between marks are read on a log scale; * means outside the marked range."
            : "Mark at least two marker bands. Click Calibrate, then click the bands from the largest down."));

        if (next) calBox.append(el("p", "mwg-next", "Next band to click: " + next.toLocaleString("en-US") + " bp"));

        const actions = el("div", "mwg-exportrow");

        actions.append(
            button("Detect marker", "Find the marker bands automatically", detectLadder),
            button("Skip size", "This marker band is not visible; go to the next size", () => {
                if (S.calStep < list.length) S.calStep += 1;
                changed();
            }),
            button("Undo mark", "Remove the last marker mark", () => {
                if (S.cal.length) {
                    S.cal.pop();
                    S.calStep = Math.max(0, S.calStep - 1);
                }

                changed();
            }),
            button("Reset", "Remove all marker marks", () => {
                S.cal = [];
                S.calStep = 0;
                changed();
            }),
        );
        calBox.append(actions);

        const sens = el("input", "mwg-range");

        sens.type = "range";
        sens.min = "5";
        sens.max = "95";
        sens.value = String(S.sensitivity);
        sens.addEventListener("input", () => {
            S.sensitivity = Number(sens.value);
        });
        calBox.append(labelled("Detection sensitivity", sens));

        bandsBox.replaceChildren(el("div", "mwg-cardtitle", "Bands · " + S.bands.length));

        if (!S.bands.length) {
            bandsBox.append(el("p", "mwg-muted", S.cal.length >= 2 ? "Click in a sample lane, or use Detect bands." : "Calibrate the marker first to see sizes."));
        } else {
            const table = el("table", "mwp-table mwg-table");
            const header = el("tr");

            ["Lane", "Size (bp)", "Expected", "Δ"].forEach(text => header.append(el("th", "", text)));
            const thead = el("thead");

            thead.append(header);
            table.append(thead);

            const tbody = el("tbody");

            S.lanes.forEach(lane => {
                S.bands.filter(band => band.lane === lane.id).sort((a, b) => a.y - b.y).forEach(band => {
                    const reading = readBand(band);
                    const row = el("tr", S.sel && S.sel.id === band.id ? "is-selected" : "");
                    const delta = el("td", "", reading.match ? (reading.match.delta > 0 ? "+" : "") + reading.match.delta.toFixed(1) + "%" : "");

                    if (reading.match) delta.style.color = matchColor(reading.match.delta);

                    row.append(
                        el("td", "", lane.name),
                        el("td", "mwp-size", reading.size ? reading.size.toLocaleString("en-US") + (reading.extrapolated ? "*" : "") : "–"),
                        el("td", "mwp-size", reading.match ? reading.match.expected.toLocaleString("en-US") : ""),
                        delta,
                    );
                    row.addEventListener("click", () => {
                        S.sel = {type: "band", id: band.id};
                        redraw(false);
                    });
                    tbody.append(row);
                });
            });
            table.append(tbody);
            const wrap = el("div", "mwp-scroll mwg-tablewrap");

            wrap.append(table);
            bandsBox.append(wrap);
        }
    }

    /* ---------- demo gel ---------- */

    // Simulated gel: wells start at the left edge; the marker is lane 1, the
    // record and its digest (when a record is open) come next, then the lanes
    // added by hand. The number of wells is adjustable.
    function demoGel() {
        const workspace = window.BiobankMolecularWorkspace;
        const snapshot = workspace ? workspace.getSnapshot() : null;
        const digest = window.BiobankDigest;
        const ladder = LADDERS[S.ladderName] || LADDERS["1 kb"];
        const lanes = [{label: "M", bands: ladder, marker: true}];

        if (!snapshot && !S.sim.lanes.length) {
            S.sim.lanes = [
                {label: "Sample 1", bands: [3000, 1500, 500]},
                {label: "Sample 2", bands: [2000, 800]},
                {label: "Sample 3", bands: [4000, 1000, 250]},
            ];
            renderSim();
        }

        if (snapshot) {
            const fragments = digest ? digest.fragments().map(fragment => fragment.length) : [];

            lanes.push({label: "Uncut", bands: [snapshot.sequence.length]});
            lanes.push(fragments.length ? {label: digest.enzymes().join("+"), bands: fragments} : {label: "Digest", bands: []});
        }

        S.sim.lanes.forEach(lane => lanes.push({label: lane.label, bands: lane.bands}));

        const wells = Math.max(S.sim.wells, lanes.length);
        const pitch = 78;
        const laneW = 66;
        const width = Math.max(760, wells * pitch + 24);
        const height = 520;
        const canvas = newCanvas(width, height);
        const ctx = canvas.getContext("2d");
        const sizes = lanes.reduce((all, lane) => all.concat(lane.bands), []);
        const min = Math.max(20, Math.min.apply(null, sizes) * 0.7);
        const max = Math.max.apply(null, sizes) * 1.15;
        const top = Math.max.apply(null, sizes.concat([1]));

        ctx.fillStyle = "#101820";
        ctx.fillRect(0, 0, width, height);

        // Smear of noise, so detection works on something that looks like a photo.
        for (let i = 0; i < 2500; i++) {
            ctx.fillStyle = "rgba(255,255,255," + (Math.random() * 0.04).toFixed(3) + ")";
            ctx.fillRect(Math.random() * width, Math.random() * height, 2, 2);
        }

        // Every well is drawn, used or not, starting at the left corner.
        for (let index = 0; index < wells; index++) {
            const x = 12 + index * pitch;

            ctx.fillStyle = "#070D12";
            ctx.fillRect(x + 6, 40, laneW - 12, 8);
        }

        lanes.forEach((lane, index) => {
            const x = 12 + index * pitch;

            lane.bands.forEach(size => {
                const y = 70 + calc.gelPosition(size, min, max) * (height - 110);
                const strong = lane.marker ? 0.7 : Math.min(1, 0.45 + size / top * 0.5);
                const gradient = ctx.createLinearGradient(0, y - 7, 0, y + 7);

                gradient.addColorStop(0, "rgba(220,235,255,0)");
                gradient.addColorStop(0.5, "rgba(235,245,255," + strong + ")");
                gradient.addColorStop(1, "rgba(220,235,255,0)");
                ctx.fillStyle = gradient;
                ctx.fillRect(x + 8, y - 7, laneW - 16, 14);
            });
        });

        const sim = S.sim;

        loadBitmap(canvas);
        S.sim = sim;
        S.ladderName = LADDERS[S.ladderName] ? S.ladderName : "1 kb";
        ladderSelect.value = S.ladderName;
        hint.textContent = "Simulated gel with " + wells + " wells. Mark the lanes (drag), calibrate on the marker, then read the bands.";
        redraw(false);
    }

    /* ---------- simulated gel designer ---------- */

    function parseSizes(text) {
        return String(text || "").split(/[\s,;]+/).map(Number).filter(value => value > 0 && value < 1000000);
    }

    function renderSim() {
        const wells = el("input", "mwp-cell");
        const rows = el("div");

        wells.type = "number";
        wells.min = "4";
        wells.max = "30";
        wells.value = String(S.sim.wells);
        wells.addEventListener("change", () => {
            S.sim.wells = Math.max(4, Math.min(30, Number(wells.value) || 10));
            wells.value = String(S.sim.wells);
        });
        wells.addEventListener("keydown", event => event.stopPropagation());

        S.sim.lanes.forEach((lane, index) => {
            const row = el("div", "mwg-lane mwg-simrow");
            const label = el("input", "mwp-cell");
            const bands = el("input", "mwp-cell");
            const remove = el("button", "mwp-icon", "✕");

            label.value = lane.label;
            label.placeholder = "Lane name";
            bands.value = lane.bands.join(", ");
            bands.placeholder = "Sizes in bp, e.g. 3000, 1200, 400";
            label.addEventListener("change", () => {
                lane.label = label.value.trim() || lane.label;
            });
            bands.addEventListener("change", () => {
                lane.bands = parseSizes(bands.value);
                bands.value = lane.bands.join(", ");
            });
            [label, bands].forEach(node => node.addEventListener("keydown", event => event.stopPropagation()));
            remove.type = "button";
            remove.title = "Remove this lane";
            remove.addEventListener("click", () => {
                S.sim.lanes.splice(index, 1);
                renderSim();
            });
            row.append(label, bands, remove);
            rows.append(row);
        });

        const add = button("+ Lane", "Add a lane with the band sizes you want to see", () => {
            S.sim.lanes.push({label: "Sample " + (S.sim.lanes.length + 1), bands: []});
            renderSim();
        });
        const draw = button("Draw gel", "Draw the simulated gel from the marker, the lanes below and the number of wells", () => demoGel(), "mwp-btn is-primary");
        const actions = el("div", "mwg-exportrow");

        actions.append(add, draw);
        simBox.replaceChildren(
            el("div", "mwg-cardtitle", "Simulated gel"),
            labelled("Wells", wells),
            rows,
            actions,
        );
    }

    /* ---------- export ---------- */

    function download(name, blob) {
        const link = document.createElement("a");

        link.href = URL.createObjectURL(blob);
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
    }

    let nameOverride = "";

    function baseName() {
        if (nameOverride) return nameOverride.replace(/[^A-Za-z0-9._-]+/g, "_");

        const workspace = window.BiobankMolecularWorkspace;
        const snapshot = workspace ? workspace.getSnapshot() : null;

        return ((snapshot && snapshot.name) || "gel").replace(/[^A-Za-z0-9._-]+/g, "_");
    }

    function exportPng() {
        if (!S.work) return;

        const out = newCanvas(S.work.width + Math.round(S.work.width * 0.12), S.work.height);
        const ctx = out.getContext("2d");
        const font = Math.max(12, S.work.width / 70);

        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, out.width, out.height);
        ctx.drawImage(adjusted(S.work), 0, 0);

        const saved = {width: overlay.width, height: overlay.height};
        const layer = newCanvas(saved.width, saved.height);
        const sel = S.sel;

        S.sel = null;

        // drawOverlay paints onto the live overlay canvas; copy the result across.
        drawOverlay(overlay.getContext("2d"), font, Math.max(1, font / 8));
        layer.getContext("2d").drawImage(overlay, 0, 0);
        S.sel = sel;
        ctx.drawImage(layer, 0, 0);
        drawOverlay(overlay.getContext("2d"), Math.max(11, 13 / S.zoom), Math.max(1, 1.5 / S.zoom));
        out.toBlob(blob => download(baseName() + "_gel_annotated.png", blob), "image/png");
    }

    function tableRows() {
        const rows = [["lane", "band", "size_bp", "extrapolated", "expected_bp", "delta_percent"]];

        S.lanes.forEach(lane => {
            S.bands.filter(band => band.lane === lane.id).sort((a, b) => a.y - b.y).forEach((band, index) => {
                const reading = readBand(band);

                rows.push([lane.name, index + 1, reading.size || "", reading.extrapolated ? "yes" : "", reading.match ? reading.match.expected : "", reading.match ? reading.match.delta.toFixed(1) : ""]);
            });
        });

        return rows;
    }

    function exportCsv() {
        const cell = value => (/[",\n]/.test(String(value)) ? '"' + String(value).replace(/"/g, '""') + '"' : String(value));

        download(baseName() + "_gel_bands.csv", new Blob([tableRows().map(row => row.map(cell).join(",")).join("\n") + "\n"], {type: "text/csv"}));
    }

    function copyTable() {
        if (navigator.clipboard) navigator.clipboard.writeText(tableRows().map(row => row.join("\t")).join("\n")).catch(() => {});

        hint.textContent = "Band table copied.";
    }

    /* ---------- events ---------- */

    fileInput.addEventListener("change", () => {
        loadFile(fileInput.files[0]);
        fileInput.value = "";
    });
    ladderSelect.addEventListener("change", () => {
        S.ladderName = ladderSelect.value;
        S.cal = [];
        S.calStep = 0;
        changed();
    });
    ["dragenter", "dragover"].forEach(type => stage.addEventListener(type, event => {
        event.preventDefault();
        stage.classList.add("is-drop");
    }));
    ["dragleave", "drop"].forEach(type => stage.addEventListener(type, event => {
        event.preventDefault();
        stage.classList.remove("is-drop");

        if (type === "drop" && event.dataTransfer.files.length) loadFile(event.dataTransfer.files[0]);
    }));
    document.addEventListener("paste", event => {
        if (pane.hidden) return;

        const item = Array.from(event.clipboardData ? event.clipboardData.items : []).find(entry => /^image\//.test(entry.type));

        if (item) loadFile(item.getAsFile());
    });
    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail.layout === "gel") {
            window.requestAnimationFrame(() => {
                setMode(S.mode);
                updateSide();

                if (S.work && S.zoom === 1) fit();
            });
        }
    });
    root.addEventListener("biobank:molecular-workspace-change", () => {
        if (!pane.hidden && !frame) {
            frame = window.requestAnimationFrame(() => {
                frame = 0;
                updateSide();
                redraw(false);
            });
        }
    });
    document.addEventListener("biobank:digest-change", () => {
        if (!pane.hidden) redraw(false);
    });

    const STATE_KEYS = ["rot", "fine", "bright", "contrast", "invert", "zoom", "lanes", "bands", "cal", "calStep", "ladderName", "ladderLane", "nextId", "sensitivity", "sim"];

    function getState() {
        const out = {};

        STATE_KEYS.forEach(key => {
            out[key] = S[key];
        });

        return JSON.parse(JSON.stringify(out));
    }

    function applyState(state) {
        if (!state || typeof state !== "object") return;

        STATE_KEYS.forEach(key => {
            if (state[key] !== undefined) S[key] = JSON.parse(JSON.stringify(state[key]));
        });
        if (!LADDERS[S.ladderName]) S.ladderName = "1 kb";
        ["bright", "contrast", "fine", "zoom"].forEach(key => {
            sliders[key].value = String(S[key]);
        });
        invertBox.checked = !!S.invert;
        ladderSelect.value = S.ladderName;
        if (!S.sim || !Array.isArray(S.sim.lanes)) S.sim = {wells: 10, lanes: []};
        renderSim();
    }

    // Load a stored photo and then restore the marks made on it.
    function loadUrl(url, state) {
        return new Promise((resolve, reject) => {
            const image = new Image();

            image.onload = () => {
                const scale = Math.min(1, MAX_SIDE / Math.max(image.width, image.height));
                const canvas = newCanvas(image.width * scale, image.height * scale);

                canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
                S.source = canvas;
                applyState(state);
                rebuild();

                if (!state || !state.zoom) fit();
                else layout();

                setMode("lanes");
                resolve();
            };
            image.onerror = () => reject(new Error("The stored photo could not be read."));
            image.src = url;
        });
    }

    window.BiobankGel = {
        getState,
        setState: state => {
            applyState(state);
            if (S.source) rebuild();
            else redraw(false);
        },
        loadUrl,
        loadFile,
        hasPhoto: () => !!S.source,
        photoBlob: () => new Promise(resolve => {
            if (!S.source) resolve(null);
            else S.source.toBlob(blob => resolve(blob), "image/png");
        }),
        setName: value => {
            nameOverride = String(value || "");
        },
        refresh: () => {
            setMode(S.mode);
            updateSide();

            if (S.work && S.zoom === 1) fit();
        },
        state: () => ({lanes: S.lanes.length, bands: S.bands.length, calibrated: S.cal.length >= 2}),
        loadCanvas: canvas => loadBitmap(canvas),
        demo: demoGel,
        addLane: (x0, x1) => {
            addLane(x0, x1);
            changed();
        },
        readings: () => S.bands.map(band => Object.assign({}, readBand(band), {lane: (laneById(band.lane) || {}).name})),
    };

    renderSim();
    setMode("lanes");
    redraw(true);
}());
