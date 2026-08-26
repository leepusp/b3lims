(() => {
    "use strict";

    const VERSION = (
        "PROTEIN_PREDICTED_PREVIEW_V1_20260816"
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

            return;
        }

        callback();
    }

    function clean(value) {
        return String(
            value
            ?? ""
        ).trim();
    }

    function make(
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

    ready(() => {
        const root = document.querySelector(
            ".mw-page"
        );

        if (!root) {
            return;
        }

        if (
            clean(
                root.dataset.sequenceType
            ).toLowerCase()
            !== "protein"
        ) {
            return;
        }

        const previewUrl = clean(
            root.dataset.proteinStructurePreviewUrl
        );

        if (!previewUrl) {
            return;
        }

        let activeCard = null;

        function setSummary(
            message,
        ) {
            const summary = (
                document.getElementById(
                    "mps-pdb-summary"
                )
            );

            if (summary) {
                summary.textContent = (
                    message
                );
            }
        }

        function clearActivePredictedCard() {
            if (!activeCard) {
                return;
            }

            activeCard.classList.remove(
                "is-previewing"
            );

            const button = (
                activeCard.querySelector(
                    ".mps-computational-preview"
                )
            );

            if (button) {
                button.textContent = (
                    "Preview"
                );

                button.setAttribute(
                    "aria-pressed",
                    "false",
                );
            }

            activeCard = null;
        }

        function clearPdbPreviewVisualState() {
            document.querySelectorAll(
                ".mps-pdb-hit.is-previewing"
            ).forEach(card => {
                card.classList.remove(
                    "is-previewing"
                );

                const button = (
                    card.querySelector(
                        ".mps-pdb-preview"
                    )
                );

                if (button) {
                    button.textContent = (
                        "Preview"
                    );

                    button.setAttribute(
                        "aria-pressed",
                        "false",
                    );
                }
            });
        }

        function responseErrorMessage(
            response,
            payload,
        ) {
            return (
                clean(
                    payload?.message
                )
                || clean(
                    payload?.error
                )
                || `HTTP ${response.status}`
            );
        }

        async function preview(
            card,
            button,
        ) {
            const canonicalKey = clean(
                card.dataset.canonicalKey
            );

            const accession = clean(
                card.dataset.accession
            );

            const provider = clean(
                card.dataset.provider
            );

            const providerName = clean(
                card.querySelector(
                    ".text-body-secondary.small"
                )?.textContent
            );

            if (!canonicalKey) {
                throw new Error(
                    "Could not determine the "
                    + "predicted-model canonical key."
                );
            }

            const adapter = (
                window.BiobankProteinStructure
            );

            if (
                !adapter
                || typeof adapter
                    .loadComputationalPreviewData
                    !== "function"
            ) {
                throw new Error(
                    "The predicted-model Mol* "
                    + "Preview adapter is unavailable."
                );
            }

            const buttons = (
                document.querySelectorAll(
                    ".mps-computational-preview"
                )
            );

            buttons.forEach(
                candidate => {
                    candidate.disabled = true;
                },
            );

            button.textContent = (
                "Loading…"
            );

            setSummary(
                (
                    "Loading predicted model "
                    + (
                        accession
                        || canonicalKey
                    )
                    + "…"
                )
            );

            const params = (
                new URLSearchParams({
                    canonical_key:
                        canonicalKey,
                })
            );

            try {
                const response = await fetch(
                    (
                        `${previewUrl}?`
                        + params.toString()
                    ),
                    {
                        credentials:
                            "same-origin",

                        headers: {
                            "Accept":
                                "chemical/x-cif",
                        },
                    },
                );

                if (!response.ok) {
                    let payload = {};

                    try {
                        payload = (
                            await response.json()
                        );

                    } catch (error) {
                        payload = {};
                    }

                    throw new Error(
                        responseErrorMessage(
                            response,
                            payload,
                        )
                    );
                }

                const mmcif = (
                    await response.text()
                );

                await adapter
                    .loadComputationalPreviewData(
                        mmcif,
                        {
                            canonicalKey,
                            accession,
                            provider,
                            providerName,
                        },
                    );

                clearPdbPreviewVisualState();
                clearActivePredictedCard();

                activeCard = card;

                activeCard.classList.add(
                    "is-previewing"
                );

                button.textContent = (
                    "Previewing"
                );

                button.setAttribute(
                    "aria-pressed",
                    "true",
                );

                setSummary(
                    (
                        "Previewing predicted model "
                        + (
                            accession
                            || canonicalKey
                        )
                        + (
                            providerName
                                ? ` · ${providerName}`
                                : ""
                        )
                        + " · temporary · not saved"
                    )
                );

            } finally {
                buttons.forEach(
                    candidate => {
                        candidate.disabled = false;
                    },
                );
            }
        }

        function enhanceCard(
            card,
        ) {
            if (
                card.dataset
                    .biobankComputationalPreviewEnhanced
                === "1"
            ) {
                return;
            }

            const sourceType = clean(
                card.dataset.sourceType
            ).toLowerCase();

            if (
                sourceType
                !== "computational"
            ) {
                return;
            }

            const canonicalKey = clean(
                card.dataset.canonicalKey
            );

            if (!canonicalKey) {
                return;
            }

            card.dataset
                .biobankComputationalPreviewEnhanced = (
                    "1"
                );

            const oldNote = (
                card.querySelector(
                    ".mps-structure-preview-note"
                )
            );

            oldNote?.remove();

            const actions = make(
                "div",
                (
                    "mps-structure-preview-actions "
                    + "mt-2 d-flex align-items-center gap-2"
                ),
            );

            const button = make(
                "button",
                (
                    "btn btn-sm "
                    + "btn-outline-primary "
                    + "mps-computational-preview "
                    + "ms-auto"
                ),
                "Preview",
            );

            button.type = "button";

            button.setAttribute(
                "aria-pressed",
                "false",
            );

            button.addEventListener(
                "click",
                async () => {
                    const oldError = (
                        actions.querySelector(
                            ".mps-structure-preview-error"
                        )
                    );

                    oldError?.remove();

                    try {
                        await preview(
                            card,
                            button,
                        );

                    } catch (error) {
                        console.error(
                            error
                        );

                        button.textContent = (
                            "Preview"
                        );

                        button.setAttribute(
                            "aria-pressed",
                            "false",
                        );

                        setSummary(
                            (
                                error.message
                                || (
                                    "Predicted-model "
                                    + "Preview failed."
                                )
                            )
                        );

                        const errorNode = make(
                            "span",
                            (
                                "mps-structure-preview-error "
                                + "text-danger small"
                            ),
                            (
                                error.message
                                || "Preview failed."
                            ),
                        );

                        actions.insertBefore(
                            errorNode,
                            button,
                        );
                    }
                },
            );

            actions.appendChild(
                button
            );

            card.appendChild(
                actions
            );
        }

        function enhanceResults() {
            document.querySelectorAll(
                ".mps-predicted-hit"
            ).forEach(
                enhanceCard
            );
        }

        enhanceResults();

        const observer = (
            new MutationObserver(
                enhanceResults
            )
        );

        observer.observe(
            root,
            {
                childList: true,
                subtree: true,
            },
        );

        window.BiobankProteinPredictedPreview = {
            version:
                VERSION,

            enhance:
                enhanceResults,

            getActiveCanonicalKey:
                () => (
                    activeCard
                        ?.dataset
                        ?.canonicalKey
                    || null
                ),
        };
    });
})();
