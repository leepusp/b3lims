/*
 * Primers window: check primers and simulate a PCR on the open record.
 *
 * - Each primer gets length, Tm (nearest neighbour), GC, 3' clamp, runs, the
 *   longest hairpin stem and self-dimer, and its binding sites on the record.
 * - Pick a forward and a reverse primer to see the products: size, range,
 *   sequence (with the primer tails), a small gel, and the cross-dimer check.
 * - On a primer record the record itself is the first primer.
 *
 * The dimer and hairpin numbers are screening estimates (longest
 * complementary stretch), not free energies.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const pane = document.getElementById("mw-primers");
    const calc = window.BiobankMolecularCalc;
    const digestCalc = window.BiobankDigestCalc;

    if (!root || !pane || !calc) {
        return;
    }

    const STORE = "biobank.primers.v1:" + window.location.pathname;
    const SEED = 12;
    const COMP = {A: "T", T: "A", G: "C", C: "G", N: "N", R: "Y", Y: "R", K: "M", M: "K", S: "S", W: "W", B: "V", V: "B", D: "H", H: "D"};
    const MASS = {A: 313.21, C: 289.18, G: 329.21, T: 304.2};
    const ui = {minMatch: 15, selected: null, fwd: "", rev: "", paste: false, maxProduct: 20000};
    let primers = [];
    let nextId = 1;
    let frame = 0;

    const api = () => window.BiobankMolecularWorkspace || null;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function button(text, title, onClick, className) {
        const node = el("button", className || "mwp-btn", text);

        node.type = "button";
        node.title = title || "";
        node.addEventListener("click", onClick);

        return node;
    }

    const clean = text => String(text || "").toUpperCase().replace(/U/g, "T").replace(/[^ACGTNRYKMSWBDHV]/g, "");
    const rc = text => Array.from(text).reverse().map(base => COMP[base] || "N").join("");
    const gcPercent = text => (text.length ? Math.round((text.match(/[GC]/g) || []).length / text.length * 1000) / 10 : 0);

    /* ---------- storage ---------- */

    function save() {
        try {
            window.localStorage.setItem(STORE, JSON.stringify(primers.filter(item => !item.self).map(item => ({name: item.name, seq: item.seq}))));
        } catch (error) {
            // Not persisted; fine.
        }
    }

    function load() {
        try {
            JSON.parse(window.localStorage.getItem(STORE) || "[]").forEach(item => {
                if (item && item.seq) primers.push({id: nextId++, name: String(item.name || "primer"), seq: clean(item.seq)});
            });
        } catch (error) {
            // Nothing stored or unreadable.
        }
    }

    function addPrimer(name, seq) {
        const sequence = clean(seq);

        if (sequence.length < 6) return null;

        const item = {id: nextId++, name: name || "primer " + (primers.length + 1), seq: sequence};

        primers.push(item);
        save();

        return item;
    }

    // "name sequence" per line, or FASTA.
    function parseList(text) {
        const found = [];
        let current = null;

        String(text).split(/\r?\n/).forEach(line => {
            const row = line.trim();

            if (!row) return;

            if (row[0] === ">") {
                current = {name: row.slice(1).trim(), seq: ""};
                found.push(current);
            } else if (current && /^[A-Za-z\s]+$/.test(row)) {
                current.seq += row;
            } else {
                const parts = row.split(/[\s,;\t]+/).filter(Boolean);
                const last = parts[parts.length - 1] || "";

                current = null;

                if (parts.length >= 2) found.push({name: parts.slice(0, -1).join(" "), seq: last});
                else found.push({name: "", seq: last});
            }
        });

        return found;
    }

    /* ---------- analysis ---------- */

    function longestComplement(a, b) {
        // Longest stretch of `a` that pairs with `b` read in the opposite direction.
        const other = rc(b);
        let best = {length: 0, at: 0};
        let previous = new Array(other.length + 1).fill(0);

        for (let i = 1; i <= a.length; i++) {
            const row = new Array(other.length + 1).fill(0);

            for (let j = 1; j <= other.length; j++) {
                if (a[i - 1] === other[j - 1]) {
                    row[j] = previous[j - 1] + 1;

                    if (row[j] > best.length) best = {length: row[j], at: i - row[j]};
                }
            }

            previous = row;
        }

        return {length: best.length, at: best.at, threePrime: best.length > 0 && best.at + best.length === a.length};
    }

    function hairpin(seq) {
        let best = 0;

        for (let size = Math.min(12, Math.floor(seq.length / 2)); size >= 3; size--) {
            for (let i = 0; i + size <= seq.length; i++) {
                const stem = seq.slice(i, i + size);
                const at = seq.indexOf(rc(stem), i + size + 3);

                if (at >= 0) {
                    best = size;
                    break;
                }
            }

            if (best) break;
        }

        return best;
    }

    function weight(seq) {
        let total = -61.96;

        for (const base of seq) total += MASS[base] || 308;

        return Math.round(total * 10) / 10;
    }

    function analyse(seq) {
        const tm = calc.meltingTemperature(seq);
        const checks = calc.primerChecks(seq);
        const self = longestComplement(seq, seq);
        const notes = [];

        if (seq.length < 18) notes.push("short (< 18 nt)");
        if (seq.length > 35) notes.push("long (> 35 nt)");

        const gc = gcPercent(seq);

        if (gc < 40 || gc > 60) notes.push("GC " + gc + "% outside 40–60%");
        if (checks.clampGc > 3) notes.push("GC clamp too strong (" + checks.clampGc + " of last 5)");
        else if (!checks.endsWithGc) notes.push("3′ end is A/T");
        if (checks.longestRun >= 4) notes.push("run of " + checks.longestRun + " identical bases");
        if (tm !== null && (tm < 50 || tm > 68)) notes.push("Tm " + tm.toFixed(1) + " °C is unusual");

        const stem = hairpin(seq);

        if (stem >= 5) notes.push("hairpin stem of " + stem + " nt");
        if (self.length >= 5 || (self.threePrime && self.length >= 4)) notes.push("self-dimer of " + self.length + " nt" + (self.threePrime ? " at the 3′ end" : ""));

        return {length: seq.length, tm, gc, clamp: checks.clampGc, run: checks.longestRun, stem, self, mass: weight(seq), notes};
    }

    /* ---------- binding sites ---------- */

    // Sites where the 3' end of the primer anneals; `matched` counts the contiguous
    // 3' bases that pair, the rest of the primer is a tail.
    function findSites(primer, sequence, circular) {
        const seq = sequence;
        const n = seq.length;
        const sites = [];

        if (primer.length < SEED || !n) return sites;

        const text = circular ? seq + seq.slice(0, primer.length) : seq;
        const seedF = primer.slice(-SEED);
        const seedR = rc(seedF);
        const reverse = rc(primer);
        const seen = new Set();

        const scan = (needle, handler) => {
            let from = text.indexOf(needle);

            while (from >= 0) {
                if (from < n) handler(from);

                from = text.indexOf(needle, from + 1);
            }
        };

        scan(seedF, at => {
            let matched = SEED;

            while (matched < primer.length && at - (matched - SEED) - 1 >= (circular ? -n : 0)
                && primer[primer.length - matched - 1] === text[(at - (matched - SEED) - 1 + text.length) % text.length]) {
                matched += 1;
            }

            const start = at - (matched - SEED);

            if (matched >= ui.minMatch) {
                const key = "+" + ((start % n) + n) % n;

                if (!seen.has(key)) {
                    seen.add(key);
                    sites.push({strand: "+", start: ((start % n) + n) % n + 1, end: ((start + matched - 1) % n) + 1, matched, tail: primer.length - matched});
                }
            }
        });
        scan(seedR, at => {
            let matched = SEED;

            while (matched < primer.length && reverse[matched] === text[(at + matched) % text.length] && at + matched < text.length) {
                matched += 1;
            }

            if (matched >= ui.minMatch) {
                const key = "-" + at;

                if (!seen.has(key)) {
                    seen.add(key);
                    sites.push({strand: "-", start: at + 1, end: ((at + matched - 1) % n) + 1, matched, tail: primer.length - matched});
                }
            }
        });

        return sites.sort((a, b) => a.start - b.start);
    }

    function slice(sequence, start, end, circular) {
        if (start <= end) return sequence.slice(start - 1, end);

        return circular ? sequence.slice(start - 1) + sequence.slice(0, end) : "";
    }

    function products(fwd, rev, snapshot) {
        const sequence = snapshot.sequence;
        const circular = snapshot.topology === "circular";
        const n = sequence.length;
        const found = [];

        findSites(fwd.seq, sequence, circular).filter(site => site.strand === "+").forEach(f => {
            findSites(rev.seq, sequence, circular).filter(site => site.strand === "-").forEach(r => {
                let span = r.end - f.start + 1;

                if (span <= 0) {
                    if (!circular) return;

                    span += n;
                }

                const inner = slice(sequence, f.start, r.end, circular);
                const tailF = fwd.seq.slice(0, f.tail);
                const tailR = rc(rev.seq.slice(0, r.tail));
                const amplicon = tailF + inner + tailR;

                if (amplicon.length > ui.maxProduct || !inner) return;

                found.push({f, r, size: amplicon.length, amplicon, start: f.start, end: r.end});
            });
        });

        return found.sort((a, b) => a.size - b.size);
    }

    /* ---------- gel preview ---------- */

    function gelSvg(sizes) {
        const NS = "http://www.w3.org/2000/svg";
        const ladder = digestCalc ? digestCalc.LADDER : [10000, 5000, 3000, 2000, 1500, 1000, 500];
        const width = 150;
        const height = 190;
        const top = 22;
        const usable = height - top - 10;
        const node = document.createElementNS(NS, "svg");
        const y = size => top + digestCalc.gelPosition(size, 250, 12000) * usable;
        const add = (tag, attrs, text) => {
            const child = document.createElementNS(NS, tag);

            Object.entries(attrs).forEach(([key, value]) => child.setAttribute(key, String(value)));

            if (text !== undefined) child.textContent = text;

            node.append(child);
        };

        node.setAttribute("viewBox", "0 0 " + width + " " + height);
        node.setAttribute("class", "mwpr-gel");
        add("rect", {x: 0, y: 0, width, height, rx: 6, fill: "#12202E"});
        add("text", {x: 52, y: 14, "text-anchor": "middle", "font-size": 9, fill: "#9FB3C8"}, "Ladder");
        add("text", {x: 110, y: 14, "text-anchor": "middle", "font-size": 9, fill: "#9FB3C8"}, "PCR");
        ladder.forEach(size => {
            add("rect", {x: 34, y: y(size) - 1.5, width: 36, height: 3, rx: 1, fill: "#C8D6E5", opacity: 0.8});
            add("text", {x: 31, y: y(size) + 3, "text-anchor": "end", "font-size": 7, fill: "#9FB3C8"}, size >= 1000 ? size / 1000 + "k" : size);
        });
        sizes.forEach(size => add("rect", {x: 92, y: y(size) - 2.5, width: 36, height: 5, rx: 1.5, fill: "#EAF2FA"}));

        return node;
    }

    /* ---------- skeleton ---------- */

    const head = el("div", "mwp-head");
    const title = el("strong", "mwp-title", "Primers");
    const minSelect = el("select", "mwp-select");
    const pasteBox = el("div", "mwpr-paste");
    const pasteArea = el("textarea", "mwpr-area");
    const listBox = el("div", "mwp-scroll mwpr-list");
    const sitesBox = el("div", "mwpr-card");
    const pcrBox = el("div", "mwpr-card");
    const note = el("p", "mwp-note");

    [[12, "≥ 12 nt 3′ match"], [15, "≥ 15 nt 3′ match"], [18, "≥ 18 nt 3′ match"], [22, "≥ 22 nt 3′ match"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = String(value);
        minSelect.append(option);
    });
    minSelect.value = String(ui.minMatch);
    minSelect.setAttribute("aria-label", "How much of the 3′ end must pair to count as a binding site");
    pasteArea.placeholder = "One primer per line: name sequence   (or FASTA)\nFwd_T7 TAATACGACTCACTATAGGG\nRev_T7term GCTAGTTATTGCTCAGCGG";
    pasteArea.rows = 4;
    pasteArea.setAttribute("aria-label", "Primers to add");
    pasteBox.hidden = true;
    pasteBox.append(pasteArea, el("div", "mwpr-row"));
    pasteBox.lastChild.append(
        button("Add primers", "Add the primers typed above", () => {
            parseList(pasteArea.value).forEach(item => addPrimer(item.name, item.seq));
            pasteArea.value = "";
            pasteBox.hidden = true;
            render();
        }, "mwp-btn is-primary"),
        button("Cancel", "", () => {
            pasteBox.hidden = true;
        }),
    );
    head.append(
        title,
        button("+ Add primers", "Type or paste primers", () => {
            pasteBox.hidden = !pasteBox.hidden;

            if (!pasteBox.hidden) pasteArea.focus();
        }, "mwp-btn is-primary"),
        button("From annotations", "Take the primer-binding annotations of this record as primers", fromAnnotations),
        minSelect,
        button("CSV", "Download the primer table", exportCsv),
        button("Order list", "Copy name and sequence of every primer", copyOrder),
    );
    pane.append(head, pasteBox, listBox, sitesBox, pcrBox, note);

    function fromAnnotations() {
        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        let added = 0;

        snapshot.features.filter(feature => feature.type === "primer").forEach(feature => {
            const piece = slice(snapshot.sequence, feature.start, feature.end, snapshot.topology === "circular");
            const seq = feature.strand === "-" ? rc(piece) : piece;

            if (seq.length >= 6 && !primers.some(item => item.seq === seq)) {
                addPrimer(feature.name, seq);
                added += 1;
            }
        });
        note.textContent = added ? added + " primer" + (added > 1 ? "s" : "") + " taken from the annotations." : "No new primer-binding annotations on this record.";
        render();
    }

    function tableRows() {
        const snapshot = api() ? api().getSnapshot() : null;
        const rows = [["name", "sequence_5_3", "length", "tm_c", "gc_percent", "gc_clamp", "hairpin_stem", "self_dimer", "weight_gmol", "sites", "notes"]];

        primers.forEach(item => {
            const info = analyse(item.seq);
            const sites = snapshot ? findSites(item.seq, snapshot.sequence, snapshot.topology === "circular") : [];

            rows.push([item.name, item.seq, info.length, info.tm === null ? "" : info.tm.toFixed(1), info.gc, info.clamp, info.stem, info.self.length, info.mass, sites.map(site => site.strand + site.start + "-" + site.end).join(" "), info.notes.join("; ")]);
        });

        return rows;
    }

    function download(name, type, content) {
        const link = document.createElement("a");

        link.href = URL.createObjectURL(new Blob([content], {type}));
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
    }

    function baseName() {
        const snapshot = api() ? api().getSnapshot() : null;

        return ((snapshot && snapshot.name) || "record").replace(/[^A-Za-z0-9._-]+/g, "_");
    }

    function exportCsv() {
        const cell = value => (/[",\n]/.test(String(value)) ? '"' + String(value).replace(/"/g, '""') + '"' : String(value));

        download(baseName() + "_primers.csv", "text/csv", tableRows().map(row => row.map(cell).join(",")).join("\n") + "\n");
    }

    function copyOrder() {
        const text = primers.map(item => item.name + "\t" + item.seq).join("\n");

        if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});

        note.textContent = "Order list copied (name, tab, sequence).";
    }

    /* ---------- render ---------- */

    function syncSelf(snapshot) {
        const mine = primers.find(item => item.self);
        const isPrimer = api() && root.dataset.sequenceType === "primer";

        if (!isPrimer) return;

        const seq = clean(snapshot.sequence);

        if (mine) {
            mine.seq = seq;
            mine.name = snapshot.name || mine.name;
        } else if (seq) {
            primers.unshift({id: nextId++, name: snapshot.name || "this primer", seq, self: true});
        }
    }

    function cellInput(value, onChange, className) {
        const node = el("input", className || "mwp-cell");

        node.value = value;
        node.addEventListener("change", () => onChange(node.value));
        node.addEventListener("keydown", event => {
            event.stopPropagation();

            if (event.key === "Enter") node.blur();
        });

        return node;
    }

    function render() {
        frame = 0;

        const workspace = api();

        if (!workspace || pane.hidden) return;

        const snapshot = workspace.getSnapshot();
        const circular = snapshot.topology === "circular";

        syncSelf(snapshot);

        if (!ui.selected || !primers.some(item => item.id === ui.selected)) ui.selected = primers.length ? primers[0].id : null;
        if (!primers.some(item => item.id === Number(ui.fwd))) ui.fwd = primers.length ? String(primers[0].id) : "";
        if (!primers.some(item => item.id === Number(ui.rev))) ui.rev = primers.length > 1 ? String(primers[1].id) : ui.fwd;

        title.textContent = "Primers · " + primers.length;

        const table = el("table", "mwp-table mwpr-table");
        const header = el("tr");
        const thead = el("thead");

        ["Name", "Sequence 5′→3′", "nt", "Tm °C", "GC %", "Sites", "Checks", ""].forEach(text => header.append(el("th", "", text)));
        thead.append(header);
        table.append(thead);

        const tbody = el("tbody");

        primers.forEach(item => {
            const info = analyse(item.seq);
            const sites = snapshot.sequence ? findSites(item.seq, snapshot.sequence, circular) : [];
            const row = el("tr", item.id === ui.selected ? "is-selected" : "");
            const remove = button("✕", item.self ? "This is the record itself" : "Remove this primer", () => {
                primers = primers.filter(other => other.id !== item.id);
                save();
                render();
            }, "mwp-icon");
            const name = cellInput(item.name, value => {
                item.name = value.trim() || item.name;
                save();
                render();
            });
            const seq = cellInput(item.seq, value => {
                const next = clean(value);

                if (next.length >= 6) item.seq = next;

                save();
                render();
            }, "mwp-cell mwpr-seq");
            const verdict = el("td", "mwpr-verdict" + (info.notes.length ? " has-notes" : " is-ok"), info.notes.length ? info.notes.length + " to check" : "OK");

            verdict.title = info.notes.length ? info.notes.join("\n") : "No problem found by the quick checks";
            name.disabled = seq.disabled = Boolean(item.self);
            remove.disabled = Boolean(item.self);

            const cells = [name, seq].map(node => {
                const cell = el("td");

                cell.append(node);

                return cell;
            });

            row.append(
                ...cells,
                el("td", "mwp-size", String(info.length)),
                el("td", "mwp-size", info.tm === null ? "–" : info.tm.toFixed(1)),
                el("td", "mwp-size", String(info.gc)),
                el("td", "mwp-size", sites.length ? sites.map(site => site.strand).join("") + " ×" + sites.length : "none"),
                verdict,
            );

            const last = el("td");

            last.append(remove);
            row.append(last);
            row.addEventListener("click", event => {
                if (event.target.tagName === "INPUT" || event.target.tagName === "BUTTON") return;

                ui.selected = item.id;
                render();
            });
            tbody.append(row);
        });
        table.append(tbody);
        listBox.replaceChildren(primers.length ? table : el("p", "mwp-empty", "No primers yet. Use “+ Add primers”, or “From annotations” to take the primer-binding sites annotated on this record."));

        renderSites(snapshot);
        renderPcr(snapshot);

        note.textContent = "Tm is nearest-neighbour (SantaLucia), 50 mM Na⁺, 250 nM primer. Hairpin and dimer checks are the longest complementary stretch, a screen and not a free energy. A site needs the last " + ui.minMatch + " nt of the primer to pair; unpaired 5′ bases count as a tail (restriction site, overhang).";
    }

    function renderSites(snapshot) {
        const item = primers.find(other => other.id === ui.selected);

        sitesBox.replaceChildren();

        if (!item) {
            sitesBox.hidden = true;

            return;
        }

        sitesBox.hidden = false;

        const info = analyse(item.seq);
        const sites = findSites(item.seq, snapshot.sequence, snapshot.topology === "circular");

        sitesBox.append(el("div", "mwg-cardtitle", item.name + " · " + item.seq.length + " nt"));
        sitesBox.append(el("p", "mwpr-seqline", item.seq));

        const facts = el("div", "mwpr-facts");

        [["Tm", info.tm === null ? "–" : info.tm.toFixed(1) + " °C"], ["GC", info.gc + " %"], ["3′ GC clamp", info.clamp + " of last 5"], ["Hairpin stem", info.stem ? info.stem + " nt" : "none"],
            ["Self-dimer", info.self.length + " nt" + (info.self.threePrime ? " (3′)" : "")], ["Weight", info.mass.toLocaleString("en-US") + " g/mol"]].forEach(([label, value]) => {
            const box = el("div", "mwpr-fact");

            box.append(el("span", "", label), el("b", "", value));
            facts.append(box);
        });
        sitesBox.append(facts);

        if (info.notes.length) {
            const list = el("ul", "mwpr-notes");

            info.notes.forEach(text => list.append(el("li", "", text)));
            sitesBox.append(list);
        }

        sitesBox.append(el("div", "mwg-cardtitle", "Binding sites on this record · " + sites.length));

        if (!sites.length) sitesBox.append(el("p", "mwg-muted", "The 3′ end of this primer does not pair anywhere on the record with the current setting."));

        sites.forEach(site => {
            const row = el("div", "mwpr-site");
            const select = button(site.start.toLocaleString() + "–" + site.end.toLocaleString() + " (" + (site.strand === "+" ? "forward" : "reverse") + ")", "Select this site on the map and in the sequence", () => {
                const workspace = api();

                if (workspace) workspace.selectSequenceRange(site.start, site.end, {source: "primer-window"});
            }, "mwp-btn");
            const annotate = button("Annotate", "Add a primer-binding annotation here", () => {
                const workspace = api();

                if (!workspace) return;

                workspace.selectSequenceRange(site.start, site.end, {source: "primer-window"});
                workspace.createFeatureFromSelection({type: "primer", name: item.name, strand: site.strand, focusEditor: false});
            }, "mwp-btn");

            annotate.disabled = !snapshot.canEdit;
            row.append(select, el("span", "mwg-muted", site.matched + " of " + item.seq.length + " nt pair" + (site.tail ? ", " + site.tail + " nt 5′ tail" : ", complete")), annotate);
            sitesBox.append(row);
        });
    }

    function renderPcr(snapshot) {
        pcrBox.replaceChildren();

        if (primers.length < 1) {
            pcrBox.hidden = true;

            return;
        }

        pcrBox.hidden = false;
        pcrBox.append(el("div", "mwg-cardtitle", "PCR on this record"));

        const picker = el("div", "mwpr-row");
        const make = (key, label) => {
            const select = el("select", "mwp-select");

            primers.forEach(item => {
                const option = el("option", "", item.name);

                option.value = String(item.id);
                select.append(option);
            });
            select.value = ui[key];
            select.addEventListener("change", () => {
                ui[key] = select.value;
                render();
            });

            const wrap = el("label", "mwg-item");

            wrap.append(el("span", "", label), select);

            return wrap;
        };

        picker.append(make("fwd", "Forward"), make("rev", "Reverse"));
        pcrBox.append(picker);

        const fwd = primers.find(item => item.id === Number(ui.fwd));
        const rev = primers.find(item => item.id === Number(ui.rev));

        if (!fwd || !rev) return;

        const result = products(fwd, rev, snapshot);
        const tmF = calc.meltingTemperature(fwd.seq);
        const tmR = calc.meltingTemperature(rev.seq);
        const cross = longestComplement(fwd.seq, rev.seq);

        if (tmF !== null && tmR !== null) {
            const gap = Math.abs(tmF - tmR);
            const line = el("p", "mwpr-line", "Tm " + tmF.toFixed(1) + " / " + tmR.toFixed(1) + " °C · difference " + gap.toFixed(1) + " °C" + (gap > 5 ? " (more than 5 °C apart)" : "") + " · suggested annealing " + (Math.min(tmF, tmR) - 5).toFixed(0) + " °C");

            pcrBox.append(line);
        }

        pcrBox.append(el("p", "mwpr-line" + (cross.length >= 5 || (cross.threePrime && cross.length >= 4) ? " is-warn" : ""), "Cross-dimer: longest complementary stretch " + cross.length + " nt" + (cross.threePrime ? " involving the 3′ end of the forward primer" : "")));

        if (!result.length) {
            pcrBox.append(el("p", "mwg-muted", "No product: the forward primer must pair on the top strand and the reverse primer downstream on the bottom strand."));

            return;
        }

        const holder = el("div", "mwpr-products");
        const list = el("div", "mwpr-productlist");

        result.slice(0, 12).forEach((product, index) => {
            const row = el("div", "mwpr-product");
            const select = button(product.size.toLocaleString("en-US") + " bp", "Select the product region", () => {
                const workspace = api();

                if (workspace) workspace.selectSequenceRange(product.start, product.end, {source: "primer-window"});
            }, "mwp-btn");

            row.append(
                select,
                el("span", "mwg-muted", product.start.toLocaleString() + "–" + product.end.toLocaleString() + (product.f.tail || product.r.tail ? " + tails " + product.f.tail + "/" + product.r.tail + " nt" : "")),
                button("Copy", "Copy the product sequence", () => {
                    if (navigator.clipboard) navigator.clipboard.writeText(product.amplicon).catch(() => {});

                    note.textContent = "Product " + (index + 1) + " copied (" + product.size + " bp).";
                }),
                button("FASTA", "Download the product", () => download(baseName() + "_PCR_" + product.size + "bp.fasta", "text/plain", ">" + fwd.name + "_" + rev.name + " " + product.size + "bp\n" + product.amplicon.replace(/(.{70})/g, "$1\n").replace(/\n$/, "") + "\n")),
                button("Annotate", "Annotate the product region", () => {
                    const workspace = api();

                    if (!workspace) return;

                    workspace.selectSequenceRange(product.start, product.end, {source: "primer-window"});
                    workspace.createFeatureFromSelection({type: "custom", name: "PCR " + product.size + " bp", focusEditor: false});
                }),
            );
            list.append(row);
        });

        if (result.length > 12) list.append(el("p", "mwg-muted", result.length - 12 + " more products not listed."));

        if (result.length > 1) list.prepend(el("p", "mwpr-line is-warn", result.length + " products: these primers bind in more than one place."));

        holder.append(list, digestCalc ? gelSvg(result.slice(0, 12).map(product => product.size)) : el("span"));
        pcrBox.append(holder);
    }

    function schedule() {
        if (!frame) frame = window.requestAnimationFrame(render);
    }

    minSelect.addEventListener("change", () => {
        ui.minMatch = Number(minSelect.value);
        render();
    });
    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail.layout === "primers") window.requestAnimationFrame(render);
    });
    root.addEventListener("biobank:molecular-workspace-change", () => {
        const active = document.activeElement;

        if (active && pane.contains(active) && active.tagName === "INPUT") return;

        schedule();
    });

    window.BiobankPrimers = {
        add: addPrimer,
        list: () => primers.map(item => ({name: item.name, seq: item.seq})),
        sites: seq => {
            const snapshot = api().getSnapshot();

            return findSites(clean(seq), snapshot.sequence, snapshot.topology === "circular");
        },
        pcr: (fwdSeq, revSeq) => {
            const snapshot = api().getSnapshot();

            return products({seq: clean(fwdSeq)}, {seq: clean(revSeq)}, snapshot).map(item => ({size: item.size, start: item.start, end: item.end}));
        },
        analyse: seq => analyse(clean(seq)),
    };

    load();
}());
