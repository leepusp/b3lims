(() => {
    "use strict";

    const VERSION = (
        "PROTEIN_OVERVIEW_SPLITTER_V2_20260817"
    );

    const DEFAULT_PERCENT = 60;

    const MIN_SEQUENCE_PX = 320;
    const MIN_STRUCTURE_PX = 360;

    const DESKTOP_QUERY = (
        "(min-width: 1181px)"
    );

    let resizeFrame = null;

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener(
                "DOMContentLoaded",
                callback,
                {
                    once: true,
                },
            );

            return;
        }

        callback();
    }

    function clamp(
        value,
        minimum,
        maximum,
    ) {
        return Math.min(
            maximum,
            Math.max(
                minimum,
                value,
            ),
        );
    }

    function storageKey() {
        return (
            "mw-protein-overview-split:"
            + window.location.pathname
        );
    }

    function scheduleViewerResize() {
        if (resizeFrame !== null) {
            window.cancelAnimationFrame(
                resizeFrame,
            );
        }

        resizeFrame = window.requestAnimationFrame(
            () => {
                resizeFrame = null;

                window.dispatchEvent(
                    new Event(
                        "resize",
                    ),
                );
            },
        );
    }

    async function waitForGrid() {
        for (
            let attempt = 0;
            attempt < 80;
            attempt += 1
        ) {
            const grid = document.querySelector(
                ".mps-overview-grid",
            );

            if (
                grid
                && grid.children.length >= 2
            ) {
                return grid;
            }

            await new Promise(resolve => {
                window.setTimeout(
                    resolve,
                    50,
                );
            });
        }

        return null;
    }

    ready(async () => {
        const root = document.querySelector(
            ".mw-page",
        );

        if (!root) {
            return;
        }

        const sequenceType = String(
            root.dataset.sequenceType || "",
        ).toLowerCase();

        if (sequenceType !== "protein") {
            return;
        }

        const grid = await waitForGrid();

        if (!grid) {
            console.error(
                "Protein sequence/structure grid "
                + "was not found.",
            );

            return;
        }

        if (
            grid.querySelector(
                ":scope > .mps-panel-splitter",
            )
        ) {
            return;
        }

        const children = Array.from(
            grid.children,
        );

        const sequencePanel = children.find(
            node => (
                node.classList.contains(
                    "mw-protein-overview-sequence",
                )
            ),
        );

        const structurePanel = children.find(
            node => (
                node.classList.contains(
                    "mps-card",
                )
            ),
        );

        if (
            !sequencePanel
            || !structurePanel
        ) {
            console.error(
                "Protein splitter panels are unavailable.",
            );

            return;
        }

        grid.classList.add(
            "mps-resizable-grid",
        );

        grid.dataset.splitterVersion = VERSION;

        const splitter = document.createElement(
            "div",
        );

        splitter.id = "mps-panel-splitter";
        splitter.className = "mps-panel-splitter";
        splitter.tabIndex = 0;

        splitter.setAttribute(
            "role",
            "separator",
        );

        splitter.setAttribute(
            "aria-orientation",
            "vertical",
        );

        splitter.setAttribute(
            "aria-label",
            "Resize Protein sequence and structure panels",
        );

        splitter.setAttribute(
            "aria-valuemin",
            "0",
        );

        splitter.setAttribute(
            "aria-valuemax",
            "100",
        );

        splitter.title = (
            "Drag left or right to resize. "
            + "Double-click to reset."
        );

        grid.insertBefore(
            splitter,
            structurePanel,
        );

        /*
         * MOLSTAR EXPANDED/FULLSCREEN GUARD V2 20260817
         *
         * Mol* "expanded" mode is not equivalent to the browser
         * Fullscreen API. Mol* can make its layout fixed to the
         * viewport through plugin.layout.state.isExpanded, and it
         * also exposes expandToFullscreen.
         *
         * The splitter therefore follows all authoritative signals:
         *
         *   - plugin.layout.state.isExpanded
         *   - plugin.layout.state.expandToFullscreen
         *   - .msp-layout-expanded DOM state
         *   - browser document.fullscreenElement
         *
         * During expanded/fullscreen mode the separator keeps its
         * grid column but becomes invisible and non-interactive.
         * The user's saved 60/40 (or custom) split is untouched.
         */

        let activePointerId = null;
        let layoutSubscription = null;
        let subscribedViewer = null;
        let expandedState = null;

        function cancelResize() {
            const wasResizing = (
                grid.classList.contains(
                    "is-resizing",
                )
            );

            grid.classList.remove(
                "is-resizing",
            );

            document.documentElement.classList.remove(
                "mps-resizing",
            );

            if (
                activePointerId !== null
                && splitter.hasPointerCapture(
                    activePointerId,
                )
            ) {
                try {
                    splitter.releasePointerCapture(
                        activePointerId,
                    );
                } catch (error) {
                    console.warn(
                        "Could not release Protein splitter "
                        + "pointer capture.",
                        error,
                    );
                }
            }

            activePointerId = null;

            if (wasResizing) {
                scheduleViewerResize();
            }
        }

        function currentViewer() {
            const direct = (
                window.BiobankProteinStructureViewer
                || null
            );

            if (direct) {
                return direct;
            }

            const adapter = (
                window.BiobankProteinStructure
                || null
            );

            if (
                adapter
                && typeof adapter.getViewer === "function"
            ) {
                return (
                    adapter.getViewer()
                    || null
                );
            }

            return null;
        }

        function browserFullscreenContainsStructure() {
            const fullscreenElement = (
                document.fullscreenElement
                || document.webkitFullscreenElement
                || null
            );

            if (!fullscreenElement) {
                return false;
            }

            return (
                fullscreenElement === structurePanel
                || structurePanel.contains(
                    fullscreenElement,
                )
                || (
                    typeof fullscreenElement.contains
                        === "function"
                    && fullscreenElement.contains(
                        structurePanel,
                    )
                )
            );
        }

        function isMolstarExpanded(
            viewer = currentViewer(),
        ) {
            const layoutState = (
                viewer
                    ?.plugin
                    ?.layout
                    ?.state
                || {}
            );

            const pluginExpanded = Boolean(
                layoutState.isExpanded
                || layoutState.expandToFullscreen
            );

            const domExpanded = Boolean(
                structurePanel.querySelector(
                    ".msp-layout-expanded",
                )
            );

            const browserExpanded = (
                browserFullscreenContainsStructure()
            );

            return (
                pluginExpanded
                || domExpanded
                || browserExpanded
            );
        }

        function syncMolstarExpandedState(
            viewer = currentViewer(),
        ) {
            const expanded = (
                isMolstarExpanded(
                    viewer,
                )
            );

            if (expandedState === expanded) {
                return;
            }

            expandedState = expanded;

            grid.classList.toggle(
                "is-molstar-expanded",
                expanded,
            );

            splitter.setAttribute(
                "aria-hidden",
                expanded
                    ? "true"
                    : "false",
            );

            splitter.tabIndex = (
                expanded
                    ? -1
                    : 0
            );

            if (expanded) {
                cancelResize();
            }

            scheduleViewerResize();
        }

        function bindViewerLayout() {
            const viewer = (
                currentViewer()
            );

            if (viewer === subscribedViewer) {
                syncMolstarExpandedState(
                    viewer,
                );

                return;
            }

            if (
                layoutSubscription
                && typeof layoutSubscription.unsubscribe
                    === "function"
            ) {
                layoutSubscription.unsubscribe();
            }

            layoutSubscription = null;
            subscribedViewer = viewer;

            const updated = (
                viewer
                    ?.plugin
                    ?.layout
                    ?.events
                    ?.updated
            );

            if (
                updated
                && typeof updated.subscribe
                    === "function"
            ) {
                layoutSubscription = (
                    updated.subscribe(
                        () => {
                            syncMolstarExpandedState(
                                viewer,
                            );
                        },
                    )
                );
            }

            syncMolstarExpandedState(
                viewer,
            );
        }

        function scheduleViewerBinding() {
            window.setTimeout(
                () => {
                    bindViewerLayout();
                },
                0,
            );
        }

        function availableWidth() {
            const rect = (
                grid.getBoundingClientRect()
            );

            const splitterWidth = (
                splitter.getBoundingClientRect().width
                || 14
            );

            return Math.max(
                1,
                rect.width
                - splitterWidth,
            );
        }

        function allowedPercentRange() {
            const width = availableWidth();

            const minimumSequence = Math.min(
                MIN_SEQUENCE_PX,
                width * 0.45,
            );

            const minimumStructure = Math.min(
                MIN_STRUCTURE_PX,
                width * 0.45,
            );

            const minimumPercent = (
                minimumSequence
                / width
                * 100
            );

            const maximumPercent = (
                (
                    width
                    - minimumStructure
                )
                / width
                * 100
            );

            return {
                minimumPercent,
                maximumPercent,
            };
        }

        function setSplit(
            percent,
            {
                persist = true,
            } = {},
        ) {
            const range = (
                allowedPercentRange()
            );

            const normalized = clamp(
                Number(percent)
                || DEFAULT_PERCENT,
                range.minimumPercent,
                range.maximumPercent,
            );

            grid.style.setProperty(
                "--mps-sequence-panel-width",
                `${normalized}%`,
            );

            grid.dataset.sequencePanelPercent = (
                normalized.toFixed(2)
            );

            splitter.setAttribute(
                "aria-valuenow",
                String(
                    Math.round(
                        normalized,
                    )
                ),
            );

            splitter.setAttribute(
                "aria-valuetext",
                (
                    `${Math.round(normalized)}% sequence, `
                    + `${Math.round(100 - normalized)}% structure`
                ),
            );

            if (persist) {
                try {
                    window.localStorage.setItem(
                        storageKey(),
                        String(
                            normalized,
                        ),
                    );
                } catch (error) {
                    console.warn(
                        "Could not save Protein splitter width.",
                        error,
                    );
                }
            }

            scheduleViewerResize();
        }

        function restoreSplit() {
            try {
                const stored = Number(
                    window.localStorage.getItem(
                        storageKey(),
                    ),
                );

                if (
                    Number.isFinite(
                        stored,
                    )
                    && stored > 0
                    && stored < 100
                ) {
                    return stored;
                }
            } catch (error) {
                console.warn(
                    "Could not restore Protein splitter width.",
                    error,
                );
            }

            return DEFAULT_PERCENT;
        }

        function pointerPercent(
            clientX,
        ) {
            const rect = (
                grid.getBoundingClientRect()
            );

            const width = availableWidth();

            const splitterWidth = (
                splitter.getBoundingClientRect().width
                || 14
            );

            const requested = (
                clientX
                - rect.left
                - (
                    splitterWidth
                    / 2
                )
            );

            return (
                requested
                / width
                * 100
            );
        }

        function beginResize(
            event,
        ) {
            if (
                !window.matchMedia(
                    DESKTOP_QUERY,
                ).matches
            ) {
                return;
            }

            if (
                grid.classList.contains(
                    "is-molstar-expanded",
                )
            ) {
                return;
            }

            if (
                event.pointerType === "mouse"
                && event.button !== 0
            ) {
                return;
            }

            event.preventDefault();

            splitter.setPointerCapture(
                event.pointerId,
            );

            activePointerId = (
                event.pointerId
            );

            grid.classList.add(
                "is-resizing",
            );

            document.documentElement.classList.add(
                "mps-resizing",
            );

            setSplit(
                pointerPercent(
                    event.clientX,
                ),
            );
        }

        function moveResize(
            event,
        ) {
            if (
                !grid.classList.contains(
                    "is-resizing",
                )
            ) {
                return;
            }

            event.preventDefault();

            setSplit(
                pointerPercent(
                    event.clientX,
                ),
            );
        }

        function endResize(
            event,
        ) {
            if (
                !grid.classList.contains(
                    "is-resizing",
                )
            ) {
                return;
            }

            if (
                activePointerId === null
                && Number.isInteger(
                    event?.pointerId,
                )
            ) {
                activePointerId = (
                    event.pointerId
                );
            }

            cancelResize();

            scheduleViewerResize();
        }

        splitter.addEventListener(
            "pointerdown",
            beginResize,
        );

        splitter.addEventListener(
            "pointermove",
            moveResize,
        );

        splitter.addEventListener(
            "pointerup",
            endResize,
        );

        splitter.addEventListener(
            "pointercancel",
            endResize,
        );

        /*
         * Mol* emits a layout update whenever Expanded Viewport
         * or Fullscreen is toggled. The MutationObserver is a
         * second, implementation-independent guard for the
         * .msp-layout-expanded class.
         */
        const molstarLayoutObserver = (
            new MutationObserver(
                () => {
                    bindViewerLayout();
                    syncMolstarExpandedState();
                },
            )
        );

        molstarLayoutObserver.observe(
            structurePanel,
            {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: [
                    "class",
                ],
            },
        );

        document.addEventListener(
            "fullscreenchange",
            () => {
                syncMolstarExpandedState();
            },
        );

        document.addEventListener(
            "webkitfullscreenchange",
            () => {
                syncMolstarExpandedState();
            },
        );

        [
            "biobank:protein-structure-loaded",
            "biobank:protein-pdb-preview-loaded",
            (
                "biobank:"
                + "protein-computational-structure-preview-loaded"
            ),
        ].forEach(
            eventName => {
                root.addEventListener(
                    eventName,
                    scheduleViewerBinding,
                );
            },
        );

        splitter.addEventListener(
            "dblclick",
            event => {
                event.preventDefault();

                setSplit(
                    DEFAULT_PERCENT,
                );
            },
        );

        splitter.addEventListener(
            "keydown",
            event => {
                const current = Number(
                    grid.dataset.sequencePanelPercent
                    || DEFAULT_PERCENT
                );

                let next = null;

                if (
                    event.key === "ArrowLeft"
                ) {
                    next = current - 2;
                }

                if (
                    event.key === "ArrowRight"
                ) {
                    next = current + 2;
                }

                if (
                    event.key === "Home"
                ) {
                    next = DEFAULT_PERCENT;
                }

                if (next === null) {
                    return;
                }

                event.preventDefault();

                setSplit(
                    next,
                );
            },
        );

        window.addEventListener(
            "resize",
            () => {
                if (
                    window.matchMedia(
                        DESKTOP_QUERY,
                    ).matches
                ) {
                    setSplit(
                        Number(
                            grid.dataset.sequencePanelPercent
                            || DEFAULT_PERCENT
                        ),
                        {
                            persist: false,
                        },
                    );
                }
            },
        );

        setSplit(
            restoreSplit(),
            {
                persist: false,
            },
        );

        bindViewerLayout();
        syncMolstarExpandedState();

        window.BiobankProteinSplitter = {
            version: VERSION,
            reset: () => {
                setSplit(
                    DEFAULT_PERCENT,
                );
            },
            setPercent: percent => {
                setSplit(
                    percent,
                );
            },
            getPercent: () => Number(
                grid.dataset.sequencePanelPercent
                || DEFAULT_PERCENT
            ),
        };
    });
})();
