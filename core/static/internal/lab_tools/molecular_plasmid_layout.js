(() => {
    "use strict";

    const SVG_NS =
        "http://www.w3.org/2000/svg";

    const CENTER_X = 500;
    const CENTER_Y = 370;

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

    function polar(
        radius,
        angle,
    ) {
        return {
            x: (
                CENTER_X
                + Math.cos(angle)
                * radius
            ),
            y: (
                CENTER_Y
                + Math.sin(angle)
                * radius
            ),
        };
    }

    function boxesOverlap(
        first,
        second,
        padding = 4,
    ) {
        return !(
            first.right + padding
                < second.left
            || second.right + padding
                < first.left
            || first.bottom + padding
                < second.top
            || second.bottom + padding
                < first.top
        );
    }

    function featureLength(
        feature,
        sequenceLength,
        circular,
    ) {
        if (!sequenceLength) {
            return 0;
        }

        const start = clamp(
            numeric(
                feature.start,
                1,
            ),
            1,
            sequenceLength,
        );

        const end = clamp(
            numeric(
                feature.end,
                1,
            ),
            1,
            sequenceLength,
        );

        if (
            circular
            && start > end
        ) {
            return (
                sequenceLength
                - start
                + 1
                + end
            );
        }

        return (
            Math.abs(
                end - start
            )
            + 1
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

        const shell = (
            document.getElementById(
                "mw-detailed-plasmid-map",
            )
        );

        const svg = (
            document.getElementById(
                "mpm-svg",
            )
        );

        if (
            !shell
            || !svg
        ) {
            return;
        }

        if (
            document.getElementById(
                "mpl-map-size",
            )
        ) {
            return;
        }

        const toolbar = (
            shell.querySelector(
                ".mpm-toolbar",
            )
        );

        if (!toolbar) {
            return;
        }

        const controls = (
            document.createElement(
                "div",
            )
        );

        controls.className = (
            "mpm-toolbar-group "
            + "mpl-layout-controls"
        );

        controls.innerHTML = `
            <label>
                <span>Map size</span>
                <select id="mpl-map-size"
                        class="form-select form-select-sm">
                    <option value="auto" selected>Auto</option>
                    <option value="large">Large</option>
                    <option value="xl">Extra large</option>
                    <option value="fit">Fit annotations</option>
                </select>
            </label>

            <label class="mpm-check">
                <input id="mpl-smart-feature-spacing"
                       type="checkbox"
                       checked>
                <span>Space internal labels</span>
            </label>
        `;

        const actions = (
            toolbar.querySelector(
                ".mpm-toolbar-actions",
            )
        );

        if (actions) {
            toolbar.insertBefore(
                controls,
                actions,
            );
        } else {
            toolbar.appendChild(
                controls,
            );
        }

        const sizeControl = (
            controls.querySelector(
                "#mpl-map-size",
            )
        );

        const spacingControl = (
            controls.querySelector(
                "#mpl-smart-feature-spacing",
            )
        );

        const state = {
            snapshot: null,
            applying: false,
            frame: null,
        };

        function mapHeight() {
            const mode = (
                sizeControl.value
            );

            const featureCount = (
                Array.isArray(
                    state.snapshot?.features,
                )
                    ? state.snapshot
                        .features
                        .length
                    : 0
            );

            const restrictionLabels = (
                svg.querySelectorAll(
                    ".mpm-restriction-label",
                ).length
            );

            if (mode === "large") {
                return 820;
            }

            if (mode === "xl") {
                return 980;
            }

            if (mode === "fit") {
                return clamp(
                    (
                        760
                        + featureCount * 9
                        + restrictionLabels * 2
                    ),
                    820,
                    1180,
                );
            }

            return clamp(
                (
                    640
                    + featureCount * 5
                ),
                640,
                790,
            );
        }

        function applyMapSize() {
            const height = (
                mapHeight()
            );

            shell.style.setProperty(
                "--mpl-map-height",
                `${height}px`,
            );

            shell.dataset.mapSize = (
                sizeControl.value
            );
        }

        function restoreLabels() {
            svg.querySelectorAll(
                ".mpl-feature-label-leader",
            ).forEach(
                node => node.remove(),
            );

            svg.querySelectorAll(
                ".mpm-feature-label"
            ).forEach(
                label => {
                    if (
                        label.dataset
                            .mplOriginalX
                    ) {
                        label.setAttribute(
                            "x",
                            label.dataset
                                .mplOriginalX,
                        );
                    }

                    if (
                        label.dataset
                            .mplOriginalY
                    ) {
                        label.setAttribute(
                            "y",
                            label.dataset
                                .mplOriginalY,
                        );
                    }

                    label.classList.remove(
                        "mpl-feature-label-spaced",
                    );
                },
            );
        }

        function labelWidth(
            label,
        ) {
            try {
                const measured = (
                    label
                        .getComputedTextLength()
                );

                if (
                    Number.isFinite(
                        measured,
                    )
                    && measured > 0
                ) {
                    return measured;
                }
            } catch (_error) {
                // Fall back below.
            }

            return Math.max(
                38,
                String(
                    label.textContent
                    || "",
                ).length * 7,
            );
        }

        function leaderLine(
            startX,
            startY,
            endX,
            endY,
        ) {
            const line = (
                document.createElementNS(
                    SVG_NS,
                    "line",
                )
            );

            line.setAttribute(
                "x1",
                String(startX),
            );

            line.setAttribute(
                "y1",
                String(startY),
            );

            line.setAttribute(
                "x2",
                String(endX),
            );

            line.setAttribute(
                "y2",
                String(endY),
            );

            line.setAttribute(
                "stroke",
                "#98a2b3",
            );

            line.setAttribute(
                "stroke-width",
                "0.8",
            );

            line.setAttribute(
                "pointer-events",
                "none",
            );

            line.setAttribute(
                "class",
                "mpl-feature-label-leader",
            );

            return line;
        }

        function reflowFeatureLabels() {
            if (
                state.applying
            ) {
                return;
            }

            state.applying = true;

            observer.disconnect();

            try {
                restoreLabels();

                const snapshot = (
                    state.snapshot
                );

                if (
                    !spacingControl.checked
                    || !snapshot
                    || snapshot.topology
                        !== "circular"
                    || !snapshot.sequence
                ) {
                    return;
                }

                const features = (
                    Array.isArray(
                        snapshot.features,
                    )
                        ? snapshot.features
                        : []
                );

                const sequenceLength = (
                    snapshot.sequence.length
                );

                const labels = [
                    ...svg.querySelectorAll(
                        (
                            ".mpm-feature-label"
                            + "[data-feature-index]"
                        ),
                    ),
                ];

                const centerBox = {
                    left: 360,
                    right: 640,
                    top: 300,
                    bottom: 445,
                };

                const placed = [];

                const items = labels
                    .map(
                        label => {
                            const index = (
                                Number(
                                    label.dataset
                                        .featureIndex,
                                )
                            );

                            const feature = (
                                features[index]
                            );

                            if (!feature) {
                                return null;
                            }

                            const x = numeric(
                                label.getAttribute(
                                    "x",
                                ),
                                CENTER_X,
                            );

                            const y = numeric(
                                label.getAttribute(
                                    "y",
                                ),
                                CENTER_Y,
                            );

                            if (
                                !label.dataset
                                    .mplOriginalX
                            ) {
                                label.dataset
                                    .mplOriginalX = (
                                        String(x)
                                    );

                                label.dataset
                                    .mplOriginalY = (
                                        String(y)
                                    );
                            }

                            const angle = Math.atan2(
                                y - CENTER_Y,
                                x - CENTER_X,
                            );

                            const fraction = (
                                featureLength(
                                    feature,
                                    sequenceLength,
                                    true,
                                )
                                / sequenceLength
                            );

                            return {
                                label,
                                index,
                                feature,
                                x,
                                y,
                                angle,
                                fraction,
                                selected: (
                                    index
                                    === snapshot
                                        .selectedFeature
                                ),
                            };
                        },
                    )
                    .filter(Boolean)
                    .sort(
                        (
                            first,
                            second,
                        ) => (
                            first.angle
                            - second.angle
                        ),
                    );

                items.forEach(
                    (
                        item,
                        itemIndex,
                    ) => {
                        /*
                         * Large annotations generally read best
                         * directly on their arc. Concentrate the
                         * callout algorithm on short/dense items.
                         */
                        if (
                            item.fraction >= 0.085
                            && !item.selected
                        ) {
                            const width = (
                                labelWidth(
                                    item.label,
                                )
                            );

                            placed.push(
                                {
                                    left: (
                                        item.x
                                        - width / 2
                                    ),
                                    right: (
                                        item.x
                                        + width / 2
                                    ),
                                    top: item.y - 8,
                                    bottom: item.y + 8,
                                },
                            );

                            return;
                        }

                        const width = (
                            labelWidth(
                                item.label,
                            )
                        );

                        const height = 16;

                        const radii = [
                            176,
                            151,
                            126,
                            101,
                            82,
                        ];

                        const tangentOffsets = [
                            0,
                            -22,
                            22,
                            -44,
                            44,
                            -66,
                            66,
                        ];

                        let chosen = null;

                        outer:
                        for (
                            const radius
                            of radii
                        ) {
                            for (
                                const tangentOffset
                                of tangentOffsets
                            ) {
                                const radial = polar(
                                    radius,
                                    item.angle,
                                );

                                const tangentX = (
                                    -Math.sin(
                                        item.angle,
                                    )
                                );

                                const tangentY = (
                                    Math.cos(
                                        item.angle,
                                    )
                                );

                                const x = (
                                    radial.x
                                    + tangentX
                                    * tangentOffset
                                );

                                const y = (
                                    radial.y
                                    + tangentY
                                    * tangentOffset
                                );

                                const box = {
                                    left: (
                                        x
                                        - width / 2
                                    ),
                                    right: (
                                        x
                                        + width / 2
                                    ),
                                    top: (
                                        y
                                        - height / 2
                                    ),
                                    bottom: (
                                        y
                                        + height / 2
                                    ),
                                };

                                const centerConflict = (
                                    boxesOverlap(
                                        box,
                                        centerBox,
                                        6,
                                    )
                                );

                                const labelConflict = (
                                    placed.some(
                                        other => (
                                            boxesOverlap(
                                                box,
                                                other,
                                                5,
                                            )
                                        ),
                                    )
                                );

                                if (
                                    !centerConflict
                                    && !labelConflict
                                ) {
                                    chosen = {
                                        x,
                                        y,
                                        box,
                                    };

                                    break outer;
                                }
                            }
                        }

                        if (!chosen) {
                            return;
                        }

                        item.label.setAttribute(
                            "x",
                            String(chosen.x),
                        );

                        item.label.setAttribute(
                            "y",
                            String(chosen.y),
                        );

                        item.label.setAttribute(
                            "text-anchor",
                            "middle",
                        );

                        item.label.classList.add(
                            "mpl-feature-label-spaced",
                        );

                        const line = leaderLine(
                            item.x,
                            item.y,
                            chosen.x,
                            chosen.y,
                        );

                        item.label.parentNode
                            .insertBefore(
                                line,
                                item.label,
                            );

                        placed.push(
                            chosen.box,
                        );
                    },
                );
            } finally {
                observer.observe(
                    svg,
                    {
                        childList: true,
                        subtree: true,
                    },
                );

                state.applying = false;
            }
        }

        function scheduleReflow() {
            if (
                state.frame !== null
            ) {
                cancelAnimationFrame(
                    state.frame,
                );
            }

            state.frame = (
                requestAnimationFrame(
                    () => {
                        state.frame = null;

                        applyMapSize();
                        reflowFeatureLabels();
                    },
                )
            );
        }

        const observer = (
            new MutationObserver(
                () => {
                    if (
                        !state.applying
                    ) {
                        scheduleReflow();
                    }
                },
            )
        );

        observer.observe(
            svg,
            {
                childList: true,
                subtree: true,
            },
        );

        root.addEventListener(
            "biobank:molecular-workspace-change",
            event => {
                if (
                    event.detail?.snapshot
                ) {
                    state.snapshot = (
                        event.detail.snapshot
                    );

                    scheduleReflow();
                }
            },
        );

        sizeControl.addEventListener(
            "change",
            scheduleReflow,
        );

        spacingControl.addEventListener(
            "change",
            scheduleReflow,
        );

        scheduleReflow();
    });
})();
