/*
 * Molecular Registry tracks rail (left column).
 *
 * Lists the record's features and open reading frames. Clicking a row
 * selects it through the public workspace API, so the map, sequence,
 * inspector and every other view follow.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("mw-tracks");
    const calc = window.BiobankMolecularCalc;

    if (!root || !host || !calc) return;

    let tab = "features";
    let queued = false;
    let minAa = 30;
    let strandFilter = "both";
    let flash = "";

    const api = () => window.BiobankMolecularWorkspace;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function safeColor(value) {
        return /^#[0-9a-fA-F]{6}$/.test(value || "") ? value : "#64748B";
    }

    function range(start, end) {
        return start === end ? String(start) : start + "–" + end;
    }

    function tabs(counts) {
        const bar = el("div", "mwt-tabs");

        [["features", "Features"], ["orfs", "ORFs"]].forEach(([key, label]) => {
            const button = el(
                "button",
                "mwt-tab" + (tab === key ? " is-active" : ""),
                label + " " + counts[key]
            );

            button.type = "button";
            button.addEventListener("click", () => {
                tab = key;
                render();
            });
            bar.append(button);
        });

        return bar;
    }

    function row(options) {
        const item = el(
            "button",
            "mwt-row" + (options.selected ? " is-selected" : "")
        );

        item.type = "button";
        item.title = options.title || "";

        const dot = el("span", "mwt-dot");

        dot.style.background = options.color;
        item.append(dot, el("span", "mwt-name", options.name),
            el("span", "mwt-range", options.range));
        item.addEventListener("click", options.onClick);

        return item;
    }

    function isSelected(orf, selection) {
        return Boolean(
            selection && selection.start === orf.start &&
            selection.end === orf.end
        );
    }

    function orfControls() {
        const box = el("div", "mwt-controls");
        const minLabel = el("label", "mwt-field", "Min. aa");
        const min = el("input");
        const strandLabel = el("label", "mwt-field", "Strand");
        const strand = el("select");

        min.type = "number";
        min.min = "10";
        min.max = "2000";
        min.step = "10";
        min.value = String(minAa);
        min.addEventListener("change", () => {
            minAa = Math.max(10, Math.min(2000, Number(min.value) || 30));
            render();
        });
        minLabel.append(min);

        [["both", "Both"], ["+", "Forward +"], ["-", "Reverse −"]].forEach(
            ([value, label]) => {
                const option = el("option", "", label);

                option.value = value;
                option.selected = strandFilter === value;
                strand.append(option);
            }
        );
        strand.addEventListener("change", () => {
            strandFilter = strand.value;
            render();
        });
        strandLabel.append(strand);

        box.append(minLabel, strandLabel);

        return box;
    }

    /** Six reading-frame lanes over the whole molecule; click to select. */
    function orfMap(orfs, length, selection) {
        const ns = "http://www.w3.org/2000/svg";
        const lane = 9;
        const svg = document.createElementNS(ns, "svg");

        svg.setAttribute("viewBox", "0 0 100 " + (lane * 6 + 2));
        svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("class", "mwt-map");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "ORFs by reading frame");

        for (let i = 0; i < 6; i++) {
            const guide = document.createElementNS(ns, "rect");

            guide.setAttribute("x", "0");
            guide.setAttribute("y", String(1 + i * lane));
            guide.setAttribute("width", "100");
            guide.setAttribute("height", String(lane - 2));
            guide.setAttribute("class", "mwt-lane");
            svg.append(guide);
        }

        orfs.forEach(orf => {
            const index = (orf.strand === "-" ? 3 : 0) + orf.frame - 1;
            const rect = document.createElementNS(ns, "rect");
            const x = (orf.start - 1) / length * 100;
            const width = Math.max((orf.end - orf.start + 1) / length * 100, 0.6);

            rect.setAttribute("x", x.toFixed(3));
            rect.setAttribute("y", String(1 + index * lane));
            rect.setAttribute("width", width.toFixed(3));
            rect.setAttribute("height", String(lane - 2));
            rect.setAttribute("class", "mwt-orf" +
                (orf.strand === "-" ? " is-reverse" : "") +
                (isSelected(orf, selection) ? " is-selected" : ""));
            rect.addEventListener("click", () => api().selectSequenceRange(
                orf.start, orf.end, {source: "tracks"}
            ));

            const title = document.createElementNS(ns, "title");

            title.textContent = orf.aminoAcids + " aa · " + orf.strand +
                orf.frame + " · " + range(orf.start, orf.end);
            rect.append(title);
            svg.append(rect);
        });

        return svg;
    }

    function orfActions(orf, snapshot) {
        const box = el("div", "mwt-actions");
        const protein = () => calc.translate(
            orf.strand === "-"
                ? calc.reverseComplement(
                    calc.slice(snapshot.sequence, orf.start, orf.end))
                : calc.slice(snapshot.sequence, orf.start, orf.end),
            0
        ).replace(/\*$/, "");

        const copy = el("button", "mwt-action", "Copy protein");

        copy.type = "button";
        copy.addEventListener("click", () => {
            const text = protein();

            if (navigator.clipboard) navigator.clipboard.writeText(text);
            flash = "Copied " + text.length + " aa";
            copy.textContent = flash;
        });
        box.append(copy);

        if (snapshot.canEdit) {
            const make = el("button", "mwt-action", "Make it a CDS feature");

            make.type = "button";
            make.addEventListener("click", () => {
                api().selectSequenceRange(
                    orf.start, orf.end, {source: "tracks"}
                );
                api().createFeatureFromSelection({
                    type: "cds",
                    name: "ORF " + orf.aminoAcids + " aa",
                    strand: orf.strand,
                    focusEditor: true,
                });
            });
            box.append(make);
        }

        return box;
    }

    function render() {
        queued = false;

        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const features = snapshot.features || [];
        const nucleotide = snapshot.sequenceType !== "protein";
        const orfs = nucleotide
            ? calc.findOrfs(snapshot.sequence, minAa, {strand: strandFilter})
            : [];
        const selection = snapshot.sequenceSelection;
        const list = el("div", "mwt-list");

        if (tab === "features") {
            if (!features.length) {
                list.append(el("p", "mwt-empty",
                    "No features yet. Select a region and make it a feature."));
            }

            features.forEach((feature, index) => {
                list.append(row({
                    name: feature.name || "Unnamed",
                    range: range(feature.start, feature.end),
                    color: safeColor(feature.color),
                    selected: snapshot.selectedFeature === index,
                    title: feature.type || feature.feature_type || "",
                    onClick: () => workspace.selectFeature(index),
                }));
            });
        } else {
            list.append(orfControls(), orfMap(orfs, snapshot.sequence.length, selection));

            if (!orfs.length) {
                list.append(el("p", "mwt-empty",
                    "No ORF of " + minAa + " aa or more with these settings."));
            }

            orfs.slice(0, 60).forEach(orf => {
                const selected = isSelected(orf, selection);

                list.append(row({
                    name: orf.aminoAcids + " aa · " + orf.strand + orf.frame,
                    range: range(orf.start, orf.end),
                    color: orf.strand === "-" ? "#DB2777" : "#4F46E5",
                    selected,
                    title: "Select this ORF",
                    onClick: () => workspace.selectSequenceRange(
                        orf.start, orf.end, {source: "tracks"}
                    ),
                }));

                if (selected) list.append(orfActions(orf, snapshot));
            });

            if (orfs.length > 60) {
                list.append(el("p", "mwt-empty",
                    "Showing the 60 longest of " + orfs.length +
                    ". Raise the minimum length to narrow."));
            }
        }

        host.replaceChildren(
            tabs({features: features.length, orfs: orfs.length}),
            list
        );
    }

    function schedule() {
        if (queued) return;

        queued = true;
        window.requestAnimationFrame(render);
    }

    root.addEventListener("biobank:molecular-workspace-change", schedule);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", schedule);
    } else {
        schedule();
    }

    window.addEventListener("load", schedule);
})();
