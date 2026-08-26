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

    const NUCLEOTIDE_COLORS = {
        A: "#b7e4c7",
        C: "#a9d6e5",
        G: "#ffd166",
        T: "#ffadad",
        U: "#cdb4db",
        N: "#e9ecef",
    };

    const AMINO_ACID_COLORS = {
        A: "#ffd18a",
        C: "#ffb4a2",
        D: "#ff8787",
        E: "#ff8787",
        F: "#d8f3dc",
        G: "#a9b8ff",
        H: "#91a7ff",
        I: "#d8f3dc",
        K: "#91a7ff",
        L: "#d8f3dc",
        M: "#d8f3dc",
        N: "#a8e6e6",
        P: "#e9c46a",
        Q: "#a8e6e6",
        R: "#91a7ff",
        S: "#a8e6e6",
        T: "#a8e6e6",
        V: "#d8f3dc",
        W: "#d8f3dc",
        Y: "#d8f3dc",
        X: "#e9ecef",
    };

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
        const zoom = document.getElementById("mw-seqviz-zoom");
        const zoomValue = document.getElementById("mw-seqviz-zoom-value");
        const enzymeMode = document.getElementById("mw-seqviz-enzymes");
        const colorMode = document.getElementById("mw-seqviz-colors");
        const search = document.getElementById("mw-seqviz-search");
        const mismatch = document.getElementById("mw-seqviz-mismatch");
        const showComplement = document.getElementById(
            "mw-seqviz-show-complement"
        );
        const showIndex = document.getElementById("mw-seqviz-show-index");
        const reset = document.getElementById("mw-seqviz-reset");
        const selectionLabel = document.getElementById("mw-seqviz-selection");
        const legend = document.getElementById("mw-seqviz-legend");
        const labelMode = document.getElementById(
            "mw-unified-label-mode"
        );
        const createFeature = document.getElementById(
            "mw-seqviz-create-feature"
        );
        const featureForm = document.getElementById(
            "mw-seqviz-feature-form"
        );
        const featureName = document.getElementById(
            "mw-seqviz-feature-name"
        );
        const featureType = document.getElementById(
            "mw-seqviz-feature-type"
        );
        const featureStrand = document.getElementById(
            "mw-seqviz-feature-strand"
        );
        const featureColor = document.getElementById(
            "mw-seqviz-feature-color"
        );
        const featureNotes = document.getElementById(
            "mw-seqviz-feature-notes"
        );
        const featureCancel = document.getElementById(
            "mw-seqviz-feature-cancel"
        );

        if (!root || !viewerRoot) {
            return;
        }

        const isRnaWorkspace = (
            root.dataset.sequenceType === "rna"
        );

        if (isRnaWorkspace) {
            const enzymeControl = (
                enzymeMode?.closest("label")
            );
            const complementControl = (
                showComplement?.closest("label")
            );

            if (enzymeControl) {
                enzymeControl.hidden = true;
            }

            if (complementControl) {
                complementControl.hidden = true;
            }

            enzymeMode.value = "none";
            showComplement.checked = false;
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
                    name: (
                        (labelMode?.value || "selected") === "all"
                        || (
                            (labelMode?.value || "selected")
                            === "selected"
                            && featureIndex === data.selectedFeature
                        )
                    )
                        ? (feature.name || "Feature")
                        : "",
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

        function symbolColorsFor(data) {
            if (colorMode?.value === "monochrome") {
                return Object.fromEntries(
                    [...new Set(data.sequence)]
                        .map(symbol => [
                            symbol,
                            "#f1f3f5",
                        ])
                );
            }

            if (data.sequenceType === "protein") {
                return AMINO_ACID_COLORS;
            }

            return NUCLEOTIDE_COLORS;
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

            if (!data.features.length) {
                const empty = document.createElement("p");
                empty.className = "mw-seqviz-help";
                empty.textContent = "No annotations are registered for this sequence.";
                legend.appendChild(empty);
                return;
            }

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

        function selectionUnit() {
            const type = String(
                document
                    .getElementById("mw-type")
                    ?.value
                || ""
            ).toLowerCase();

            if (type === "protein") {
                return "aa";
            }

            if (
                type === "rna"
                || type === "primer"
            ) {
                return "nt";
            }

            if (type === "other") {
                return "symbols";
            }

            return "bp";
        }

        function selectionText(selection) {
            if (!selection || selection.start === undefined || selection.end === undefined) {
                return "Select a feature or sequence region in any representation.";
            }

            return [
                selection.name,
                `${Number(selection.start) + 1}..${Number(selection.end)}`,
                selection.length ? `${selection.length} ${selectionUnit()}` : null,
                selection.type,
            ].filter(Boolean).join(" · ");
        }

        function syncFeatureCreator(data = snapshot()) {
            if (!createFeature || !data) {
                return;
            }

            const selection = data.sequenceSelection;
            const canCreate = Boolean(
                data.canEdit
                && selection
                && !Number.isInteger(selection.featureIndex)
            );

            createFeature.disabled = !canCreate;

            if (!canCreate && featureForm) {
                featureForm.hidden = true;
            }
        }

        function openFeatureCreator() {
            const data = snapshot();
            const selection = data?.sequenceSelection;

            if (
                !featureForm
                || !data?.canEdit
                || !selection
                || Number.isInteger(selection.featureIndex)
            ) {
                return;
            }

            featureName.value = "Selected region";
            featureType.value = "custom";
            featureStrand.value = data.sequenceType === "protein"
                ? "."
                : "+";
            featureColor.value = "#8f96a3";
            featureNotes.value = "";
            featureForm.hidden = false;
            featureName.focus();
            featureName.select();
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
                Number(selection.end),
                {source: "seqviz"}
            );
            syncFeatureCreator();
        }

        function renderSeqViz() {
            clearTimeout(renderTimer);
            const data = snapshot();

            if (!data) {
                showMessage("Molecular workspace is not ready.");
                return;
            }

            renderLegend(data);
            syncFeatureCreator(data);

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

            if (
                data.sequenceType === "rna"
                && data.topology === "linear"
            ) {
                mode.value = "linear";
            }

            const props = {
                name: data.name || "Molecular item",
                seq: data.sequence,
                seqType: data.sequenceType === "protein"
                    ? "aa"
                    : (data.sequenceType === "rna" ? "rna" : "dna"),
                viewer: (
                    data.sequenceType === "rna"
                    && data.topology === "linear"
                        ? "linear"
                        : mode.value
                ),
                zoom: {linear: Number(zoom.value || 50)},
                bpColors: symbolColorsFor(data),
                annotations,
                translations: translationsFor(data, annotations),
                primers: primersFor(data, annotations),
                enzymes: (
                    data.sequenceType === "rna"
                        ? []
                        : (
                            enzymeMode.value === "common"
                                ? COMMON_ENZYMES
                                : []
                        )
                ),
                search: query ? {
                    query,
                    mismatch: Number(mismatch.value || 0),
                } : undefined,
                selection: selected,
                showComplement: (
                    data.sequenceType !== "protein"
                    && data.sequenceType !== "rna"
                    && showComplement.checked
                ),
                showIndex: showIndex.checked,
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
            if (
                event.detail?.reason === "selection"
                && event.detail?.source === "seqviz"
            ) {
                syncFeatureCreator(event.detail.snapshot);
                return;
            }

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
        [
            mode,
            enzymeMode,
            colorMode,
            mismatch,
            showComplement,
            showIndex,
        ].forEach(control => {
            control?.addEventListener(
                "change",
                () => scheduleRender(20)
            );
        });
        zoom?.addEventListener("input", () => {
            zoomValue.value = `${zoom.value}%`;
            scheduleRender(60);
        });
        search.addEventListener("input", () => scheduleRender(180));
        createFeature?.addEventListener("click", openFeatureCreator);
        featureCancel?.addEventListener("click", () => {
            featureForm.hidden = true;
        });
        featureForm?.addEventListener("submit", event => {
            event.preventDefault();

            const featureIndex = workspace()
                ?.createFeatureFromSelection?.({
                    name: featureName.value,
                    type: featureType.value,
                    strand: featureStrand.value,
                    color: featureColor.value,
                    notes: featureNotes.value,
                    focusEditor: false,
                });

            if (Number.isInteger(featureIndex)) {
                featureForm.hidden = true;
            }
        });
        reset?.addEventListener("click", () => {
            mode.value = isRnaWorkspace
                ? "linear"
                : "both";
            zoom.value = "50";
            zoomValue.value = "50%";
            enzymeMode.value = "none";
            colorMode.value = "colored";
            search.value = "";
            mismatch.value = "0";
            showComplement.checked = !isRnaWorkspace;
            showIndex.checked = true;
            scheduleRender(20);
        });

        scheduleRender(20);
    });
})();
