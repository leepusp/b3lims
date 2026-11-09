/*
 * Plasmid assembly window: join parts in order, with or without overlaps, and
 * save the result as a registry record. It needs no open vector: parts are
 * pasted or taken from the registry (a whole record or a range of it).
 */
(function () {
    "use strict";

    const host = document.getElementById("tw-assembly");
    const page = document.getElementById("tool-workbench");

    if (!host || !page) return;

    const COLORS = ["#1D4ED8", "#D9480F", "#2B8A3E", "#9C36B5", "#C2255C", "#0B7285", "#E67700", "#495057"];
    const COMP = {A: "T", T: "A", G: "C", C: "G", U: "A", N: "N", R: "Y", Y: "R", K: "M", M: "K", S: "S", W: "W", B: "V", V: "B", D: "H", H: "D"};
    const S = {parts: [], method: "overlap", minOverlap: 15, circular: true, nextId: 1};

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function btn(text, title, onClick, className) {
        const node = el("button", "tw-btn" + (className ? " " + className : ""), text);

        node.type = "button";
        node.title = title || "";
        node.addEventListener("click", onClick);

        return node;
    }

    const clean = text => String(text || "").replace(/^>.*$/gm, "").replace(/[^A-Za-z]/g, "").toUpperCase();
    const revcomp = seq => seq.split("").reverse().map(base => COMP[base] || "N").join("");
    const partSeq = part => (part.rc ? revcomp(part.seq) : part.seq);

    function gc(seq) {
        const n = seq.replace(/[^ACGT]/g, "").length;

        return n ? Math.round((seq.split("").filter(base => base === "G" || base === "C").length / n) * 1000) / 10 : 0;
    }

    function overlapLength(left, right, min) {
        const max = Math.min(left.length, right.length, 120);

        for (let n = max; n >= min; n -= 1) {
            if (left.slice(left.length - n) === right.slice(0, n)) return n;
        }

        return 0;
    }

    // Join the parts; `junctions[i]` describes the join of part i to part i+1 (the last one wraps).
    function assemble() {
        const parts = S.parts.filter(part => part.seq);
        const junctions = [];
        const spans = [];
        let result = "";

        parts.forEach((part, index) => {
            const seq = partSeq(part);
            let skip = 0;

            if (index > 0 && S.method === "overlap") {
                skip = overlapLength(result, seq, S.minOverlap);
            }

            if (index > 0) {
                junctions.push({from: parts[index - 1].name, to: part.name, overlap: skip, ok: S.method === "direct" || skip > 0});
            }

            spans.push({name: part.name, start: result.length, end: result.length + seq.length - skip, id: part.id});
            result += seq.slice(skip);
        });

        if (S.circular && parts.length > 1) {
            const first = partSeq(parts[0]);
            let wrap = 0;

            if (S.method === "overlap") {
                wrap = overlapLength(result, first, S.minOverlap);

                if (wrap > 0) result = result.slice(0, result.length - wrap);
            }

            junctions.push({from: parts[parts.length - 1].name, to: parts[0].name + " (closing)", overlap: wrap, ok: S.method === "direct" || wrap > 0});
        }

        return {seq: result, junctions, spans};
    }

    /* ---------- skeleton ---------- */

    const listBox = el("div");
    const addBox = el("div");
    const optBox = el("div", "tw-row");
    const outBox = el("div");
    const note = el("p", "tw-note");

    host.append(optBox, listBox, addBox, outBox, note);

    const methodSel = el("select");

    [["overlap", "Overlap (Gibson / HiFi / SLiC)"], ["direct", "Direct join (ligation, no overlap)"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        methodSel.append(option);
    });
    methodSel.addEventListener("change", () => {
        S.method = methodSel.value;
        changed();
    });

    const minInput = el("input");

    minInput.type = "number";
    minInput.min = "8";
    minInput.max = "80";
    minInput.addEventListener("change", () => {
        S.minOverlap = Math.max(8, Math.min(80, Number(minInput.value) || 15));
        changed();
    });

    const circBox = el("input");

    circBox.type = "checkbox";
    circBox.addEventListener("change", () => {
        S.circular = circBox.checked;
        changed();
    });

    function field(text, node) {
        const wrap = el("label", "tw-field");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    const circWrap = field("Circular product", circBox);

    circWrap.style.flex = "0 0 auto";
    minInput.style.width = "5rem";
    optBox.append(field("Method", methodSel), field("Min. overlap (bp)", minInput), circWrap);

    /* ---------- parts ---------- */

    function addPart(name, seq, recordId) {
        const cleaned = clean(seq);

        if (!cleaned) return false;

        S.parts.push({id: S.nextId++, name: name || ("Part " + S.nextId), seq: cleaned, rc: false, recordId: recordId || null});
        changed();

        return true;
    }

    function move(index, delta) {
        const target = index + delta;

        if (target < 0 || target >= S.parts.length) return;

        const [item] = S.parts.splice(index, 1);

        S.parts.splice(target, 0, item);
        changed();
    }

    function renderList() {
        listBox.replaceChildren();

        if (!S.parts.length) {
            listBox.append(el("p", "tw-note", "No parts yet. Paste a sequence or pick one from the registry below."));

            return;
        }

        const table = el("table", "tw-table");
        const head = el("tr");

        ["#", "Name", "Length", "Reverse", ""].forEach(label => head.append(el("th", "", label)));
        table.append(head);

        S.parts.forEach((part, index) => {
            const row = el("tr");
            const name = el("input");
            const rc = el("input");
            const actions = el("td");

            name.value = part.name;
            name.addEventListener("change", () => {
                part.name = name.value.trim() || part.name;
                changed();
            });
            rc.type = "checkbox";
            rc.checked = part.rc;
            rc.title = "Use the reverse complement of this part";
            rc.addEventListener("change", () => {
                part.rc = rc.checked;
                changed();
            });
            actions.append(
                btn("↑", "Move up", () => move(index, -1)),
                btn("↓", "Move down", () => move(index, 1)),
                btn("✕", "Remove part", () => {
                    S.parts.splice(index, 1);
                    changed();
                }, "is-danger"),
            );

            const swatch = el("td");
            const dot = el("span", "", "■ " + (index + 1));

            dot.style.color = COLORS[index % COLORS.length];
            swatch.append(dot);

            const nameCell = el("td");
            const rcCell = el("td");
            const lenCell = el("td", "tw-mono", part.seq.length.toLocaleString("en-US") + " bp");

            nameCell.append(name);
            rcCell.append(rc);
            row.append(swatch, nameCell, lenCell, rcCell, actions);
            table.append(row);
        });

        listBox.append(table);
    }

    /* ---------- add parts ---------- */

    const pasteName = el("input");
    const pasteSeq = el("textarea");
    const search = el("input");
    const results = el("div", "tw-results");
    const rangeFrom = el("input");
    const rangeTo = el("input");

    pasteName.placeholder = "Part name";
    pasteSeq.rows = 3;
    pasteSeq.placeholder = "Paste DNA (FASTA headers and spaces are ignored)";
    pasteSeq.spellcheck = false;
    search.placeholder = "Search the registry (DNA, plasmid, insert, primer)…";
    rangeFrom.placeholder = "from";
    rangeTo.placeholder = "to";
    rangeFrom.type = rangeTo.type = "number";
    rangeFrom.min = rangeTo.min = "1";
    results.hidden = true;

    const addPaste = btn("Add pasted part", "Add the pasted sequence as the next part", () => {
        if (addPart(pasteName.value.trim(), pasteSeq.value)) {
            pasteName.value = "";
            pasteSeq.value = "";
        } else {
            note.textContent = "Paste a DNA sequence first.";
        }
    }, "is-primary");

    const rangeRow = el("div", "tw-row");

    rangeFrom.style.width = rangeTo.style.width = "6rem";
    rangeRow.append(el("span", "tw-note", "Optional range of the registry record (1-based, inclusive):"), rangeFrom, rangeTo);

    addBox.append(
        el("div", "tw-note", "Add a part"),
        field("Name", pasteName),
        field("Sequence", pasteSeq),
        addPaste,
        el("hr"),
        field("From the registry", search),
        rangeRow,
        results,
    );

    let searchTimer = 0;

    search.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(async () => {
            const query = search.value.trim();

            results.replaceChildren();

            if (!query) {
                results.hidden = true;

                return;
            }

            const response = await fetch(page.dataset.searchUrl + "?q=" + encodeURIComponent(query), {credentials: "same-origin"});
            const found = response.ok ? (await response.json()).results || [] : [];

            results.hidden = false;

            if (!found.length) results.append(el("p", "tw-note", "No records found."));

            found.forEach(record => {
                const row = el("button");
                const type = record.sequence_type || record.type || "";

                row.type = "button";
                row.append(el("span", "", record.name), el("span", "tw-note", type));
                row.addEventListener("click", async () => {
                    const url = page.dataset.recordUrl.replace("/0/", "/" + record.id + "/");
                    const detail = await fetch(url, {credentials: "same-origin"});

                    if (!detail.ok) {
                        note.textContent = "That record could not be read.";

                        return;
                    }

                    const data = await detail.json();
                    const from = Math.max(1, Number(rangeFrom.value) || 1);
                    const to = Math.min(data.sequence.length, Number(rangeTo.value) || data.sequence.length);
                    const seq = data.sequence.slice(from - 1, to);
                    const label = from === 1 && to === data.sequence.length ? data.name : data.name + " " + from + "-" + to;

                    addPart(label, seq, data.id);
                    results.hidden = true;
                    search.value = "";
                });
                results.append(row);
            });
        }, 250);
    });

    /* ---------- result ---------- */

    function diagram(out) {
        const total = Math.max(1, out.seq.length);
        const width = 640;
        const ns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(ns, "svg");

        svg.setAttribute("viewBox", "0 0 " + width + " 46");
        svg.setAttribute("width", "100%");
        svg.style.maxWidth = "640px";
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Assembled parts in order");
        out.spans.forEach((span, index) => {
            const x = (span.start / total) * width;
            const w = Math.max(2, ((span.end - span.start) / total) * width);
            const rect = document.createElementNS(ns, "rect");
            const label = document.createElementNS(ns, "text");

            rect.setAttribute("x", x.toFixed(1));
            rect.setAttribute("y", "6");
            rect.setAttribute("width", w.toFixed(1));
            rect.setAttribute("height", "26");
            rect.setAttribute("rx", "4");
            rect.setAttribute("fill", COLORS[index % COLORS.length]);
            label.setAttribute("x", (x + w / 2).toFixed(1));
            label.setAttribute("y", "23");
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("font-size", "11");
            label.setAttribute("fill", "#fff");
            label.textContent = w > 46 ? span.name.slice(0, Math.floor(w / 7)) : "";
            svg.append(rect, label);
        });

        return svg;
    }

    function fasta(out) {
        const name = (document.getElementById("tw-name").value || "assembly").replace(/[^A-Za-z0-9._-]+/g, "_");

        return {name, text: ">" + name + "\n" + (out.seq.match(/.{1,70}/g) || []).join("\n") + "\n"};
    }

    function download(filename, text) {
        const link = document.createElement("a");

        link.href = URL.createObjectURL(new Blob([text], {type: "text/plain"}));
        link.download = filename;
        document.body.append(link);
        link.click();
        link.remove();
    }

    async function saveToRegistry(out) {
        const defaultName = document.getElementById("tw-name").value || "Assembly";
        const name = window.prompt("Name of the new registry record", defaultName);

        if (!name) return;

        const form = new FormData();
        const token = (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";

        form.append("csrfmiddlewaretoken", token);
        form.append("name", name.trim());
        form.append("sequence_type", S.circular ? "plasmid" : "dna");
        form.append("topology", S.circular ? "circular" : "linear");
        form.append("description", "Assembled from " + S.parts.map(part => part.name).join(" + "));
        form.append("type_confirmation", "confirmed");
        form.append("sequence", out.seq);

        const response = await fetch(page.dataset.registryUrl, {method: "POST", body: form, credentials: "same-origin", headers: {"X-CSRFToken": token}});

        if (response.redirected && /molecular-registry\/\d+\//.test(response.url)) {
            note.textContent = "Saved to the registry.";
            window.open(response.url, "_blank", "noopener");
        } else {
            note.textContent = "The registry did not accept the new record. Check the name and the sequence.";
        }
    }

    function renderOut() {
        outBox.replaceChildren();

        const out = assemble();

        if (!out.seq) return;

        const summary = el("p", "tw-note", out.seq.length.toLocaleString("en-US") + " bp · GC " + gc(out.seq) + "% · " + (S.circular ? "circular" : "linear") + " · " + out.spans.length + " part" + (out.spans.length === 1 ? "" : "s"));

        outBox.append(el("div", "tw-note", "Result"), diagram(out), summary);

        if (out.junctions.length) {
            const table = el("table", "tw-table");
            const head = el("tr");

            ["Junction", "Overlap", ""].forEach(label => head.append(el("th", "", label)));
            table.append(head);
            out.junctions.forEach(junction => {
                const row = el("tr");
                const status = el("td", junction.ok ? "tw-ok" : "tw-bad", S.method === "direct" ? "joined" : (junction.ok ? "overlap found" : "no overlap ≥ " + S.minOverlap + " bp"));

                row.append(el("td", "", junction.from + " → " + junction.to), el("td", "tw-mono", S.method === "direct" ? "—" : junction.overlap + " bp"), status);
                table.append(row);
            });
            outBox.append(table);
        }

        const actions = el("div", "tw-row");

        actions.append(
            btn("Download FASTA", "Download the assembled sequence", () => {
                const f = fasta(out);

                download(f.name + ".fasta", f.text);
            }),
            btn("Copy sequence", "Copy the assembled sequence", () => {
                if (navigator.clipboard) navigator.clipboard.writeText(out.seq).catch(() => {});

                note.textContent = "Sequence copied.";
            }),
            btn("Save to registry…", "Create a registry record from this assembly", () => saveToRegistry(out), "is-primary"),
        );
        outBox.append(actions);
    }

    function render() {
        methodSel.value = S.method;
        minInput.value = String(S.minOverlap);
        circBox.checked = S.circular;
        minInput.disabled = S.method === "direct";
        renderList();
        renderOut();
    }

    function changed() {
        render();
        document.dispatchEvent(new CustomEvent("biobank:assembly-change"));
    }

    window.BiobankAssembly = {
        getState: () => JSON.parse(JSON.stringify(S)),
        setState: state => {
            if (!state || typeof state !== "object") return;

            if (Array.isArray(state.parts)) {
                S.parts = state.parts
                    .map(part => ({id: Number(part.id) || 0, name: String(part.name || "Part"), seq: clean(part.seq), rc: !!part.rc, recordId: part.recordId || null}))
                    .filter(part => part.seq);
            }

            if (state.method === "direct" || state.method === "overlap") S.method = state.method;

            S.minOverlap = Math.max(8, Math.min(80, Number(state.minOverlap) || 15));
            S.circular = state.circular !== false;
            S.nextId = Math.max(Number(state.nextId) || 1, S.parts.reduce((max, part) => Math.max(max, part.id), 0) + 1);
            render();
        },
        addPart,
        assemble,
    };

    render();
}());
