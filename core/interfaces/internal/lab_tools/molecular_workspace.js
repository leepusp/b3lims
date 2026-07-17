(() => {
    "use strict";

    const SVG_NS = "http://www.w3.org/2000/svg";

    const FEATURE_COLORS = {
        cds: "#4f8cff",
        promoter: "#f6a623",
        terminator: "#8e6cef",
        primer: "#00a896",
        origin: "#e45756",
        ori: "#e45756",
        resistance: "#d45087",
        antibiotic: "#d45087",
        domain: "#54a24b",
        rbs: "#72b7b2",
        signal_peptide: "#ff9da6",
        custom: "#8f96a3",
    };

    const ENZYMES = {
        EcoRI: "GAATTC",
        BamHI: "GGATCC",
        HindIII: "AAGCTT",
        NotI: "GCGGCCGC",
        XhoI: "CTCGAG",
        SalI: "GTCGAC",
        NcoI: "CCATGG",
        NdeI: "CATATG",
        XbaI: "TCTAGA",
        KpnI: "GGTACC",
        SacI: "GAGCTC",
        PstI: "CTGCAG",
        SphI: "GCATGC",
        SmaI: "CCCGGG",
        EcoRV: "GATATC",
        BglII: "AGATCT",
        NheI: "GCTAGC",
        SpeI: "ACTAGT",
        ApaI: "GGGCCC",
        MluI: "ACGCGT",
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
        if (!root) {
            return;
        }

        const canEdit = root.dataset.canEdit === "true";
        const sequenceData = document.getElementById("mw-sequence-data");

        const elements = {
            title: document.getElementById("mw-title"),
            name: document.getElementById("mw-name"),
            type: document.getElementById("mw-type"),
            topology: document.getElementById("mw-topology"),
            description: document.getElementById("mw-description"),
            sequence: document.getElementById("mw-sequence"),
            save: document.getElementById("mw-save"),
            delete: document.getElementById("mw-delete"),
            status: document.getElementById("mw-save-status"),
            statLength: document.getElementById("mw-stat-length"),
            statUnit: document.getElementById("mw-stat-unit"),
            statGc: document.getElementById("mw-stat-gc"),
            statChecksum: document.getElementById("mw-stat-checksum"),
            typeBadge: document.getElementById("mw-type-badge"),
            topologyBadge: document.getElementById("mw-topology-badge"),
            map: document.getElementById("mw-map"),
            mapEmpty: document.getElementById("mw-map-empty"),
            mapLegend: document.getElementById("mw-map-legend"),
            mapMode: document.getElementById("mw-map-mode"),
            enzymeMode: document.getElementById("mw-enzyme-mode"),
            showLabels: document.getElementById("mw-show-labels"),
            featureList: document.getElementById("mw-feature-list"),
            featureEmpty: document.getElementById("mw-feature-empty"),
            featureForm: document.getElementById("mw-feature-form"),
            featureHeading: document.getElementById("mw-feature-form-heading"),
            featureAdd: document.getElementById("mw-feature-add"),
            featureRemove: document.getElementById("mw-feature-remove"),
            featureName: document.getElementById("mw-feature-name"),
            featureType: document.getElementById("mw-feature-type"),
            featureStart: document.getElementById("mw-feature-start"),
            featureEnd: document.getElementById("mw-feature-end"),
            featureStrand: document.getElementById("mw-feature-strand"),
            featureColor: document.getElementById("mw-feature-color"),
            featureNotes: document.getElementById("mw-feature-notes"),
            search: document.getElementById("mw-search"),
            searchResult: document.getElementById("mw-search-result"),
            preview: document.getElementById("mw-sequence-preview"),
            copy: document.getElementById("mw-copy"),
            importFasta: document.getElementById("mw-import-fasta"),
            fastaFile: document.getElementById("mw-fasta-file"),
            exportFasta: document.getElementById("mw-export-fasta"),
            exportGenbank: document.getElementById("mw-export-genbank"),
        };

        const state = {
            sequence: parseSequenceData(sequenceData),
            features: [],
            selectedFeature: -1,
            dirty: false,
            renderTimer: null,
        };

        elements.sequence.value = state.sequence;

        function parseSequenceData(node) {
            if (!node) {
                return "";
            }

            try {
                return String(JSON.parse(node.textContent) || "");
            } catch (error) {
                console.error("Could not parse molecular sequence.", error);
                return "";
            }
        }

        function cleanSequence(value) {
            return String(value || "")
                .replace(/^>.*$/gm, "")
                .replace(/\s+/g, "")
                .toUpperCase();
        }

        function csrfToken() {
            return document.querySelector(
                'input[name="csrfmiddlewaretoken"]'
            )?.value || "";
        }

        async function requestJson(url, options = {}) {
            const response = await fetch(url, options);
            const contentType = response.headers.get("content-type") || "";
            let data = {};

            if (contentType.includes("application/json")) {
                data = await response.json();
            } else {
                const body = await response.text();
                throw new Error(
                    body || `HTTP ${response.status}`
                );
            }

            if (!response.ok || data.status === "error") {
                throw new Error(
                    data.message || `HTTP ${response.status}`
                );
            }

            return data;
        }

        function setStatus(message, mode = "") {
            elements.status.textContent = message;
            elements.status.classList.remove(
                "is-success",
                "is-error"
            );

            if (mode) {
                elements.status.classList.add(`is-${mode}`);
            }
        }

        function markDirty() {
            if (!canEdit) {
                return;
            }

            state.dirty = true;
            setStatus("Unsaved changes");
        }

        function currentSequence() {
            state.sequence = cleanSequence(elements.sequence.value);
            return state.sequence;
        }

        function currentType() {
            return elements.type.value;
        }

        function currentTopology() {
            return elements.topology.value;
        }

        function sequenceUnit() {
            return currentType() === "protein" ? "aa" : "bp";
        }

        function gcContent(sequence) {
            if (
                !sequence
                || !["dna", "rna", "plasmid", "primer", "insert"]
                    .includes(currentType())
            ) {
                return null;
            }

            const canonical = [...sequence].filter(
                base => "ATUGC".includes(base)
            );

            if (!canonical.length) {
                return null;
            }

            const gc = canonical.filter(
                base => base === "G" || base === "C"
            ).length;

            return (gc / canonical.length) * 100;
        }

        function fallbackColor(type) {
            return FEATURE_COLORS[
                String(type || "").toLowerCase()
            ] || FEATURE_COLORS.custom;
        }

        function normalizeFeature(feature, index) {
            return {
                id: feature.id || `local-${Date.now()}-${index}`,
                name: String(feature.name || "Feature"),
                type: String(
                    feature.type || feature.feature_type || "custom"
                ).toLowerCase(),
                start: Number(feature.start) || 1,
                end: Number(feature.end) || 1,
                strand: ["+", "-", "."].includes(feature.strand)
                    ? feature.strand
                    : "+",
                color: feature.color || fallbackColor(feature.type),
                notes: String(feature.notes || ""),
                qualifiers: feature.qualifiers || {},
                order: Number.isInteger(feature.order)
                    ? feature.order
                    : index,
            };
        }

        function featureSegments(feature, length, circular) {
            if (!length) {
                return [];
            }

            const start = Math.max(
                1,
                Math.min(length, Number(feature.start) || 1)
            );
            const end = Math.max(
                1,
                Math.min(length, Number(feature.end) || 1)
            );

            if (circular && start > end) {
                return [
                    [start, length],
                    [1, end],
                ];
            }

            return [[Math.min(start, end), Math.max(start, end)]];
        }

        function svgElement(name, attributes = {}) {
            const node = document.createElementNS(SVG_NS, name);

            Object.entries(attributes).forEach(([key, value]) => {
                node.setAttribute(key, String(value));
            });

            return node;
        }

        function polarPoint(cx, cy, radius, angleDegrees) {
            const angle = angleDegrees * Math.PI / 180;

            return {
                x: cx + radius * Math.cos(angle),
                y: cy + radius * Math.sin(angle),
            };
        }

        function circularArcPath(
            cx,
            cy,
            radius,
            start,
            end,
            length
        ) {
            const startAngle = ((start - 1) / length) * 360 - 90;
            const endAngle = (end / length) * 360 - 90;
            const delta = Math.max(0.1, endAngle - startAngle);
            const startPoint = polarPoint(
                cx,
                cy,
                radius,
                startAngle
            );
            const endPoint = polarPoint(
                cx,
                cy,
                radius,
                endAngle
            );
            const largeArc = delta > 180 ? 1 : 0;

            return [
                `M ${startPoint.x} ${startPoint.y}`,
                `A ${radius} ${radius} 0 ${largeArc} 1`,
                `${endPoint.x} ${endPoint.y}`,
            ].join(" ");
        }

        function clearMap() {
            elements.map.replaceChildren();
            elements.mapLegend.replaceChildren();
        }

        function appendSvgText(parent, text, attributes) {
            const node = svgElement("text", attributes);
            node.textContent = text;
            parent.appendChild(node);
            return node;
        }

        function selectedClass(index) {
            return index === state.selectedFeature
                ? "mw-map-feature is-selected"
                : "mw-map-feature";
        }

        function resolvedMapMode() {
            if (elements.mapMode.value !== "auto") {
                return elements.mapMode.value;
            }

            return currentTopology() === "circular"
                ? "circular"
                : "linear";
        }

        function renderCircularMap(sequence) {
            const length = sequence.length;
            const cx = 410;
            const cy = 278;
            const radius = 168;

            elements.map.appendChild(
                svgElement("circle", {
                    cx,
                    cy,
                    r: radius,
                    class: "mw-map-track",
                })
            );

            state.features.forEach((feature, index) => {
                const segments = featureSegments(
                    feature,
                    length,
                    true
                );

                segments.forEach(([start, end]) => {
                    const fullLength = start === 1 && end === length;
                    let node;

                    if (fullLength) {
                        node = svgElement("circle", {
                            cx,
                            cy,
                            r: radius,
                        });
                    } else {
                        node = svgElement("path", {
                            d: circularArcPath(
                                cx,
                                cy,
                                radius,
                                start,
                                end,
                                length
                            ),
                        });
                    }

                    node.setAttribute(
                        "class",
                        selectedClass(index)
                    );
                    node.setAttribute("stroke", feature.color);
                    node.dataset.featureIndex = String(index);
                    node.addEventListener(
                        "click",
                        () => selectFeature(index)
                    );
                    elements.map.appendChild(node);
                });

                if (elements.showLabels.checked) {
                    const midpoint = feature.start <= feature.end
                        ? (feature.start + feature.end) / 2
                        : (
                            feature.start
                            + (length + feature.end)
                        ) / 2 % length;

                    const angle = (midpoint / length) * 360 - 90;
                    const point = polarPoint(
                        cx,
                        cy,
                        radius + 42,
                        angle
                    );

                    appendSvgText(
                        elements.map,
                        feature.name,
                        {
                            x: point.x,
                            y: point.y,
                            class: "mw-map-label",
                            "text-anchor": point.x < cx
                                ? "end"
                                : "start",
                        }
                    );
                }
            });

            [0, 0.25, 0.5, 0.75].forEach(fraction => {
                const point = polarPoint(
                    cx,
                    cy,
                    radius - 29,
                    fraction * 360 - 90
                );

                appendSvgText(
                    elements.map,
                    String(Math.round(length * fraction)),
                    {
                        x: point.x,
                        y: point.y,
                        class: "mw-map-coordinate",
                        "text-anchor": "middle",
                    }
                );
            });

            appendSvgText(elements.map, elements.name.value, {
                x: cx,
                y: cy - 5,
                class: "mw-map-center-title",
            });

            appendSvgText(
                elements.map,
                `${length.toLocaleString()} ${sequenceUnit()}`,
                {
                    x: cx,
                    y: cy + 18,
                    class: "mw-map-center-subtitle",
                }
            );

            renderRestrictionSites(
                sequence,
                true,
                {
                    cx,
                    cy,
                    radius,
                }
            );
        }

        function renderLinearMap(sequence) {
            const length = sequence.length;
            const left = 65;
            const right = 755;
            const width = right - left;
            const y = 278;

            elements.map.appendChild(
                svgElement("line", {
                    x1: left,
                    x2: right,
                    y1: y,
                    y2: y,
                    class: "mw-map-track",
                })
            );

            state.features.forEach((feature, index) => {
                featureSegments(feature, length, false)
                    .forEach(([start, end]) => {
                        const x1 = left + (
                            (start - 1) / length
                        ) * width;
                        const x2 = left + (
                            end / length
                        ) * width;

                        const node = svgElement("line", {
                            x1,
                            x2,
                            y1: y,
                            y2: y,
                            class: selectedClass(index),
                            stroke: feature.color,
                        });

                        node.dataset.featureIndex = String(index);
                        node.addEventListener(
                            "click",
                            () => selectFeature(index)
                        );
                        elements.map.appendChild(node);

                        if (elements.showLabels.checked) {
                            appendSvgText(
                                elements.map,
                                feature.name,
                                {
                                    x: (x1 + x2) / 2,
                                    y: y - 28 - (
                                        index % 3
                                    ) * 18,
                                    class: "mw-map-label",
                                    "text-anchor": "middle",
                                }
                            );
                        }
                    });
            });

            for (let fraction = 0; fraction <= 1; fraction += .2) {
                const x = left + width * fraction;

                elements.map.appendChild(
                    svgElement("line", {
                        x1: x,
                        x2: x,
                        y1: y + 14,
                        y2: y + 24,
                        class: "mw-enzyme-tick",
                    })
                );

                appendSvgText(
                    elements.map,
                    String(Math.round(length * fraction)),
                    {
                        x,
                        y: y + 42,
                        class: "mw-map-coordinate",
                        "text-anchor": "middle",
                    }
                );
            }

            appendSvgText(elements.map, elements.name.value, {
                x: 410,
                y: 110,
                class: "mw-map-center-title",
            });

            appendSvgText(
                elements.map,
                `${length.toLocaleString()} ${sequenceUnit()}`,
                {
                    x: 410,
                    y: 134,
                    class: "mw-map-center-subtitle",
                }
            );

            renderRestrictionSites(
                sequence,
                false,
                {
                    left,
                    width,
                    y,
                }
            );
        }

        function restrictionSites(sequence, circular) {
            const mode = elements.enzymeMode.value;

            if (
                mode === "none"
                || !sequence
                || currentType() === "protein"
            ) {
                return [];
            }

            const maximumMotif = Math.max(
                ...Object.values(ENZYMES).map(item => item.length)
            );

            const searchable = circular
                ? sequence + sequence.slice(0, maximumMotif - 1)
                : sequence;

            const sites = [];

            Object.entries(ENZYMES).forEach(([name, motif]) => {
                const positions = [];
                let position = searchable.indexOf(motif);

                while (position !== -1) {
                    if (position < sequence.length) {
                        positions.push(position + 1);
                    }

                    position = searchable.indexOf(
                        motif,
                        position + 1
                    );
                }

                if (
                    positions.length
                    && (
                        mode === "all"
                        || positions.length === 1
                    )
                ) {
                    positions.forEach(site => {
                        sites.push({name, position: site});
                    });
                }
            });

            return sites.slice(0, 120);
        }

        function renderRestrictionSites(
            sequence,
            circular,
            geometry
        ) {
            restrictionSites(sequence, circular)
                .forEach((site, index) => {
                    if (circular) {
                        const angle = (
                            site.position / sequence.length
                        ) * 360 - 90;
                        const inner = polarPoint(
                            geometry.cx,
                            geometry.cy,
                            geometry.radius + 13,
                            angle
                        );
                        const outer = polarPoint(
                            geometry.cx,
                            geometry.cy,
                            geometry.radius + 28,
                            angle
                        );

                        elements.map.appendChild(
                            svgElement("line", {
                                x1: inner.x,
                                y1: inner.y,
                                x2: outer.x,
                                y2: outer.y,
                                class: "mw-enzyme-tick",
                            })
                        );

                        if (index < 35) {
                            const label = polarPoint(
                                geometry.cx,
                                geometry.cy,
                                geometry.radius + 38,
                                angle
                            );

                            appendSvgText(
                                elements.map,
                                site.name,
                                {
                                    x: label.x,
                                    y: label.y,
                                    class: "mw-enzyme-label",
                                    "text-anchor": label.x < geometry.cx
                                        ? "end"
                                        : "start",
                                }
                            );
                        }
                    } else {
                        const x = geometry.left + (
                            site.position / sequence.length
                        ) * geometry.width;

                        elements.map.appendChild(
                            svgElement("line", {
                                x1: x,
                                x2: x,
                                y1: geometry.y + 12,
                                y2: geometry.y + 30,
                                class: "mw-enzyme-tick",
                            })
                        );

                        if (index < 35) {
                            appendSvgText(
                                elements.map,
                                site.name,
                                {
                                    x,
                                    y: geometry.y + 52 + (
                                        index % 2
                                    ) * 13,
                                    class: "mw-enzyme-label",
                                    "text-anchor": "middle",
                                }
                            );
                        }
                    }
                });
        }

        function renderLegend() {
            elements.mapLegend.replaceChildren();

            state.features.forEach((feature, index) => {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "mw-legend-chip";

                const dot = document.createElement("span");
                dot.className = "mw-legend-dot";
                dot.style.backgroundColor = feature.color;

                const label = document.createElement("span");
                label.textContent = feature.name;

                chip.append(dot, label);
                chip.addEventListener(
                    "click",
                    () => selectFeature(index)
                );

                elements.mapLegend.appendChild(chip);
            });
        }

        function renderMap() {
            const sequence = currentSequence();
            clearMap();

            elements.map.hidden = !sequence.length;
            elements.mapEmpty.hidden = Boolean(sequence.length);

            if (!sequence.length) {
                return;
            }

            if (resolvedMapMode() === "circular") {
                renderCircularMap(sequence);
            } else {
                renderLinearMap(sequence);
            }

            renderLegend();
        }

        function renderFeatureList() {
            elements.featureList.replaceChildren();
            elements.featureEmpty.hidden = state.features.length > 0;

            state.features.forEach((feature, index) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "mw-feature-item";

                if (index === state.selectedFeature) {
                    button.classList.add("is-selected");
                }

                const color = document.createElement("span");
                color.className = "mw-feature-color";
                color.style.backgroundColor = feature.color;

                const identity = document.createElement("span");

                const name = document.createElement("span");
                name.className = "mw-feature-name";
                name.textContent = feature.name;

                const meta = document.createElement("span");
                meta.className = "mw-feature-meta";
                meta.textContent = [
                    feature.type,
                    `${feature.start}..${feature.end}`,
                    feature.strand,
                ].join(" · ");

                identity.append(name, meta);

                const order = document.createElement("span");
                order.className = "mw-feature-meta";
                order.textContent = `#${index + 1}`;

                button.append(color, identity, order);
                button.addEventListener(
                    "click",
                    () => selectFeature(index)
                );

                elements.featureList.appendChild(button);
            });
        }

        function selectFeature(index) {
            if (
                index < 0
                || index >= state.features.length
            ) {
                state.selectedFeature = -1;
                elements.featureForm.hidden = true;
                renderFeatureList();
                renderMap();
                return;
            }

            state.selectedFeature = index;
            const feature = state.features[index];

            elements.featureForm.hidden = false;
            elements.featureHeading.textContent = feature.name;
            elements.featureName.value = feature.name;
            elements.featureType.value = feature.type;
            elements.featureStart.value = feature.start;
            elements.featureEnd.value = feature.end;
            elements.featureStrand.value = feature.strand;
            elements.featureColor.value = feature.color;
            elements.featureNotes.value = feature.notes;

            renderFeatureList();
            renderMap();
        }

        function updateSelectedFeature() {
            if (
                !canEdit
                || state.selectedFeature < 0
            ) {
                return;
            }

            const feature = state.features[state.selectedFeature];

            feature.name = elements.featureName.value.trim()
                || "Feature";
            feature.type = elements.featureType.value;
            feature.start = Number(elements.featureStart.value) || 1;
            feature.end = Number(elements.featureEnd.value) || 1;
            feature.strand = elements.featureStrand.value;
            feature.color = elements.featureColor.value
                || fallbackColor(feature.type);
            feature.notes = elements.featureNotes.value;
            elements.featureHeading.textContent = feature.name;

            markDirty();
            renderFeatureList();
            renderMap();
        }

        function addFeature() {
            if (!canEdit) {
                return;
            }

            const length = Math.max(1, currentSequence().length);

            state.features.push(
                normalizeFeature(
                    {
                        name: "New feature",
                        type: "custom",
                        start: 1,
                        end: Math.min(length, 10),
                        strand: "+",
                        color: FEATURE_COLORS.custom,
                    },
                    state.features.length
                )
            );

            markDirty();
            selectFeature(state.features.length - 1);
        }

        function removeFeature() {
            if (
                !canEdit
                || state.selectedFeature < 0
            ) {
                return;
            }

            state.features.splice(state.selectedFeature, 1);
            state.selectedFeature = -1;
            elements.featureForm.hidden = true;

            markDirty();
            renderFeatureList();
            renderMap();
        }

        function searchMatches(sequence, query) {
            if (!query) {
                return [];
            }

            const matches = [];
            let position = sequence.indexOf(query);

            while (position !== -1) {
                matches.push([position, position + query.length]);
                position = sequence.indexOf(query, position + 1);
            }

            return matches;
        }

        function appendHighlightedSequence(
            container,
            text,
            offset,
            matches
        ) {
            let cursor = 0;

            matches
                .filter(([start, end]) => (
                    end > offset
                    && start < offset + text.length
                ))
                .forEach(([start, end]) => {
                    const localStart = Math.max(0, start - offset);
                    const localEnd = Math.min(
                        text.length,
                        end - offset
                    );

                    if (localStart > cursor) {
                        container.append(
                            text.slice(cursor, localStart)
                        );
                    }

                    const mark = document.createElement("mark");
                    mark.textContent = text.slice(
                        localStart,
                        localEnd
                    );
                    container.appendChild(mark);
                    cursor = Math.max(cursor, localEnd);
                });

            if (cursor < text.length) {
                container.append(text.slice(cursor));
            }
        }

        function renderSequencePreview() {
            const sequence = currentSequence();
            const query = cleanSequence(elements.search.value);
            const matches = searchMatches(sequence, query);

            elements.preview.replaceChildren();
            elements.searchResult.textContent = query
                ? `${matches.length} match${matches.length === 1 ? "" : "es"}`
                : "";

            if (!sequence.length) {
                const empty = document.createElement("div");
                empty.className = "mw-empty";
                empty.textContent = "No sequence available.";
                elements.preview.appendChild(empty);
                return;
            }

            const width = 60;

            for (
                let offset = 0;
                offset < sequence.length;
                offset += width
            ) {
                const rowSequence = sequence.slice(
                    offset,
                    offset + width
                );
                const row = document.createElement("div");
                row.className = "mw-sequence-row";

                const start = document.createElement("span");
                start.className = "mw-sequence-coordinate";
                start.textContent = String(offset + 1);

                const text = document.createElement("span");
                text.className = "mw-sequence-text";

                for (
                    let chunkOffset = 0;
                    chunkOffset < rowSequence.length;
                    chunkOffset += 10
                ) {
                    const chunk = rowSequence.slice(
                        chunkOffset,
                        chunkOffset + 10
                    );

                    appendHighlightedSequence(
                        text,
                        chunk,
                        offset + chunkOffset,
                        matches
                    );

                    if (
                        chunkOffset + 10
                        < rowSequence.length
                    ) {
                        text.append(" ");
                    }
                }

                const end = document.createElement("span");
                end.className = "mw-sequence-end";
                end.textContent = String(
                    offset + rowSequence.length
                );

                row.append(start, text, end);
                elements.preview.appendChild(row);
            }
        }

        function syncStatistics() {
            const sequence = currentSequence();
            const gc = gcContent(sequence);

            elements.statLength.textContent =
                sequence.length.toLocaleString();
            elements.statUnit.textContent = sequenceUnit();
            elements.statGc.textContent = gc === null
                ? "—"
                : `${gc.toFixed(2)}%`;
            elements.title.textContent =
                elements.name.value || "Untitled molecular item";
            elements.typeBadge.textContent =
                elements.type.options[
                    elements.type.selectedIndex
                ]?.text || currentType();
            elements.topologyBadge.textContent =
                elements.topology.options[
                    elements.topology.selectedIndex
                ]?.text || currentTopology();
        }

        function renderAll() {
            syncStatistics();
            renderMap();
            renderFeatureList();
            renderSequencePreview();
        }

        function scheduleRender() {
            clearTimeout(state.renderTimer);

            state.renderTimer = setTimeout(() => {
                renderAll();
            }, 120);
        }

        function featurePayload() {
            return state.features.map((feature, order) => ({
                name: feature.name,
                type: feature.type,
                start: feature.start,
                end: feature.end,
                strand: feature.strand,
                color: feature.color,
                notes: feature.notes,
                qualifiers: feature.qualifiers || {},
                order,
            }));
        }

        async function loadFeatures() {
            setStatus("Loading annotations...");

            try {
                const data = await requestJson(
                    root.dataset.featuresUrl,
                    {
                        headers: {
                            Accept: "application/json",
                        },
                    }
                );

                state.features = (data.features || [])
                    .map(normalizeFeature);
                state.selectedFeature = -1;

                renderAll();
                setStatus(
                    canEdit ? "Ready" : "Read-only access"
                );
            } catch (error) {
                console.error(error);
                setStatus(
                    `Annotation load error: ${error.message}`,
                    "error"
                );
            }
        }

        async function saveWorkspace() {
            if (!canEdit) {
                return;
            }

            const sequence = currentSequence();

            if (!elements.name.value.trim()) {
                alert("Molecular item name is required.");
                elements.name.focus();
                return;
            }

            setStatus(
                "Saving sequence and annotations..."
            );

            try {
                const data = await requestJson(
                    root.dataset.updateUrl,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": csrfToken(),
                        },
                        body: JSON.stringify({
                            name: elements.name.value.trim(),
                            sequence_type: currentType(),
                            topology: currentTopology(),
                            description: elements.description.value,
                            sequence,
                            features: featurePayload(),
                        }),
                    }
                );

                state.features = (data.features || [])
                    .map(normalizeFeature);
                state.dirty = false;
                state.selectedFeature = -1;
                elements.featureForm.hidden = true;

                elements.statLength.textContent =
                    Number(data.length || 0)
                        .toLocaleString();
                elements.statGc.textContent =
                    data.gc_content === null
                    || data.gc_content === undefined
                        ? "—"
                        : `${data.gc_content}%`;
                elements.statChecksum.textContent =
                    data.checksum_sha256
                    || "Not calculated";

                renderAll();

                setStatus(
                    "Sequence and annotations saved",
                    "success"
                );
            } catch (error) {
                console.error(error);
                setStatus(error.message, "error");
                alert(error.message);
            }
        }

        async function deleteWorkspace() {
            if (!canEdit) {
                return;
            }

            const confirmed = window.confirm(
                `Delete molecular item "${elements.name.value}"?`
            );

            if (!confirmed) {
                return;
            }

            setStatus("Deleting...");

            try {
                const data = await requestJson(
                    root.dataset.deleteUrl,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": csrfToken(),
                        },
                    }
                );

                state.dirty = false;
                window.location.href =
                    data.redirect_url
                    || root.dataset.backUrl;
            } catch (error) {
                console.error(error);
                setStatus(error.message, "error");
                alert(error.message);
            }
        }

        function sanitizeFilename(value) {
            return String(value || "molecular-item")
                .replace(/[^A-Za-z0-9._-]+/g, "_")
                .replace(/^_+|_+$/g, "")
                || "molecular-item";
        }

        function wrapSequence(sequence, width = 70) {
            const lines = [];

            for (
                let offset = 0;
                offset < sequence.length;
                offset += width
            ) {
                lines.push(sequence.slice(offset, offset + width));
            }

            return lines.join("\n");
        }

        function downloadText(filename, content) {
            const blob = new Blob(
                [content],
                {type: "text/plain;charset=utf-8"}
            );
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");

            anchor.href = url;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();

            URL.revokeObjectURL(url);
        }

        function exportFasta() {
            const name = elements.name.value.trim()
                || "molecular-item";
            const sequence = currentSequence();

            downloadText(
                `${sanitizeFilename(name)}.fasta`,
                `>${name}\n${wrapSequence(sequence)}\n`
            );
        }

        function genbankLocation(feature, length) {
            let location;

            if (
                currentTopology() === "circular"
                && feature.start > feature.end
            ) {
                location = `join(${feature.start}..${length},1..${feature.end})`;
            } else {
                location = `${feature.start}..${feature.end}`;
            }

            if (feature.strand === "-") {
                location = `complement(${location})`;
            }

            return location;
        }

        function exportGenbank() {
            const name = elements.name.value.trim()
                || "MOLECULAR_ITEM";
            const sequence = currentSequence();
            const unit = currentType() === "protein"
                ? "aa"
                : "bp";
            const locusName = sanitizeFilename(name)
                .slice(0, 16)
                .padEnd(16, " ");

            const lines = [
                `LOCUS       ${locusName} ${String(sequence.length).padStart(7)} ${unit}    ${currentTopology()}`,
                `DEFINITION  ${elements.description.value || name}.`,
                "FEATURES             Location/Qualifiers",
            ];

            state.features.forEach(feature => {
                lines.push(
                    `     ${feature.type.padEnd(15)} ${genbankLocation(feature, sequence.length)}`
                );
                lines.push(
                    `                     /label="${feature.name.replaceAll('"', "'")}"`
                );

                if (feature.notes) {
                    lines.push(
                        `                     /note="${feature.notes.replaceAll('"', "'")}"`
                    );
                }
            });

            lines.push("ORIGIN");

            for (
                let offset = 0;
                offset < sequence.length;
                offset += 60
            ) {
                const row = sequence
                    .slice(offset, offset + 60)
                    .toLowerCase()
                    .match(/.{1,10}/g)
                    ?.join(" ") || "";

                lines.push(
                    `${String(offset + 1).padStart(9)} ${row}`
                );
            }

            lines.push("//");

            downloadText(
                `${sanitizeFilename(name)}.gb`,
                `${lines.join("\n")}\n`
            );
        }

        function importFastaFile(file) {
            const reader = new FileReader();

            reader.onload = () => {
                const text = String(reader.result || "");
                const headers = text
                    .split(/\r?\n/)
                    .filter(line => line.startsWith(">"));

                if (headers.length > 1) {
                    alert(
                        "Only one FASTA record may be imported."
                    );
                    return;
                }

                const header = headers.length
                    ? headers[0].slice(1).trim()
                    : "";

                const sequence = text
                    .split(/\r?\n/)
                    .filter(line => !line.startsWith(">"))
                    .join("");

                elements.sequence.value = cleanSequence(sequence);

                if (header && !elements.name.value.trim()) {
                    elements.name.value = header.split(/\s+/)[0];
                }

                markDirty();
                renderAll();
            };

            reader.readAsText(file);
        }

        [
            elements.name,
            elements.type,
            elements.topology,
            elements.description,
        ].forEach(element => {
            element.addEventListener("input", () => {
                markDirty();
                renderAll();
            });
        });

        elements.sequence.addEventListener("input", () => {
            markDirty();
            scheduleRender();
        });

        [
            elements.mapMode,
            elements.enzymeMode,
            elements.showLabels,
        ].forEach(element => {
            element.addEventListener("change", renderMap);
        });

        [
            elements.featureName,
            elements.featureType,
            elements.featureStart,
            elements.featureEnd,
            elements.featureStrand,
            elements.featureColor,
            elements.featureNotes,
        ].forEach(element => {
            element.addEventListener(
                "input",
                updateSelectedFeature
            );
            element.addEventListener(
                "change",
                updateSelectedFeature
            );
        });

        elements.search.addEventListener(
            "input",
            renderSequencePreview
        );

        elements.save?.addEventListener(
            "click",
            saveWorkspace
        );
        elements.delete?.addEventListener(
            "click",
            deleteWorkspace
        );
        elements.featureAdd?.addEventListener(
            "click",
            addFeature
        );
        elements.featureRemove?.addEventListener(
            "click",
            removeFeature
        );

        elements.copy.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(
                    currentSequence()
                );
                setStatus("Sequence copied", "success");
            } catch (error) {
                setStatus("Could not copy sequence", "error");
            }
        });

        elements.importFasta.addEventListener(
            "click",
            () => elements.fastaFile.click()
        );

        elements.fastaFile.addEventListener("change", () => {
            const file = elements.fastaFile.files?.[0];

            if (file) {
                importFastaFile(file);
            }

            elements.fastaFile.value = "";
        });

        elements.exportFasta.addEventListener(
            "click",
            exportFasta
        );
        elements.exportGenbank.addEventListener(
            "click",
            exportGenbank
        );

        window.addEventListener("beforeunload", event => {
            if (!state.dirty) {
                return;
            }

            event.preventDefault();
            event.returnValue = "";
        });

        renderAll();
        loadFeatures();
    });
})();
