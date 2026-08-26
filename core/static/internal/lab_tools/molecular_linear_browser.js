(() => {
    "use strict";

    const SVG_NS =
        "http://www.w3.org/2000/svg";

    const SVG_WIDTH = 1120;
    const LEFT = 72;
    const RIGHT = 1088;
    const CONTENT_WIDTH = (
        RIGHT - LEFT
    );

    function ready(callback) {
        if (
            document.readyState
            === "loading"
        ) {
            document.addEventListener(
                "DOMContentLoaded",
                callback,
                {
                    once: true,
                },
            );
        } else {
            callback();
        }
    }

    function numeric(
        value,
        fallback = 0,
    ) {
        const result = Number(
            value,
        );

        return Number.isFinite(
            result,
        )
            ? result
            : fallback;
    }

    function clamp(
        value,
        minimum,
        maximum,
    ) {
        return Math.max(
            minimum,
            Math.min(
                maximum,
                value,
            ),
        );
    }

    function formatNumber(value) {
        return numeric(
            value,
        ).toLocaleString();
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

        Object.entries(
            attributes,
        ).forEach(
            ([key, value]) => {
                if (
                    value === undefined
                    || value === null
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

        parent.appendChild(
            node,
        );

        return node;
    }

    function svgTitle(
        parent,
        text,
    ) {
        const node = svgElement(
            "title",
        );

        node.textContent = String(
            text || "",
        );

        parent.appendChild(
            node,
        );
    }

    function workspaceApi() {
        return (
            window
                .BiobankMolecularWorkspace
            || null
        );
    }

    function csrfToken(root) {
        const embedded = String(
            root.dataset.csrfToken
            || "",
        );

        if (
            embedded
            && embedded
                !== "NOTPROVIDED"
        ) {
            return embedded;
        }

        const cookie = (
            document.cookie
                .split(";")
                .map(
                    item => item.trim(),
                )
                .find(
                    item => (
                        item.startsWith(
                            "csrftoken=",
                        )
                    ),
                )
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

    function autoBasesPerRow(
        sequenceLength,
    ) {
        if (
            sequenceLength <= 5000
        ) {
            return 1000;
        }

        if (
            sequenceLength <= 10000
        ) {
            return 2000;
        }

        if (
            sequenceLength <= 25000
        ) {
            return 5000;
        }

        if (
            sequenceLength <= 100000
        ) {
            return 10000;
        }

        return 25000;
    }

    function niceStep(
        span,
    ) {
        if (span <= 250) {
            return 25;
        }

        if (span <= 500) {
            return 50;
        }

        if (span <= 1000) {
            return 100;
        }

        if (span <= 2500) {
            return 250;
        }

        if (span <= 5000) {
            return 500;
        }

        if (span <= 10000) {
            return 1000;
        }

        if (span <= 25000) {
            return 2500;
        }

        return 5000;
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

    function assignFragmentLanes(
        fragments,
        separateStrands,
    ) {
        const laneEnds = {
            plus: [],
            minus: [],
        };

        return fragments
            .sort(
                (
                    first,
                    second,
                ) => (
                    first.start
                    - second.start
                ),
            )
            .map(
                fragment => {
                    const group = (
                        separateStrands
                        && fragment.feature
                            .strand === "-"
                            ? "minus"
                            : "plus"
                    );

                    const ends = (
                        laneEnds[group]
                    );

                    let lane = (
                        ends.findIndex(
                            lastEnd => (
                                fragment.start
                                > lastEnd + 6
                            ),
                        )
                    );

                    if (lane < 0) {
                        lane = ends.length;
                        ends.push(
                            fragment.end,
                        );
                    } else {
                        ends[lane] = (
                            fragment.end
                        );
                    }

                    return {
                        ...fragment,
                        lane,
                        group,
                    };
                },
            );
    }

    function featurePolygon(
        x1,
        x2,
        y,
        strand,
    ) {
        const width = Math.max(
            4,
            x2 - x1,
        );

        const halfHeight = 8;

        const arrow = Math.min(
            12,
            Math.max(
                4,
                width * 0.35,
            ),
        );

        if (
            strand === "+"
            && width >= 10
        ) {
            return [
                [x1, y - halfHeight],
                [
                    x2 - arrow,
                    y - halfHeight,
                ],
                [x2, y],
                [
                    x2 - arrow,
                    y + halfHeight,
                ],
                [x1, y + halfHeight],
            ]
                .map(
                    point => (
                        point.join(",")
                    ),
                )
                .join(" ");
        }

        if (
            strand === "-"
            && width >= 10
        ) {
            return [
                [x2, y - halfHeight],
                [
                    x1 + arrow,
                    y - halfHeight,
                ],
                [x1, y],
                [
                    x1 + arrow,
                    y + halfHeight,
                ],
                [x2, y + halfHeight],
            ]
                .map(
                    point => (
                        point.join(",")
                    ),
                )
                .join(" ");
        }

        return [
            [x1, y - halfHeight],
            [x2, y - halfHeight],
            [x2, y + halfHeight],
            [x1, y + halfHeight],
        ]
            .map(
                point => (
                    point.join(",")
                ),
            )
            .join(" ");
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

        const viewerRoot = (
            document.getElementById(
                "mw-seqviz-viewer",
            )
        );

        const detailedShell = (
            document.getElementById(
                "mw-detailed-plasmid-map",
            )
        );

        const switcher = (
            document.querySelector(
                ".mpm-view-switcher",
            )
        );

        if (
            !viewerRoot
            || !detailedShell
            || !switcher
        ) {
            return;
        }

        if (
            document.getElementById(
                "mw-linear-browser",
            )
        ) {
            return;
        }

        const browser = (
            document.createElement(
                "section",
            )
        );

        browser.id = (
            "mw-linear-browser"
        );

        browser.className = (
            "mlb-shell"
        );

        browser.hidden = true;

        browser.innerHTML = `
            <div class="mlb-toolbar">
                <label>
                    <span>Layout</span>
                    <select id="mlb-layout"
                            class="form-select form-select-sm">
                        <option value="wrapped" selected>Wrapped</option>
                        <option value="continuous">Continuous</option>
                    </select>
                </label>

                <label>
                    <span>Bases / row</span>
                    <select id="mlb-bases-row"
                            class="form-select form-select-sm">
                        <option value="auto" selected>Auto</option>
                        <option value="500">500 bp</option>
                        <option value="1000">1,000 bp</option>
                        <option value="2000">2,000 bp</option>
                        <option value="5000">5,000 bp</option>
                        <option value="10000">10,000 bp</option>
                    </select>
                </label>

                <label>
                    <span>Feature labels</span>
                    <select id="mlb-feature-labels"
                            class="form-select form-select-sm">
                        <option value="smart" selected>Smart</option>
                        <option value="all">All labels</option>
                        <option value="none">None</option>
                    </select>
                </label>

                <label class="mlb-check">
                    <input id="mlb-separate-strands"
                           type="checkbox"
                           checked>
                    <span>Separate strands</span>
                </label>

                <label class="mlb-check">
                    <input id="mlb-restriction-ticks"
                           type="checkbox">
                    <span>Restriction ticks</span>
                </label>

                <label class="mlb-search">
                    <span>Find feature</span>
                    <input id="mlb-search"
                           class="form-control form-control-sm"
                           type="search"
                           placeholder="KanR, lacI, promoter…">
                </label>

                <button id="mlb-selected-feature"
                        type="button"
                        class="btn btn-sm btn-outline-secondary">
                    Go to selected
                </button>
            </div>

            <div class="mlb-overview-wrap">
                <div class="mlb-section-title">
                    Whole molecule overview
                </div>

                <svg id="mlb-overview"
                     viewBox="0 0 1120 86"
                     aria-label="Whole molecular sequence overview"></svg>
            </div>

            <div id="mlb-status"
                 class="mlb-status"
                 role="status"
                 aria-live="polite">
                Waiting for molecular workspace data…
            </div>

            <div id="mlb-stage"
                 class="mlb-stage">
                <svg id="mlb-svg"
                     viewBox="0 0 1120 400"
                     aria-label="Linear molecular feature browser"></svg>
            </div>
        `;

        detailedShell.after(
            browser,
        );

        const linearButton = (
            document.createElement(
                "button",
            )
        );

        linearButton.type = "button";

        linearButton.className = (
            "mpm-view-button"
        );

        linearButton.dataset.mpmView = (
            "linear"
        );

        linearButton.textContent = (
            "Linear browser"
        );

        switcher.appendChild(
            linearButton,
        );

        const elements = {
            layout: browser.querySelector(
                "#mlb-layout",
            ),
            basesRow: browser.querySelector(
                "#mlb-bases-row",
            ),
            featureLabels: browser.querySelector(
                "#mlb-feature-labels",
            ),
            separateStrands: browser.querySelector(
                "#mlb-separate-strands",
            ),
            restrictionTicks: browser.querySelector(
                "#mlb-restriction-ticks",
            ),
            search: browser.querySelector(
                "#mlb-search",
            ),
            selectedFeature: browser.querySelector(
                "#mlb-selected-feature",
            ),
            overview: browser.querySelector(
                "#mlb-overview",
            ),
            stage: browser.querySelector(
                "#mlb-stage",
            ),
            svg: browser.querySelector(
                "#mlb-svg",
            ),
            status: browser.querySelector(
                "#mlb-status",
            ),
        };

        const state = {
            snapshot: null,
            restrictions: [],
            restrictionKey: "",
            requestId: 0,
        };

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

        function showLinearBrowser() {
            viewerRoot.hidden = true;
            detailedShell.hidden = true;
            browser.hidden = false;

            [
                ...switcher.querySelectorAll(
                    ".mpm-view-button",
                ),
            ].forEach(
                button => {
                    const active = (
                        button
                        === linearButton
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

            render();

            if (
                elements
                    .restrictionTicks
                    .checked
            ) {
                loadRestrictions();
            }
        }

        linearButton.addEventListener(
            "click",
            showLinearBrowser,
        );

        switcher.querySelectorAll(
            (
                '[data-mpm-view="seqviz"],'
                + '[data-mpm-view="detailed"]'
            ),
        ).forEach(
            button => {
                button.addEventListener(
                    "click",
                    () => {
                        browser.hidden = true;
                        linearButton
                            .classList
                            .remove(
                                "is-active",
                            );

                        linearButton.setAttribute(
                            "aria-pressed",
                            "false",
                        );
                    },
                );
            },
        );

        function currentBasesPerRow() {
            const snapshot = (
                state.snapshot
            );

            if (!snapshot) {
                return 1000;
            }

            if (
                elements.layout.value
                === "continuous"
            ) {
                return Math.max(
                    1,
                    snapshot.sequence.length,
                );
            }

            if (
                elements.basesRow.value
                === "auto"
            ) {
                return autoBasesPerRow(
                    snapshot.sequence.length,
                );
            }

            return Math.max(
                100,
                numeric(
                    elements.basesRow.value,
                    1000,
                ),
            );
        }

        function coordinateX(
            coordinate,
            rowStart,
            rowEnd,
        ) {
            const span = Math.max(
                1,
                rowEnd
                - rowStart
                + 1,
            );

            return (
                LEFT
                + (
                    (
                        coordinate
                        - rowStart
                    )
                    / span
                )
                * CONTENT_WIDTH
            );
        }

        function featureMatches(
            feature,
        ) {
            const query = String(
                elements.search.value
                || "",
            )
                .trim()
                .toLowerCase();

            if (!query) {
                return false;
            }

            return [
                feature.name,
                feature.feature_type,
                feature.type,
                feature.notes,
            ]
                .filter(Boolean)
                .some(
                    value => (
                        String(value)
                            .toLowerCase()
                            .includes(query)
                    ),
                );
        }

        function renderOverview() {
            const svg = (
                elements.overview
            );

            svg.replaceChildren();

            const snapshot = (
                state.snapshot
            );

            if (
                !snapshot
                || !snapshot.sequence
            ) {
                return;
            }

            const length = (
                snapshot.sequence.length
            );

            svg.appendChild(
                svgElement(
                    "line",
                    {
                        x1: LEFT,
                        y1: 43,
                        x2: RIGHT,
                        y2: 43,
                        class: (
                            "mlb-overview-backbone"
                        ),
                    },
                ),
            );

            const features = (
                Array.isArray(
                    snapshot.features,
                )
                    ? snapshot.features
                    : []
            );

            features.forEach(
                (
                    feature,
                    featureIndex,
                ) => {
                    featureSegments(
                        feature,
                        length,
                        snapshot.topology
                            === "circular",
                    ).forEach(
                        segment => {
                            const x1 = (
                                LEFT
                                + (
                                    (
                                        segment.start
                                        - 1
                                    )
                                    / length
                                )
                                * CONTENT_WIDTH
                            );

                            const x2 = (
                                LEFT
                                + (
                                    segment.end
                                    / length
                                )
                                * CONTENT_WIDTH
                            );

                            const selected = (
                                featureIndex
                                === snapshot
                                    .selectedFeature
                            );

                            const rect = (
                                svgElement(
                                    "rect",
                                    {
                                        x: x1,
                                        y: (
                                            feature.strand
                                            === "-"
                                                ? 48
                                                : 29
                                        ),
                                        width: Math.max(
                                            2,
                                            x2 - x1,
                                        ),
                                        height: 9,
                                        rx: 2,
                                        fill: (
                                            feature.color
                                            || "#98a2b3"
                                        ),
                                        class: (
                                            selected
                                                ? "mlb-overview-feature is-selected"
                                                : "mlb-overview-feature"
                                        ),
                                        "data-feature-index": (
                                            featureIndex
                                        ),
                                    },
                                )
                            );

                            rect.addEventListener(
                                "click",
                                () => {
                                    workspaceApi()
                                        ?.selectFeature?.(
                                            featureIndex,
                                        );
                                },
                            );

                            svg.appendChild(
                                rect,
                            );
                        },
                    );
                },
            );

            const basesPerRow = (
                currentBasesPerRow()
            );

            if (
                elements.layout.value
                === "wrapped"
            ) {
                for (
                    let boundary = basesPerRow;
                    boundary < length;
                    boundary += basesPerRow
                ) {
                    const x = (
                        LEFT
                        + (
                            boundary
                            / length
                        )
                        * CONTENT_WIDTH
                    );

                    svg.appendChild(
                        svgElement(
                            "line",
                            {
                                x1: x,
                                y1: 20,
                                x2: x,
                                y2: 66,
                                class: (
                                    "mlb-overview-boundary"
                                ),
                            },
                        ),
                    );
                }
            }

            svgText(
                svg,
                "1",
                {
                    x: LEFT,
                    y: 78,
                    class: (
                        "mlb-overview-coordinate"
                    ),
                    "text-anchor": "start",
                },
            );

            svgText(
                svg,
                formatNumber(length),
                {
                    x: RIGHT,
                    y: 78,
                    class: (
                        "mlb-overview-coordinate"
                    ),
                    "text-anchor": "end",
                },
            );
        }

        function rowFragments(
            rowStart,
            rowEnd,
        ) {
            const snapshot = (
                state.snapshot
            );

            const length = (
                snapshot.sequence.length
            );

            const fragments = [];

            (
                Array.isArray(
                    snapshot.features,
                )
                    ? snapshot.features
                    : []
            ).forEach(
                (
                    feature,
                    featureIndex,
                ) => {
                    featureSegments(
                        feature,
                        length,
                        snapshot.topology
                            === "circular",
                    ).forEach(
                        segment => {
                            const start = Math.max(
                                rowStart,
                                segment.start,
                            );

                            const end = Math.min(
                                rowEnd,
                                segment.end,
                            );

                            if (start > end) {
                                return;
                            }

                            fragments.push(
                                {
                                    feature,
                                    featureIndex,
                                    start,
                                    end,
                                },
                            );
                        },
                    );
                },
            );

            return assignFragmentLanes(
                fragments,
                elements
                    .separateStrands
                    .checked,
            );
        }

        function restrictionSitesForRow(
            rowStart,
            rowEnd,
        ) {
            return state.restrictions
                .filter(
                    site => (
                        numeric(
                            site.position,
                        )
                        >= rowStart
                        && numeric(
                            site.position,
                        )
                        <= rowEnd
                    ),
                );
        }

        function shouldShowFeatureLabel(
            fragment,
            pixelWidth,
            selected,
        ) {
            const mode = (
                elements
                    .featureLabels
                    .value
            );

            if (mode === "none") {
                return false;
            }

            if (
                mode === "all"
                || selected
            ) {
                return true;
            }

            return (
                pixelWidth >= 54
                || (
                    fragment.end
                    - fragment.start
                    + 1
                )
                >= (
                    currentBasesPerRow()
                    * 0.065
                )
            );
        }

        function renderRow(
            svg,
            rowIndex,
            rowStart,
            rowEnd,
        ) {
            const rowHeight = 210;

            const rowTop = (
                rowIndex
                * rowHeight
            );

            const axisY = (
                rowTop
                + 104
            );

            const rowSpan = (
                rowEnd
                - rowStart
                + 1
            );

            svg.appendChild(
                svgElement(
                    "rect",
                    {
                        x: 0,
                        y: rowTop,
                        width: SVG_WIDTH,
                        height: rowHeight,
                        class: (
                            rowIndex % 2
                                ? "mlb-row-background is-alternate"
                                : "mlb-row-background"
                        ),
                    },
                ),
            );

            svgText(
                svg,
                (
                    `${formatNumber(
                        rowStart,
                    )}–${formatNumber(
                        rowEnd,
                    )} bp`
                ),
                {
                    x: LEFT,
                    y: rowTop + 19,
                    class: (
                        "mlb-row-title"
                    ),
                    "text-anchor": "start",
                },
            );

            svg.appendChild(
                svgElement(
                    "line",
                    {
                        x1: LEFT,
                        y1: axisY,
                        x2: RIGHT,
                        y2: axisY,
                        class: "mlb-axis",
                    },
                ),
            );

            const step = niceStep(
                rowSpan,
            );

            const firstTick = (
                Math.ceil(
                    rowStart
                    / step
                )
                * step
            );

            for (
                let position = firstTick;
                position <= rowEnd;
                position += step
            ) {
                const x = coordinateX(
                    position,
                    rowStart,
                    rowEnd,
                );

                svg.appendChild(
                    svgElement(
                        "line",
                        {
                            x1: x,
                            y1: axisY - 5,
                            x2: x,
                            y2: axisY + 5,
                            class: (
                                "mlb-axis-tick"
                            ),
                        },
                    ),
                );

                svgText(
                    svg,
                    formatNumber(
                        position,
                    ),
                    {
                        x,
                        y: axisY + 22,
                        class: (
                            "mlb-axis-label"
                        ),
                        "text-anchor": (
                            "middle"
                        ),
                    },
                );
            }

            const fragments = (
                rowFragments(
                    rowStart,
                    rowEnd,
                )
            );

            fragments.forEach(
                fragment => {
                    const x1 = coordinateX(
                        fragment.start,
                        rowStart,
                        rowEnd,
                    );

                    const x2 = coordinateX(
                        fragment.end,
                        rowStart,
                        rowEnd,
                    );

                    const strand = (
                        fragment.feature
                            .strand
                        || "."
                    );

                    let y;

                    if (
                        elements
                            .separateStrands
                            .checked
                        && fragment.group
                            === "minus"
                    ) {
                        y = (
                            axisY
                            + 30
                            + fragment.lane
                            * 24
                        );
                    } else {
                        y = (
                            axisY
                            - 28
                            - fragment.lane
                            * 24
                        );
                    }

                    const selected = (
                        fragment.featureIndex
                        === state.snapshot
                            .selectedFeature
                    );

                    const searchMatch = (
                        featureMatches(
                            fragment.feature,
                        )
                    );

                    const polygon = (
                        svgElement(
                            "polygon",
                            {
                                points: featurePolygon(
                                    x1,
                                    Math.max(
                                        x1 + 4,
                                        x2,
                                    ),
                                    y,
                                    strand,
                                ),
                                fill: (
                                    fragment.feature
                                        .color
                                    || "#98a2b3"
                                ),
                                class: [
                                    "mlb-feature",
                                    selected
                                        ? "is-selected"
                                        : "",
                                    searchMatch
                                        ? "is-search-match"
                                        : "",
                                ]
                                    .filter(Boolean)
                                    .join(" "),
                                "data-feature-index": (
                                    fragment
                                        .featureIndex
                                ),
                            },
                        )
                    );

                    svgTitle(
                        polygon,
                        [
                            fragment.feature
                                .name,
                            (
                                `${fragment.feature.start}`
                                + ".."
                                + `${fragment.feature.end}`
                            ),
                            strand,
                        ].join(" · "),
                    );

                    polygon.addEventListener(
                        "click",
                        () => {
                            workspaceApi()
                                ?.selectFeature?.(
                                    fragment
                                        .featureIndex,
                                );
                        },
                    );

                    svg.appendChild(
                        polygon,
                    );

                    const width = (
                        Math.max(
                            4,
                            x2 - x1,
                        )
                    );

                    if (
                        shouldShowFeatureLabel(
                            fragment,
                            width,
                            selected,
                        )
                    ) {
                        const label = svgText(
                            svg,
                            fragment.feature
                                .name
                                || "Feature",
                            {
                                x: (
                                    x1
                                    + width / 2
                                ),
                                y: (
                                    fragment.group
                                    === "minus"
                                    && elements
                                        .separateStrands
                                        .checked
                                        ? y + 23
                                        : y - 13
                                ),
                                class: [
                                    "mlb-feature-label",
                                    selected
                                        ? "is-selected"
                                        : "",
                                    searchMatch
                                        ? "is-search-match"
                                        : "",
                                ]
                                    .filter(Boolean)
                                    .join(" "),
                                "text-anchor": (
                                    "middle"
                                ),
                            },
                        );

                        label.addEventListener(
                            "click",
                            () => {
                                workspaceApi()
                                    ?.selectFeature?.(
                                        fragment
                                            .featureIndex,
                                    );
                            },
                        );
                    }
                },
            );

            if (
                elements
                    .restrictionTicks
                    .checked
            ) {
                restrictionSitesForRow(
                    rowStart,
                    rowEnd,
                ).forEach(
                    site => {
                        const x = coordinateX(
                            numeric(
                                site.position,
                            ),
                            rowStart,
                            rowEnd,
                        );

                        const tick = (
                            svgElement(
                                "line",
                                {
                                    x1: x,
                                    y1: axisY - 13,
                                    x2: x,
                                    y2: axisY + 13,
                                    class: (
                                        "mlb-restriction-tick"
                                    ),
                                },
                            )
                        );

                        svgTitle(
                            tick,
                            (
                                `${site.enzyme} `
                                + `(${site.position})`
                            ),
                        );

                        tick.addEventListener(
                            "click",
                            () => {
                                const length = (
                                    Math.max(
                                        1,
                                        numeric(
                                            site
                                                .recognition_length,
                                            1,
                                        ),
                                    )
                                );

                                workspaceApi()
                                    ?.selectSequenceRange?.(
                                        numeric(
                                            site.position,
                                            1,
                                        ),
                                        numeric(
                                            site.position,
                                            1,
                                        )
                                            + length
                                            - 1,
                                        {
                                            source: (
                                                "linear-browser"
                                            ),
                                        },
                                    );
                            },
                        );

                        svg.appendChild(
                            tick,
                        );
                    },
                );
            }
        }

        function render() {
            const snapshot = (
                state.snapshot
            );

            elements.svg
                .replaceChildren();

            renderOverview();

            if (
                !snapshot
                || !snapshot.sequence
            ) {
                elements.svg.setAttribute(
                    "viewBox",
                    "0 0 1120 180",
                );

                svgText(
                    elements.svg,
                    (
                        "No sequence is available "
                        + "for the linear browser."
                    ),
                    {
                        x: SVG_WIDTH / 2,
                        y: 90,
                        class: (
                            "mlb-empty"
                        ),
                        "text-anchor": (
                            "middle"
                        ),
                    },
                );

                return;
            }

            const length = (
                snapshot.sequence.length
            );

            const basesPerRow = (
                currentBasesPerRow()
            );

            const rows = (
                elements.layout.value
                === "continuous"
                    ? 1
                    : Math.ceil(
                        length
                        / basesPerRow
                    )
            );

            const rowHeight = 210;

            const height = Math.max(
                230,
                rows * rowHeight,
            );

            elements.svg.setAttribute(
                "viewBox",
                `0 0 ${SVG_WIDTH} ${height}`,
            );

            elements.svg.setAttribute(
                "height",
                String(height),
            );

            for (
                let rowIndex = 0;
                rowIndex < rows;
                rowIndex += 1
            ) {
                const rowStart = (
                    rowIndex
                    * basesPerRow
                    + 1
                );

                const rowEnd = Math.min(
                    length,
                    (
                        rowStart
                        + basesPerRow
                        - 1
                    ),
                );

                renderRow(
                    elements.svg,
                    rowIndex,
                    rowStart,
                    rowEnd,
                );
            }

            const featureCount = (
                Array.isArray(
                    snapshot.features,
                )
                    ? snapshot.features
                        .length
                    : 0
            );

            const restrictionText = (
                elements
                    .restrictionTicks
                    .checked
                    ? (
                        ` · ${formatNumber(
                            state
                                .restrictions
                                .length,
                        )} restriction tick`
                        + (
                            state
                                .restrictions
                                .length === 1
                                ? ""
                                : "s"
                        )
                    )
                    : ""
            );

            setStatus(
                (
                    `${formatNumber(length)} bp`
                    + ` · ${formatNumber(
                        featureCount,
                    )} annotation`
                    + (
                        featureCount === 1
                            ? ""
                            : "s"
                    )
                    + ` · ${formatNumber(
                        rows,
                    )} row`
                    + (
                        rows === 1
                            ? ""
                            : "s"
                    )
                    + restrictionText
                ),
                "success",
            );
        }

        function restrictionRequestKey() {
            const snapshot = (
                state.snapshot
            );

            if (!snapshot) {
                return "";
            }

            return JSON.stringify(
                {
                    sequence: snapshot.sequence,
                    topology: snapshot.topology,
                },
            );
        }

        /*
         * FINAL MOLECULAR UX REFINEMENT V2 20260810
         */
        function workspaceSequenceType() {
            return String(
                state.snapshot?.sequenceType
                || document
                    .getElementById("mw-type")
                    ?.value
                || ""
            ).toLowerCase();
        }

        function workspaceDisplayUnit() {
            const type = workspaceSequenceType();

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

        function applyTypeAwareVocabulary() {
            const type = workspaceSequenceType();
            const unit = workspaceDisplayUnit();

            const rowLabel = (
                elements.basesRow
                    ?.closest("label")
                    ?.querySelector("span")
            );

            let desired = "Bases / row";

            if (unit === "nt") {
                desired = "Nucleotides / row";
            } else if (unit === "aa") {
                desired = "Residues / row";
            } else if (unit === "symbols") {
                desired = "Symbols / row";
            }

            if (
                rowLabel
                && rowLabel.textContent !== desired
            ) {
                rowLabel.textContent = desired;
            }

            const restrictionWrap = (
                elements.restrictionTicks
                    ?.closest("label")
            );

            if (
                type === "rna"
                && elements.restrictionTicks
            ) {
                elements.restrictionTicks.checked = false;

                browser
                    .querySelectorAll(
                        ".mlb-restriction-tick"
                    )
                    .forEach(
                        node => node.remove()
                    );
            }

            if (restrictionWrap) {
                restrictionWrap.hidden = (
                    type === "rna"
                );
            }

            if (
                unit !== "bp"
                && unit !== "nt"
            ) {
                return;
            }

            const walker = (
                document.createTreeWalker(
                    browser,
                    NodeFilter.SHOW_TEXT
                )
            );

            const nodes = [];

            while (walker.nextNode()) {
                nodes.push(
                    walker.currentNode
                );
            }

            nodes.forEach(node => {
                const current = node.nodeValue || "";

                const next = current.replace(
                    /\b(?:bp|nt)\b/g,
                    unit
                );

                if (next !== current) {
                    node.nodeValue = next;
                }
            });
        }

        let typeVocabularyScheduled = false;

        function scheduleTypeAwareVocabulary() {
            if (typeVocabularyScheduled) {
                return;
            }

            typeVocabularyScheduled = true;

            window.requestAnimationFrame(
                () => {
                    typeVocabularyScheduled = false;
                    applyTypeAwareVocabulary();
                }
            );
        }

        const typeVocabularyObserver = (
            new MutationObserver(
                scheduleTypeAwareVocabulary
            )
        );

        typeVocabularyObserver.observe(
            browser,
            {
                childList: true,
                subtree: true,
                characterData: true,
            }
        );

        scheduleTypeAwareVocabulary();

        async function loadRestrictions() {
            const snapshot = (
                state.snapshot
            );

            if (
                workspaceSequenceType() === "rna"
            ) {
                state.restrictions = [];
                state.restrictionKey = "";
                render();
                return;
            }

            if (
                !snapshot
                || !snapshot.sequence
                || !root.dataset
                    .restrictionSitesUrl
            ) {
                return;
            }

            const key = (
                restrictionRequestKey()
            );

            if (
                key
                && key
                    === state
                        .restrictionKey
            ) {
                render();
                return;
            }

            const requestId = (
                ++state.requestId
            );

            setStatus(
                "Loading restriction sites…",
                "loading",
            );

            try {
                const response = await fetch(
                    root.dataset
                        .restrictionSitesUrl,
                    {
                        method: "POST",
                        credentials: (
                            "same-origin"
                        ),
                        headers: {
                            Accept: (
                                "application/json"
                            ),
                            "Content-Type": (
                                "application/json"
                            ),
                            "X-CSRFToken": (
                                csrfToken(root)
                            ),
                        },
                        body: JSON.stringify(
                            {
                                sequence: (
                                    snapshot.sequence
                                ),
                                topology: (
                                    snapshot.topology
                                ),
                                mode: "unique",
                                catalog: "common",
                                minimum_site_length: 6,
                            },
                        ),
                    },
                );

                const payload = (
                    await response.json()
                );

                if (
                    !response.ok
                    || payload.status
                        !== "success"
                ) {
                    throw new Error(
                        payload.message
                        || (
                            `HTTP `
                            + response.status
                        ),
                    );
                }

                if (
                    requestId
                    !== state.requestId
                ) {
                    return;
                }

                state.restrictions = (
                    Array.isArray(
                        payload.analysis
                            ?.sites,
                    )
                        ? payload
                            .analysis
                            .sites
                        : []
                );

                state.restrictionKey = (
                    key
                );

                render();
            } catch (error) {
                if (
                    requestId
                    !== state.requestId
                ) {
                    return;
                }

                state.restrictions = [];
                state.restrictionKey = "";

                setStatus(
                    (
                        "Restriction-site error: "
                        + error.message
                    ),
                    "error",
                );

                render();
            }
        }

        function scrollToSelectedFeature() {
            const snapshot = (
                state.snapshot
            );

            if (!snapshot) {
                return;
            }

            const index = (
                snapshot.selectedFeature
            );

            if (
                index === null
                || index === undefined
                || index < 0
            ) {
                return;
            }

            const feature = (
                snapshot.features?.[
                    index
                ]
            );

            if (!feature) {
                return;
            }

            const basesPerRow = (
                currentBasesPerRow()
            );

            const rowIndex = (
                elements.layout.value
                === "continuous"
                    ? 0
                    : Math.floor(
                        (
                            numeric(
                                feature.start,
                                1,
                            )
                            - 1
                        )
                        / basesPerRow
                    )
            );

            elements.stage.scrollTo(
                {
                    top: (
                        rowIndex
                        * 210
                        - 20
                    ),
                    behavior: "smooth",
                },
            );
        }

        root.addEventListener(
            "biobank:molecular-workspace-change",
            event => {
                const snapshot = (
                    event.detail?.snapshot
                );

                if (!snapshot) {
                    return;
                }

                const previousKey = (
                    restrictionRequestKey()
                );

                state.snapshot = snapshot;

                render();

                const nextKey = (
                    restrictionRequestKey()
                );

                if (
                    elements
                        .restrictionTicks
                        .checked
                    && (
                        previousKey
                        !== nextKey
                        || !state
                            .restrictions
                            .length
                    )
                ) {
                    state.restrictionKey = "";

                    loadRestrictions();
                }
            },
        );

        elements.layout.addEventListener(
            "change",
            render,
        );

        elements.basesRow.addEventListener(
            "change",
            render,
        );

        elements.featureLabels
            .addEventListener(
                "change",
                render,
            );

        elements.separateStrands
            .addEventListener(
                "change",
                render,
            );

        elements.search.addEventListener(
            "input",
            render,
        );

        elements.restrictionTicks
            .addEventListener(
                "change",
                () => {
                    if (
                        elements
                            .restrictionTicks
                            .checked
                    ) {
                        loadRestrictions();
                    } else {
                        render();
                    }
                },
            );

        elements.selectedFeature
            .addEventListener(
                "click",
                scrollToSelectedFeature,
            );

        elements.overview.addEventListener(
            "click",
            event => {
                const snapshot = (
                    state.snapshot
                );

                if (
                    !snapshot
                    || !snapshot.sequence
                    || elements.layout.value
                        !== "wrapped"
                ) {
                    return;
                }

                const rect = (
                    elements.overview
                        .getBoundingClientRect()
                );

                const relative = clamp(
                    (
                        event.clientX
                        - rect.left
                    )
                    / rect.width,
                    0,
                    1,
                );

                const coordinate = (
                    1
                    + relative
                    * (
                        snapshot
                            .sequence
                            .length
                        - 1
                    )
                );

                const rowIndex = (
                    Math.floor(
                        (
                            coordinate
                            - 1
                        )
                        / currentBasesPerRow()
                    )
                );

                elements.stage.scrollTo(
                    {
                        top: (
                            rowIndex
                            * 210
                            - 20
                        ),
                        behavior: (
                            "smooth"
                        ),
                    },
                );
            },
        );

        render();
    });
})();
