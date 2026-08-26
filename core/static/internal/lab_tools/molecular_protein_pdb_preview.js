(() => {
    "use strict";

    const VERSION = (
        "PROTEIN_PDB_PREVIEW_V1_20260815"
    );

    /*
     * PROTEIN_PDB_PREVIEW_MAPPING_V2_20260815
     *
     * Preview now forwards the RCSB polymer entity identifier
     * to the residue-mapping layer.
     */


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

        if (text) {
            node.textContent = text;
        }

        return node;
    }

    function pdbIdFromCard(
        card,
    ) {
        const heading = card.querySelector(
            ".mps-pdb-hit-id"
        );

        const match = String(
            heading?.textContent
            || ""
        ).trim().match(
            /^([A-Za-z0-9]{4})\b/
        );

        return (
            match
                ? match[1].toUpperCase()
                : ""
        );
    }

    function entityIdFromCard(
        card,
    ) {
        const heading = card.querySelector(
            ".mps-pdb-hit-id"
        );

        const headingText = String(
            heading?.textContent
            || ""
        );

        const match = headingText.match(
            /\bentity\s+([A-Za-z0-9._-]+)/i
        );

        return (
            match
                ? match[1]
                : ""
        );
    }

    ready(() => {
        const root = document.querySelector(
            ".mw-page"
        );

        if (!root) {
            return;
        }

        if (
            String(
                root.dataset.sequenceType
                || ""
            ).toLowerCase()
            !== "protein"
        ) {
            return;
        }

        const previewUrl = String(
            root.dataset.proteinPdbPreviewUrl
            || ""
        );

        if (!previewUrl) {
            return;
        }

        let activeCard = null;

        function setSummary(
            message,
        ) {
            const summary = document.getElementById(
                "mps-pdb-summary"
            );

            if (summary) {
                summary.textContent = message;
            }
        }

        function clearActiveCard() {
            if (!activeCard) {
                return;
            }

            activeCard.classList.remove(
                "is-previewing"
            );

            const button = activeCard.querySelector(
                ".mps-pdb-preview"
            );

            if (button) {
                button.textContent = "Preview";

                button.setAttribute(
                    "aria-pressed",
                    "false",
                );
            }

            activeCard = null;
        }

        async function preview(
            card,
            button,
        ) {
            const pdbId = pdbIdFromCard(
                card
            );

            const entityId = entityIdFromCard(
                card
            );

            if (!pdbId) {
                throw new Error(
                    "Could not determine the PDB identifier."
                );
            }

            const adapter = (
                window.BiobankProteinStructure
            );

            if (
                !adapter
                || typeof adapter.loadPreviewData
                    !== "function"
            ) {
                throw new Error(
                    "The Mol* Preview adapter is unavailable."
                );
            }

            const buttons = document.querySelectorAll(
                ".mps-pdb-preview"
            );

            buttons.forEach(candidate => {
                candidate.disabled = true;
            });

            button.textContent = "Loading…";

            setSummary(
                `Loading PDB ${pdbId} preview…`
            );

            try {
                const params = new URLSearchParams({
                    pdb_id: pdbId,
                });

                const response = await fetch(
                    `${previewUrl}?${params.toString()}`,
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
                    let message = (
                        `HTTP ${response.status}`
                    );

                    try {
                        const payload = (
                            await response.json()
                        );

                        message = (
                            payload.message
                            || payload.error
                            || message
                        );

                    } catch (_error) {
                        // Keep HTTP fallback.
                    }

                    throw new Error(
                        message
                    );
                }

                const mmcif = await response.text();

                await adapter.loadPreviewData(
                    mmcif,
                    {
                        pdbId,
                        entityId,
                    },
                );

                clearActiveCard();

                activeCard = card;

                activeCard.classList.add(
                    "is-previewing"
                );

                button.textContent = "Previewing";

                button.setAttribute(
                    "aria-pressed",
                    "true",
                );

                setSummary(
                    (
                        `Previewing PDB ${pdbId} · `
                        + "temporary · not saved"
                    )
                );

            } finally {
                buttons.forEach(candidate => {
                    candidate.disabled = false;
                });
            }
        }

        function enhanceCard(
            card,
        ) {
            if (
                card.dataset.biobankPdbPreviewEnhanced
                === "1"
            ) {
                return;
            }

            const pdbId = pdbIdFromCard(
                card
            );

            if (!pdbId) {
                return;
            }

            card.dataset.biobankPdbPreviewEnhanced = (
                "1"
            );

            card.dataset.pdbId = pdbId;

            card.dataset.entityId = (
                entityIdFromCard(
                    card
                )
            );

            const actions = make(
                "div",
                "mps-pdb-preview-actions",
            );

            const button = make(
                "button",
                (
                    "btn btn-sm "
                    + "btn-outline-primary "
                    + "mps-pdb-preview"
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
                    const oldError = actions.querySelector(
                        ".mps-pdb-preview-error"
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

                        setSummary(
                            (
                                error.message
                                || "PDB preview failed."
                            )
                        );

                        actions.appendChild(
                            make(
                                "span",
                                "mps-pdb-preview-error",
                                (
                                    error.message
                                    || "Preview failed."
                                ),
                            )
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
                ".mps-pdb-hit"
            ).forEach(
                enhanceCard
            );
        }

        enhanceResults();

        const observer = new MutationObserver(
            enhanceResults
        );

        observer.observe(
            root,
            {
                childList: true,
                subtree: true,
            },
        );

        window.BiobankProteinPdbPreview = {
            version: VERSION,
            enhance: enhanceResults,

            getActivePdbId: () => (
                activeCard?.dataset?.pdbId
                || null
            ),

            getActiveEntityId: () => (
                activeCard?.dataset?.entityId
                || null
            ),
        };
    });
})();
