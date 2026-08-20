(() => {
    "use strict";

    const VERSION = (
        "PROTEIN_STRUCTURE_SYNC_V1_20260815"
    );

    /*
     * PROTEIN_STRUCTURE_SYNC_MAPPING_V2_20260815
     *
     * PDB Preview synchronization uses an explicit
     * Registry <-> structural residue map.
     */


    const WORKSPACE_EVENT = (
        "biobank:molecular-workspace-change"
    );

    const STRUCTURE_EVENT = (
        "biobank:protein-structure-loaded"
    );

    const PREVIEW_EVENT = (
        "biobank:protein-structure-preview-loaded"
    );

    const boundViewers = new WeakSet();

    let latestSelection = null;
    let latestSelectedFeature = -1;

    let activeViewer = null;
    let activeStructure = null;

    /*
     * Preview mode is tracked independently from the mapping
     * adapter so that a missing/failed mapping script can never
     * fall back silently to Registry position == auth_seq_id.
     */
    let previewMode = false;

    let syncStatus = null;
    let focusButton = null;

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

    function wait(milliseconds) {
        return new Promise(resolve => {
            window.setTimeout(
                resolve,
                milliseconds,
            );
        });
    }

    function finiteInteger(value) {
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

    function normalizedSelection(
        selection,
    ) {
        if (!selection) {
            return null;
        }

        const start = finiteInteger(
            selection.start
        );

        const end = finiteInteger(
            selection.end
        );

        if (
            start === null
            || end === null
            || start < 1
            || end < 1
        ) {
            return null;
        }

        /*
         * Protein records are linear.
         *
         * Store the normalized range independently from the
         * direction in which the user dragged the sequence.
         */
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

    function setStatus(
        message,
        kind = "",
    ) {
        if (!syncStatus) {
            return;
        }

        syncStatus.textContent = message;

        if (kind) {
            syncStatus.dataset.kind = kind;
        } else {
            delete syncStatus.dataset.kind;
        }
    }

    function molstarLibraries() {
        const lib = (
            window.molstar?.lib
        );

        const StructureElement = (
            lib?.structure?.StructureElement
        );

        const StructureProperties = (
            lib?.structure?.StructureProperties
        );

        if (
            !StructureElement
            || !StructureProperties
        ) {
            return null;
        }

        return {
            StructureElement,
            StructureProperties,
        };
    }

    function currentViewer() {
        return (
            activeViewer
            || window.BiobankProteinStructure
                ?.getViewer?.()
            || null
        );
    }

    function clearMolstarSelection() {
        const viewer = currentViewer();

        if (
            !viewer
            || typeof viewer.structureInteractivity
                !== "function"
        ) {
            return false;
        }

        viewer.structureInteractivity({
            action: "select",
        });

        return true;
    }

    function structuralElementsForSelection(
        selection,
    ) {
        const normalized = (
            normalizedSelection(
                selection
            )
        );

        if (!normalized) {
            return null;
        }

        /*
         * Initial mapping contract:
         *
         * Molecular Registry residue coordinate
         *        =
         * structure auth_seq_id
         *
         * This is exact for the Protein 99 QA structure.
         *
         * Explicit chain/offset mappings for arbitrary
         * experimental structures will be layered on top
         * of this adapter later without changing the
         * workspace coordinate model.
         */
        return {
            beg_auth_seq_id:
                normalized.start,

            end_auth_seq_id:
                normalized.end,
        };
    }

    function selectMolstarRange(
        selection,
        {
            focus = false,
        } = {},
    ) {
        const viewer = currentViewer();

        if (
            !viewer
            || typeof viewer.structureInteractivity
                !== "function"
        ) {
            setStatus(
                "3D synchronization is waiting "
                + "for a loaded structure.",
            );

            return false;
        }

        const normalized = (
            normalizedSelection(
                selection
            )
        );

        if (!normalized) {
            clearMolstarSelection();

            setStatus(
                "3D synchronization ready. "
                + "Select residues in the sequence.",
            );

            if (focusButton) {
                focusButton.disabled = true;
            }

            return true;
        }

        const mappingAdapter = (
            window.BiobankProteinStructureMapping
        );

        const mappingActive = (
            mappingAdapter
            && typeof mappingAdapter.isActive
                === "function"
            && mappingAdapter.isActive()
        );

        if (
            previewMode
            && !mappingActive
        ) {
            clearMolstarSelection();

            if (focusButton) {
                focusButton.disabled = true;
            }

            setStatus(
                "Structure residue mapping is not available. "
                + "Sequence-to-structure synchronization is disabled "
                + "for this preview.",
                "warning",
            );

            return true;
        }

        const mapped = (
            mappingActive
            && typeof mappingAdapter.mapSelection
                === "function"
        )
            ? mappingAdapter.mapSelection(
                normalized
            )
            : null;

        if (
            mapped
            && mapped.handled
        ) {
            /*
             * PROTEIN_STRUCTURE_SYNC_ATOMIC_SCHEMA_V3_20260815
             *
             * Never use the legacy auth_seq_id fallback
             * while a real PDB Preview mapping is active.
             *
             * Mol* clears the previous selection whenever a new
             * action:"select" operation starts. Therefore all
             * mapped residues must be submitted in ONE
             * StructureElement.Schema.
             *
             * Runtime-proven contract:
             *
             *   PDB 6B3Q
             *   Registry 90..110
             *   label_asym_id C
             *   label_seq_id 90..110
             *   21 Residues Selected
             */
            const schemaItems = (
                mapped.schema?.items
            );

            if (
                !mapped.ready
                || !Array.isArray(
                    schemaItems
                )
                || !schemaItems.length
            ) {
                viewer.structureInteractivity({
                    action:
                        "select",
                });

                if (focusButton) {
                    focusButton.disabled = true;
                }

                setStatus(
                    mapped.message
                    || (
                        "No resolved structural residues "
                        + "match this sequence selection."
                    ),
                    mapped.kind
                    || "",
                );

                return true;
            }

            const options = {
                elements:
                    mapped.schema,

                action: (
                    focus
                        ? [
                            "select",
                            "focus",
                        ]
                        : "select"
                ),
            };

            if (focus) {
                options.focusOptions = {
                    extraRadius:
                        3,
                };
            }

            /*
             * One atomic selection.
             *
             * The C/a <-> D/b mapped-chain selector changes
             * the active candidate, rebuilds this exact Schema,
             * and resynchronizes the Registry selection.
             */
            viewer.structureInteractivity(
                options
            );

            if (focusButton) {
                focusButton.disabled = false;
            }

            const featureSuffix = (
                Number.isInteger(
                    latestSelectedFeature
                )
                && latestSelectedFeature >= 0
            )
                ? " · annotation selected"
                : "";

            setStatus(
                (
                    mapped.message
                    + featureSuffix
                ),
                mapped.kind
                || "success",
            );

            return true;
        }

        /*
         * Legacy direct-coordinate fallback.
         *
         * This remains available for existing stored structures
         * such as the Protein 99 QA structure. It is never used
         * while PDB Preview mode is active.
         */
        const elements = (
            structuralElementsForSelection(
                normalized
            )
        );

        viewer.structureInteractivity({
            action: "select",
        });

        viewer.structureInteractivity({
            elements,
            action: "select",
        });

        if (focus) {
            viewer.structureInteractivity({
                elements,
                action: "focus",
                focusOptions: {
                    extraRadius: 3,
                },
            });
        }

        if (focusButton) {
            focusButton.disabled = false;
        }

        const featureSuffix = (
            Number.isInteger(
                latestSelectedFeature
            )
            && latestSelectedFeature >= 0
        )
            ? " · annotation selected"
            : "";

        setStatus(
            (
                `3D selection: `
                + `${normalized.start}..${normalized.end}`
                + featureSuffix
            ),
            "success",
        );

        return true;
    }

    function focusCurrentSelection() {
        const normalized = (
            normalizedSelection(
                latestSelection
            )
        );

        if (!normalized) {
            setStatus(
                "Select a residue or annotation first.",
                "error",
            );

            return;
        }

        selectMolstarRange(
            normalized,
            {
                focus: true,
            },
        );
    }

    function firstResidueFromLoci(
        loci,
    ) {
        const libraries = (
            molstarLibraries()
        );

        if (!libraries) {
            return null;
        }

        const {
            StructureElement,
            StructureProperties,
        } = libraries;

        if (
            !StructureElement.Loci
            || typeof StructureElement.Loci.is
                !== "function"
            || typeof StructureElement.Loci.forEachLocation
                !== "function"
        ) {
            return null;
        }

        if (
            !StructureElement.Loci.is(
                loci
            )
        ) {
            return null;
        }

        let first = null;

        StructureElement.Loci.forEachLocation(
            loci,
            location => {
                if (first) {
                    return;
                }

                let authSeqId = null;
                let labelSeqId = null;
                let authChain = "";
                let labelChain = "";

                try {
                    authSeqId = finiteInteger(
                        StructureProperties
                            .residue
                            .auth_seq_id(
                                location
                            )
                    );
                } catch (error) {
                    console.debug(
                        "Molstar auth_seq_id unavailable.",
                        error,
                    );
                }

                try {
                    labelSeqId = finiteInteger(
                        StructureProperties
                            .residue
                            .label_seq_id(
                                location
                            )
                    );
                } catch (error) {
                    console.debug(
                        "Molstar label_seq_id unavailable.",
                        error,
                    );
                }

                try {
                    authChain = String(
                        StructureProperties
                            .chain
                            .auth_asym_id(
                                location
                            )
                        || ""
                    );
                } catch (error) {
                    authChain = "";
                }

                try {
                    labelChain = String(
                        StructureProperties
                            .chain
                            .label_asym_id(
                                location
                            )
                        || ""
                    );
                } catch (error) {
                    labelChain = "";
                }

                const coordinate = (
                    authSeqId
                    ?? labelSeqId
                );

                if (
                    coordinate === null
                    || coordinate < 1
                ) {
                    return;
                }

                first = {
                    coordinate,
                    authSeqId,
                    labelSeqId,

                    authAsymId:
                        authChain,

                    labelAsymId:
                        labelChain,

                    chain: (
                        authChain
                        || labelChain
                        || "?"
                    ),
                };
            },
        );

        return first;
    }

    function selectSequenceFromMolstar(
        residue,
    ) {
        if (!residue) {
            return false;
        }

        const workspace = (
            window.BiobankMolecularWorkspace
        );

        if (
            !workspace
            || typeof workspace.selectSequenceRange
                !== "function"
        ) {
            setStatus(
                "The sequence workspace is unavailable.",
                "error",
            );

            return false;
        }

        const structureCoordinate = (
            finiteInteger(
                residue.coordinate
            )
        );

        if (
            structureCoordinate === null
            || structureCoordinate < 1
        ) {
            return false;
        }

        const mappingAdapter = (
            window.BiobankProteinStructureMapping
        );

        const mappingActive = (
            mappingAdapter
            && typeof mappingAdapter.isActive
                === "function"
            && mappingAdapter.isActive()
        );

        if (
            previewMode
            && !mappingActive
        ) {
            setStatus(
                "Structure residue mapping is not available. "
                + "The structural click was not transferred "
                + "to the Molecular Registry sequence.",
                "warning",
            );

            return false;
        }

        let registryCoordinate = (
            structureCoordinate
        );

        if (mappingActive) {
            registryCoordinate = (
                typeof mappingAdapter
                    .registryPositionForResidue
                    === "function"
                    ? mappingAdapter
                        .registryPositionForResidue(
                            residue
                        )
                    : null
            );

            if (
                !Number.isInteger(
                    registryCoordinate
                )
                || registryCoordinate < 1
            ) {
                setStatus(
                    (
                        typeof mappingAdapter
                            .unmappedResidueMessage
                            === "function"
                            ? mappingAdapter
                                .unmappedResidueMessage(
                                    residue
                                )
                            : (
                                "The clicked structural residue "
                                + "is not mapped to the "
                                + "Molecular Registry sequence."
                            )
                    ),
                    "warning",
                );

                return false;
            }
        }

        /*
         * selectSequenceRange() remains the canonical Molecular
         * Registry selection API. The only change is that a
         * mapped PDB residue is translated back to Registry
         * coordinates before invoking it.
         */
        workspace.selectSequenceRange(
            registryCoordinate,
            registryCoordinate,
        );

        latestSelection = {
            start:
                registryCoordinate,

            end:
                registryCoordinate,
        };

        latestSelectedFeature = -1;

        setStatus(
            (
                `3D click: chain ${residue.chain}, `
                + `structure residue ${structureCoordinate} `
                + `→ sequence ${registryCoordinate}`
            ),
            "success",
        );

        return true;
    }

    function bindViewerInteractions(
        viewer,
    ) {
        if (
            !viewer
            || boundViewers.has(
                viewer
            )
        ) {
            return;
        }

        if (
            typeof viewer.subscribe
                !== "function"
            || !viewer.plugin?.behaviors
                ?.interaction
                ?.click
        ) {
            setStatus(
                "Mol* interaction events are unavailable.",
                "error",
            );

            return;
        }

        boundViewers.add(
            viewer
        );

        viewer.subscribe(
            viewer.plugin
                .behaviors
                .interaction
                .click,

            event => {
                const residue = (
                    firstResidueFromLoci(
                        event?.current?.loci
                    )
                );

                if (!residue) {
                    return;
                }

                selectSequenceFromMolstar(
                    residue
                );
            },
        );

        /*
         * Hover is intentionally informational only.
         * It does not mutate the Molecular Registry
         * sequence selection.
         */
        if (
            viewer.plugin
                ?.behaviors
                ?.interaction
                ?.hover
        ) {
            viewer.subscribe(
                viewer.plugin
                    .behaviors
                    .interaction
                    .hover,

                event => {
                    const residue = (
                        firstResidueFromLoci(
                            event?.current?.loci
                        )
                    );

                    if (!residue) {
                        return;
                    }

                    if (
                        normalizedSelection(
                            latestSelection
                        )
                    ) {
                        return;
                    }

                    setStatus(
                        (
                            `3D hover: chain ${residue.chain}, `
                            + `residue ${residue.coordinate}`
                        ),
                    );
                },
            );
        }

        activeViewer = viewer;

        /*
         * If the user already selected a sequence range
         * while the structure was loading, reconcile now.
         */
        if (
            normalizedSelection(
                latestSelection
            )
        ) {
            selectMolstarRange(
                latestSelection
            );
        } else {
            setStatus(
                "3D synchronization ready. "
                + "Select residues in the sequence.",
            );
        }
    }

    /*
     * PROTEIN_STRUCTURE_SYNC_WORKSPACE_HYDRATION_V4_20260815
     *
     * The sequence workspace can already contain a selection
     * before this structure-sync adapter initializes or before
     * a PDB Preview finishes loading.
     *
     * Event listeners alone are therefore insufficient:
     * initialize from the canonical workspace snapshot too.
     */
    function applyWorkspaceSnapshot(
        snapshot,
    ) {
        if (!snapshot) {
            return false;
        }

        latestSelection = (
            snapshot.sequenceSelection
                ? {
                    ...snapshot.sequenceSelection,
                }
                : null
        );

        latestSelectedFeature = (
            Number.isInteger(
                snapshot.selectedFeature
            )
                ? snapshot.selectedFeature
                : -1
        );

        return true;
    }

    function hydrateWorkspaceSnapshot() {
        const workspace = (
            window.BiobankMolecularWorkspace
        );

        if (
            !workspace
            || typeof workspace.getSnapshot
                !== "function"
        ) {
            return false;
        }

        let snapshot = null;

        try {
            snapshot = (
                workspace.getSnapshot()
            );
        } catch (error) {
            console.error(
                "Unable to hydrate Molecular Registry "
                + "workspace state.",
                error,
            );

            return false;
        }

        return applyWorkspaceSnapshot(
            snapshot
        );
    }

    function handleWorkspaceChange(
        event,
    ) {
        const snapshot = (
            event?.detail?.snapshot
        );

        if (
            !applyWorkspaceSnapshot(
                snapshot
            )
        ) {
            return;
        }

        selectMolstarRange(
            latestSelection
        );
    }

    function handleStructureLoaded(
        event,
    ) {
        const viewer = (
            event?.detail?.viewer
            || window.BiobankProteinStructure
                ?.getViewer?.()
            || null
        );

        activeStructure = (
            event?.detail?.structure
            || null
        );

        /*
         * Stored/uploaded structures also require the validated
         * residue map before direct sequence <-> Mol*
         * synchronization is allowed.
         */
        previewMode = true;

        activeViewer = viewer;

        bindViewerInteractions(
            viewer
        );

        if (activeStructure) {
            const label = (
                activeStructure.label
                || activeStructure.original_filename
                || `Structure ${activeStructure.id}`
            );

            setStatus(
                `3D synchronization ready · ${label}`,
            );
        }

        if (
            normalizedSelection(
                latestSelection
            )
        ) {
            selectMolstarRange(
                latestSelection
            );
        }
    }

    function createControls() {
        const toolbar = document.querySelector(
            "#mw-protein-structure .mps-toolbar",
        );

        const card = document.getElementById(
            "mw-protein-structure",
        );

        if (
            !toolbar
            || !card
        ) {
            return false;
        }

        if (
            document.getElementById(
                "mps-focus-sequence-selection"
            )
        ) {
            syncStatus = document.getElementById(
                "mps-sync-status"
            );

            focusButton = document.getElementById(
                "mps-focus-sequence-selection"
            );

            return true;
        }

        focusButton = document.createElement(
            "button"
        );

        focusButton.type = "button";
        focusButton.id = (
            "mps-focus-sequence-selection"
        );

        focusButton.className = (
            "btn btn-sm btn-outline-secondary"
        );

        focusButton.textContent = (
            "Focus selected residues"
        );

        focusButton.disabled = true;

        focusButton.title = (
            "Center the Mol* camera on the residues "
            + "selected in the sequence."
        );

        focusButton.addEventListener(
            "click",
            focusCurrentSelection,
        );

        toolbar.appendChild(
            focusButton
        );

        syncStatus = document.createElement(
            "div"
        );

        syncStatus.id = "mps-sync-status";

        syncStatus.className = (
            "small text-body-secondary mt-2"
        );

        syncStatus.setAttribute(
            "role",
            "status"
        );

        syncStatus.dataset.syncVersion = (
            VERSION
        );

        syncStatus.textContent = (
            "Preparing sequence ↔ 3D synchronization…"
        );

        const body = card.querySelector(
            ".mps-body"
        );

        if (body) {
            const structureStatus = (
                body.querySelector(
                    "#mps-status"
                )
            );

            if (structureStatus) {
                structureStatus.insertAdjacentElement(
                    "afterend",
                    syncStatus,
                );
            } else {
                body.prepend(
                    syncStatus
                );
            }
        }

        return true;
    }

    async function initialize() {
        const root = document.querySelector(
            ".mw-page"
        );

        if (!root) {
            return;
        }

        const sequenceType = String(
            root.dataset.sequenceType
            || ""
        ).toLowerCase();

        if (sequenceType !== "protein") {
            return;
        }

        /*
         * Wait for the structure adapter and final
         * Protein Overview to finish initialization.
         */
        let readyState = false;

        for (
            let attempt = 0;
            attempt < 120;
            attempt += 1
        ) {
            const workspaceReady = (
                window.BiobankMolecularWorkspace
                && typeof window
                    .BiobankMolecularWorkspace
                    .selectSequenceRange
                    === "function"
            );

            const structureReady = (
                window.BiobankProteinStructure
                && typeof window
                    .BiobankProteinStructure
                    .getViewer
                    === "function"
            );

            const controlsReady = (
                createControls()
            );

            if (
                workspaceReady
                && structureReady
                && controlsReady
            ) {
                readyState = true;
                break;
            }

            await wait(
                50
            );
        }

        if (!readyState) {
            console.error(
                "Protein structure synchronization "
                + "could not initialize."
            );

            return;
        }

        root.addEventListener(
            WORKSPACE_EVENT,
            handleWorkspaceChange,
        );

        root.addEventListener(
            STRUCTURE_EVENT,
            handleStructureLoaded,
        );

        /*
         * Computational Preview uses protected transient
         * synchronization mode without a residue-mapping adapter.
         */
        root.addEventListener(
            "biobank:protein-computational-structure-preview-loaded",
            event => {
                const viewer = (
                    event?.detail?.viewer
                    || window.BiobankProteinStructure
                        ?.getViewer?.()
                    || null
                );

                previewMode = true;
                activeStructure = null;
                activeViewer = viewer;

                hydrateWorkspaceSnapshot();

                if (viewer) {
                    bindViewerInteractions(
                        viewer
                    );
                }

                selectMolstarRange(
                    latestSelection
                );
            },
        );

        root.addEventListener(
            PREVIEW_EVENT,
            event => {
                const viewer = (
                    event?.detail?.viewer
                    || window.BiobankProteinStructure
                        ?.getViewer?.()
                    || null
                );

                previewMode = true;
                activeStructure = null;
                activeViewer = viewer;

                /*
                 * Refresh from the canonical workspace state
                 * at Preview-load time. This guarantees that a
                 * sequence selection made before Preview is
                 * immediately transferred to Mol*.
                 */
                hydrateWorkspaceSnapshot();

                if (viewer) {
                    bindViewerInteractions(
                        viewer
                    );
                }

                if (
                    normalizedSelection(
                        latestSelection
                    )
                ) {
                    selectMolstarRange(
                        latestSelection
                    );
                }
            },
        );

        /*
         * Hydrate any sequence/annotation selection that
         * predates this adapter.
         *
         * This closes the state gap where the sequence track
         * visually showed 90..110 while latestSelection was
         * still null.
         */
        hydrateWorkspaceSnapshot();

        /*
         * A PDB Preview can theoretically finish just before
         * this sync adapter attaches its Preview listener.
         *
         * The mapping adapter is active only for a mapped
         * Preview in this workflow, so recover Preview mode
         * from that authoritative state when necessary.
         */
        const existingMappingAdapter = (
            window.BiobankProteinStructureMapping
        );

        if (
            existingMappingAdapter
            && typeof existingMappingAdapter.isActive
                === "function"
            && existingMappingAdapter.isActive()
        ) {
            previewMode = true;
        }

        /*
         * The structure might already have completed its
         * asynchronous initial load before this adapter
         * attached the structure-loaded listener.
         */
        const existingViewer = (
            window.BiobankProteinStructure
                ?.getViewer?.()
        );

        if (existingViewer) {
            activeViewer = existingViewer;

            bindViewerInteractions(
                existingViewer
            );
        }

        window.BiobankProteinStructureSync = {
            version: VERSION,

            selectRange: (
                start,
                end,
            ) => {
                latestSelection = {
                    start,
                    end,
                };

                return selectMolstarRange(
                    latestSelection
                );
            },

            focusRange: (
                start,
                end,
            ) => {
                latestSelection = {
                    start,
                    end,
                };

                return selectMolstarRange(
                    latestSelection,
                    {
                        focus: true,
                    },
                );
            },

            focusSelection:
                focusCurrentSelection,

            getSelection: () => (
                latestSelection
                    ? {
                        ...latestSelection,
                    }
                    : null
            ),

            getViewer: currentViewer,

            getStructure: () => (
                activeStructure
            ),

            isPreviewMode: () => (
                previewMode
            ),

            getMapping: () => (
                window.BiobankProteinStructureMapping
                    ?.getActiveCandidate?.()
                || null
            ),
        };

        setStatus(
            "3D synchronization ready. "
            + "Select residues in the sequence.",
        );
    }

    ready(
        initialize
    );
})();
