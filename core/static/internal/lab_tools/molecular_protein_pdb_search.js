(() => {
    "use strict";

    const VERSION = "20260816-find-structure-v1";

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

    function element(
        tag,
        className = "",
        text = "",
    ) {
        const node = document.createElement(
            tag
        );

        if (className) {
            node.className = className;
        }

        if (
            text !== undefined
            && text !== null
            && text !== ""
        ) {
            node.textContent = text;
        }

        return node;
    }

    function cleanString(value) {
        return String(
            value ?? ""
        ).trim();
    }

    function sourceType(hit) {
        return cleanString(
            hit?.source_type
        ).toLowerCase();
    }

    function isExperimental(hit) {
        return (
            sourceType(hit)
            === "experimental"
        );
    }

    function isPredicted(hit) {
        return (
            sourceType(hit)
            === "computational"
        );
    }

    function formatPercent(value) {
        const number = Number(
            value
        );

        if (!Number.isFinite(number)) {
            return "—";
        }

        return `${(number * 100).toFixed(1)}%`;
    }

    function formatDecimal(
        value,
        digits = 2,
    ) {
        const number = Number(
            value
        );

        if (!Number.isFinite(number)) {
            return "—";
        }

        return number.toFixed(
            digits
        );
    }

    function humanize(value) {
        const raw = cleanString(
            value
        );

        if (!raw) {
            return "—";
        }

        return raw
            .replace(
                /[-_]+/g,
                " ",
            )
            .replace(
                /\b\w/g,
                character => (
                    character.toUpperCase()
                ),
            );
    }

    function addMetric(
        container,
        label,
        value,
    ) {
        const metric = element(
            "span",
            (
                "mps-pdb-metric "
                + "mps-structure-metric"
            ),
        );

        metric.append(
            element(
                "strong",
                "",
                label,
            ),
            document.createTextNode(
                ` ${value}`
            ),
        );

        container.appendChild(
            metric
        );
    }

    function providerLabel(hit) {
        return (
            cleanString(
                hit?.provider_name
            )
            || cleanString(
                hit?.provider
            )
            || "Unknown provider"
        );
    }

    function resultLabel(hit) {
        if (isExperimental(hit)) {
            const pdbId = cleanString(
                hit?.accession
            ).toUpperCase();

            const entityId = cleanString(
                hit?.entity_id
            );

            return (
                entityId
                    ? (
                        `${pdbId} · entity ${entityId}`
                    )
                    : pdbId
            );
        }

        return (
            cleanString(
                hit?.accession
            )
            || cleanString(
                hit?.canonical_key
            )
            || "Predicted model"
        );
    }

    function providerStatusText(
        providers,
    ) {
        if (!Array.isArray(providers)) {
            return "";
        }

        const degraded = (
            providers.filter(
                provider => (
                    cleanString(
                        provider?.state
                    ).toLowerCase()
                    !== "available"
                ),
            )
        );

        if (!degraded.length) {
            return "";
        }

        return (
            " · "
            + degraded
                .map(provider => (
                    `${
                        cleanString(
                            provider?.provider_name
                        )
                        || cleanString(
                            provider?.provider
                        )
                        || "provider"
                    } ${
                        cleanString(
                            provider?.state
                        )
                        || "degraded"
                    }`
                ))
                .join(", ")
        );
    }

    ready(async () => {
        const root = document.querySelector(
            ".mw-page"
        );

        if (!root) {
            return;
        }

        if (
            cleanString(
                root.dataset.sequenceType
            ).toLowerCase()
            !== "protein"
        ) {
            return;
        }

        const searchUrl = cleanString(
            root.dataset.proteinStructureSearchUrl
        );

        if (!searchUrl) {
            return;
        }

        let structureCard = null;
        let toolbar = null;

        for (
            let attempt = 0;
            attempt < 120;
            attempt += 1
        ) {
            structureCard = (
                document.getElementById(
                    "mw-protein-structure"
                )
            );

            toolbar = (
                structureCard?.querySelector(
                    ".mps-toolbar"
                )
            );

            if (
                structureCard
                && toolbar
            ) {
                break;
            }

            await new Promise(resolve => {
                window.setTimeout(
                    resolve,
                    50,
                );
            });
        }

        if (
            !structureCard
            || !toolbar
        ) {
            console.error(
                "Structure Finder could not locate "
                + "the Protein structure card."
            );

            return;
        }

        /*
         * The existing DOM id remains stable because PDB Preview
         * and browser QA already use this finder surface.
         */
        if (
            document.getElementById(
                "mps-pdb-find"
            )
        ) {
            return;
        }

        const state = {
            hits: [],
            providers: [],
            activeFilter: "all",
            queryLength: null,
            totalCount: null,
        };

        root.dataset.proteinStructureFinderVersion = (
            VERSION
        );

        const findButton = element(
            "button",
            "btn btn-sm btn-outline-primary",
            "Find structure",
        );

        findButton.id = "mps-pdb-find";
        findButton.type = "button";

        const uploadButton = (
            document.getElementById(
                "mps-upload"
            )
        );

        if (
            uploadButton
            && uploadButton.parentElement
                === toolbar
        ) {
            toolbar.insertBefore(
                findButton,
                uploadButton,
            );

        } else {
            toolbar.appendChild(
                findButton
            );
        }

        const panel = element(
            "section",
            (
                "mps-pdb-finder "
                + "mps-structure-finder"
            ),
        );

        panel.id = "mps-pdb-finder";
        panel.hidden = true;

        const header = element(
            "div",
            (
                "mps-pdb-finder-header "
                + "mps-structure-finder-header"
            ),
        );

        const headingText = element(
            "div"
        );

        headingText.append(
            element(
                "h4",
                "",
                "Structure Finder",
            ),
            element(
                "p",
                "",
                (
                    "Search available experimental and predicted structures "
                    + "across supported structure databases and model providers."
                ),
            ),
        );

        const close = element(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Close",
        );

        close.type = "button";

        header.append(
            headingText,
            close,
        );

        const controls = element(
            "div",
            (
                "mps-pdb-controls "
                + "mps-structure-controls"
            ),
        );

        const filters = element(
            "div",
            "mps-structure-filters",
        );

        filters.setAttribute(
            "role",
            "group",
        );

        filters.setAttribute(
            "aria-label",
            "Structure type",
        );

        const filterDefinitions = [
            [
                "all",
                "All",
            ],
            [
                "experimental",
                "Experimental",
            ],
            [
                "computational",
                "Predicted",
            ],
        ];

        const filterButtons = new Map();

        filterDefinitions.forEach(
            ([value, label]) => {
                const button = element(
                    "button",
                    (
                        "btn btn-sm "
                        + (
                            value === "all"
                                ? "btn-primary"
                                : "btn-outline-secondary"
                        )
                        + " mps-structure-filter"
                    ),
                    label,
                );

                button.type = "button";

                button.dataset.structureFilter = (
                    value
                );

                button.setAttribute(
                    "aria-pressed",
                    value === "all"
                        ? "true"
                        : "false",
                );

                filterButtons.set(
                    value,
                    button,
                );

                filters.appendChild(
                    button
                );
            },
        );

        const searchButton = element(
            "button",
            "btn btn-sm btn-primary",
            "Search structures",
        );

        /*
         * Keep the established id for compatibility with the
         * current Finder DOM contract.
         */
        searchButton.id = "mps-pdb-search";
        searchButton.type = "button";

        controls.append(
            filters,
            searchButton,
        );

        const summary = element(
            "div",
            (
                "mps-pdb-summary "
                + "mps-structure-summary"
            ),
            (
                "Search the current Protein sequence "
                + "for available structures."
            ),
        );

        summary.id = "mps-pdb-summary";

        const results = element(
            "div",
            (
                "mps-pdb-results "
                + "mps-structure-results"
            ),
        );

        results.id = "mps-pdb-results";

        panel.append(
            header,
            controls,
            summary,
            results,
        );

        const body = (
            structureCard.querySelector(
                ".mps-body"
            )
            || structureCard
        );

        const structureStatus = (
            body.querySelector(
                "#mps-status"
            )
        );

        if (structureStatus) {
            structureStatus.insertAdjacentElement(
                "afterend",
                panel,
            );

        } else {
            body.prepend(
                panel
            );
        }

        function renderEmpty(
            message,
        ) {
            results.replaceChildren(
                element(
                    "div",
                    (
                        "mps-pdb-empty "
                        + "mps-structure-empty"
                    ),
                    message,
                ),
            );
        }

        function renderHit(
            hit,
        ) {
            const experimental = (
                isExperimental(hit)
            );

            const predicted = (
                isPredicted(hit)
            );

            const card = element(
                "article",
                (
                    "mps-structure-hit"
                    + (
                        experimental
                            ? " mps-pdb-hit"
                            : ""
                    )
                    + (
                        predicted
                            ? " mps-predicted-hit"
                            : ""
                    )
                ),
            );

            card.dataset.sourceType = (
                sourceType(hit)
            );

            card.dataset.provider = cleanString(
                hit?.provider
            );

            card.dataset.accession = cleanString(
                hit?.accession
            );

            card.dataset.canonicalKey = cleanString(
                hit?.canonical_key
            );

            /*
             * Experimental cards deliberately retain the
             * established PDB Preview contract.
             *
             * Predicted cards NEVER receive mps-pdb-hit,
             * pdbId or entityId, so the existing PDB Preview
             * enhancer cannot mistake them for PDB records.
             */
            if (experimental) {
                card.dataset.pdbId = cleanString(
                    hit?.accession
                ).toUpperCase();

                card.dataset.entityId = cleanString(
                    hit?.entity_id
                );
            }

            const heading = element(
                "div",
                (
                    "mps-pdb-hit-heading "
                    + "mps-structure-hit-heading"
                ),
            );

            const identifierClasses = (
                experimental
                    ? (
                        "mps-pdb-hit-id "
                        + "mps-structure-hit-id"
                    )
                    : "mps-structure-hit-id"
            );

            heading.append(
                element(
                    "span",
                    identifierClasses,
                    resultLabel(
                        hit
                    ),
                ),
                element(
                    "span",
                    (
                        "mps-structure-source-badge "
                        + (
                            experimental
                                ? "is-experimental"
                                : "is-predicted"
                        )
                    ),
                    experimental
                        ? "Experimental"
                        : "Predicted",
                ),
                element(
                    "span",
                    "text-body-secondary small",
                    providerLabel(
                        hit
                    ),
                ),
            );

            card.appendChild(
                heading
            );

            if (hit?.description) {
                card.appendChild(
                    element(
                        "div",
                        (
                            "mps-pdb-hit-description "
                            + "mps-structure-hit-description"
                        ),
                        cleanString(
                            hit.description
                        ),
                    ),
                );
            }

            if (
                hit?.title
                && cleanString(
                    hit.title
                )
                !== cleanString(
                    hit.description
                )
            ) {
                card.appendChild(
                    element(
                        "div",
                        (
                            "mps-pdb-hit-title "
                            + "mps-structure-hit-title"
                        ),
                        cleanString(
                            hit.title
                        ),
                    ),
                );
            }

            const metrics = element(
                "div",
                (
                    "mps-pdb-hit-metrics "
                    + "mps-structure-hit-metrics"
                ),
            );

            if (
                hit?.identity !== null
                && hit?.identity !== undefined
            ) {
                addMetric(
                    metrics,
                    "Sequence identity",
                    formatPercent(
                        hit.identity
                    ),
                );
            }

            if (
                hit?.sequence_coverage !== null
                && hit?.sequence_coverage !== undefined
            ) {
                addMetric(
                    metrics,
                    "Query coverage",
                    formatPercent(
                        hit.sequence_coverage
                    ),
                );
            }

            if (experimental) {
                addMetric(
                    metrics,
                    "Method",
                    (
                        cleanString(
                            hit?.experimental_method
                        )
                        || "—"
                    ),
                );

                addMetric(
                    metrics,
                    "Resolution",
                    (
                        Number.isFinite(
                            Number(
                                hit?.resolution
                            )
                        )
                            ? (
                                `${Number(hit.resolution).toFixed(2)} Å`
                            )
                            : "—"
                    ),
                );

                addMetric(
                    metrics,
                    "Chains",
                    (
                        Array.isArray(
                            hit?.chains
                        )
                        && hit.chains.length
                            ? hit.chains.join(", ")
                            : "—"
                    ),
                );
            }

            if (predicted) {
                addMetric(
                    metrics,
                    "Model type",
                    humanize(
                        hit?.model_type
                    ),
                );

                if (
                    hit?.model_coverage !== null
                    && hit?.model_coverage !== undefined
                ) {
                    addMetric(
                        metrics,
                        "Model coverage",
                        formatPercent(
                            hit.model_coverage
                        ),
                    );
                }

                if (
                    hit?.confidence_type
                    || (
                        hit?.confidence_value !== null
                        && hit?.confidence_value !== undefined
                    )
                ) {
                    const confidence = (
                        hit?.confidence_value !== null
                        && hit?.confidence_value !== undefined
                            ? formatDecimal(
                                hit.confidence_value,
                                2,
                            )
                            : "—"
                    );

                    addMetric(
                        metrics,
                        (
                            cleanString(
                                hit?.confidence_type
                            )
                            || "Confidence"
                        ),
                        confidence,
                    );
                }

                if (
                    hit?.sequence_accession
                ) {
                    addMetric(
                        metrics,
                        "Sequence accession",
                        cleanString(
                            hit.sequence_accession
                        ),
                    );
                }
            }

            card.appendChild(
                metrics
            );

            if (
                Array.isArray(
                    hit?.warnings
                )
                && hit.warnings.length
            ) {
                card.appendChild(
                    element(
                        "div",
                        (
                            "mps-pdb-hit-warning "
                            + "mps-structure-hit-warning"
                        ),
                        (
                            "Some structure metadata "
                            + "could not be retrieved."
                        ),
                    ),
                );
            }

            if (predicted) {
                card.appendChild(
                    element(
                        "div",
                        "mps-structure-preview-note",
                        (
                            "Predicted structures can be previewed temporarily in Mol* "
                            + "and are not saved."
                        ),
                    ),
                );
            }

            return card;
        }

        function filteredHits() {
            if (
                state.activeFilter
                === "all"
            ) {
                return state.hits;
            }

            return state.hits.filter(
                hit => (
                    sourceType(hit)
                    === state.activeFilter
                ),
            );
        }

        function counts() {
            return {
                all:
                    state.hits.length,

                experimental:
                    state.hits.filter(
                        isExperimental
                    ).length,

                computational:
                    state.hits.filter(
                        isPredicted
                    ).length,
            };
        }

        function updateFilterButtons() {
            const values = counts();

            filterDefinitions.forEach(
                ([value, label]) => {
                    const button = (
                        filterButtons.get(
                            value
                        )
                    );

                    if (!button) {
                        return;
                    }

                    const active = (
                        state.activeFilter
                        === value
                    );

                    button.textContent = (
                        `${label} (${values[value]})`
                    );

                    button.classList.toggle(
                        "btn-primary",
                        active,
                    );

                    button.classList.toggle(
                        "btn-outline-secondary",
                        !active,
                    );

                    button.setAttribute(
                        "aria-pressed",
                        active
                            ? "true"
                            : "false",
                    );
                },
            );
        }

        function updateSummary(
            visibleCount,
        ) {
            const total = (
                Number.isFinite(
                    Number(
                        state.totalCount
                    )
                )
                    ? Number(
                        state.totalCount
                    )
                    : state.hits.length
            );

            summary.textContent = (
                `${visibleCount} result(s) shown`
                + ` · ${state.hits.length} loaded`
                + (
                    total !== state.hits.length
                        ? ` · ${total} total`
                        : ""
                )
                + (
                    state.queryLength
                        ? (
                            ` · query ${state.queryLength} aa`
                        )
                        : ""
                )
                + providerStatusText(
                    state.providers
                )
            );
        }

        function renderResults() {
            updateFilterButtons();

            const visible = (
                filteredHits()
            );

            results.replaceChildren();

            if (!visible.length) {
                renderEmpty(
                    state.hits.length
                        ? (
                            "No structures are available "
                            + "for this filter."
                        )
                        : (
                            "No structures were returned "
                            + "for this sequence."
                        ),
                );

                updateSummary(
                    0
                );

                return;
            }

            visible.forEach(hit => {
                results.appendChild(
                    renderHit(
                        hit
                    ),
                );
            });

            updateSummary(
                visible.length
            );
        }

        async function search() {
            searchButton.disabled = true;
            findButton.disabled = true;

            searchButton.textContent = (
                "Searching…"
            );

            summary.textContent = (
                "Searching experimental and "
                + "predicted structures…"
            );

            renderEmpty(
                "Searching structures…"
            );

            const params = (
                new URLSearchParams({
                    rows: "10",
                })
            );

            try {
                const response = await fetch(
                    (
                        `${searchUrl}?`
                        + params.toString()
                    ),
                    {
                        credentials:
                            "same-origin",

                        headers: {
                            "Accept":
                                "application/json",
                        },
                    },
                );

                const payload = (
                    await response.json()
                );

                if (!response.ok) {
                    throw new Error(
                        payload.message
                        || payload.error
                        || `HTTP ${response.status}`
                    );
                }

                const searchResult = (
                    payload.search
                    || {}
                );

                state.hits = (
                    Array.isArray(
                        searchResult.hits
                    )
                        ? searchResult.hits
                        : []
                );

                state.providers = (
                    Array.isArray(
                        searchResult.providers
                    )
                        ? searchResult.providers
                        : []
                );

                state.queryLength = (
                    searchResult.query_length
                    ?? null
                );

                state.totalCount = (
                    searchResult.total_count
                    ?? state.hits.length
                );

                renderResults();

            } catch (error) {
                console.error(
                    error
                );

                state.hits = [];
                state.providers = [];
                state.queryLength = null;
                state.totalCount = null;

                summary.textContent = (
                    "Structure search failed."
                );

                renderEmpty(
                    error.message
                    || "Could not search structures."
                );

                updateFilterButtons();

            } finally {
                searchButton.disabled = false;
                findButton.disabled = false;

                searchButton.textContent = (
                    "Search structures"
                );
            }
        }

        filterButtons.forEach(
            (button, value) => {
                button.addEventListener(
                    "click",
                    () => {
                        state.activeFilter = (
                            value
                        );

                        renderResults();
                    },
                );
            },
        );

        findButton.addEventListener(
            "click",
            () => {
                panel.hidden = false;

                panel.scrollIntoView({
                    block: "nearest",
                });
            },
        );

        close.addEventListener(
            "click",
            () => {
                panel.hidden = true;
            },
        );

        searchButton.addEventListener(
            "click",
            search,
        );
    });
})();
