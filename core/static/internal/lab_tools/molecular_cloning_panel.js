/*
 * Cloning window: put an insert into the open record (the vector).
 *
 * Restriction cloning: pick the two enzymes that cut the vector; the insert is
 * cut with the same enzymes, oriented so that it goes in the right way, and
 * ligated. Homology cloning (Gibson, In-Fusion): choose where the insert goes
 * (selected region, an enzyme cut, or a position) and get the construct plus
 * the primers with the overlaps. Either result can be applied to the record
 * (one undo step) or copied / downloaded.
 *
 * The insert comes from a pasted sequence, another record of the registry, or
 * the region selected in this record.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const pane = document.getElementById("mw-cloning");
    const digest = window.BiobankDigestCalc;
    const calc = window.BiobankMolecularCalc;

    if (!root || !pane || !digest || !calc) {
        return;
    }

    const COMP = {A: "T", T: "A", G: "C", C: "G", N: "N"};
    const ui = {
        mode: "restriction", source: "paste", insertName: "insert", insertSeq: "", flip: false,
        e1: "", e2: "", site1: 0, site2: 0, place: "selection", enzyme: "", position: 1, remove: 0, overlap: 20, results: [], status: "",
    };
    let frame = 0;

    const api = () => window.BiobankMolecularWorkspace || null;
    const clean = text => String(text || "").toUpperCase().replace(/U/g, "T").replace(/[^ACGTN]/g, "");
    const rc = text => Array.from(text).reverse().map(base => COMP[base] || "N").join("");

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

    function labelled(text, node) {
        const wrap = el("label", "mwg-item");

        wrap.append(el("span", "", text), node);

        return wrap;
    }

    function select(options, value, onChange, className) {
        const node = el("select", className || "mwp-select");

        options.forEach(([optionValue, label]) => {
            const option = el("option", "", label);

            option.value = optionValue;
            node.append(option);
        });
        node.value = value;
        node.addEventListener("change", () => onChange(node.value));

        return node;
    }

    /* ---------- the plans ---------- */

    function enzymeTable(vector, circular, insert) {
        return digest.CATALOG.map(item => ({
            name: item.name,
            site: item.site,
            vector: digest.cutSites(vector, item.name, circular),
            insert: insert ? digest.cutSites(insert, item.name, false) : [],
        }));
    }

    function overhang(sequence, cut) {
        return sequence.slice(Math.min(cut.position, cut.bottom), Math.max(cut.position, cut.bottom));
    }

    function restrictionPlan(snapshot) {
        const vector = snapshot.sequence;
        const circular = snapshot.topology === "circular";
        const insert = ui.flip ? rc(clean(ui.insertSeq)) : clean(ui.insertSeq);
        const issues = [];

        if (!insert) return {error: "Add an insert first (paste it, pick a record, or use the selection)."};
        if (!ui.e1) return {error: "Choose the enzyme for the 5′ end."};

        const e2 = ui.e2 || ui.e1;
        const sites = name => digest.cutSites(vector, name, circular);
        const v1 = sites(ui.e1);
        const v2 = sites(e2);

        if (!v1.length || !v2.length) return {error: "The vector has no site for " + (!v1.length ? ui.e1 : e2) + "."};

        const eA = ui.e1;
        const eB = e2;
        let cA;
        let cB;

        if (eA === eB) {
            if (v1.length === 1) {
                cA = cB = v1[0];
            } else {
                const i = Math.min(ui.site1, v1.length - 1);
                let j = Math.min(ui.site2, v1.length - 1);

                if (j === i) j = (i + 1) % v1.length;

                cA = v1[i];
                cB = v1[j];
                issues.push(eA + " cuts the vector " + v1.length + " times; the region between site " + (Math.min(i, j) + 1) + " and site " + (Math.max(i, j) + 1) + " is replaced.");
            }
        } else {
            cA = v1[Math.min(ui.site1, v1.length - 1)];
            cB = v2[Math.min(ui.site2, v2.length - 1)];

            if (v1.length > 1) issues.push(eA + " cuts the vector " + v1.length + " times; site " + (Math.min(ui.site1, v1.length - 1) + 1) + " is used.");
            if (v2.length > 1) issues.push(eB + " cuts the vector " + v2.length + " times; site " + (Math.min(ui.site2, v2.length - 1) + 1) + " is used.");
        }

        // The enzyme whose vector site is leftmost opens the insert.
        const swap = cA.position > cB.position;
        const leftName = swap ? eB : eA;
        const rightName = swap ? eA : eB;
        const leftCut = swap ? cB : cA;
        const rightCut = swap ? cA : cB;


        let oriented = insert;
        let reversed = false;
        let iLeft;
        let iRight;

        const find = (seq, name) => digest.cutSites(seq, name, false);

        if (leftName === rightName) {
            const all = find(oriented, leftName);

            if (leftCut === rightCut) {
                // One enzyme, one vector site: the insert is the piece between two of its sites.
                if (all.length < 2) return {error: "The insert needs two " + leftName + " sites (one at each end) to be cut out; it has " + all.length + "."};

                iLeft = all[0];
                iRight = all[all.length - 1];

                if (all.length > 2) issues.push("The insert has " + all.length + " " + leftName + " sites; the piece between the first and the last is used.");
            } else {
                if (all.length < 2) return {error: "The insert needs two " + leftName + " sites; it has " + all.length + "."};

                iLeft = all[0];
                iRight = all[all.length - 1];
            }
        } else {
            let left = find(oriented, leftName);
            let right = find(oriented, rightName);

            if (!left.length || !right.length) return {error: "The insert has no site for " + (!left.length ? leftName : rightName) + "."};

            if (left[0].position > right[right.length - 1].position) {
                oriented = rc(insert);
                reversed = true;
                left = find(oriented, leftName);
                right = find(oriented, rightName);
            }

            iLeft = left[0];
            iRight = right.find(site => site.position > iLeft.position) || right[right.length - 1];

            if (iLeft.position >= iRight.position) return {error: "In the insert " + leftName + " must come before " + rightName + " (in one of the two orientations)."};

            if (left.length > 1) issues.push(leftName + " cuts the insert " + left.length + " times; the first site is used.");
            if (right.length > 1) issues.push(rightName + " cuts the insert " + right.length + " times; the first one after it is used.");
        }

        // Compatibility of the sticky ends (same enzymes: always, shown for the record).
        const ovL = overhang(vector, leftCut);
        const ovI = overhang(oriented, iLeft);

        if (ovL !== ovI) issues.push("The 5′ overhangs do not match (" + (ovL || "blunt") + " / " + (ovI || "blunt") + ").");

        const fragment = oriented.slice(iLeft.position, iRight.position);
        const p1 = leftCut.position;
        const p2 = rightCut.position;
        const construct = vector.slice(0, p1) + fragment + vector.slice(p2);
        const keptTop = leftCut === rightCut ? 0 : p2 - p1;
        const after = p1 + fragment.length;
        const restored = digest.cutSites(construct, leftName, circular).some(site => site.position === p1)
            && digest.cutSites(construct, rightName, circular).some(site => site.position === after);

        if (!restored) issues.push("The junctions do not recreate the enzyme sites (check the overhangs).");

        if (circular && p1 > p2) return {error: "The region between the sites spans the origin; not supported."};

        return {
            kind: "restriction", construct, fragment, p1, p2, left: leftName, right: rightName, reversed, flipped: ui.flip, issues,
            removed: keptTop,
            junctions: [
                vector.slice(Math.max(0, p1 - 12), p1) + " | " + fragment.slice(0, 12),
                fragment.slice(-12) + " | " + vector.slice(p2, p2 + 12),
            ],
        };
    }

    function annealing(sequence, fromEnd) {
        // Insert-binding part of a primer: grow until Tm is about 60 °C.
        for (let size = 18; size <= 32; size++) {
            const part = fromEnd ? sequence.slice(-size) : sequence.slice(0, size);
            const tm = calc.meltingTemperature(part);

            if (tm !== null && tm >= 60) return {part, tm};
        }

        const part = fromEnd ? sequence.slice(-32) : sequence.slice(0, 32);

        return {part, tm: calc.meltingTemperature(part)};
    }

    function homologyPlan(snapshot) {
        const vector = snapshot.sequence;
        const insert = ui.flip ? rc(clean(ui.insertSeq)) : clean(ui.insertSeq);
        const overlap = Math.max(12, Math.min(60, ui.overlap));
        const issues = [];
        let p1;
        let p2;

        if (!insert) return {error: "Add an insert first (paste it, pick a record, or use the selection)."};

        if (ui.place === "selection") {
            const selection = snapshot.sequenceSelection;

            if (!selection) return {error: "Select the region of the vector to replace, or click where the insert goes."};

            p1 = selection.start - 1;
            p2 = selection.end;
        } else if (ui.place === "enzyme") {
            const sites = ui.enzyme ? digest.cutSites(vector, ui.enzyme, snapshot.topology === "circular") : [];

            if (!ui.enzyme) return {error: "Choose the enzyme that linearises the vector."};
            if (!sites.length) return {error: "The vector has no site for " + ui.enzyme + "."};

            if (sites.length > 1) issues.push(ui.enzyme + " cuts " + sites.length + " times; the first site is used.");

            p1 = p2 = sites[Math.min(ui.site1, sites.length - 1)].position;
        } else {
            p1 = Math.max(0, Math.min(vector.length, ui.position));
            p2 = Math.max(p1, Math.min(vector.length, p1 + ui.remove));
        }

        if (p1 < overlap || vector.length - p2 < overlap) issues.push("The vector arms are shorter than the overlap on one side.");

        const left = vector.slice(Math.max(0, p1 - overlap), p1);
        const right = vector.slice(p2, p2 + overlap);
        const start = annealing(insert, false);
        const end = annealing(insert, true);
        const forward = left + start.part;
        const reverse = rc(end.part + right);
        const construct = vector.slice(0, p1) + insert + vector.slice(p2);

        return {
            kind: "homology", construct, fragment: insert, p1, p2, issues, removed: p2 - p1,
            primers: [
                {name: ui.insertName + "_F", seq: forward, bind: start.part.length, tm: start.tm},
                {name: ui.insertName + "_R", seq: reverse, bind: end.part.length, tm: end.tm},
            ],
            junctions: [left.slice(-12) + " | " + insert.slice(0, 12), insert.slice(-12) + " | " + right.slice(0, 12)],
        };
    }

    /* ---------- insert sources ---------- */

    function download(name, content) {
        const link = document.createElement("a");

        link.href = URL.createObjectURL(new Blob([content], {type: "text/plain"}));
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
    }

    async function searchRegistry(query) {
        const url = pane.dataset.searchUrl;

        if (!url || query.length < 1) return [];

        const response = await fetch(url + "?q=" + encodeURIComponent(query), {credentials: "same-origin"});

        if (!response.ok) return [];

        return (await response.json()).results || [];
    }

    async function loadRecord(id) {
        const template = pane.dataset.recordUrl || "";
        const response = await fetch(template.replace("/0/", "/" + id + "/"), {credentials: "same-origin"});

        if (!response.ok) throw new Error("The record could not be read.");

        return response.json();
    }

    /* ---------- skeleton ---------- */

    const head = el("div", "mwp-head");
    const body = el("div", "mwcl-body");
    const note = el("p", "mwp-note");

    pane.append(head, body, note);

    function renderHead() {
        head.replaceChildren(
            el("strong", "mwp-title", "Cloning"),
            select([["restriction", "Restriction enzymes"], ["homology", "Homology (Gibson, In-Fusion)"]], ui.mode, value => {
                ui.mode = value;
                render();
            }),
            el("span", "mwg-muted", "Vector: this record"),
        );
    }

    function insertCard(snapshot) {
        const card = el("div", "mwpr-card");
        const sources = select([["paste", "Paste a sequence"], ["registry", "Another record"], ["selection", "Selection of this record"]], ui.source, value => {
            ui.source = value;
            ui.results = [];
            render();
        });

        card.append(el("div", "mwg-cardtitle", "Insert"), labelled("From", sources));

        if (ui.source === "paste") {
            const area = el("textarea", "mwpr-area");

            area.rows = 3;
            area.placeholder = "Paste the insert sequence (FASTA header allowed)";
            area.value = ui.insertSeq;
            area.addEventListener("change", () => {
                const lines = area.value.split(/\r?\n/);

                ui.insertName = lines[0] && lines[0][0] === ">" ? lines[0].slice(1).trim().split(/\s+/)[0] || "insert" : "insert";
                ui.insertSeq = clean(lines.filter(line => line[0] !== ">").join(""));
                render();
            });
            card.append(area);
        } else if (ui.source === "registry") {
            const query = el("input", "mwp-filter");
            const list = el("div", "mwcl-results");

            query.type = "search";
            query.placeholder = "Search the registry by name";
            query.addEventListener("keydown", event => {
                event.stopPropagation();

                if (event.key === "Enter") event.preventDefault();
            });
            query.addEventListener("input", async () => {
                ui.results = await searchRegistry(query.value.trim());
                drawResults(list);
            });
            card.append(query, list);
            drawResults(list);
        } else {
            const selection = snapshot.sequenceSelection;
            const usable = selection && selection.start <= selection.end;

            card.append(el("p", "mwg-muted", usable ? "Selected " + selection.start.toLocaleString() + "–" + selection.end.toLocaleString() + " (" + (selection.end - selection.start + 1).toLocaleString() + " bp)." : "Select a region of this record first."));
            card.append(button("Use the selection", "Copy the selected region as the insert", () => {
                if (!usable) return;

                ui.insertSeq = snapshot.sequence.slice(selection.start - 1, selection.end);
                ui.insertName = "subclone";
                render();
            }));
        }

        const flip = el("input");

        flip.type = "checkbox";
        flip.checked = ui.flip;
        flip.addEventListener("change", () => {
            ui.flip = flip.checked;
            render();
        });
        card.append(labelled("Reverse-complement the insert", flip));
        card.append(el("p", "mwg-muted", ui.insertSeq ? ui.insertName + ": " + clean(ui.insertSeq).length.toLocaleString() + " bp" : "No insert yet."));

        return card;
    }

    function drawResults(list) {
        list.replaceChildren();

        ui.results.slice(0, 8).forEach(item => {
            const row = button(item.name + " · " + (item.length || 0).toLocaleString() + " bp · " + (item.sequence_type_display || item.sequence_type || ""), "Use this record as the insert", async () => {
                try {
                    const data = await loadRecord(item.id);

                    ui.insertSeq = clean(data.sequence);
                    ui.insertName = String(data.name || "insert").replace(/\s+/g, "_");
                    ui.source = "paste";
                    render();
                } catch (error) {
                    note.textContent = error.message;
                }
            }, "mwcl-result");

            list.append(row);
        });

        if (!ui.results.length) list.append(el("p", "mwg-muted", "Type to search."));
    }

    function enzymeCard(snapshot) {
        const card = el("div", "mwpr-card");
        const vector = snapshot.sequence;
        const circular = snapshot.topology === "circular";
        const insert = clean(ui.insertSeq);
        const table = enzymeTable(vector, circular, insert);

        card.append(el("div", "mwg-cardtitle", ui.mode === "restriction" ? "Enzymes" : "Where the insert goes"));

        if (ui.mode === "restriction") {
            const usable = table.filter(item => item.vector.length && (!insert || item.insert.length));
            const options = [["", "choose…"]].concat(usable.map(item => [item.name, item.name + " · vector ×" + item.vector.length + (insert ? " · insert ×" + item.insert.length : "")]));

            if (!ui.e1 && usable.length) {
                const pick = usable.find(item => item.vector.length === 1 && item.insert.length === 1) || usable[0];

                ui.e1 = pick.name;
            }

            card.append(labelled("5′ enzyme", select(options, ui.e1, value => {
                ui.e1 = value;
                ui.site1 = 0;
                render();
            })));
            card.append(labelled("3′ enzyme", select([["", "same as the 5′ enzyme"]].concat(options.slice(1)), ui.e2, value => {
                ui.e2 = value;
                ui.site2 = 0;
                render();
            })));

            const suggestion = usable.filter(item => item.vector.length === 1 && item.insert.length === 1).map(item => item.name);

            if (insert) {
                card.append(el("p", "mwg-muted", suggestion.length > 1
                    ? "Cut once in the vector and once in the insert: " + suggestion.slice(0, 10).join(", ") + ". Two different enzymes give a directional clone."
                    : (usable.length ? "No enzyme cuts both the vector and the insert exactly once; check the counts in the lists." : "No enzyme of the list cuts both. Add sites to the insert (e.g. with PCR primers) or use the homology method.")));
            }

            [["e1", "site1", ui.e1], ["e2", "site2", ui.e2 || ui.e1]].forEach(([key, siteKey, name]) => {
                const found = name ? digest.cutSites(vector, name, circular) : [];

                if (found.length > 1) {
                    card.append(labelled(name + " site in the vector", select(found.map((site, index) => [String(index), "site " + (index + 1) + " · cut at " + site.position.toLocaleString()]), String(ui[siteKey]), value => {
                        ui[siteKey] = Number(value);
                        render();
                    })));
                }
            });
        } else {
            card.append(labelled("Place", select([["selection", "Replace the selected region"], ["enzyme", "Linearise with an enzyme"], ["position", "At a position"]], ui.place, value => {
                ui.place = value;
                render();
            })));

            if (ui.place === "enzyme") {
                const options = [["", "choose…"]].concat(table.filter(item => item.vector.length).map(item => [item.name, item.name + " · ×" + item.vector.length]));

                card.append(labelled("Enzyme", select(options, ui.enzyme, value => {
                    ui.enzyme = value;
                    render();
                })));
            } else if (ui.place === "position") {
                const position = el("input", "mwp-num");
                const remove = el("input", "mwp-num");

                position.type = remove.type = "number";
                position.min = remove.min = "0";
                position.value = String(ui.position);
                remove.value = String(ui.remove);
                position.addEventListener("change", () => {
                    ui.position = Number(position.value) || 0;
                    render();
                });
                remove.addEventListener("change", () => {
                    ui.remove = Number(remove.value) || 0;
                    render();
                });
                card.append(labelled("Insert after base", position), labelled("Remove the next", remove), el("span", "mwg-muted", "bases"));
            }

            const overlap = el("input", "mwp-num");

            overlap.type = "number";
            overlap.min = "12";
            overlap.max = "60";
            overlap.value = String(ui.overlap);
            overlap.addEventListener("change", () => {
                ui.overlap = Number(overlap.value) || 20;
                render();
            });
            card.append(labelled("Overlap (nt)", overlap));
        }

        return card;
    }

    function resultCard(snapshot) {
        const card = el("div", "mwpr-card mwcl-result-card");
        const plan = ui.mode === "restriction" ? restrictionPlan(snapshot) : homologyPlan(snapshot);

        card.append(el("div", "mwg-cardtitle", "Result"));

        if (plan.error) {
            card.append(el("p", "mwg-muted", plan.error));

            return card;
        }

        const facts = el("div", "mwpr-facts");

        [["Construct", plan.construct.length.toLocaleString() + " bp"], ["Insert", plan.fragment.length.toLocaleString() + " bp"], ["Removed from vector", plan.removed.toLocaleString() + " bp"],
            ["Vector", snapshot.sequence.length.toLocaleString() + " bp"]].forEach(([label, value]) => {
            const box = el("div", "mwpr-fact");

            box.append(el("span", "", label), el("b", "", value));
            facts.append(box);
        });
        card.append(facts);

        if (plan.kind === "restriction") {
            card.append(el("p", "mwpr-line", plan.left + (plan.left === plan.right ? "" : " … " + plan.right) + (plan.reversed ? " · the insert was reverse-complemented to fit" : "") + (plan.flipped ? " · insert flipped by you" : "")));
        }

        card.append(el("p", "mwpr-line mwcl-junction", "Left junction  " + plan.junctions[0]), el("p", "mwpr-line mwcl-junction", "Right junction " + plan.junctions[1]));

        if (plan.issues.length) {
            const list = el("ul", "mwpr-notes");

            plan.issues.forEach(text => list.append(el("li", "", text)));
            card.append(list);
        } else {
            card.append(el("p", "mwpr-line", "No problem found."));
        }

        if (plan.kind === "homology") {
            const table = el("table", "mwp-table mwcl-primers");
            const header = el("tr");
            const thead = el("thead");
            const tbody = el("tbody");

            ["Primer", "Sequence 5′→3′", "nt", "Binds insert (Tm)"].forEach(text => header.append(el("th", "", text)));
            thead.append(header);
            table.append(thead);
            plan.primers.forEach(primer => {
                const row = el("tr");

                row.append(el("td", "", primer.name), el("td", "mwpr-seqline", primer.seq), el("td", "mwp-size", String(primer.seq.length)), el("td", "mwp-size", primer.bind + " nt" + (primer.tm === null ? "" : " · " + primer.tm.toFixed(1) + " °C")));
                tbody.append(row);
            });
            table.append(tbody);

            const wrap = el("div", "mwp-scroll");

            wrap.append(table);
            card.append(wrap);
        }

        const actions = el("div", "mwg-exportrow");
        const apply = button("Apply to this record", "Replace the region in this record; Undo restores it", () => {
            const workspace = api();

            if (workspace && workspace.replaceRange(plan.p1, plan.p2, plan.fragment)) {
                note.textContent = "Applied: " + plan.fragment.length.toLocaleString() + " bp inserted. Undo in the edit bar reverts it.";
            }
        }, "mwp-btn is-primary");

        apply.disabled = !snapshot.canEdit;
        apply.title = snapshot.canEdit ? apply.title : "Read only record";
        actions.append(
            apply,
            button("Copy construct", "Copy the new sequence", () => {
                if (navigator.clipboard) navigator.clipboard.writeText(plan.construct).catch(() => {});

                note.textContent = "Construct sequence copied.";
            }),
            button("FASTA", "Download the construct", () => download((snapshot.name || "construct").replace(/[^A-Za-z0-9._-]+/g, "_") + "_" + ui.insertName + ".fasta", ">" + (snapshot.name || "vector") + "_" + ui.insertName + " " + plan.construct.length + "bp\n" + plan.construct.replace(/(.{70})/g, "$1\n").replace(/\n$/, "") + "\n")),
        );

        if (plan.kind === "homology") {
            actions.append(button("Add primers to Primers", "Send both primers to the Primers window", () => {
                if (!window.BiobankPrimers) return;

                plan.primers.forEach(primer => window.BiobankPrimers.add(primer.name, primer.seq));
                note.textContent = "Primers added: open the Primers window to check them.";
            }), button("Copy primers", "Copy name and sequence of both primers", () => {
                if (navigator.clipboard) navigator.clipboard.writeText(plan.primers.map(primer => primer.name + "\t" + primer.seq).join("\n")).catch(() => {});

                note.textContent = "Primers copied.";
            }));
        }

        card.append(actions);

        return card;
    }

    function render() {
        frame = 0;

        const workspace = api();

        if (!workspace || pane.hidden) return;

        const snapshot = workspace.getSnapshot();
        const active = document.activeElement;

        if (active && pane.contains(active) && active.tagName === "TEXTAREA") return;

        renderHead();
        body.replaceChildren(insertCard(snapshot), enzymeCard(snapshot), resultCard(snapshot));
        note.textContent = note.textContent && /Applied|copied|added|Primers|Construct/.test(note.textContent)
            ? note.textContent
            : ui.mode === "restriction"
                ? "Restriction cloning cuts vector and insert with the same enzymes and joins them. Enzymes that cut once in each give the cleanest clone; two different enzymes keep the orientation. Sticky ends of different enzymes that are compatible (BamHI/BglII) are not handled."
                : "Homology cloning adds ~" + ui.overlap + " nt of vector sequence to each end of the insert by PCR; the vector is linearised or cut open at the chosen place and the pieces are joined by the assembly mix.";
    }

    function schedule() {
        if (!frame) frame = window.requestAnimationFrame(render);
    }

    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail.layout === "cloning") window.requestAnimationFrame(render);
    });
    root.addEventListener("biobank:molecular-workspace-change", schedule);

    window.BiobankCloning = {
        setInsert(name, sequence) {
            ui.insertName = name || "insert";
            ui.insertSeq = clean(sequence);
            ui.source = "paste";
        },
        configure(options) {
            Object.assign(ui, options || {});
        },
        plan() {
            const workspace = api();

            if (!workspace) return null;

            const snapshot = workspace.getSnapshot();

            return ui.mode === "restriction" ? restrictionPlan(snapshot) : homologyPlan(snapshot);
        },
        render,
    };
}());
