(() => {
    "use strict";

    const COMMON_ENZYMES = [
        "EcoRI",
        "BamHI",
        "HindIII",
        "PstI",
        "SalI",
        "XhoI",
        "NcoI",
        "NotI",
        "NdeI",
        "XbaI",
        "SpeI",
        "SacI",
    ];

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    ready(() => {
        const root = document.getElementById("molecular-workspace");
        const viewerRoot = document.getElementById("mw-seqviz-viewer");
        const mode = document.getElementById("mw-seqviz-mode");
        const enzymeMode = document.getElementById("mw-seqviz-enzymes");
        const search = document.getElementById("mw-seqviz-search");
        const selectionLabel = document.getElementById("mw-seqviz-selection");
        const legend = document.getElementById("mw-seqviz-legend");

        if (!root || !viewerRoot) {
            return;
        }

        let viewer = null;
        let renderTimer = null;
        let lastSelectionKey = "";

        function workspace() {
            return window.BiobankMolecularWorkspace;
        }

        function snapshot() {
            return workspace()?.getSnapshot?.() || null;
        }

        function showMessage(message, error = false) {
            viewerRoot.replaceChildren();
            const box = document.createElement("div");
            box.className = error ? "mw-empty mw-seqviz-error" : "mw-empty";
            box.textContent = message;
            viewerRoot.appendChild(box);
        }

        function featureSegments(feature, sequenceLength, circular) {
            const start = Math.max(1, Math.min(sequenceLength, Number(feature.start) || 1));
            const end = Math.max(1, Math.min(sequenceLength, Number(feature.end) || 1));

            if (circular && start > end) {
                return [
                    {start, end: sequenceLength},
                    {start: 1, end},
                ];
            }

            return [{start: Math.min(start, end), end: Math.max(start, end)}];
        }

        function annotationsFor(data) {
            return data.features.flatMap((feature, featureIndex) => (
                featureSegments(
                    feature,
                    data.sequence.length,
                    data.topology === "circular"
                ).map((segment, segmentIndex) => ({
                    id: `feature-${featureIndex}-${segmentIndex}`,
                    name: feature.name || "Feature",
                    start: segment.start - 1,
                    end: segment.end,
                    direction: feature.strand === "-" ? -1 : 1,
                    color: feature.color || "#868e96",
                    _featureIndex: featureIndex,
                }))
            ));
        }

        function translationsFor(data, annotations) {
            if (!["dna", "plasmid", "insert"].includes(data.sequenceType)) {
                return [];
            }

            return annotations
                .filter(annotation => {
                    const feature = data.features[annotation._featureIndex];
                    return ["cds", "orf", "gene", "insert"]
                        .includes(String(feature?.type || "").toLowerCase());
                })
                .map(annotation => ({
                    start: annotation.start,
                    end: annotation.end,
                    direction: annotation.direction,
                    name: annotation.name,
                    color: annotation.color,
                }));
        }

        function primersFor(data, annotations) {
            if (data.sequenceType === "primer") {
                return [{
                    name: data.name || "Primer",
                    start: 0,
                    end: data.sequence.length,
                    direction: 1,
                    color: "#15aabf",
                }];
            }

            return annotations
                .filter(annotation => {
                    const feature = data.features[annotation._featureIndex];
                    return String(feature?.type || "").toLowerCase() === "primer";
                })
                .map(annotation => ({
                    start: annotation.start,
                    end: annotation.end,
                    direction: annotation.direction,
                    name: annotation.name,
                    color: annotation.color,
                }));
        }

        function externalSelection(data) {
            const selection = data.sequenceSelection;
            if (!selection || !data.sequence.length) {
                return undefined;
            }

            return {
                start: Math.max(0, Number(selection.start || 1) - 1),
                end: Math.max(1, Number(selection.end || 1)),
                clockwise: !(
                    data.topology === "circular"
                    && selection.start > selection.end
                ),
            };
        }

        function renderLegend(data) {
            legend.replaceChildren();
            data.features.forEach((feature, index) => {
                const button = document.createElement("button");
                const dot = document.createElement("span");
                const name = document.createElement("span");

                button.type = "button";
                button.className = "mw-legend-chip";
                button.classList.toggle("is-selected", index === data.selectedFeature);
                dot.className = "mw-legend-dot";
                dot.style.backgroundColor = feature.color || "#868e96";
                name.textContent = feature.name;
                button.append(dot, name);
                button.addEventListener("click", () => workspace()?.selectFeature?.(index));
                legend.appendChild(button);
            });
        }

        function selectionText(selection) {
            if (!selection || selection.start === undefined || selection.end === undefined) {
                return "Select a feature or sequence region in any representation.";
            }

            return [
                selection.name,
                `${Number(selection.start) + 1}..${Number(selection.end)}`,
                selection.length ? `${selection.length} residues` : null,
                selection.type,
            ].filter(Boolean).join(" · ");
        }

        function handleSelection(selection, data) {
            selectionLabel.textContent = selectionText(selection);

            if (!selection || selection.start === undefined || selection.end === undefined) {
                return;
            }

            const key = [selection.start, selection.end, selection.name, selection.type].join(":");
            if (key === lastSelectionKey) {
                return;
            }
            lastSelectionKey = key;

            if (selection.name || selection.id) {
                const idMatch = String(selection.id || "")
                    .match(/^feature-(\d+)-/);
                const featureIndex = idMatch
                    ? Number(idMatch[1])
                    : data.features.findIndex(
                        feature => feature.name === selection.name
                    );
                if (featureIndex >= 0) {
                    workspace()?.selectFeature?.(featureIndex);
                    return;
                }
            }

            workspace()?.selectSequenceRange?.(
                Number(selection.start) + 1,
                Number(selection.end)
            );
        }

        function renderSeqViz() {
            clearTimeout(renderTimer);
            const data = snapshot();

            if (!data) {
                showMessage("Molecular workspace is not ready.");
                return;
            }

            renderLegend(data);

            if (!data.sequence.length) {
                showMessage("Add a sequence to render SeqViz.");
                return;
            }

            if (!window.seqviz?.Viewer) {
                showMessage("The local SeqViz asset could not be loaded.", true);
                return;
            }

            const annotations = annotationsFor(data);
            const selected = externalSelection(data);
            const query = String(search.value || "").replace(/\s+/g, "").toUpperCase();
            const mount = document.createElement("div");
            mount.id = "mw-seqviz-mount";
            viewerRoot.replaceChildren(mount);

            try {
                viewer?.destroy?.();
            } catch (error) {
                console.warn("Could not destroy the previous SeqViz instance.", error);
            }

            const props = {
                name: data.name || "Molecular item",
                seq: data.sequence,
                seqType: data.sequenceType === "protein"
                    ? "aa"
                    : (data.sequenceType === "rna" ? "rna" : "dna"),
                viewer: mode.value,
                annotations,
                translations: translationsFor(data, annotations),
                primers: primersFor(data, annotations),
                enzymes: enzymeMode.value === "common" ? COMMON_ENZYMES : [],
                search: query ? {query, mismatch: 0} : undefined,
                selection: selected,
                showComplement: data.sequenceType !== "protein",
                showIndex: true,
                rotateOnScroll: true,
                disableExternalFonts: true,
                style: {height: "680px", width: "100%"},
                onSelection: selection => handleSelection(selection, data),
            };

            try {
                viewer = window.seqviz.Viewer(mount.id, props);
                viewer.render();
            } catch (error) {
                console.error(error);
                showMessage(`SeqViz rendering error: ${error.message}`, true);
            }
        }

        function scheduleRender(delay = 100) {
            clearTimeout(renderTimer);
            renderTimer = setTimeout(renderSeqViz, delay);
        }

        root.addEventListener("biobank:molecular-workspace-change", event => {
            if (event.detail?.reason === "selection") {
                scheduleRender(40);
            } else {
                scheduleRender();
            }
        });
        root.addEventListener("biobank:molecular-view-change", event => {
            if (["seqviz", "all"].includes(event.detail?.view)) {
                scheduleRender(20);
            }
        });
        [mode, enzymeMode].forEach(control => {
            control.addEventListener("change", () => scheduleRender(20));
        });
        search.addEventListener("input", () => scheduleRender(180));

        scheduleRender(20);
    });
})();
