/*
 * Biobank — shared sequence-track renderer.
 *
 * Coordinates are 1-based and inclusive, matching MolecularFeature and
 * molecular_workspace.js. This component renders only; the raw textarea
 * remains the editing/import surface in this phase.
 */
(function () {
    "use strict";

    const COMPLEMENT = {
        A: "T", T: "A", U: "A", G: "C", C: "G",
        R: "Y", Y: "R", S: "S", W: "W", K: "M", M: "K",
        B: "V", V: "B", D: "H", H: "D", N: "N",
    };

    const NUCLEOTIDE_COLORS = {
        A: "#f4a6a6",
        C: "#8ecae6",
        G: "#f6c453",
        T: "#9bd3ae",
        U: "#9bd3ae",
        R: "#d8c2f0",
        Y: "#b8d8d8",
        S: "#c9d6ff",
        W: "#f5d0c5",
        K: "#c8e6c9",
        M: "#ffe0b2",
        B: "#d7e3fc",
        D: "#f8d7da",
        H: "#d1e7dd",
        V: "#fff3cd",
        N: "#c9ced6",
    };

    const AMINO_ACID_COLORS = {
        A: "#d8f3dc", C: "#ffe8a1", D: "#ffadad", E: "#ffadad",
        F: "#d8f3dc", G: "#f1f3f5", H: "#91a7ff", I: "#d8f3dc",
        K: "#91a7ff", L: "#d8f3dc", M: "#d8f3dc", N: "#a8e6e6",
        P: "#ffd6a5", Q: "#a8e6e6", R: "#91a7ff", S: "#a8e6e6",
        T: "#a8e6e6", V: "#d8f3dc", W: "#d8f3dc", Y: "#d8f3dc",
        X: "#e9ecef", "*": "#d93a3a",
    };

    const CODONS = (() => {
        const bases = "TCAG";
        const acids = (
            "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRR" +
            "IIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
        );
        const table = {};
        let index = 0;

        for (const first of bases) {
            for (const second of bases) {
                for (const third of bases) {
                    table[first + second + third] = acids[index];
                    index += 1;
                }
            }
        }

        return table;
    })();

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function element(tag, className = "", text = undefined) {
        const node = document.createElement(tag);

        if (className) {
            node.className = className;
        }

        if (text !== undefined) {
            node.textContent = text;
        }

        return node;
    }

    function track(className, rowBases) {
        const node = element("div", `mw-track ${className}`);
        node.style.setProperty("--mw-row-bases", String(rowBases));
        return node;
    }

    function complementOf(sequence) {
        return [...String(sequence || "")]
            .map(symbol => COMPLEMENT[symbol] || "N")
            .join("");
    }

    function translateCodon(codon) {
        return CODONS[String(codon || "").replace(/U/g, "T")] || "X";
    }

    function symbolColorsForType(sequenceType) {
        return sequenceType === "protein"
            ? AMINO_ACID_COLORS
            : NUCLEOTIDE_COLORS;
    }

    function featureSegments(feature, length, circular) {
        if (!length) {
            return [];
        }

        const start = clamp(Number(feature.start) || 1, 1, length);
        const end = clamp(Number(feature.end) || 1, 1, length);

        if (circular && start > end) {
            return [
                {start, end: length, continuedRight: true},
                {start: 1, end, continuedLeft: true},
            ];
        }

        return [{
            start: Math.min(start, end),
            end: Math.max(start, end),
        }];
    }

    function containsCoordinate(selection, coordinate, length, circular) {
        if (!selection) {
            return false;
        }

        const start = Number(selection.start);
        const end = Number(selection.end);

        if (circular && start > end) {
            return coordinate >= start || coordinate <= end;
        }

        return coordinate >= Math.min(start, end)
            && coordinate <= Math.max(start, end);
    }

    function coveringFeatures(options, coordinate) {
        return options.features
            .map((feature, index) => ({feature, index}))
            .filter(({feature}) => featureSegments(
                feature,
                options.length,
                options.circular
            ).some(segment => (
                coordinate >= segment.start
                && coordinate <= segment.end
            )));
    }

    function assignLanes(segments) {
        const laneEnds = [];

        segments.forEach(segment => {
            let lane = laneEnds.findIndex(lastEnd => lastEnd < segment.start);

            if (lane === -1) {
                lane = laneEnds.length;
            }

            laneEnds[lane] = segment.end;
            segment.lane = lane + 1;
        });

        return segments;
    }

    function normalizeOptions(rawOptions = {}) {
        const sequence = String(rawOptions.sequence || "").toUpperCase();

        return {
            sequence,
            sequenceType: String(rawOptions.sequenceType || "dna").toLowerCase(),
            length: sequence.length,
            circular: rawOptions.circular === true,
            features: Array.isArray(rawOptions.features)
                ? rawOptions.features
                : [],
            translations: Array.isArray(rawOptions.translations)
                ? rawOptions.translations
                : [],
            enzymes: Array.isArray(rawOptions.enzymes)
                ? rawOptions.enzymes
                : [],
            matches: rawOptions.matches instanceof Set
                ? rawOptions.matches
                : new Set(rawOptions.matches || []),
            structureCoverage: (
                rawOptions.structureCoverage instanceof Set
                    ? rawOptions.structureCoverage
                    : new Set(
                        rawOptions.structureCoverage
                        || []
                    )
            ),
            selection: rawOptions.selection || null,
            selectedFeature: Number.isInteger(rawOptions.selectedFeature)
                ? rawOptions.selectedFeature
                : -1,
            showComplement: rawOptions.showComplement !== false,
            showCodons: rawOptions.showCodons !== false,
            showIndex: rawOptions.showIndex !== false,
            basesPerRow: Math.max(10, Number(rawOptions.basesPerRow) || 60),
            rulerStep: Math.max(1, Number(rawOptions.rulerStep) || 10),
            symbolColors: rawOptions.symbolColors || symbolColorsForType(
                String(rawOptions.sequenceType || "dna").toLowerCase()
            ),
        };
    }

    function buildCodonTrack(options, rowStart, rowEnd, rowBases) {
        const node = track("mw-track-codons", rowBases);

        options.translations.forEach(translation => {
            const start = Number(translation.start);
            const end = Number(translation.end);

            // Reverse, circular and phased translations remain delegated to
            // SeqViz until their biological frame handling is implemented.
            if (
                translation.strand === "-"
                || !Number.isInteger(start)
                || !Number.isInteger(end)
                || start > end
            ) {
                return;
            }

            for (
                let codonStart = start;
                codonStart + 2 <= end;
                codonStart += 3
            ) {
                const codonEnd = codonStart + 2;

                if (codonEnd < rowStart || codonStart > rowEnd) {
                    continue;
                }

                const aminoAcid = translateCodon(
                    options.sequence.slice(codonStart - 1, codonEnd)
                );
                const visibleStart = Math.max(codonStart, rowStart);
                const visibleEnd = Math.min(codonEnd, rowEnd);
                const alternate = ((codonStart - start) / 3) % 2 === 0;
                const chip = element(
                    "span",
                    [
                        "mw-codon",
                        aminoAcid === "*"
                            ? "is-stop"
                            : (alternate ? "is-shade-a" : "is-shade-b"),
                    ].join(" "),
                    aminoAcid
                );

                chip.style.setProperty(
                    "--mw-col",
                    String(visibleStart - rowStart + 1)
                );
                chip.style.setProperty(
                    "--mw-span",
                    String(visibleEnd - visibleStart + 1)
                );
                chip.title = [
                    translation.name || "CDS",
                    `${codonStart}..${codonEnd}`,
                ].join(" · ");
                node.appendChild(chip);
            }
        });

        return node;
    }

    function buildEnzymeTrack(options, rowStart, rowEnd, rowBases) {
        const node = track("mw-track-enzymes", rowBases);

        options.enzymes.forEach((site, index) => {
            const coordinate = Number(site.coordinate);

            if (coordinate < rowStart || coordinate > rowEnd) {
                return;
            }

            const label = element("span", "mw-enzyme-label", site.name);
            label.style.setProperty(
                "--mw-col",
                String(coordinate - rowStart + 1)
            );
            label.style.setProperty(
                "--mw-enzyme-lane",
                String(index % 3)
            );
            label.title = `${site.name} · ${coordinate}`;
            node.appendChild(label);
        });

        return node;
    }

    function buildStrandTrack(options, rowStart, rowEnd, rowBases, reverse) {
        const node = track(
            `mw-track-strand ${reverse ? "mw-track-complement" : "mw-track-forward"}`,
            rowBases
        );
        const selectionStart = options.selection
            ? Number(options.selection.start)
            : null;
        const selectionEnd = options.selection
            ? Number(options.selection.end)
            : null;

        for (
            let coordinate = rowStart;
            coordinate <= rowEnd;
            coordinate += 1
        ) {
            const symbol = options.sequence[coordinate - 1];
            const shownSymbol = reverse
                ? (COMPLEMENT[symbol] || "N")
                : symbol;
            const base = element("span", "mw-base", shownSymbol);
            const features = coveringFeatures(options, coordinate);

            base.style.setProperty(
                "--mw-symbol-color",
                options.symbolColors[shownSymbol] || "#687386"
            );

            if (!reverse) {
                base.dataset.coordinate = String(coordinate);

                if (features.length) {
                    base.dataset.featureIndex = String(features[0].index);
                    base.style.setProperty(
                        "--mw-base-feature-color",
                        features[0].feature.color || "#8f96a3"
                    );
                    base.classList.add("has-feature");
                    base.title = features
                        .map(item => item.feature.name)
                        .join(", ");
                }
            }

            if (containsCoordinate(
                options.selection,
                coordinate,
                options.length,
                options.circular
            )) {
                base.classList.add("is-selected");

                if (coordinate === selectionStart) {
                    base.classList.add("is-selection-start");
                }

                if (coordinate === selectionEnd) {
                    base.classList.add("is-selection-end");
                }
            }

            if (options.matches.has(coordinate)) {
                base.classList.add("is-match");
            }

            if (
                !reverse
                && options.structureCoverage.has(
                    coordinate
                )
            ) {
                base.classList.add(
                    "is-structure-covered"
                );
            }

            node.appendChild(base);
        }

        return node;
    }

    function buildRulerTrack(rowStart, rowEnd, rowBases, step) {
        const node = track("mw-track-ruler", rowBases);
        const first = Math.ceil(rowStart / step) * step;

        if (rowStart === 1) {
            const origin = element("span", "mw-tick", "1");
            origin.style.setProperty("--mw-col", "1");
            node.appendChild(origin);
        }

        for (
            let coordinate = first;
            coordinate <= rowEnd;
            coordinate += step
        ) {
            const tick = element("span", "mw-tick", String(coordinate));
            tick.style.setProperty(
                "--mw-col",
                String(coordinate - rowStart + 1)
            );
            node.appendChild(tick);
        }

        return node;
    }

    function buildFeatureTrack(options, rowStart, rowEnd, rowBases) {
        const node = track("mw-track-features", rowBases);
        const visible = [];

        options.features.forEach((feature, featureIndex) => {
            featureSegments(feature, options.length, options.circular)
                .forEach(segment => {
                    if (segment.end < rowStart || segment.start > rowEnd) {
                        return;
                    }

                    visible.push({
                        feature,
                        featureIndex,
                        start: Math.max(segment.start, rowStart),
                        end: Math.min(segment.end, rowEnd),
                        continuedLeft: Boolean(
                            segment.continuedLeft || segment.start < rowStart
                        ),
                        continuedRight: Boolean(
                            segment.continuedRight || segment.end > rowEnd
                        ),
                    });
                });
        });

        visible.sort((left, right) => (
            left.start - right.start || left.end - right.end
        ));

        assignLanes(visible).forEach(segment => {
            const {feature} = segment;
            const span = segment.end - segment.start + 1;
            const forward = feature.strand !== "-";
            const classes = ["mw-feature-bar"];

            if (forward && !segment.continuedRight) {
                classes.push("is-forward");
            }

            if (!forward && !segment.continuedLeft) {
                classes.push("is-reverse");
            }

            if (segment.continuedLeft) {
                classes.push("is-continued-left");
            }

            if (segment.continuedRight) {
                classes.push("is-continued-right");
            }

            if (segment.featureIndex === options.selectedFeature) {
                classes.push("is-selected");
            }

            const bar = element(
                "span",
                classes.join(" "),
                span >= 5 ? feature.name : ""
            );

            bar.tabIndex = 0;
            bar.setAttribute("role", "button");
            bar.setAttribute(
                "aria-label",
                `${feature.name}, ${feature.start} to ${feature.end}`
            );
            bar.setAttribute("data-feature-bar", "true");
            bar.dataset.featureIndex = String(segment.featureIndex);
            bar.style.setProperty(
                "--mw-col",
                String(segment.start - rowStart + 1)
            );
            bar.style.setProperty("--mw-span", String(span));
            bar.style.setProperty("--mw-lane", String(segment.lane));
            bar.style.setProperty(
                "--mw-feature-color",
                feature.color || "#8f96a3"
            );
            bar.title = `${feature.name} · ${feature.start}..${feature.end}`;
            node.appendChild(bar);
        });

        return node;
    }

    function renderSequenceTracks(container, rawOptions = {}) {
        if (!container) {
            return;
        }

        const options = normalizeOptions(rawOptions);
        const previousScrollTop = container.scrollTop;
        const previousScrollLeft = container.scrollLeft;

        container.replaceChildren();
        container.classList.add("mw-seq-track");

        if (!options.length) {
            container.appendChild(
                element("div", "mw-empty", "No sequence available.")
            );
            return;
        }

        const fragment = document.createDocumentFragment();

        for (
            let rowStart = 1;
            rowStart <= options.length;
            rowStart += options.basesPerRow
        ) {
            const rowEnd = Math.min(
                rowStart + options.basesPerRow - 1,
                options.length
            );
            const rowBases = rowEnd - rowStart + 1;
            const row = element("div", "mw-seq-row");
            const tracks = element("div", "mw-seq-tracks");

            row.dataset.rowStart = String(rowStart);
            row.dataset.rowEnd = String(rowEnd);

            if (
                options.sequenceType !== "protein"
                && options.showCodons
                && options.translations.length
            ) {
                tracks.appendChild(
                    buildCodonTrack(options, rowStart, rowEnd, rowBases)
                );
            }

            if (options.enzymes.length) {
                tracks.appendChild(
                    buildEnzymeTrack(options, rowStart, rowEnd, rowBases)
                );
            }

            tracks.appendChild(
                buildStrandTrack(options, rowStart, rowEnd, rowBases, false)
            );

            if (
                options.sequenceType !== "protein"
                && options.showComplement
            ) {
                tracks.appendChild(
                    buildStrandTrack(options, rowStart, rowEnd, rowBases, true)
                );
            }

            if (options.showIndex) {
                tracks.appendChild(
                    buildRulerTrack(
                        rowStart,
                        rowEnd,
                        rowBases,
                        options.rulerStep
                    )
                );
            }

            if (options.features.length) {
                tracks.appendChild(
                    buildFeatureTrack(options, rowStart, rowEnd, rowBases)
                );
            }

            row.append(
                element("span", "mw-seq-gutter", String(rowStart)),
                tracks,
                element(
                    "span",
                    "mw-seq-gutter mw-seq-gutter-end",
                    String(rowEnd)
                )
            );
            fragment.appendChild(row);
        }

        container.appendChild(fragment);
        container.scrollTop = previousScrollTop;
        container.scrollLeft = previousScrollLeft;
    }

    window.BiobankSequenceTrack = {
        render: renderSequenceTracks,
        complementOf,
        translateCodon,
        featureSegments,
        symbolColorsForType,
        NUCLEOTIDE_COLORS,
        AMINO_ACID_COLORS,
    };
})();
