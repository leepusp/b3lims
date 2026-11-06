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

    function render() {
        queued = false;

        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const features = snapshot.features || [];
        const nucleotide = snapshot.sequenceType !== "protein";
        const orfs = nucleotide
            ? calc.findOrfs(snapshot.sequence, 30).slice(0, 12)
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
            if (!orfs.length) {
                list.append(el("p", "mwt-empty",
                    "No forward ORF of 30 aa or more."));
            }

            orfs.forEach(orf => {
                const selected = Boolean(
                    selection && selection.start === orf.start &&
                    selection.end === orf.end
                );

                list.append(row({
                    name: orf.aminoAcids + " aa · frame " + orf.frame,
                    range: range(orf.start, orf.end),
                    color: "#4F46E5",
                    selected,
                    onClick: () => workspace.selectSequenceRange(
                        orf.start, orf.end, {source: "tracks"}
                    ),
                }));
            });
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
