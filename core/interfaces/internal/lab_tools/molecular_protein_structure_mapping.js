(() => {
    "use strict";

    const VERSION = (
        "PROTEIN_STRUCTURE_MAPPING_V1_20260815"
    );

    const PREVIEW_EVENT = (
        "biobank:protein-structure-preview-loaded"
    );

    const STORED_STRUCTURE_EVENT = (
        "biobank:protein-structure-loaded"
    );

    const state = {
        mode: "none",
        pdbId: "",
        entityId: "",
        candidates: [],
        activeCandidateId: "",
        error: "",
    };

    let root = null;
    let controls = null;
    let selector = null;
    let summary = null;

    const MAPPING_CHANGE_EVENT = (
        "biobank:protein-structure-mapping-change"
    );

    function coveredRegistryPositions() {
        const candidate = currentCandidate();

        if (
            !candidate
            || !Array.isArray(
                candidate.resolved_registry_positions
            )
        ) {
            return [];
        }

        return [
            ...new Set(
                candidate
                    .resolved_registry_positions
                    .map(
                        value => Number(
                            value
                        )
                    )
                    .filter(
                        value => (
                            Number.isInteger(
                                value
                            )
                            && value > 0
                        )
                    )
            ),
        ].sort(
            (
                left,
                right,
            ) => (
                left - right
            )
        );
    }

    function updateCoverageSummary() {
        const summary = (
            document.getElementById(
                "mw-structure-coverage-summary"
            )
        );

        if (!summary) {
            return;
        }

        const covered = (
            coveredRegistryPositions()
        );

        const sequence = String(
            window.BiobankMolecularWorkspace
                ?.getSnapshot?.()
                ?.sequence
            || ""
        );

        const length = sequence.length;

        if (
            !covered.length
            || !length
        ) {
            summary.hidden = true;
            summary.textContent = "";
            return;
        }

        const count = covered.length;

        const percent = (
            (
                count
                / length
            )
            * 100
        );

        summary.textContent = (
            `Resolved in active structure: ${count} / ${length} aa `
            + `(${percent.toFixed(1)}%)`
        );

        summary.hidden = false;
    }

    function notifyMappingChange() {
        updateCoverageSummary();

        if (!root) {
            return;
        }

        root.dispatchEvent(
            new CustomEvent(
                MAPPING_CHANGE_EVENT,
                {
                    detail: {
                        coveredRegistryPositions:
                            coveredRegistryPositions(),
                    },
                },
            )
        );
    }

    function integer(
        value,
    ) {
        const number = Number(
            value
        );

        if (
            !Number.isFinite(number)
            || !Number.isInteger(number)
        ) {
            return null;
        }

        return number;
    }

    function normalizedRange(
        selection,
    ) {
        const start = integer(
            selection?.start
        );

        const end = integer(
            selection?.end
        );

        if (
            start === null
            || end === null
            || start < 1
            || end < 1
        ) {
            return null;
        }

        return {
            start: Math.min(
                start,
                end,
            ),

            end: Math.max(
                start,
                end,
            ),
        };
    }

    function setSyncStatus(
        message,
        kind = "",
    ) {
        const status = document.getElementById(
            "mps-sync-status"
        );

        if (!status) {
            return;
        }

        status.textContent = message;

        if (kind) {
            status.dataset.kind = kind;
        } else {
            delete status.dataset.kind;
        }
    }

    function currentCandidate() {
        if (
            state.mode !== "ready"
        ) {
            return null;
        }

        return (
            state.candidates.find(
                candidate => (
                    candidate.candidate_id
                    === state.activeCandidateId
                )
            )
            || state.candidates[0]
            || null
        );
    }

    function candidateLabel(
        candidate,
    ) {
        const labelChain = String(
            candidate?.label_asym_id
            || "—"
        );

        const authorChain = String(
            candidate?.auth_asym_id
            || "—"
        );

        const resolved = Number(
            candidate?.resolved_mapped_positions
            || 0
        );

        const total = Number(
            candidate?.registry_length
            || 0
        );

        return (
            `${labelChain} `
            + `(author ${authorChain}) `
            + `· ${resolved}/${total} resolved`
        );
    }

    function percentage(
        value,
    ) {
        const number = Number(
            value
        );

        if (!Number.isFinite(number)) {
            return "—";
        }

        return (
            `${(number * 100).toFixed(1)}%`
        );
    }

    function mappingReadyMessage(
        candidate,
    ) {
        if (!candidate) {
            return (
                "No compatible mapped chain is available."
            );
        }

        return (
            `PDB ${state.pdbId} mapped`
            + ` · chain ${candidate.label_asym_id}`
            + ` (author ${candidate.auth_asym_id})`
            + ` · ${candidate.resolved_mapped_positions}`
            + `/${candidate.registry_length} residues resolved`
        );
    }

    function ensureControls() {
        if (controls) {
            return true;
        }

        const syncStatus = document.getElementById(
            "mps-sync-status"
        );

        if (!syncStatus) {
            return false;
        }

        controls = document.createElement(
            "div"
        );

        controls.id = (
            "mps-structure-mapping-controls"
        );

        controls.className = (
            "mps-structure-mapping-controls"
        );

        controls.hidden = true;

        const chainField = document.createElement(
            "label"
        );

        chainField.className = (
            "mps-structure-mapping-chain"
        );

        const chainLabel = document.createElement(
            "span"
        );

        chainLabel.textContent = (
            "Mapped chain"
        );

        selector = document.createElement(
            "select"
        );

        selector.id = (
            "mps-structure-mapping-chain"
        );

        selector.className = (
            "form-select form-select-sm"
        );

        chainField.append(
            chainLabel,
            selector,
        );

        summary = document.createElement(
            "span"
        );

        summary.id = (
            "mps-structure-mapping-summary"
        );

        summary.className = (
            "mps-structure-mapping-summary"
        );

        controls.append(
            chainField,
            summary,
        );

        syncStatus.insertAdjacentElement(
            "afterend",
            controls,
        );

        selector.addEventListener(
            "change",
            () => {
                state.activeCandidateId = (
                    selector.value
                );

                render();

                const candidate = currentCandidate();

                setSyncStatus(
                    mappingReadyMessage(
                        candidate
                    ),
                    "success",
                );

                resynchronize({
                    focus: true,
                });
            },
        );

        return true;
    }

    function render() {
        if (!ensureControls()) {
            return;
        }

        if (
            state.mode === "none"
        ) {
            controls.hidden = true;
            selector.replaceChildren();
            summary.textContent = "";
            return;
        }

        controls.hidden = false;

        if (
            state.mode === "loading"
        ) {
            selector.disabled = true;
            selector.replaceChildren();

            const option = document.createElement(
                "option"
            );

            option.textContent = (
                "Loading residue mapping…"
            );

            selector.appendChild(
                option
            );

            summary.textContent = (
                state.pdbId
                    ? `PDB ${state.pdbId}`
                    : ""
            );

            return;
        }

        if (
            state.mode === "error"
        ) {
            selector.disabled = true;
            selector.replaceChildren();

            const option = document.createElement(
                "option"
            );

            option.textContent = (
                "Mapping unavailable"
            );

            selector.appendChild(
                option
            );

            summary.textContent = (
                state.error
                || "Could not build residue mapping."
            );

            return;
        }

        selector.disabled = false;
        selector.replaceChildren();

        state.candidates.forEach(
            candidate => {
                const option = (
                    document.createElement(
                        "option"
                    )
                );

                option.value = (
                    candidate.candidate_id
                );

                option.textContent = (
                    candidateLabel(
                        candidate
                    )
                );

                option.selected = (
                    candidate.candidate_id
                    === state.activeCandidateId
                );

                selector.appendChild(
                    option
                );
            },
        );

        const candidate = currentCandidate();

        if (!candidate) {
            summary.textContent = (
                "No compatible mapped chain."
            );

            return;
        }

        summary.textContent = (
            `${percentage(candidate.identity)} identity`
            + ` · ${percentage(candidate.alignment_coverage)} alignment coverage`
            + ` · ${percentage(candidate.resolved_coverage)} resolved coordinates`
        );
    }

    function selectedEntries(
        candidate,
        selection,
    ) {
        const range = normalizedRange(
            selection
        );

        if (
            !candidate
            || !range
        ) {
            return [];
        }

        const mapping = (
            Array.isArray(
                candidate.mapping
            )
                ? candidate.mapping
                : []
        );

        return mapping.filter(
            entry => {
                const position = integer(
                    entry.registry_position
                );

                return (
                    entry.resolved === true
                    && position !== null
                    && position >= range.start
                    && position <= range.end
                );
            },
        );
    }

    function groupedElements(
        entries,
    ) {
        const ordered = [
            ...entries,
        ].sort(
            (
                left,
                right,
            ) => {
                const chainOrder = String(
                    left.label_asym_id
                    || ""
                ).localeCompare(
                    String(
                        right.label_asym_id
                        || ""
                    )
                );

                if (chainOrder) {
                    return chainOrder;
                }

                return (
                    Number(
                        left.label_seq_id
                    )
                    - Number(
                        right.label_seq_id
                    )
                );
            },
        );

        const groups = [];

        for (const entry of ordered) {
            const labelAsymId = String(
                entry.label_asym_id
                || ""
            );

            const labelSeqId = integer(
                entry.label_seq_id
            );

            if (
                !labelAsymId
                || labelSeqId === null
            ) {
                continue;
            }

            const previous = (
                groups[
                    groups.length - 1
                ]
            );

            if (
                previous
                && previous.label_asym_id
                    === labelAsymId
                && previous.end_label_seq_id + 1
                    === labelSeqId
            ) {
                previous.end_label_seq_id = (
                    labelSeqId
                );

                continue;
            }

            groups.push({
                label_asym_id:
                    labelAsymId,

                beg_label_seq_id:
                    labelSeqId,

                end_label_seq_id:
                    labelSeqId,
            });
        }

        return groups;
    }

    /*
     * PROTEIN_STRUCTURE_MAPPING_EXACT_SCHEMA_V2_20260815
     *
     * Runtime validation against PDB 6B3Q proved that Mol*
     * correctly selects mapped residues when they are sent
     * as one StructureElement.Schema containing exact
     * label_asym_id + label_seq_id items.
     */
    function exactSelectionSchema(
        entries,
    ) {
        const items = [];

        for (const entry of entries) {
            const labelAsymId = String(
                entry.label_asym_id
                || ""
            );

            const labelSeqId = integer(
                entry.label_seq_id
            );

            if (
                !labelAsymId
                || labelSeqId === null
            ) {
                continue;
            }

            items.push({
                label_asym_id:
                    labelAsymId,

                label_seq_id:
                    labelSeqId,
            });
        }

        return {
            items,
        };
    }

    function mapSelection(
        selection,
    ) {
        if (
            state.mode === "none"
        ) {
            return {
                handled: false,
            };
        }

        const range = normalizedRange(
            selection
        );

        if (!range) {
            return {
                handled: true,
                ready: false,
                elements: [],
                kind: "",
                message:
                    "Select residues in the sequence.",
            };
        }

        if (
            state.mode === "loading"
        ) {
            return {
                handled: true,
                ready: false,
                elements: [],
                kind: "",
                message:
                    "Loading PDB residue mapping…",
            };
        }

        if (
            state.mode === "error"
        ) {
            return {
                handled: true,
                ready: false,
                elements: [],
                kind: "error",
                message:
                    state.error
                    || "PDB residue mapping is unavailable.",
            };
        }

        const candidate = currentCandidate();

        if (!candidate) {
            return {
                handled: true,
                ready: false,
                elements: [],
                kind: "error",
                message:
                    "No mapped structural chain is available.",
            };
        }

        const entries = selectedEntries(
            candidate,
            range,
        );

        const selectedCount = (
            range.end
            - range.start
            + 1
        );

        const resolvedCount = (
            entries.length
        );

        if (!resolvedCount) {
            return {
                handled: true,
                ready: true,
                elements: [],
                resolvedCount: 0,
                totalCount: selectedCount,
                kind: "warning",

                message: (
                    `Selected residues ${range.start}..${range.end} `
                    + `are mapped to PDB ${state.pdbId}, `
                    + "but this structure has no resolved "
                    + "coordinates for this region."
                ),
            };
        }

        const labelChain = (
            candidate.label_asym_id
            || "?"
        );

        const authorChain = (
            candidate.auth_asym_id
            || "?"
        );

        return {
            handled: true,
            ready: true,

            /*
             * Keep grouped elements for diagnostics.
             * Mol* receives the exact residue Schema below.
             */
            elements:
                groupedElements(
                    entries
                ),

            schema:
                exactSelectionSchema(
                    entries
                ),

            resolvedCount,
            totalCount:
                selectedCount,

            kind:
                resolvedCount === selectedCount
                    ? "success"
                    : "warning",

            message: (
                `3D selection: ${range.start}..${range.end}`
                + ` · ${resolvedCount}/${selectedCount} residues resolved`
                + ` · chain ${labelChain}`
                + ` (author ${authorChain})`
            ),
        };
    }

    function residueValue(
        residue,
        names,
    ) {
        for (const name of names) {
            const value = residue?.[
                name
            ];

            if (
                value !== undefined
                && value !== null
                && value !== ""
            ) {
                return value;
            }
        }

        return null;
    }

    function registryPositionForResidue(
        residue,
    ) {
        if (
            state.mode !== "ready"
        ) {
            return null;
        }

        const candidate = currentCandidate();

        if (!candidate) {
            return null;
        }

        const labelAsymId = String(
            residueValue(
                residue,
                [
                    "labelAsymId",
                    "label_asym_id",
                ],
            )
            || ""
        );

        const labelSeqId = integer(
            residueValue(
                residue,
                [
                    "labelSeqId",
                    "label_seq_id",
                ],
            )
        );

        const authAsymId = String(
            residueValue(
                residue,
                [
                    "authAsymId",
                    "auth_asym_id",
                    "chain",
                ],
            )
            || ""
        );

        const authSeqId = integer(
            residueValue(
                residue,
                [
                    "authSeqId",
                    "auth_seq_id",
                    "coordinate",
                ],
            )
        );

        const mapping = (
            Array.isArray(
                candidate.mapping
            )
                ? candidate.mapping
                : []
        ).filter(
            entry => (
                entry.resolved === true
            )
        );

        if (
            labelAsymId
            && labelSeqId !== null
        ) {
            const match = mapping.find(
                entry => (
                    String(
                        entry.label_asym_id
                        || ""
                    ) === labelAsymId
                    && integer(
                        entry.label_seq_id
                    ) === labelSeqId
                )
            );

            if (match) {
                return integer(
                    match.registry_position
                );
            }
        }

        if (
            authAsymId
            && authSeqId !== null
        ) {
            const match = mapping.find(
                entry => (
                    String(
                        entry.auth_asym_id
                        || ""
                    ) === authAsymId
                    && integer(
                        entry.auth_seq_id
                    ) === authSeqId
                )
            );

            if (match) {
                return integer(
                    match.registry_position
                );
            }
        }

        return null;
    }

    function unmappedResidueMessage() {
        const candidate = currentCandidate();

        if (!candidate) {
            return (
                "The clicked structural residue is not "
                + "mapped to the Molecular Registry sequence."
            );
        }

        return (
            "The clicked structural residue is not part of "
            + `the active mapped chain ${candidate.label_asym_id} `
            + `(author ${candidate.auth_asym_id}).`
        );
    }

    /*
     * MAPPED_CHAIN_EXPLICIT_REFOCUS_V2_20260817
     *
     * Normal mapping hydration only rebuilds the Mol* selection.
     * An explicit mapped-chain change may additionally refocus the
     * camera on the coordinates resolved by the newly active
     * candidate, while preserving the Registry sequence selection.
     */
    function resynchronize(
        {
            focus = false,
        } = {},
    ) {
        notifyMappingChange();

        const sync = (
            window.BiobankProteinStructureSync
        );

        const selection = (
            sync?.getSelection?.()
        );

        if (!selection) {
            return;
        }

        if (
            focus
            && typeof sync?.focusRange
                === "function"
        ) {
            sync.focusRange(
                selection.start,
                selection.end,
            );

            return;
        }

        if (
            typeof sync?.selectRange
                !== "function"
        ) {
            return;
        }

        sync.selectRange(
            selection.start,
            selection.end,
        );
    }

    async function loadPreviewMapping(
        preview,
    ) {
        const mappingUrl = String(
            root.dataset.proteinPdbMappingUrl
            || ""
        );

        const pdbId = String(
            preview?.pdbId
            || preview?.pdb_id
            || ""
        );

        const entityId = String(
            preview?.entityId
            || preview?.entity_id
            || ""
        );

        state.mode = "loading";
        state.pdbId = pdbId;
        state.entityId = entityId;
        state.candidates = [];
        state.activeCandidateId = "";
        state.error = "";

        render();

        setSyncStatus(
            (
                pdbId
                    ? `Loading PDB ${pdbId} residue mapping…`
                    : "Loading PDB residue mapping…"
            )
        );

        if (
            !mappingUrl
            || !pdbId
        ) {
            state.mode = "error";

            state.error = (
                "The PDB residue-mapping endpoint "
                + "or PDB identifier is unavailable."
            );

            render();

            setSyncStatus(
                state.error,
                "error",
            );

            resynchronize();

            return;
        }

        const params = new URLSearchParams({
            pdb_id:
                pdbId,
        });

        if (entityId) {
            params.set(
                "entity_id",
                entityId,
            );
        }

        try {
            const response = await fetch(
                (
                    `${mappingUrl}?`
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

            const candidates = (
                payload.mapping?.candidates
            );

            if (
                !Array.isArray(
                    candidates
                )
                || !candidates.length
            ) {
                throw new Error(
                    "No compatible structural chain "
                    + "was found for this Protein sequence."
                );
            }

            state.candidates = candidates;

            state.activeCandidateId = (
                candidates[
                    0
                ].candidate_id
            );

            state.mode = "ready";
            state.error = "";

            render();

            const candidate = currentCandidate();

            setSyncStatus(
                mappingReadyMessage(
                    candidate
                ),
                "success",
            );

            resynchronize();

        } catch (error) {
            console.error(
                error
            );

            state.mode = "error";

            state.error = (
                error.message
                || "Could not load PDB residue mapping."
            );

            render();

            setSyncStatus(
                state.error,
                "error",
            );

            resynchronize();
        }
    }

    function clearMapping() {
        state.mode = "none";
        state.pdbId = "";
        state.entityId = "";
        state.candidates = [];
        state.activeCandidateId = "";
        state.error = "";

        render();
        notifyMappingChange();
    }

    function initialize() {
        root = document.querySelector(
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

        root.addEventListener(
            PREVIEW_EVENT,
            event => {
                loadPreviewMapping(
                    event.detail?.preview
                    || {}
                );
            },
        );

        /*
         * UNIVERSAL STRUCTURE MAPPING V1 20260817
         *
         * Experimental PDB Preview continues through PREVIEW_EVENT.
         *
         * Computational and stored structures are passed through
         * the same authoritative residue-mapping backend instead of
         * using Registry position == auth_seq_id.
         */
        root.addEventListener(
            "biobank:protein-computational-structure-preview-loaded",
            event => {
                const preview = (
                    event.detail?.preview
                    || {}
                );

                const canonicalKey = String(
                    preview.canonicalKey
                    || preview.canonical_key
                    || ""
                ).trim();

                if (!canonicalKey) {
                    clearMapping();
                    return;
                }

                clearMapping();

                loadPreviewMapping({
                    ...preview,

                    pdbId:
                        "computational:"
                        + canonicalKey,
                });
            },
        );

        root.addEventListener(
            STORED_STRUCTURE_EVENT,
            event => {
                const structure = (
                    event.detail?.structure
                    || {}
                );

                const structureId = Number(
                    structure.id
                );

                if (
                    !Number.isInteger(
                        structureId
                    )
                    || structureId < 1
                ) {
                    clearMapping();
                    return;
                }

                clearMapping();

                loadPreviewMapping({
                    pdbId:
                        "stored:"
                        + String(
                            structureId
                        ),

                    structureId,

                    sourceFormat:
                        structure.source_format
                        || "",

                    label:
                        structure.label
                        || structure.original_filename
                        || `Structure ${structureId}`,
                });
            },
        );

        window.BiobankProteinStructureMapping = {
            version:
                VERSION,

            isActive: () => (
                state.mode !== "none"
            ),

            isReady: () => (
                state.mode === "ready"
            ),

            mapSelection,

            registryPositionForResidue,

            unmappedResidueMessage,

            getCoveredRegistryPositions: () => (
                coveredRegistryPositions()
            ),

            getCoverage: () => {
                const positions = (
                    coveredRegistryPositions()
                );

                const sequence = String(
                    window.BiobankMolecularWorkspace
                        ?.getSnapshot?.()
                        ?.sequence
                    || ""
                );

                return {
                    covered:
                        positions.length,

                    registryLength:
                        sequence.length,

                    positions: [
                        ...positions,
                    ],
                };
            },

            getCandidates: () => (
                state.candidates.map(
                    candidate => ({
                        ...candidate,
                    })
                )
            ),

            getActiveCandidate: () => {
                const candidate = (
                    currentCandidate()
                );

                return (
                    candidate
                        ? {
                            ...candidate,
                        }
                        : null
                );
            },

            setCandidate:
                candidateId => {
                    const exists = (
                        state.candidates.some(
                            candidate => (
                                candidate.candidate_id
                                === candidateId
                            )
                        )
                    );

                    if (!exists) {
                        return false;
                    }

                    state.activeCandidateId = (
                        candidateId
                    );

                    render();

                    setSyncStatus(
                        mappingReadyMessage(
                            currentCandidate()
                        ),
                        "success",
                    );

                    resynchronize({
                        focus: true,
                    });

                    return true;
                },

            clear:
                clearMapping,

            getState: () => ({
                mode:
                    state.mode,

                pdbId:
                    state.pdbId,

                entityId:
                    state.entityId,

                activeCandidateId:
                    state.activeCandidateId,
            }),
        };

        ensureControls();
        render();
    }

    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initialize,
            {
                once: true,
            },
        );

    } else {
        initialize();
    }
})();
