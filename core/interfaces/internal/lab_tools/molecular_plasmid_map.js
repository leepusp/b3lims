(() => {
    "use strict";

    const SVG_NS = "http://www.w3.org/2000/svg";

    const DEFAULT_VIEW_BOX = {
        x: 0,
        y: 0,
        width: 1000,
        height: 760,
    };

    const VIEW_STORAGE_KEY =
        "biobank.molecular-workspace.plasmid-map-view.v2";

    const LABEL_LIMITS = {
        compact: 60,
        detailed: 220,
        publication: 360,
    };

    const SVG_EXPORT_STYLE = `
        .mpm-map-background { fill: #ffffff; }
        .mpm-backbone {
            fill: none;
            stroke: #344054;
            stroke-width: 2.25;
        }
        .mpm-linear-backbone {
            stroke: #344054;
            stroke-width: 3;
        }
        .mpm-coordinate-tick {
            stroke: #98a2b3;
            stroke-width: 1;
        }
        .mpm-coordinate-label {
            fill: #667085;
            font: 600 10px sans-serif;
        }
        .mpm-center-title {
            fill: #101828;
            font: 800 19px sans-serif;
        }
        .mpm-center-length {
            fill: #344054;
            font: 700 13px sans-serif;
        }
        .mpm-center-topology {
            fill: #667085;
            font: 600 10px sans-serif;
        }
        .mpm-feature-arc {
            fill: none;
            stroke-linecap: round;
        }
        .mpm-feature-label {
            fill: #344054;
            font: 700 10.5px sans-serif;
            paint-order: stroke;
            stroke: #ffffff;
            stroke-width: 3px;
            stroke-linejoin: round;
        }
        .mpm-restriction-tick {
            stroke: #344054;
            stroke-width: 1.45;
        }
        .mpm-restriction-leader {
            fill: none;
            stroke: #98a2b3;
            stroke-width: .8;
        }
        .mpm-restriction-label {
            fill: #344054;
            font: 650 9.5px sans-serif;
            paint-order: stroke;
            stroke: #ffffff;
            stroke-width: 3px;
            stroke-linejoin: round;
        }
        .mpm-label-limit-note {
            fill: #667085;
            font: 600 9px sans-serif;
        }
    `;

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener(
                "DOMContentLoaded",
                callback,
                {once: true},
            );
        } else {
            callback();
        }
    }

    function clamp(value, minimum, maximum) {
        return Math.max(
            minimum,
            Math.min(maximum, value),
        );
    }

    function numeric(value, fallback = 0) {
        const parsed = Number(value);

        return Number.isFinite(parsed)
            ? parsed
            : fallback;
    }

    function formatted(value) {
        return numeric(value)
            .toLocaleString();
    }

    function safeFilename(value) {
        return String(
            value || "molecular-map",
        )
            .trim()
            .replace(
                /[^A-Za-z0-9._-]+/g,
                "_",
            )
            .replace(
                /^_+|_+$/g,
                "",
            )
            || "molecular-map";
    }

    function svgElement(
        tag,
        attributes = {},
    ) {
        const node = (
            document.createElementNS(
                SVG_NS,
                tag,
            )
        );

        Object.entries(attributes)
            .forEach(
                ([key, value]) => {
                    if (
                        value === null
                        || value === undefined
                    ) {
                        return;
                    }

                    node.setAttribute(
                        key,
                        String(value),
                    );
                },
            );

        return node;
    }

    function svgText(
        parent,
        text,
        attributes = {},
    ) {
        const node = svgElement(
            "text",
            attributes,
        );

        node.textContent = String(
            text ?? "",
        );

        parent.appendChild(node);

        return node;
    }

    function svgTitle(
        parent,
        text,
    ) {
        const title = svgElement(
            "title",
        );

        title.textContent = String(
            text || "",
        );

        parent.appendChild(title);
    }

    function workspaceApi() {
        return (
            window.BiobankMolecularWorkspace
            || null
        );
    }

    function csrfToken(root) {
        const embedded = String(
            root.dataset.csrfToken || "",
        );

        if (
            embedded
            && embedded !== "NOTPROVIDED"
        ) {
            return embedded;
        }

        const cookie = document.cookie
            .split(";")
            .map(item => item.trim())
            .find(
                item => (
                    item.startsWith(
                        "csrftoken=",
                    )
                ),
            );

        if (!cookie) {
            return "";
        }

        return decodeURIComponent(
            cookie.slice(
                "csrftoken=".length,
            ),
        );
    }

    function snapshotFeatures(snapshot) {
        return Array.isArray(
            snapshot?.features,
        )
            ? snapshot.features
            : [];
    }

    function featureSegments(
        feature,
        sequenceLength,
        circular,
    ) {
        if (!sequenceLength) {
            return [];
        }

        const start = clamp(
            Math.round(
                numeric(
                    feature.start,
                    1,
                ),
            ),
            1,
            sequenceLength,
        );

        const end = clamp(
            Math.round(
                numeric(
                    feature.end,
                    1,
                ),
            ),
            1,
            sequenceLength,
        );

        if (
            circular
            && start > end
        ) {
            return [
                {
                    start,
                    end: sequenceLength,
                },
                {
                    start: 1,
                    end,
                },
            ];
        }

        return [
            {
                start: Math.min(
                    start,
                    end,
                ),
                end: Math.max(
                    start,
                    end,
                ),
            },
        ];
    }

    function featureLength(
        feature,
        sequenceLength,
        circular,
    ) {
        return featureSegments(
            feature,
            sequenceLength,
            circular,
        ).reduce(
            (
                total,
                segment,
            ) => (
                total
                + segment.end
                - segment.start
                + 1
            ),
            0,
        );
    }

    function segmentsOverlap(
        first,
        second,
        padding = 0,
    ) {
        return !(
            first.end + padding
                < second.start
            || second.end + padding
                < first.start
        );
    }

    function assignCircularFeatureLanes(
        features,
        sequenceLength,
    ) {
        const lanes = [];

        return features
            .map(
                (
                    feature,
                    featureIndex,
                ) => ({
                    feature,
                    featureIndex,
                    segments: featureSegments(
                        feature,
                        sequenceLength,
                        true,
                    ),
                }),
            )
            .sort(
                (first, second) => (
                    numeric(
                        first.feature.start,
                    )
                    - numeric(
                        second.feature.start,
                    )
                ),
            )
            .map(entry => {
                let chosenLane = -1;

                for (
                    let laneIndex = 0;
                    laneIndex < lanes.length;
                    laneIndex += 1
                ) {
                    const conflict = (
                        lanes[laneIndex]
                            .some(
                                existing => (
                                    entry.segments.some(
                                        segment => (
                                            existing.segments.some(
                                                other => (
                                                    segmentsOverlap(
                                                        segment,
                                                        other,
                                                        3,
                                                    )
                                                ),
                                            )
                                        ),
                                    )
                                ),
                            )
                    );

                    if (!conflict) {
                        chosenLane = laneIndex;
                        break;
                    }
                }

                if (chosenLane < 0) {
                    chosenLane = lanes.length;
                    lanes.push([]);
                }

                lanes[chosenLane].push(
                    entry,
                );

                return {
                    ...entry,
                    lane: Math.min(
                        chosenLane,
                        5,
                    ),
                };
            });
    }

    function coordinateAngle(
        coordinate,
        sequenceLength,
    ) {
        if (!sequenceLength) {
            return -Math.PI / 2;
        }

        return (
            (
                (
                    numeric(
                        coordinate,
                        1,
                    )
                    - 1
                )
                / sequenceLength
            )
            * Math.PI
            * 2
            - Math.PI / 2
        );
    }

    function boundaryAngle(
        boundary,
        sequenceLength,
    ) {
        if (!sequenceLength) {
            return -Math.PI / 2;
        }

        return (
            (
                numeric(
                    boundary,
                    0,
                )
                / sequenceLength
            )
            * Math.PI
            * 2
            - Math.PI / 2
        );
    }

    function polarPoint(
        cx,
        cy,
        radius,
        angle,
    ) {
        return {
            x: (
                cx
                + Math.cos(angle)
                * radius
            ),
            y: (
                cy
                + Math.sin(angle)
                * radius
            ),
        };
    }

    function arcPath(
        cx,
        cy,
        radius,
        start,
        end,
        sequenceLength,
    ) {
        const span = (
            end
            - start
            + 1
        );

        if (
            span >= sequenceLength
            && sequenceLength > 0
        ) {
            return null;
        }

        const startAngle = (
            boundaryAngle(
                start - 1,
                sequenceLength,
            )
        );

        const endAngle = (
            boundaryAngle(
                end,
                sequenceLength,
            )
        );

        const first = polarPoint(
            cx,
            cy,
            radius,
            startAngle,
        );

        const last = polarPoint(
            cx,
            cy,
            radius,
            endAngle,
        );

        const angularSpan = (
            span
            / sequenceLength
            * Math.PI
            * 2
        );

        return [
            "M",
            first.x,
            first.y,
            "A",
            radius,
            radius,
            0,
            angularSpan > Math.PI
                ? 1
                : 0,
            1,
            last.x,
            last.y,
        ].join(" ");
    }

    function featureMiddleAngle(
        feature,
        sequenceLength,
        circular,
    ) {
        const start = clamp(
            numeric(
                feature.start,
                1,
            ),
            1,
            sequenceLength,
        );

        const span = featureLength(
            feature,
            sequenceLength,
            circular,
        );

        const boundary = (
            (
                start
                - 1
                + span / 2
            )
            % sequenceLength
        );

        return boundaryAngle(
            boundary,
            sequenceLength,
        );
    }

    function arrowPolygon(
        cx,
        cy,
        radius,
        angle,
        forward,
        size,
    ) {
        const tip = polarPoint(
            cx,
            cy,
            radius,
            angle,
        );

        let tangentX = (
            -Math.sin(angle)
        );

        let tangentY = (
            Math.cos(angle)
        );

        if (!forward) {
            tangentX *= -1;
            tangentY *= -1;
        }

        const normalX = -tangentY;
        const normalY = tangentX;

        const baseX = (
            tip.x
            - tangentX
            * size
        );

        const baseY = (
            tip.y
            - tangentY
            * size
        );

        const halfWidth = (
            size * 0.65
        );

        return [
            [
                tip.x,
                tip.y,
            ],
            [
                baseX
                    + normalX
                    * halfWidth,
                baseY
                    + normalY
                    * halfWidth,
            ],
            [
                baseX
                    - normalX
                    * halfWidth,
                baseY
                    - normalY
                    * halfWidth,
            ],
        ]
            .map(
                pair => (
                    pair.join(",")
                ),
            )
            .join(" ");
    }

    function niceCoordinateStep(length) {
        if (length <= 100) {
            return 10;
        }

        if (length <= 500) {
            return 50;
        }

        if (length <= 1000) {
            return 100;
        }

        if (length <= 2500) {
            return 250;
        }

        if (length <= 5000) {
            return 500;
        }

        if (length <= 10000) {
            return 1000;
        }

        if (length <= 25000) {
            return 2500;
        }

        if (length <= 50000) {
            return 5000;
        }

        if (length <= 100000) {
            return 10000;
        }

        return Math.pow(
            10,
            Math.max(
                1,
                Math.floor(
                    Math.log10(
                        length,
                    ),
                )
                - 1,
            ),
        );
    }

    function distributeVerticalLabels(
        items,
        minimumY,
        maximumY,
        gap,
    ) {
        if (!items.length) {
            return;
        }

        items.sort(
            (
                first,
                second,
            ) => (
                first.preferredY
                - second.preferredY
            ),
        );

        items[0].y = clamp(
            items[0].preferredY,
            minimumY,
            maximumY,
        );

        for (
            let index = 1;
            index < items.length;
            index += 1
        ) {
            items[index].y = Math.max(
                clamp(
                    items[index]
                        .preferredY,
                    minimumY,
                    maximumY,
                ),
                items[index - 1].y
                    + gap,
            );
        }

        const overflow = (
            items[
                items.length - 1
            ].y
            - maximumY
        );

        if (overflow > 0) {
            items[
                items.length - 1
            ].y -= overflow;

            for (
                let index = (
                    items.length - 2
                );
                index >= 0;
                index -= 1
            ) {
                items[index].y = Math.min(
                    items[index].y,
                    items[index + 1].y
                        - gap,
                );
            }
        }

        if (
            items[0].y
            < minimumY
        ) {
            const shift = (
                minimumY
                - items[0].y
            );

            items.forEach(
                item => {
                    item.y += shift;
                },
            );
        }
    }

    function parseSelectedEnzymes(
        value,
    ) {
        return [
            ...new Set(
                String(
                    value || "",
                )
                    .split(
                        /[\s,;]+/,
                    )
                    .map(
                        item => (
                            item.trim()
                        ),
                    )
                    .filter(Boolean),
            ),
        ];
    }

    function restrictionLabelLimit(
        detailMode,
    ) {
        return (
            LABEL_LIMITS[
                detailMode
            ]
            || LABEL_LIMITS.detailed
        );
    }

    ready(() => {
        const root = (
            document.getElementById(
                "molecular-workspace",
            )
        );

        if (!root) {
            return;
        }

        if (
            document.getElementById(
                "mw-detailed-plasmid-map",
            )
        ) {
            return;
        }

        const seqvizPanel = (
            root.querySelector(
                '[data-mw-view-panel="seqviz"]',
            )
        );

        const viewerRoot = (
            document.getElementById(
                "mw-seqviz-viewer",
            )
        );

        const toolbar = (
            seqvizPanel?.querySelector(
                ".mw-seqviz-controls",
            )
        );

        const inspector = (
            seqvizPanel?.querySelector(
                ".mw-seqviz-inspector",
            )
        );

        if (
            !seqvizPanel
            || !viewerRoot
            || !root.dataset
                .restrictionSitesUrl
        ) {
            return;
        }

        const shell = (
            document.createElement(
                "section",
            )
        );

        shell.id = (
            "mw-detailed-plasmid-map"
        );

        shell.className = (
            "mpm-shell"
        );

        shell.hidden = true;

        shell.innerHTML = `
            <div class="mpm-toolbar">
                <div class="mpm-toolbar-group">
                    <label>
                        <span>Detail</span>
                        <select id="mpm-detail-mode"
                                class="form-select form-select-sm">
                            <option value="compact">Compact</option>
                            <option value="detailed" selected>Detailed</option>
                            <option value="publication">Publication</option>
                        </select>
                    </label>

                    <label>
                        <span>Restriction sites</span>
                        <select id="mpm-restriction-mode"
                                class="form-select form-select-sm">
                            <option value="none">None</option>
                            <option value="unique" selected>Unique cutters</option>
                            <option value="selected">Selected enzymes</option>
                            <option value="common">Common cutters</option>
                            <option value="all">All cutters</option>
                        </select>
                    </label>

                    <label>
                        <span>Catalog</span>
                        <select id="mpm-catalog"
                                class="form-select form-select-sm">
                            <option value="common" selected>Common enzymes</option>
                            <option value="all">All known enzymes</option>
                        </select>
                    </label>

                    <label>
                        <span>Min. site</span>
                        <select id="mpm-min-site"
                                class="form-select form-select-sm">
                            <option value="4">4 bp</option>
                            <option value="5">5 bp</option>
                            <option value="6" selected>6 bp</option>
                            <option value="8">8 bp</option>
                        </select>
                    </label>
                    <label>
                        <span>Restriction labels</span>
                        <select id="mpm-restriction-label-mode"
                                class="form-select form-select-sm">
                            <option value="smart" selected>Smart</option>
                            <option value="all">All labels</option>
                        </select>
                    </label>

                    <label>
                        <span>Feature label density</span>
                        <select id="mpm-feature-label-mode"
                                class="form-select form-select-sm">
                            <option value="smart" selected>Smart</option>
                            <option value="all">All labels</option>
                        </select>
                    </label>
                </div>

                <div class="mpm-toolbar-group">
                    <label class="mpm-check">
                        <input id="mpm-show-feature-labels"
                               type="checkbox"
                               checked>
                        <span>Feature labels</span>
                    </label>

                    <label class="mpm-check">
                        <input id="mpm-show-positions"
                               type="checkbox"
                               checked>
                        <span>Cut positions</span>
                    </label>

                    <label class="mpm-check">
                        <input id="mpm-show-leaders"
                               type="checkbox"
                               checked>
                        <span>Leader lines</span>
                    </label>

                    <label class="mpm-check">
                        <input id="mpm-avoid-overlap"
                               type="checkbox"
                               checked>
                        <span>Avoid overlap</span>
                    </label>
                </div>

                <div class="mpm-toolbar-group mpm-toolbar-actions">
                    <button id="mpm-reset-view"
                            type="button"
                            class="btn btn-sm btn-outline-secondary">
                        Reset view
                    </button>

                    <button id="mpm-export-svg"
                            type="button"
                            class="btn btn-sm btn-outline-secondary">
                        Export SVG
                    </button>

                    <button id="mpm-toggle-site-list"
                            type="button"
                            class="btn btn-sm btn-outline-secondary"
                            aria-expanded="false">
                        Sites list
                    </button>
                </div>
            </div>

            <div id="mpm-selected-enzymes-wrap"
                 class="mpm-selected-enzymes"
                 hidden>
                <label>
                    <span>Selected enzymes</span>
                    <input id="mpm-selected-enzymes"
                           class="form-control form-control-sm"
                           type="text"
                           value="EcoRI BamHI XhoI HindIII"
                           placeholder="EcoRI BamHI XhoI">
                </label>
            </div>

            <div class="mpm-secondary-row">
                <label class="mpm-search">
                    <span>Filter displayed enzymes</span>
                    <input id="mpm-enzyme-search"
                           class="form-control form-control-sm"
                           type="search"
                           placeholder="EcoRI">
                </label>

                <div id="mpm-status"
                     class="mpm-status"
                     role="status"
                     aria-live="polite">
                    Waiting for molecular workspace data…
                </div>

                <div id="mpm-density-note"
                     class="mpm-density-note">
                    Smart mode changes labels only; complete site data remains available.
                </div>
            </div>

            <div id="mpm-site-list-panel"
                 class="mpm-site-list-panel"
                 hidden>
                <div class="mpm-site-list-header">
                    <strong>Restriction sites</strong>
                    <span id="mpm-site-list-count"></span>
                </div>

                <div id="mpm-site-list-items"
                     class="mpm-site-list-items"
                     role="list"></div>
            </div>


            <div class="mpm-stage">
                <svg id="mpm-svg"
                     viewBox="0 0 1000 760"
                     role="img"
                     aria-label="Detailed interactive molecular map"></svg>

                <div id="mpm-empty"
                     class="mpm-empty"
                     hidden>
                    Add a sequence to render the detailed molecular map.
                </div>
            </div>

            <div class="mpm-footer">
                <div id="mpm-summary"
                     class="mpm-summary">
                    Waiting for molecular workspace data.
                </div>

                <div id="mpm-site-details"
                     class="mpm-site-details"
                     hidden></div>
            </div>
        `;

        viewerRoot.before(
            shell,
        );

        const switcher = (
            document.createElement(
                "div",
            )
        );

        switcher.className = (
            "mpm-view-switcher"
        );

        switcher.setAttribute(
            "role",
            "group",
        );

        switcher.setAttribute(
            "aria-label",
            "Molecular map renderer",
        );

        switcher.innerHTML = `
            <button type="button"
                    class="mpm-view-button"
                    data-mpm-view="seqviz">
                SeqViz
            </button>

            <button type="button"
                    class="mpm-view-button"
                    data-mpm-view="detailed">
                Detailed map
            </button>
        `;

        if (toolbar) {
            toolbar.prepend(
                switcher,
            );
        } else {
            seqvizPanel.prepend(
                switcher,
            );
        }

        const elements = {
            svg: shell.querySelector(
                "#mpm-svg",
            ),
            empty: shell.querySelector(
                "#mpm-empty",
            ),
            status: shell.querySelector(
                "#mpm-status",
            ),
            summary: shell.querySelector(
                "#mpm-summary",
            ),
            siteDetails: shell.querySelector(
                "#mpm-site-details",
            ),
            detailMode: shell.querySelector(
                "#mpm-detail-mode",
            ),
            restrictionMode: shell.querySelector(
                "#mpm-restriction-mode",
            ),
            catalog: shell.querySelector(
                "#mpm-catalog",
            ),
            minimumSite: shell.querySelector(
                "#mpm-min-site",
            ),
            restrictionLabelMode: shell.querySelector(
                "#mpm-restriction-label-mode",
            ),
            featureLabelMode: shell.querySelector(
                "#mpm-feature-label-mode",
            ),
            showFeatureLabels: shell.querySelector(
                "#mpm-show-feature-labels",
            ),
            showPositions: shell.querySelector(
                "#mpm-show-positions",
            ),
            showLeaders: shell.querySelector(
                "#mpm-show-leaders",
            ),
            avoidOverlap: shell.querySelector(
                "#mpm-avoid-overlap",
            ),
            selectedWrap: shell.querySelector(
                "#mpm-selected-enzymes-wrap",
            ),
            selectedEnzymes: shell.querySelector(
                "#mpm-selected-enzymes",
            ),
            search: shell.querySelector(
                "#mpm-enzyme-search",
            ),
            resetView: shell.querySelector(
                "#mpm-reset-view",
            ),
            exportSvg: shell.querySelector(
                "#mpm-export-svg",
            ),
            siteListButton: shell.querySelector(
                "#mpm-toggle-site-list",
            ),
            siteListPanel: shell.querySelector(
                "#mpm-site-list-panel",
            ),
            siteListCount: shell.querySelector(
                "#mpm-site-list-count",
            ),
            siteListItems: shell.querySelector(
                "#mpm-site-list-items",
            ),
            densityNote: shell.querySelector(
                "#mpm-density-note",
            ),
            viewButtons: [
                ...switcher.querySelectorAll(
                    "[data-mpm-view]",
                ),
            ],
        };

        const state = {
            snapshot: null,
            analysis: null,
            analysisKey: "",
            requestId: 0,
            selectedSite: null,
            rendererView: "seqviz",
            firstSnapshot: true,
            viewBox: {
                ...DEFAULT_VIEW_BOX,
            },
            pointerDrag: null,
            siteListOpen: false,
            lastRestrictionTotal: 0,
            lastRestrictionLabels: 0,
            lastFeatureTotal: 0,
            lastFeatureLabels: 0,
        };


        function currentZoomFactor() {
            return clamp(
                DEFAULT_VIEW_BOX.width
                    / state.viewBox.width,
                1,
                6,
            );
        }

        function smartRestrictionSectorCount() {
            const mode = (
                elements.detailMode.value
            );

            if (mode === "compact") {
                return 18;
            }

            if (mode === "publication") {
                return 30;
            }

            return 24;
        }

        function restrictionLabelSites(
            allSites,
            sequenceLength,
        ) {
            if (
                elements
                    .restrictionLabelMode
                    .value
                === "all"
                || allSites.length <= 1
                || !sequenceLength
            ) {
                return [...allSites];
            }

            const sectorCount = (
                smartRestrictionSectorCount()
            );

            const zoomFactor = (
                currentZoomFactor()
            );

            const perSector = clamp(
                Math.ceil(
                    zoomFactor
                ),
                1,
                6,
            );

            const sectors = Array.from(
                {
                    length: sectorCount,
                },
                () => [],
            );

            allSites.forEach(
                site => {
                    const position = clamp(
                        numeric(
                            site.position,
                            1,
                        ),
                        1,
                        sequenceLength,
                    );

                    const sector = Math.min(
                        sectorCount - 1,
                        Math.floor(
                            (
                                (position - 1)
                                / sequenceLength
                            )
                            * sectorCount,
                        ),
                    );

                    sectors[sector].push(
                        site,
                    );
                },
            );

            const chosen = [];

            sectors.forEach(
                sites => {
                    if (
                        sites.length
                        <= perSector
                    ) {
                        chosen.push(
                            ...sites,
                        );

                        return;
                    }

                    for (
                        let index = 0;
                        index < perSector;
                        index += 1
                    ) {
                        const candidateIndex = Math.min(
                            sites.length - 1,
                            Math.floor(
                                (
                                    index
                                    + 0.5
                                )
                                * sites.length
                                / perSector,
                            ),
                        );

                        chosen.push(
                            sites[
                                candidateIndex
                            ],
                        );
                    }
                },
            );

            if (state.selectedSite) {
                const selected = (
                    allSites.find(
                        site => (
                            site.enzyme
                                === state
                                    .selectedSite
                                    .enzyme
                            && numeric(
                                site.position,
                            )
                                === numeric(
                                    state
                                        .selectedSite
                                        .position,
                                )
                        ),
                    )
                );

                if (selected) {
                    chosen.push(
                        selected,
                    );
                }
            }

            const unique = new Map();

            chosen.forEach(
                site => {
                    unique.set(
                        (
                            `${site.enzyme}:`
                            + `${site.position}`
                        ),
                        site,
                    );
                },
            );

            return [
                ...unique.values(),
            ].sort(
                (
                    first,
                    second,
                ) => (
                    numeric(
                        first.position,
                    )
                    - numeric(
                        second.position,
                    )
                    || String(
                        first.enzyme,
                    ).localeCompare(
                        String(
                            second.enzyme,
                        ),
                    )
                ),
            );
        }

        function smartFeatureMinimumFraction() {
            const mode = (
                elements.detailMode.value
            );

            let base = 0.045;

            if (mode === "compact") {
                base = 0.06;
            } else if (
                mode === "publication"
            ) {
                base = 0.025;
            }

            return Math.max(
                0.006,
                base
                    / currentZoomFactor(),
            );
        }

        function shouldShowFeatureLabel(
            featureFraction,
            selected,
        ) {
            if (
                !elements
                    .showFeatureLabels
                    .checked
            ) {
                return false;
            }

            if (
                elements
                    .featureLabelMode
                    .value
                === "all"
            ) {
                return true;
            }

            if (selected) {
                return true;
            }

            return (
                featureFraction
                >= smartFeatureMinimumFraction()
            );
        }

        function updateDensityNote() {
            const restrictionTotal = (
                state.lastRestrictionTotal
            );

            const restrictionLabels = (
                state.lastRestrictionLabels
            );

            const featureTotal = (
                state.lastFeatureTotal
            );

            const featureLabels = (
                state.lastFeatureLabels
            );

            const restrictionMode = (
                elements
                    .restrictionLabelMode
                    .value
            );

            const featureMode = (
                elements
                    .featureLabelMode
                    .value
            );

            const restrictionText = (
                restrictionMode === "all"
                    ? (
                        `All ${formatted(
                            restrictionTotal,
                        )} matching restriction labels shown`
                    )
                    : (
                        `${formatted(
                            restrictionLabels,
                        )}/${formatted(
                            restrictionTotal,
                        )} restriction labels shown`
                        + `; all ${formatted(
                            restrictionTotal,
                        )} matching cut ticks retained`
                    )
            );

            const featureText = (
                featureMode === "all"
                    ? (
                        `all ${formatted(
                            featureTotal,
                        )} feature labels shown`
                    )
                    : (
                        `${formatted(
                            featureLabels,
                        )}/${formatted(
                            featureTotal,
                        )} feature labels shown`
                    )
            );

            elements.densityNote.textContent = (
                `${restrictionText} · ${featureText}.`
                + (
                    restrictionMode === "smart"
                        ? (
                            " Zoom in for more labels, open Sites list, or choose All labels."
                        )
                        : ""
                )
            );
        }

        function setStatus(
            message,
            status = "",
        ) {
            elements.status.textContent = (
                message
            );

            elements.status.classList.remove(
                "is-loading",
                "is-success",
                "is-error",
            );

            if (status) {
                elements.status.classList.add(
                    `is-${status}`,
                );
            }
        }

        function updateViewBox() {
            elements.svg.setAttribute(
                "viewBox",
                [
                    state.viewBox.x,
                    state.viewBox.y,
                    state.viewBox.width,
                    state.viewBox.height,
                ].join(" "),
            );
        }

        function resetViewBox() {
            state.viewBox = {
                ...DEFAULT_VIEW_BOX,
            };

            updateViewBox();
        }

        function isRnaWorkspace() {
            return (
                String(
                    state.snapshot?.sequenceType
                    || document
                        .getElementById("mw-type")
                        ?.value
                    || ""
                ).toLowerCase()
                === "rna"
            );
        }

        function setRendererView(
            requested,
            persist = true,
        ) {
            const resolved = (
                requested === "detailed"
                && !isRnaWorkspace()
                    ? "detailed"
                    : "seqviz"
            );

            state.rendererView = (
                resolved
            );

            viewerRoot.hidden = (
                resolved === "detailed"
            );

            shell.hidden = (
                resolved !== "detailed"
            );

            if (inspector) {
                inspector.hidden = false;
            }

            elements.viewButtons
                .forEach(
                    button => {
                        const unavailable = (
                            isRnaWorkspace()
                            && button.dataset
                                .mpmView
                            === "detailed"
                        );

                        button.hidden = unavailable;

                        button.setAttribute(
                            "aria-hidden",
                            String(unavailable),
                        );

                        const active = (
                            !unavailable
                            && button.dataset
                                .mpmView
                            === resolved
                        );

                        button.classList.toggle(
                            "is-active",
                            active,
                        );

                        button.setAttribute(
                            "aria-pressed",
                            String(active),
                        );
                    },
                );

            if (persist) {
                try {
                    localStorage.setItem(
                        VIEW_STORAGE_KEY,
                        resolved,
                    );
                } catch (_error) {
                    // Storage is optional.
                }
            }

            if (
                resolved === "detailed"
            ) {
                render();
                scheduleRestrictionAnalysis(
                    20,
                );
            }
        }

        function restrictionCapable(
            snapshot,
        ) {
            return [
                "dna",
                "plasmid",
                "primer",
                "insert",
            ].includes(
                String(
                    snapshot?.sequenceType
                    || "",
                ).toLowerCase(),
            );
        }

        function restrictionRequestPayload() {
            return {
                sequence: String(
                    state.snapshot?.sequence
                    || "",
                ),
                topology: String(
                    state.snapshot?.topology
                    || "linear",
                ),
                mode: (
                    elements
                        .restrictionMode
                        .value
                ),
                catalog: (
                    elements
                        .catalog
                        .value
                ),
                minimum_site_length: Number(
                    elements
                        .minimumSite
                        .value
                    || 6,
                ),
                selected_enzymes: (
                    parseSelectedEnzymes(
                        elements
                            .selectedEnzymes
                            .value,
                    )
                ),
            };
        }

        function currentAnalysisKey() {
            if (!state.snapshot) {
                return "";
            }

            return JSON.stringify(
                restrictionRequestPayload(),
            );
        }

        let restrictionTimer = null;

        function scheduleRestrictionAnalysis(
            delay = 160,
        ) {
            clearTimeout(
                restrictionTimer,
            );

            restrictionTimer = (
                window.setTimeout(
                    analyzeRestrictions,
                    delay,
                )
            );
        }

        async function analyzeRestrictions() {
            const snapshot = (
                state.snapshot
            );

            if (
                !snapshot
                || !String(
                    snapshot.sequence
                    || "",
                )
            ) {
                state.analysis = null;
                state.analysisKey = "";
                render();
                return;
            }

            if (
                !restrictionCapable(
                    snapshot,
                )
            ) {
                state.analysis = null;
                state.analysisKey = "";

                setStatus(
                    "Restriction analysis is not applicable to this record type.",
                );

                render();
                return;
            }

            if (
                elements
                    .restrictionMode
                    .value
                === "none"
            ) {
                state.analysis = {
                    sequence_length: (
                        snapshot
                            .sequence
                            .length
                    ),
                    topology: (
                        snapshot.topology
                    ),
                    cutting_enzyme_count: 0,
                    unique_cutter_count: 0,
                    site_count: 0,
                    enzymes: [],
                    sites: [],
                };

                state.analysisKey = (
                    currentAnalysisKey()
                );

                setStatus(
                    "Restriction sites hidden.",
                );

                render();
                return;
            }

            const key = (
                currentAnalysisKey()
            );

            if (
                state.analysis
                && state.analysisKey
                    === key
            ) {
                render();
                return;
            }

            const requestId = (
                ++state.requestId
            );

            setStatus(
                "Analyzing restriction sites…",
                "loading",
            );

            try {
                const response = await fetch(
                    root.dataset
                        .restrictionSitesUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            Accept: "application/json",
                            "Content-Type": "application/json",
                            "X-CSRFToken": (
                                csrfToken(root)
                            ),
                        },
                        body: JSON.stringify(
                            restrictionRequestPayload(),
                        ),
                    },
                );

                let payload = {};

                try {
                    payload = (
                        await response.json()
                    );
                } catch (_error) {
                    payload = {};
                }

                if (
                    !response.ok
                    || payload.status
                        !== "success"
                ) {
                    throw new Error(
                        payload.message
                        || `HTTP ${response.status}`,
                    );
                }

                if (
                    requestId
                    !== state.requestId
                ) {
                    return;
                }

                state.analysis = (
                    payload.analysis
                    || null
                );

                state.analysisKey = key;

                const siteCount = numeric(
                    state.analysis
                        ?.site_count,
                );

                const enzymeCount = numeric(
                    state.analysis
                        ?.cutting_enzyme_count,
                );

                setStatus(
                    (
                        `${formatted(siteCount)} cut site`
                        + (
                            siteCount === 1
                                ? ""
                                : "s"
                        )
                        + " from "
                        + `${formatted(enzymeCount)} cutting enzyme`
                        + (
                            enzymeCount === 1
                                ? ""
                                : "s"
                        )
                        + "."
                    ),
                    "success",
                );

                render();
            } catch (error) {
                if (
                    requestId
                    !== state.requestId
                ) {
                    return;
                }

                state.analysis = null;
                state.analysisKey = "";

                setStatus(
                    (
                        "Restriction analysis error: "
                        + error.message
                    ),
                    "error",
                );

                render();
            }
        }

        function addBackground() {
            elements.svg.appendChild(
                svgElement(
                    "rect",
                    {
                        x: 0,
                        y: 0,
                        width: 1000,
                        height: 760,
                        class: (
                            "mpm-map-background"
                        ),
                    },
                ),
            );
        }

        function addCenterIdentity(
            snapshot,
            cx,
            cy,
        ) {
            svgText(
                elements.svg,
                snapshot.name
                    || "Molecular record",
                {
                    x: cx,
                    y: cy - 9,
                    class: (
                        "mpm-center-title"
                    ),
                    "text-anchor": (
                        "middle"
                    ),
                },
            );

            svgText(
                elements.svg,
                (
                    `${formatted(
                        snapshot.sequence.length,
                    )} `
                    + (
                        snapshot.sequenceType
                            === "protein"
                            ? "aa"
                            : "bp"
                    )
                ),
                {
                    x: cx,
                    y: cy + 18,
                    class: (
                        "mpm-center-length"
                    ),
                    "text-anchor": (
                        "middle"
                    ),
                },
            );

            svgText(
                elements.svg,
                (
                    snapshot.topology
                    === "circular"
                        ? "circular"
                        : "linear"
                ),
                {
                    x: cx,
                    y: cy + 40,
                    class: (
                        "mpm-center-topology"
                    ),
                    "text-anchor": (
                        "middle"
                    ),
                },
            );
        }

        function addCircularCoordinates(
            sequenceLength,
            cx,
            cy,
            radius,
        ) {
            const step = (
                niceCoordinateStep(
                    sequenceLength,
                )
            );

            for (
                let position = step;
                position <= sequenceLength;
                position += step
            ) {
                const angle = (
                    coordinateAngle(
                        position,
                        sequenceLength,
                    )
                );

                const inner = polarPoint(
                    cx,
                    cy,
                    radius - 7,
                    angle,
                );

                const outer = polarPoint(
                    cx,
                    cy,
                    radius + 7,
                    angle,
                );

                elements.svg.appendChild(
                    svgElement(
                        "line",
                        {
                            x1: inner.x,
                            y1: inner.y,
                            x2: outer.x,
                            y2: outer.y,
                            class: (
                                "mpm-coordinate-tick"
                            ),
                        },
                    ),
                );

                const label = polarPoint(
                    cx,
                    cy,
                    radius + 24,
                    angle,
                );

                svgText(
                    elements.svg,
                    formatted(position),
                    {
                        x: label.x,
                        y: label.y,
                        class: (
                            "mpm-coordinate-label"
                        ),
                        "text-anchor": (
                            "middle"
                        ),
                        "dominant-baseline": (
                            "middle"
                        ),
                    },
                );
            }
        }

        function selectFeature(
            featureIndex,
        ) {
            const api = workspaceApi();

            if (
                api
                && typeof api.selectFeature
                    === "function"
            ) {
                api.selectFeature(
                    featureIndex,
                );
            }
        }

        function selectSequenceRange(
            start,
            end,
        ) {
            const api = workspaceApi();

            if (
                api
                && typeof api.selectSequenceRange
                    === "function"
            ) {
                api.selectSequenceRange(
                    start,
                    end,
                    {
                        source: (
                            "detailed-map"
                        ),
                    },
                );
            }
        }

        function addCircularFeature(
            entry,
            snapshot,
            cx,
            cy,
            baseRadius,
        ) {
            const {
                feature,
                featureIndex,
                lane,
            } = entry;

            const sequenceLength = (
                snapshot.sequence.length
            );

            const radius = (
                baseRadius
                - lane * 20
            );

            const selected = (
                featureIndex
                === snapshot.selectedFeature
            );

            const color = (
                feature.color
                || "#868e96"
            );

            const group = svgElement(
                "g",
                {
                    class: (
                        selected
                            ? "mpm-feature is-selected"
                            : "mpm-feature"
                    ),
                    "data-feature-index": (
                        featureIndex
                    ),
                    tabindex: 0,
                    role: "button",
                },
            );

            featureSegments(
                feature,
                sequenceLength,
                true,
            ).forEach(
                segment => {
                    const span = (
                        segment.end
                        - segment.start
                        + 1
                    );

                    if (
                        span
                        >= sequenceLength
                    ) {
                        group.appendChild(
                            svgElement(
                                "circle",
                                {
                                    cx,
                                    cy,
                                    r: radius,
                                    fill: "none",
                                    stroke: color,
                                    "stroke-width": (
                                        selected
                                            ? 19
                                            : 15
                                    ),
                                    class: (
                                        "mpm-feature-arc"
                                    ),
                                },
                            ),
                        );

                        return;
                    }

                    const path = arcPath(
                        cx,
                        cy,
                        radius,
                        segment.start,
                        segment.end,
                        sequenceLength,
                    );

                    if (!path) {
                        return;
                    }

                    group.appendChild(
                        svgElement(
                            "path",
                            {
                                d: path,
                                fill: "none",
                                stroke: color,
                                "stroke-width": (
                                    selected
                                        ? 19
                                        : 15
                                ),
                                class: (
                                    "mpm-feature-arc"
                                ),
                            },
                        ),
                    );
                },
            );

            if (
                feature.strand === "+"
                || feature.strand === "-"
            ) {
                const forward = (
                    feature.strand === "+"
                );

                const arrowCoordinate = (
                    forward
                        ? feature.end
                        : feature.start
                );

                const angle = (
                    coordinateAngle(
                        arrowCoordinate,
                        sequenceLength,
                    )
                );

                group.appendChild(
                    svgElement(
                        "polygon",
                        {
                            points: arrowPolygon(
                                cx,
                                cy,
                                radius,
                                angle,
                                forward,
                                selected
                                    ? 15
                                    : 13,
                            ),
                            fill: color,
                            class: (
                                "mpm-feature-arrow"
                            ),
                        },
                    ),
                );
            }

            svgTitle(
                group,
                [
                    feature.name,
                    `${feature.start}..${feature.end}`,
                    feature.strand || ".",
                ].join(" · "),
            );

            group.addEventListener(
                "click",
                event => {
                    event.stopPropagation();

                    selectFeature(
                        featureIndex,
                    );
                },
            );

            group.addEventListener(
                "keydown",
                event => {
                    if (
                        event.key === "Enter"
                        || event.key === " "
                    ) {
                        event.preventDefault();

                        selectFeature(
                            featureIndex,
                        );
                    }
                },
            );

            elements.svg.appendChild(
                group,
            );

            const featureFraction = (
                featureLength(
                    feature,
                    sequenceLength,
                    true,
                )
                / sequenceLength
            );

            const showLabel = (
                shouldShowFeatureLabel(
                    featureFraction,
                    selected,
                )
            );

            if (showLabel) {
                state.lastFeatureLabels += 1;
            }

            if (!showLabel) {
                return;
            }

            const angle = (
                featureMiddleAngle(
                    feature,
                    sequenceLength,
                    true,
                )
            );

            const position = polarPoint(
                cx,
                cy,
                radius - 14,
                angle,
            );

            const label = svgText(
                elements.svg,
                feature.name
                    || "Feature",
                {
                    x: position.x,
                    y: position.y,
                    class: (
                        selected
                            ? "mpm-feature-label is-selected"
                            : "mpm-feature-label"
                    ),
                    "text-anchor": (
                        "middle"
                    ),
                    "dominant-baseline": (
                        "middle"
                    ),
                    "data-feature-index": (
                        featureIndex
                    ),
                },
            );

            label.addEventListener(
                "click",
                event => {
                    event.stopPropagation();

                    selectFeature(
                        featureIndex,
                    );
                },
            );
        }

        function filteredRestrictionSites() {
            const sites = Array.isArray(
                state.analysis?.sites,
            )
                ? state.analysis.sites
                : [];

            const query = String(
                elements.search.value
                || "",
            )
                .trim()
                .toLowerCase();

            if (!query) {
                return sites;
            }

            return sites.filter(
                site => (
                    String(
                        site.enzyme
                        || "",
                    )
                        .toLowerCase()
                        .includes(query)
                    || String(
                        site
                            .recognition_sequence
                        || "",
                    )
                        .toLowerCase()
                        .includes(query)
                ),
            );
        }

        function restrictionLabel(
            site,
        ) {
            if (
                elements
                    .showPositions
                    .checked
            ) {
                return (
                    `${site.enzyme} `
                    + `(${formatted(
                        site.position,
                    )})`
                );
            }

            return String(
                site.enzyme || "",
            );
        }

        function selectRestrictionSite(
            site,
            snapshot,
        ) {
            state.selectedSite = site;

            const recognitionLength = (
                Math.max(
                    1,
                    numeric(
                        site
                            .recognition_length,
                        1,
                    ),
                )
            );

            const sequenceLength = (
                snapshot.sequence.length
            );

            let end = (
                numeric(
                    site.position,
                    1,
                )
                + recognitionLength
                - 1
            );

            if (
                snapshot.topology
                    === "circular"
                && sequenceLength
            ) {
                end = (
                    (
                        (end - 1)
                        % sequenceLength
                    )
                    + 1
                );
            } else {
                end = Math.min(
                    end,
                    sequenceLength,
                );
            }

            selectSequenceRange(
                numeric(
                    site.position,
                    1,
                ),
                end,
            );

            render();
        }


        function renderSiteList(
            snapshot,
        ) {
            const sites = (
                filteredRestrictionSites()
            );

            elements.siteListCount.textContent = (
                `${formatted(
                    sites.length,
                )} matching site`
                + (
                    sites.length === 1
                        ? ""
                        : "s"
                )
            );

            elements.siteListButton.textContent = (
                `Sites list (${formatted(
                    sites.length,
                )})`
            );

            elements.siteListButton.setAttribute(
                "aria-expanded",
                String(
                    state.siteListOpen,
                ),
            );

            elements.siteListPanel.hidden = (
                !state.siteListOpen
            );

            elements.siteListItems.replaceChildren();

            if (!state.siteListOpen) {
                return;
            }

            if (!sites.length) {
                const empty = (
                    document.createElement(
                        "div",
                    )
                );

                empty.className = (
                    "mpm-site-list-empty"
                );

                empty.textContent = (
                    "No restriction sites match the current filter."
                );

                elements.siteListItems.appendChild(
                    empty,
                );

                return;
            }

            sites.forEach(
                site => {
                    const button = (
                        document.createElement(
                            "button",
                        )
                    );

                    button.type = "button";

                    button.className = (
                        "mpm-site-list-item"
                    );

                    const selected = (
                        state.selectedSite
                        && state.selectedSite
                            .enzyme
                            === site.enzyme
                        && numeric(
                            state
                                .selectedSite
                                .position,
                        )
                            === numeric(
                                site.position,
                            )
                    );

                    if (selected) {
                        button.classList.add(
                            "is-selected",
                        );
                    }

                    const name = (
                        document.createElement(
                            "strong",
                        )
                    );

                    name.textContent = (
                        site.enzyme
                    );

                    const details = (
                        document.createElement(
                            "span",
                        )
                    );

                    details.textContent = [
                        formatted(
                            site.position,
                        ),
                        site.recognition_sequence,
                        site.unique
                            ? "unique"
                            : (
                                `${site.site_count} sites`
                            ),
                    ]
                        .filter(Boolean)
                        .join(" · ");

                    button.append(
                        name,
                        details,
                    );

                    button.addEventListener(
                        "click",
                        () => {
                            selectRestrictionSite(
                                site,
                                snapshot,
                            );
                        },
                    );

                    elements.siteListItems.appendChild(
                        button,
                    );
                },
            );
        }

        function renderSiteDetails() {
            const site = (
                state.selectedSite
            );

            elements
                .siteDetails
                .replaceChildren();

            if (!site) {
                elements.siteDetails.hidden = true;
                return;
            }

            elements.siteDetails.hidden = false;

            const title = (
                document.createElement(
                    "strong",
                )
            );

            title.textContent = (
                `${site.enzyme} · `
                + formatted(
                    site.position,
                )
            );

            const description = (
                document.createElement(
                    "span",
                )
            );

            let endType = "unknown end";

            if (
                site.overhang_type
                === "5_prime"
            ) {
                endType = "5′ sticky";
            } else if (
                site.overhang_type
                === "3_prime"
            ) {
                endType = "3′ sticky";
            } else if (
                site.overhang_type
                === "blunt"
            ) {
                endType = "blunt";
            }

            description.textContent = [
                site.recognition_sequence,
                endType,
                site.unique
                    ? "unique cutter"
                    : (
                        `${site.site_count} sites`
                    ),
            ]
                .filter(Boolean)
                .join(" · ");

            elements.siteDetails.append(
                title,
                description,
            );
        }

        function addCircularRestrictionSites(
            snapshot,
            cx,
            cy,
            radius,
        ) {
            const sequenceLength = (
                snapshot.sequence.length
            );

            const allSites = (
                filteredRestrictionSites()
            );

            if (!allSites.length) {
                return;
            }

            const labelSites = (
                restrictionLabelSites(
                    allSites,
                    sequenceLength,
                )
            );

            state.lastRestrictionTotal = (
                allSites.length
            );

            state.lastRestrictionLabels = (
                labelSites.length
            );

            allSites.forEach(
                site => {
                    const angle = (
                        coordinateAngle(
                            site.position,
                            sequenceLength,
                        )
                    );

                    const inner = polarPoint(
                        cx,
                        cy,
                        radius + 3,
                        angle,
                    );

                    const outer = polarPoint(
                        cx,
                        cy,
                        radius + 18,
                        angle,
                    );

                    const selected = (
                        state.selectedSite
                        && state.selectedSite
                            .enzyme
                            === site.enzyme
                        && numeric(
                            state.selectedSite
                                .position,
                        )
                            === numeric(
                                site.position,
                            )
                    );

                    const tick = svgElement(
                        "line",
                        {
                            x1: inner.x,
                            y1: inner.y,
                            x2: outer.x,
                            y2: outer.y,
                            class: (
                                selected
                                    ? "mpm-restriction-tick is-selected"
                                    : "mpm-restriction-tick"
                            ),
                            "data-enzyme": (
                                site.enzyme
                            ),
                            "data-position": (
                                site.position
                            ),
                        },
                    );

                    svgTitle(
                        tick,
                        restrictionLabel(
                            site,
                        ),
                    );

                    tick.addEventListener(
                        "click",
                        event => {
                            event.stopPropagation();

                            selectRestrictionSite(
                                site,
                                snapshot,
                            );
                        },
                    );

                    elements.svg
                        .appendChild(
                            tick,
                        );
                },
            );

            const labels = {
                left: [],
                right: [],
            };

            labelSites.forEach(
                site => {
                    const angle = (
                        coordinateAngle(
                            site.position,
                            sequenceLength,
                        )
                    );

                    const anchor = polarPoint(
                        cx,
                        cy,
                        radius + 19,
                        angle,
                    );

                    const guide = polarPoint(
                        cx,
                        cy,
                        radius + 54,
                        angle,
                    );

                    const side = (
                        Math.cos(angle)
                        >= 0
                            ? "right"
                            : "left"
                    );

                    labels[side].push(
                        {
                            site,
                            anchor,
                            guide,
                            preferredY: (
                                guide.y
                            ),
                            y: guide.y,
                        },
                    );
                },
            );

            if (
                elements
                    .avoidOverlap
                    .checked
            ) {
                const gap = (
                    elements
                        .detailMode
                        .value
                    === "publication"
                        ? 14
                        : 13
                );

                distributeVerticalLabels(
                    labels.left,
                    42,
                    718,
                    gap,
                );

                distributeVerticalLabels(
                    labels.right,
                    42,
                    718,
                    gap,
                );
            }

            [
                {
                    side: "left",
                    textX: cx - 390,
                    textAnchor: "end",
                },
                {
                    side: "right",
                    textX: cx + 390,
                    textAnchor: "start",
                },
            ].forEach(
                configuration => {
                    labels[
                        configuration.side
                    ].forEach(
                        item => {
                            const selected = (
                                state.selectedSite
                                && state
                                    .selectedSite
                                    .enzyme
                                    === item
                                        .site
                                        .enzyme
                                && numeric(
                                    state
                                        .selectedSite
                                        .position,
                                )
                                    === numeric(
                                        item
                                            .site
                                            .position,
                                    )
                            );

                            const elbowX = (
                                configuration.side
                                === "left"
                                    ? (
                                        cx
                                        - radius
                                        - 78
                                    )
                                    : (
                                        cx
                                        + radius
                                        + 78
                                    )
                            );

                            if (
                                elements
                                    .showLeaders
                                    .checked
                            ) {
                                const line = (
                                    svgElement(
                                        "polyline",
                                        {
                                            points: [
                                                [
                                                    item
                                                        .anchor
                                                        .x,
                                                    item
                                                        .anchor
                                                        .y,
                                                ],
                                                [
                                                    item
                                                        .guide
                                                        .x,
                                                    item
                                                        .guide
                                                        .y,
                                                ],
                                                [
                                                    elbowX,
                                                    item.y,
                                                ],
                                                [
                                                    configuration
                                                        .side
                                                    === "left"
                                                        ? (
                                                            configuration
                                                                .textX
                                                            + 7
                                                        )
                                                        : (
                                                            configuration
                                                                .textX
                                                            - 7
                                                        ),
                                                    item.y,
                                                ],
                                            ]
                                                .map(
                                                    pair => (
                                                        pair.join(
                                                            ",",
                                                        )
                                                    ),
                                                )
                                                .join(" "),
                                            class: (
                                                selected
                                                    ? "mpm-restriction-leader is-selected"
                                                    : "mpm-restriction-leader"
                                            ),
                                        },
                                    )
                                );

                                elements.svg
                                    .appendChild(
                                        line,
                                    );
                            }

                            const label = svgText(
                                elements.svg,
                                restrictionLabel(
                                    item.site,
                                ),
                                {
                                    x: (
                                        configuration
                                            .textX
                                    ),
                                    y: item.y,
                                    class: (
                                        selected
                                            ? "mpm-restriction-label is-selected"
                                            : "mpm-restriction-label"
                                    ),
                                    "text-anchor": (
                                        configuration
                                            .textAnchor
                                    ),
                                    "dominant-baseline": (
                                        "middle"
                                    ),
                                    "data-enzyme": (
                                        item
                                            .site
                                            .enzyme
                                    ),
                                },
                            );

                            label.addEventListener(
                                "click",
                                event => {
                                    event.stopPropagation();

                                    selectRestrictionSite(
                                        item.site,
                                        snapshot,
                                    );
                                },
                            );
                        },
                    );
                },
            );

            if (
                allSites.length
                > labelSites.length
            ) {
                svgText(
                    elements.svg,
                    (
                        `${formatted(
                            labelSites.length,
                        )} of `
                        + `${formatted(
                            allSites.length,
                        )} restriction labels shown`
                    ),
                    {
                        x: cx,
                        y: 742,
                        class: (
                            "mpm-label-limit-note"
                        ),
                        "text-anchor": (
                            "middle"
                        ),
                    },
                );
            }
        }

        function renderCircular(
            snapshot,
        ) {
            const sequenceLength = (
                snapshot.sequence.length
            );

            const cx = 500;
            const cy = 370;
            const backboneRadius = 238;
            const featureRadius = 216;

            addBackground();

            elements.svg.appendChild(
                svgElement(
                    "circle",
                    {
                        cx,
                        cy,
                        r: backboneRadius,
                        class: "mpm-backbone",
                    },
                ),
            );

            addCircularCoordinates(
                sequenceLength,
                cx,
                cy,
                backboneRadius,
            );

            assignCircularFeatureLanes(
                snapshotFeatures(
                    snapshot,
                ),
                sequenceLength,
            ).forEach(
                entry => {
                    addCircularFeature(
                        entry,
                        snapshot,
                        cx,
                        cy,
                        featureRadius,
                    );
                },
            );

            addCircularRestrictionSites(
                snapshot,
                cx,
                cy,
                backboneRadius,
            );

            addCenterIdentity(
                snapshot,
                cx,
                cy,
            );
        }

        function linearX(
            coordinate,
            sequenceLength,
        ) {
            if (!sequenceLength) {
                return 100;
            }

            return (
                100
                + (
                    (
                        numeric(
                            coordinate,
                            1,
                        )
                        - 1
                    )
                    / Math.max(
                        1,
                        sequenceLength - 1,
                    )
                )
                * 800
            );
        }

        function renderLinear(
            snapshot,
        ) {
            const sequenceLength = (
                snapshot.sequence.length
            );

            const baselineY = 360;

            addBackground();

            elements.svg.appendChild(
                svgElement(
                    "line",
                    {
                        x1: 100,
                        y1: baselineY,
                        x2: 900,
                        y2: baselineY,
                        class: (
                            "mpm-linear-backbone"
                        ),
                    },
                ),
            );

            const step = (
                niceCoordinateStep(
                    sequenceLength,
                )
            );

            for (
                let position = step;
                position <= sequenceLength;
                position += step
            ) {
                const x = linearX(
                    position,
                    sequenceLength,
                );

                elements.svg.appendChild(
                    svgElement(
                        "line",
                        {
                            x1: x,
                            y1: (
                                baselineY
                                - 8
                            ),
                            x2: x,
                            y2: (
                                baselineY
                                + 8
                            ),
                            class: (
                                "mpm-coordinate-tick"
                            ),
                        },
                    ),
                );

                svgText(
                    elements.svg,
                    formatted(position),
                    {
                        x,
                        y: baselineY + 29,
                        class: (
                            "mpm-coordinate-label"
                        ),
                        "text-anchor": (
                            "middle"
                        ),
                    },
                );
            }

            snapshotFeatures(
                snapshot,
            ).forEach(
                (
                    feature,
                    featureIndex,
                ) => {
                    const lane = (
                        featureIndex % 6
                    );

                    const y = (
                        baselineY
                        - 28
                        - lane * 25
                    );

                    const startX = linearX(
                        feature.start,
                        sequenceLength,
                    );

                    const endX = linearX(
                        feature.end,
                        sequenceLength,
                    );

                    const left = Math.min(
                        startX,
                        endX,
                    );

                    const width = Math.max(
                        5,
                        Math.abs(
                            endX - startX,
                        ),
                    );

                    const selected = (
                        featureIndex
                        === snapshot
                            .selectedFeature
                    );

                    const group = svgElement(
                        "g",
                        {
                            class: (
                                selected
                                    ? "mpm-feature is-selected"
                                    : "mpm-feature"
                            ),
                            "data-feature-index": (
                                featureIndex
                            ),
                        },
                    );

                    group.appendChild(
                        svgElement(
                            "rect",
                            {
                                x: left,
                                y: y - 8,
                                width,
                                height: 16,
                                rx: 5,
                                fill: (
                                    feature.color
                                    || "#868e96"
                                ),
                                class: (
                                    "mpm-linear-feature"
                                ),
                            },
                        ),
                    );

                    svgTitle(
                        group,
                        [
                            feature.name,
                            `${feature.start}..${feature.end}`,
                        ].join(" · "),
                    );

                    group.addEventListener(
                        "click",
                        event => {
                            event.stopPropagation();

                            selectFeature(
                                featureIndex,
                            );
                        },
                    );

                    elements.svg
                        .appendChild(
                            group,
                        );

                    const linearFeatureFraction = (
                        featureLength(
                            feature,
                            sequenceLength,
                            false,
                        )
                        / Math.max(
                            1,
                            sequenceLength,
                        )
                    );

                    const showLinearLabel = (
                        shouldShowFeatureLabel(
                            linearFeatureFraction,
                            selected,
                        )
                    );

                    if (showLinearLabel) {
                        state.lastFeatureLabels += 1;
                        const label = svgText(
                            elements.svg,
                            feature.name
                                || "Feature",
                            {
                                x: (
                                    left
                                    + width / 2
                                ),
                                y: y - 13,
                                class: (
                                    selected
                                        ? "mpm-feature-label is-selected"
                                        : "mpm-feature-label"
                                ),
                                "text-anchor": (
                                    "middle"
                                ),
                            },
                        );

                        label.addEventListener(
                            "click",
                            event => {
                                event.stopPropagation();

                                selectFeature(
                                    featureIndex,
                                );
                            },
                        );
                    }
                },
            );

            const allLinearSites = (
                filteredRestrictionSites()
            );

            const linearLabelSites = (
                restrictionLabelSites(
                    allLinearSites,
                    sequenceLength,
                )
            );

            state.lastRestrictionTotal = (
                allLinearSites.length
            );

            state.lastRestrictionLabels = (
                linearLabelSites.length
            );

            allLinearSites.forEach(
                site => {
                    const x = linearX(
                        site.position,
                        sequenceLength,
                    );

                    const selected = (
                        state.selectedSite
                        && state.selectedSite
                            .enzyme
                            === site.enzyme
                        && numeric(
                            state
                                .selectedSite
                                .position,
                        )
                            === numeric(
                                site.position,
                            )
                    );

                    const tick = svgElement(
                        "line",
                        {
                            x1: x,
                            y1: (
                                baselineY
                                + 10
                            ),
                            x2: x,
                            y2: (
                                baselineY
                                + 35
                            ),
                            class: (
                                selected
                                    ? "mpm-restriction-tick is-selected"
                                    : "mpm-restriction-tick"
                            ),
                            "data-enzyme": (
                                site.enzyme
                            ),
                            "data-position": (
                                site.position
                            ),
                        },
                    );

                    svgTitle(
                        tick,
                        restrictionLabel(
                            site,
                        ),
                    );

                    tick.addEventListener(
                        "click",
                        event => {
                            event.stopPropagation();

                            selectRestrictionSite(
                                site,
                                snapshot,
                            );
                        },
                    );

                    elements.svg
                        .appendChild(
                            tick,
                        );
                },
            );

            linearLabelSites.forEach(
                (
                    site,
                    index,
                ) => {
                    const x = linearX(
                        site.position,
                        sequenceLength,
                    );

                    const selected = (
                        state.selectedSite
                        && state.selectedSite
                            .enzyme
                            === site.enzyme
                        && numeric(
                            state
                                .selectedSite
                                .position,
                        )
                            === numeric(
                                site.position,
                            )
                    );

                    const label = svgText(
                        elements.svg,
                        restrictionLabel(
                            site,
                        ),
                        {
                            x,
                            y: (
                                baselineY
                                + 53
                                + (
                                    index % 4
                                )
                                * 17
                            ),
                            class: (
                                selected
                                    ? "mpm-restriction-label is-selected"
                                    : "mpm-restriction-label"
                            ),
                            "text-anchor": (
                                "middle"
                            ),
                            "data-enzyme": (
                                site.enzyme
                            ),
                        },
                    );

                    label.addEventListener(
                        "click",
                        event => {
                            event.stopPropagation();

                            selectRestrictionSite(
                                site,
                                snapshot,
                            );
                        },
                    );
                },
            );

            addCenterIdentity(
                snapshot,
                500,
                600,
            );
        }

        function updateSummary() {
            const snapshot = (
                state.snapshot
            );

            if (!snapshot) {
                elements.summary
                    .textContent = (
                        "Waiting for molecular workspace data."
                    );

                return;
            }

            const featureCount = (
                snapshotFeatures(
                    snapshot,
                ).length
            );

            const siteCount = numeric(
                state.analysis
                    ?.site_count,
            );

            const enzymeCount = numeric(
                state.analysis
                    ?.cutting_enzyme_count,
            );

            const uniqueCount = numeric(
                state.analysis
                    ?.unique_cutter_count,
            );

            elements.summary.textContent = [
                (
                    `${formatted(
                        snapshot.sequence.length,
                    )} `
                    + (
                        snapshot.sequenceType
                            === "protein"
                            ? "aa"
                            : "bp"
                    )
                ),
                (
                    `${formatted(
                        featureCount,
                    )} annotation`
                    + (
                        featureCount === 1
                            ? ""
                            : "s"
                    )
                ),
                (
                    `${formatted(
                        siteCount,
                    )} restriction site`
                    + (
                        siteCount === 1
                            ? ""
                            : "s"
                    )
                ),
                (
                    `${formatted(
                        enzymeCount,
                    )} cutting enzyme`
                    + (
                        enzymeCount === 1
                            ? ""
                            : "s"
                    )
                ),
                (
                    `${formatted(
                        uniqueCount,
                    )} unique cutter`
                    + (
                        uniqueCount === 1
                            ? ""
                            : "s"
                    )
                ),
            ].join(" · ");
        }

        function render() {
            const snapshot = (
                state.snapshot
            );

            state.lastRestrictionTotal = 0;
            state.lastRestrictionLabels = 0;

            state.lastFeatureTotal = (
                snapshotFeatures(
                    snapshot,
                ).length
            );

            state.lastFeatureLabels = 0;

            elements.svg
                .replaceChildren();

            updateViewBox();
            updateSummary();
            renderSiteDetails();

            if (
                !snapshot
                || !String(
                    snapshot.sequence
                    || "",
                )
            ) {
                elements.empty.hidden = false;
                elements.svg.hidden = true;

                renderSiteList(
                    snapshot,
                );

                updateDensityNote();

                return;
            }

            elements.empty.hidden = true;
            elements.svg.hidden = false;

            shell.dataset.detailMode = (
                elements
                    .detailMode
                    .value
            );

            if (
                snapshot.topology
                === "circular"
            ) {
                renderCircular(
                    snapshot,
                );
            } else {
                renderLinear(
                    snapshot,
                );
            }

            renderSiteList(
                snapshot,
            );

            updateDensityNote();
        }

        function exportSvg() {
            if (
                !state.snapshot
                || !state.snapshot.sequence
            ) {
                return;
            }

            const clone = (
                elements.svg.cloneNode(
                    true,
                )
            );

            clone.setAttribute(
                "xmlns",
                SVG_NS,
            );

            clone.setAttribute(
                "width",
                "1000",
            );

            clone.setAttribute(
                "height",
                "760",
            );

            const style = svgElement(
                "style",
            );

            style.textContent = (
                SVG_EXPORT_STYLE
            );

            clone.insertBefore(
                style,
                clone.firstChild,
            );

            const serializer = (
                new XMLSerializer()
            );

            const source = (
                serializer
                    .serializeToString(
                        clone,
                    )
            );

            const blob = new Blob(
                [source],
                {
                    type: (
                        "image/svg+xml;charset=utf-8"
                    ),
                },
            );

            const objectUrl = (
                URL.createObjectURL(
                    blob,
                )
            );

            const anchor = (
                document.createElement(
                    "a",
                )
            );

            anchor.href = objectUrl;

            anchor.download = (
                `${safeFilename(
                    state.snapshot.name,
                )}_detailed_map.svg`
            );

            document.body
                .appendChild(
                    anchor,
                );

            anchor.click();
            anchor.remove();

            window.setTimeout(
                () => {
                    URL.revokeObjectURL(
                        objectUrl,
                    );
                },
                1000,
            );
        }

        function zoomAt(
            clientX,
            clientY,
            factor,
        ) {
            const rect = (
                elements.svg
                    .getBoundingClientRect()
            );

            if (
                !rect.width
                || !rect.height
            ) {
                return;
            }

            const current = (
                state.viewBox
            );

            const pointX = (
                current.x
                + (
                    (
                        clientX
                        - rect.left
                    )
                    / rect.width
                )
                * current.width
            );

            const pointY = (
                current.y
                + (
                    (
                        clientY
                        - rect.top
                    )
                    / rect.height
                )
                * current.height
            );

            const nextWidth = clamp(
                current.width
                    * factor,
                420,
                1800,
            );

            const nextHeight = (
                nextWidth
                * (
                    DEFAULT_VIEW_BOX
                        .height
                    / DEFAULT_VIEW_BOX
                        .width
                )
            );

            const relativeX = (
                (
                    pointX
                    - current.x
                )
                / current.width
            );

            const relativeY = (
                (
                    pointY
                    - current.y
                )
                / current.height
            );

            state.viewBox = {
                x: (
                    pointX
                    - relativeX
                    * nextWidth
                ),
                y: (
                    pointY
                    - relativeY
                    * nextHeight
                ),
                width: nextWidth,
                height: nextHeight,
            };

            updateViewBox();

            render();
        }

        elements.svg.addEventListener(
            "wheel",
            event => {
                if (
                    state.rendererView
                    !== "detailed"
                ) {
                    return;
                }

                event.preventDefault();

                zoomAt(
                    event.clientX,
                    event.clientY,
                    event.deltaY > 0
                        ? 1.12
                        : 0.89,
                );
            },
            {
                passive: false,
            },
        );

        elements.svg.addEventListener(
            "pointerdown",
            event => {
                const background = (
                    event.target
                    === elements.svg
                    || event.target
                        .classList
                        ?.contains(
                            "mpm-map-background",
                        )
                );

                if (!background) {
                    return;
                }

                elements.svg
                    .setPointerCapture(
                        event.pointerId,
                    );

                state.pointerDrag = {
                    pointerId: (
                        event.pointerId
                    ),
                    clientX: (
                        event.clientX
                    ),
                    clientY: (
                        event.clientY
                    ),
                    viewBox: {
                        ...state.viewBox,
                    },
                };
            },
        );

        elements.svg.addEventListener(
            "pointermove",
            event => {
                const drag = (
                    state.pointerDrag
                );

                if (
                    !drag
                    || drag.pointerId
                        !== event.pointerId
                ) {
                    return;
                }

                const rect = (
                    elements.svg
                        .getBoundingClientRect()
                );

                if (
                    !rect.width
                    || !rect.height
                ) {
                    return;
                }

                state.viewBox = {
                    ...drag.viewBox,
                    x: (
                        drag.viewBox.x
                        - (
                            event.clientX
                            - drag.clientX
                        )
                        * drag.viewBox.width
                        / rect.width
                    ),
                    y: (
                        drag.viewBox.y
                        - (
                            event.clientY
                            - drag.clientY
                        )
                        * drag.viewBox.height
                        / rect.height
                    ),
                };

                updateViewBox();
            },
        );

        function endPointerDrag(
            event,
        ) {
            if (
                !state.pointerDrag
                || state.pointerDrag
                    .pointerId
                    !== event.pointerId
            ) {
                return;
            }

            state.pointerDrag = null;
        }

        elements.svg.addEventListener(
            "pointerup",
            endPointerDrag,
        );

        elements.svg.addEventListener(
            "pointercancel",
            endPointerDrag,
        );

        elements.viewButtons
            .forEach(
                button => {
                    button.addEventListener(
                        "click",
                        () => {
                            setRendererView(
                                button.dataset
                                    .mpmView,
                            );
                        },
                    );
                },
            );

        elements.detailMode
            .addEventListener(
                "change",
                render,
            );

        elements.showFeatureLabels
            .addEventListener(
                "change",
                render,
            );

        elements.showPositions
            .addEventListener(
                "change",
                render,
            );

        elements.showLeaders
            .addEventListener(
                "change",
                render,
            );

        elements.avoidOverlap
            .addEventListener(
                "change",
                render,
            );

        elements.search
            .addEventListener(
                "input",
                render,
            );

        elements.restrictionLabelMode
            .addEventListener(
                "change",
                render,
            );

        elements.featureLabelMode
            .addEventListener(
                "change",
                render,
            );

        elements.siteListButton
            .addEventListener(
                "click",
                () => {
                    state.siteListOpen = (
                        !state.siteListOpen
                    );

                    renderSiteList(
                        state.snapshot,
                    );
                },
            );

        elements.restrictionMode
            .addEventListener(
                "change",
                () => {
                    elements.selectedWrap.hidden = (
                        elements
                            .restrictionMode
                            .value
                        !== "selected"
                    );

                    state.analysisKey = "";

                    scheduleRestrictionAnalysis(
                        30,
                    );
                },
            );

        elements.catalog
            .addEventListener(
                "change",
                () => {
                    state.analysisKey = "";

                    scheduleRestrictionAnalysis(
                        30,
                    );
                },
            );

        elements.minimumSite
            .addEventListener(
                "change",
                () => {
                    state.analysisKey = "";

                    scheduleRestrictionAnalysis(
                        30,
                    );
                },
            );

        elements.selectedEnzymes
            .addEventListener(
                "input",
                () => {
                    if (
                        elements
                            .restrictionMode
                            .value
                        !== "selected"
                    ) {
                        return;
                    }

                    state.analysisKey = "";

                    scheduleRestrictionAnalysis(
                        260,
                    );
                },
            );

        elements.resetView
            .addEventListener(
                "click",
                () => {
                    resetViewBox();
                    render();
                },
            );

        elements.exportSvg
            .addEventListener(
                "click",
                exportSvg,
            );

        root.addEventListener(
            "biobank:molecular-workspace-change",
            event => {
                const snapshot = (
                    event.detail?.snapshot
                );

                if (!snapshot) {
                    return;
                }

                state.snapshot = (
                    snapshot
                );

                if (
                    state.firstSnapshot
                ) {
                    state.firstSnapshot = false;

                    let storedView = "";

                    try {
                        storedView = (
                            localStorage
                                .getItem(
                                    VIEW_STORAGE_KEY,
                                )
                            || ""
                        );
                    } catch (_error) {
                        storedView = "";
                    }

                    if (storedView) {
                        setRendererView(
                            storedView,
                            false,
                        );
                    } else if (
                        snapshot.topology
                            === "circular"
                        && snapshot.sequenceType
                            === "plasmid"
                    ) {
                        setRendererView(
                            "detailed",
                            false,
                        );
                    }
                }

                render();

                const key = (
                    currentAnalysisKey()
                );

                if (
                    !state.analysis
                    || key
                        !== state.analysisKey
                ) {
                    scheduleRestrictionAnalysis();
                }
            },
        );

        let initialView = "seqviz";

        try {
            initialView = (
                localStorage.getItem(
                    VIEW_STORAGE_KEY,
                )
                || "seqviz"
            );
        } catch (_error) {
            initialView = "seqviz";
        }

        setRendererView(
            initialView,
            false,
        );

        resetViewBox();

        let attempts = 0;

        function requestInitialSnapshot() {
            const api = (
                workspaceApi()
            );

            if (
                api
                && typeof api.refresh
                    === "function"
            ) {
                api.refresh();
                return;
            }

            attempts += 1;

            if (attempts < 60) {
                window.setTimeout(
                    requestInitialSnapshot,
                    100,
                );

                return;
            }

            setStatus(
                "Molecular workspace API was not available.",
                "error",
            );
        }

        requestInitialSnapshot();
    });
})();
