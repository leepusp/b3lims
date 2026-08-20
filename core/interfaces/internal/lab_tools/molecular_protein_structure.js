(() => {
    "use strict";

    const VERSION = "PROTEIN_STRUCTURE_VIEWER_V1_20260815";

    function element(tag, className, text) {
        const node = document.createElement(tag);

        if (className) {
            node.className = className;
        }

        if (text !== undefined) {
            node.textContent = text;
        }

        return node;
    }

    function onReady(callback) {
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

    async function waitForOverview(root) {
        for (let attempt = 0; attempt < 40; attempt += 1) {
            const overview = root.querySelector(
                ".mw-protein-final-overview",
            );

            const sequenceCard = root.querySelector(
                ".mw-protein-overview-sequence",
            );

            if (overview && sequenceCard) {
                return {
                    overview,
                    sequenceCard,
                };
            }

            await new Promise(resolve => {
                window.setTimeout(resolve, 50);
            });
        }

        return null;
    }

    onReady(async () => {
        const root = document.querySelector(".mw-page");

        if (!root) {
            return;
        }

        const sequenceType = String(
            root.dataset.sequenceType || "",
        ).toLowerCase();

        if (sequenceType !== "protein") {
            return;
        }

        if (document.getElementById("mw-protein-structure")) {
            return;
        }

        const structuresUrl = String(
            root.dataset.proteinStructuresUrl || "",
        );

        if (!structuresUrl) {
            console.error(
                "Protein Structure URL is unavailable.",
            );
            return;
        }

        const workspace = await waitForOverview(root);

        if (!workspace) {
            console.error(
                "Protein Overview was not available for "
                + "structure viewer integration.",
            );
            return;
        }

        if (
            !window.molstar
            || !window.molstar.Viewer
            || typeof window.molstar.Viewer.create !== "function"
        ) {
            console.error(
                "Molstar 5.11.0 bundle is unavailable.",
            );
            return;
        }

        const canEdit = String(
            root.dataset.canEdit || "",
        ).toLowerCase() === "true";

        const csrfToken = String(
            root.dataset.csrfToken || "",
        );

        const card = element(
            "section",
            "mw-card mps-card",
        );

        card.id = "mw-protein-structure";
        card.dataset.proteinStructureVersion = VERSION;

        const header = element(
            "div",
            "mw-card-header",
        );

        const headingGroup = element(
            "div",
            "",
        );

        const heading = element(
            "h2",
            "",
            "Protein structure",
        );

        const description = element(
            "p",
            "",
            "Inspect PDB or mmCIF structures in Mol* alongside "
            + "the annotated amino-acid sequence.",
        );

        headingGroup.append(
            heading,
            description,
        );

        header.appendChild(
            headingGroup,
        );

        const body = element(
            "div",
            "mps-body",
        );

        const toolbar = element(
            "div",
            "mps-toolbar",
        );

        const select = document.createElement("select");

        select.id = "mps-structure-select";
        select.className = "form-select form-select-sm";
        select.setAttribute(
            "aria-label",
            "Stored Protein structures",
        );

        const loadButton = element(
            "button",
            "btn btn-sm btn-primary",
            "Load stored structure",
        );

        loadButton.type = "button";
        loadButton.id = "mps-load";

        const downloadLink = element(
            "a",
            "btn btn-sm btn-outline-secondary",
            "Download",
        );

        downloadLink.id = "mps-download";
        downloadLink.href = "#";
        downloadLink.hidden = true;

        toolbar.append(
            select,
            loadButton,
            downloadLink,
        );

        let uploadInput = null;
        let uploadButton = null;
        let deleteButton = null;

        if (canEdit) {
            uploadInput = document.createElement("input");

            uploadInput.type = "file";
            uploadInput.id = "mps-upload-file";
            uploadInput.className = (
                "form-control form-control-sm mps-file-input"
            );
            uploadInput.accept = ".pdb,.cif,.mmcif";

            uploadButton = element(
                "button",
                "btn btn-sm btn-outline-primary",
                "Upload",
            );

            uploadButton.type = "button";
            uploadButton.id = "mps-upload";

            deleteButton = element(
                "button",
                "btn btn-sm btn-outline-danger",
                "Remove",
            );

            deleteButton.type = "button";
            deleteButton.id = "mps-remove";

            toolbar.append(
                uploadInput,
                uploadButton,
                deleteButton,
            );
        }

        const status = element(
            "div",
            "mps-status",
            "Checking stored structures…",
        );

        status.id = "mps-status";
        status.setAttribute(
            "role",
            "status",
        );

        const viewerShell = element(
            "div",
            "mps-viewer-shell",
        );

        const viewerMount = element(
            "div",
            "mps-viewer",
        );

        viewerMount.id = "mps-viewer";

        const empty = element(
            "div",
            "mps-empty",
            "Upload or select a PDB/mmCIF structure to inspect it in 3D.",
        );

        empty.id = "mps-empty";

        viewerShell.append(
            empty,
            viewerMount,
        );

        viewerMount.hidden = true;

        const footer = element(
            "div",
            "mps-footer",
        );

        footer.append(
            element(
                "p",
                "",
                "Mol* 5.11.0 · local vendored viewer",
            ),
            element(
                "p",
                "",
                "Representation and color controls are available "
                + "inside the Mol* panel.",
            ),
        );

        body.append(
            toolbar,
            status,
            viewerShell,
            footer,
        );

        card.append(
            header,
            body,
        );

        const grid = element(
            "div",
            "mps-overview-grid",
        );

        grid.id = "mw-protein-overview-structure-grid";

        workspace.overview.insertBefore(
            grid,
            workspace.sequenceCard,
        );

        grid.append(
            workspace.sequenceCard,
            card,
        );

        let structures = [];
        let selectedId = null;
        let viewer = null;

        function setStatus(message, kind = "") {
            status.textContent = message;

            if (kind) {
                status.dataset.kind = kind;
            } else {
                delete status.dataset.kind;
            }
        }

        function selectedStructure() {
            return structures.find(item => (
                Number(item.id) === Number(selectedId)
            )) || null;
        }

        function structureUrl(structureId, mode) {
            const url = new URL(
                structuresUrl,
                window.location.origin,
            );

            url.searchParams.set(
                "structure_id",
                String(structureId),
            );

            if (mode) {
                url.searchParams.set(
                    mode,
                    "1",
                );
            }

            return url.toString();
        }

        function renderSelect() {
            select.replaceChildren();

            if (!structures.length) {
                const option = new Option(
                    "No stored structures",
                    "",
                    true,
                    true,
                );

                select.appendChild(option);
                select.disabled = true;
                loadButton.disabled = true;
                downloadLink.hidden = true;

                if (deleteButton) {
                    deleteButton.disabled = true;
                }

                return;
            }

            select.disabled = false;
            loadButton.disabled = false;

            for (const item of structures) {
                const label = (
                    item.label
                    || item.original_filename
                    || `Structure ${item.id}`
                );

                const option = new Option(
                    `${label} · ${String(
                        item.source_format_label
                        || item.source_format
                        || "",
                    )}`,
                    String(item.id),
                );

                select.appendChild(option);
            }

            const preferred = structures.some(item => (
                Number(item.id) === Number(selectedId)
            ))
                ? selectedId
                : structures[0].id;

            selectedId = Number(preferred);
            select.value = String(selectedId);

            downloadLink.href = structureUrl(
                selectedId,
                "download",
            );

            downloadLink.hidden = false;

            if (deleteButton) {
                deleteButton.disabled = false;
            }
        }

        async function ensureViewer() {
            if (viewer) {
                return viewer;
            }

            empty.hidden = true;
            viewerMount.hidden = false;

            viewer = await window.molstar.Viewer.create(
                viewerMount,
                {
                    layoutIsExpanded: false,
                    layoutShowControls: true,
                    layoutShowRemoteState: false,
                    layoutShowSequence: false,
                    layoutShowLog: false,
                    layoutShowLeftPanel: false,
                    viewportShowExpand: true,
                    viewportShowSelectionMode: true,
                    viewportShowControls: true,
                    viewportShowAnimation: false,
                    viewportBackgroundColor: "#111318",
                },
            );

            window.BiobankProteinStructureViewer = viewer;

            return viewer;
        }

        async function resetViewer() {
            if (
                viewer
                && viewer.plugin
                && typeof viewer.plugin.dispose === "function"
            ) {
                try {
                    viewer.plugin.dispose();
                } catch (error) {
                    console.warn(
                        "Could not dispose previous Molstar viewer.",
                        error,
                    );
                }
            }

            viewer = null;
            viewerMount.replaceChildren();
            viewerMount.hidden = false;
            empty.hidden = true;

            return ensureViewer();
        }

        async function loadStructure(structureId) {
            const item = structures.find(candidate => (
                Number(candidate.id) === Number(structureId)
            ));

            if (!item) {
                return;
            }

            selectedId = Number(item.id);
            select.value = String(selectedId);

            downloadLink.href = structureUrl(
                selectedId,
                "download",
            );

            downloadLink.hidden = false;

            const label = (
                item.label
                || item.original_filename
                || `Structure ${item.id}`
            );

            setStatus(
                `Loading ${label}…`,
            );

            try {
                const response = await fetch(
                    structureUrl(
                        item.id,
                        "raw",
                    ),
                    {
                        credentials: "same-origin",
                    },
                );

                if (!response.ok) {
                    throw new Error(
                        `HTTP ${response.status}`,
                    );
                }

                const data = await response.text();

                const instance = await resetViewer();

                const format = (
                    String(item.source_format).toLowerCase()
                    === "pdb"
                )
                    ? "pdb"
                    : "mmcif";

                await instance.loadStructureFromData(
                    data,
                    format,
                    {
                        dataLabel: label,
                    },
                );

                setStatus(
                    `${label} loaded.`,
                    "success",
                );

                root.dispatchEvent(
                    new CustomEvent(
                        "biobank:protein-structure-loaded",
                        {
                            detail: {
                                structure: item,
                                viewer: instance,
                            },
                        },
                    ),
                );
            } catch (error) {
                console.error(error);

                setStatus(
                    `Could not load ${label}.`,
                    "error",
                );
            }
        }

        async function refreshStructures({
            autoLoad = false,
        } = {}) {
            setStatus(
                "Checking stored structures…",
            );

            try {
                const response = await fetch(
                    structuresUrl,
                    {
                        credentials: "same-origin",
                    },
                );

                if (!response.ok) {
                    throw new Error(
                        `HTTP ${response.status}`,
                    );
                }

                const payload = await response.json();

                structures = Array.isArray(
                    payload.structures,
                )
                    ? payload.structures
                    : [];

                renderSelect();

                if (!structures.length) {
                    setStatus(
                        "No Protein structure is attached yet.",
                    );

                    viewerMount.hidden = true;
                    empty.hidden = false;
                    return;
                }

                setStatus(
                    `${structures.length} stored structure`
                    + `${structures.length === 1 ? "" : "s"}.`,
                );

                if (autoLoad) {
                    await loadStructure(
                        selectedId,
                    );
                }
            } catch (error) {
                console.error(error);

                setStatus(
                    "Could not load Protein structures.",
                    "error",
                );
            }
        }

        async function uploadStructure() {
            if (
                !uploadInput
                || !uploadInput.files
                || !uploadInput.files.length
            ) {
                setStatus(
                    "Choose a PDB or mmCIF file first.",
                    "error",
                );
                return;
            }

            const file = uploadInput.files[0];

            const form = new FormData();

            form.set(
                "action",
                "upload",
            );

            form.set(
                "label",
                file.name,
            );

            form.set(
                "file",
                file,
            );

            setStatus(
                `Uploading ${file.name}…`,
            );

            try {
                const response = await fetch(
                    structuresUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: csrfToken
                            ? {
                                "X-CSRFToken": csrfToken,
                            }
                            : {},
                        body: form,
                    },
                );

                const payload = await response.json();

                if (!response.ok) {
                    throw new Error(
                        payload.error
                        || `HTTP ${response.status}`,
                    );
                }

                uploadInput.value = "";

                if (
                    payload.structure
                    && payload.structure.id
                ) {
                    selectedId = Number(
                        payload.structure.id,
                    );
                }

                await refreshStructures({
                    autoLoad: true,
                });
            } catch (error) {
                console.error(error);

                setStatus(
                    error.message
                    || "Structure upload failed.",
                    "error",
                );
            }
        }

        async function removeStructure() {
            const item = selectedStructure();

            if (!item) {
                return;
            }

            const label = (
                item.label
                || item.original_filename
                || `Structure ${item.id}`
            );

            if (!window.confirm(
                `Remove ${label}?`,
            )) {
                return;
            }

            const form = new URLSearchParams();

            form.set(
                "action",
                "delete",
            );

            form.set(
                "structure_id",
                String(item.id),
            );

            setStatus(
                `Removing ${label}…`,
            );

            try {
                const response = await fetch(
                    structuresUrl,
                    {
                        method: "POST",
                        credentials: "same-origin",
                        headers: {
                            "Content-Type":
                                "application/x-www-form-urlencoded;charset=UTF-8",
                            ...(csrfToken
                                ? {
                                    "X-CSRFToken": csrfToken,
                                }
                                : {}),
                        },
                        body: form.toString(),
                    },
                );

                const payload = await response.json();

                if (!response.ok) {
                    throw new Error(
                        payload.error
                        || `HTTP ${response.status}`,
                    );
                }

                selectedId = null;

                if (
                    viewer
                    && viewer.plugin
                    && typeof viewer.plugin.dispose === "function"
                ) {
                    viewer.plugin.dispose();
                }

                viewer = null;
                viewerMount.replaceChildren();
                viewerMount.hidden = true;
                empty.hidden = false;

                await refreshStructures();
            } catch (error) {
                console.error(error);

                setStatus(
                    error.message
                    || "Could not remove structure.",
                    "error",
                );
            }
        }

        select.addEventListener(
            "change",
            () => {
                selectedId = Number(
                    select.value,
                );

                if (selectedId) {
                    downloadLink.href = structureUrl(
                        selectedId,
                        "download",
                    );
                }
            },
        );

        loadButton.addEventListener(
            "click",
            () => {
                if (selectedId) {
                    loadStructure(
                        selectedId,
                    );
                }
            },
        );

        if (
            uploadButton
            && uploadInput
        ) {
            /*
             * Keep the browser-native file picker as the secure
             * local-file selection mechanism, but do not expose
             * its browser-localized control in the Biobank UI.
             */
            uploadInput.hidden = true;
            uploadInput.tabIndex = -1;

            uploadInput.setAttribute(
                "aria-hidden",
                "true",
            );

            uploadButton.textContent = (
                "Upload structure"
            );

            uploadButton.addEventListener(
                "click",
                () => {
                    uploadInput.value = "";
                    uploadInput.click();
                },
            );

            uploadInput.addEventListener(
                "change",
                () => {
                    if (
                        uploadInput.files
                        && uploadInput.files.length
                    ) {
                        uploadStructure();
                    }
                },
            );
        }

        if (deleteButton) {
            deleteButton.addEventListener(
                "click",
                removeStructure,
            );
        }

        async function loadPreviewData(
            data,
            metadata = {},
        ) {
            const source = String(
                data
                || ""
            );

            if (!source.trim()) {
                throw new Error(
                    "PDB preview returned an empty structure."
                );
            }

            const pdbId = String(
                metadata.pdbId
                || metadata.pdb_id
                || ""
            ).toUpperCase();

            const label = (
                pdbId
                    ? `PDB ${pdbId}`
                    : "PDB structure"
            );

            setStatus(
                `Loading ${label} preview…`,
                "busy",
            );

            selectedId = null;

            if (select) {
                select.value = "";
            }

            loadButton.disabled = true;
            downloadLink.hidden = true;

            if (deleteButton) {
                deleteButton.disabled = true;
            }

            if (
                viewer
                && viewer.plugin
                && typeof viewer.plugin.dispose
                    === "function"
            ) {
                viewer.plugin.dispose();
            }

            viewer = null;

            window.BiobankProteinStructureViewer = null;

            viewerMount.replaceChildren();
            viewerMount.hidden = false;
            empty.hidden = true;

            try {
                const instance = await resetViewer();

                await instance.loadStructureFromData(
                    source,
                    "mmcif",
                );

                viewer = instance;

                window.BiobankProteinStructureViewer = (
                    instance
                );

                setStatus(
                    (
                        `${label} preview · temporary · `
                        + "not saved · residue mapping pending"
                    ),
                    "ready",
                );

                root.dispatchEvent(
                    new CustomEvent(
                        "biobank:protein-structure-preview-loaded",
                        {
                            detail: {
                                viewer: instance,
                                preview: {
                                    ...metadata,
                                    pdbId,
                                },
                            },
                        },
                    )
                );

                window.dispatchEvent(
                    new Event(
                        "resize"
                    )
                );

                return instance;

            } catch (error) {
                console.error(
                    error
                );

                setStatus(
                    (
                        error.message
                        || "Could not preview the PDB structure."
                    ),
                    "error",
                );

                throw error;
            }
        }



        /*
         * Computational Preview deliberately uses a separate event
         * from the experimental PDB Preview.
         */
        async function loadComputationalPreviewData(
            data,
            metadata = {},
        ) {
            const source = String(
                data
                || ""
            );

            if (!source.trim()) {
                throw new Error(
                    "Predicted-model preview returned "
                    + "an empty structure."
                );
            }

            const accession = String(
                metadata.accession
                || metadata.modelId
                || metadata.model_id
                || ""
            ).trim();

            const providerName = String(
                metadata.providerName
                || metadata.provider_name
                || metadata.provider
                || ""
            ).trim();

            const label = (
                accession
                    ? (
                        providerName
                            ? `${providerName} ${accession}`
                            : accession
                    )
                    : (
                        providerName
                        || "Predicted model"
                    )
            );

            setStatus(
                `Loading ${label} preview…`,
                "busy",
            );

            selectedId = null;

            if (select) {
                select.value = "";
            }

            if (downloadLink) {
                downloadLink.hidden = true;
            }

            if (
                viewer
                && viewer.plugin
                && typeof viewer.plugin.dispose
                    === "function"
            ) {
                viewer.plugin.dispose();
            }

            viewer = null;

            window.BiobankProteinStructureViewer = null;

            viewerMount.replaceChildren();
            viewerMount.hidden = false;
            empty.hidden = true;

            try {
                const instance = await resetViewer();

                await instance.loadStructureFromData(
                    source,
                    "mmcif",
                );

                viewer = instance;

                window.BiobankProteinStructureViewer = (
                    instance
                );

                setStatus(
                    (
                        `${label} preview · temporary · `
                        + "not saved"
                    ),
                    "ready",
                );

                root.dispatchEvent(
                    new CustomEvent(
                        "biobank:protein-computational-structure-preview-loaded",
                        {
                            detail: {
                                viewer: instance,
                                preview: {
                                    ...metadata,
                                    sourceType:
                                        "computational",
                                    accession,
                                    providerName,
                                },
                            },
                        },
                    )
                );

                window.dispatchEvent(
                    new Event(
                        "resize"
                    )
                );

                return instance;

            } catch (error) {
                console.error(
                    error
                );

                setStatus(
                    (
                        error.message
                        || (
                            "Could not preview the "
                            + "predicted structure."
                        )
                    ),
                    "error",
                );

                throw error;
            }
        }


        window.BiobankProteinStructure = {
            version: VERSION,
            refresh: refreshStructures,
            loadStructureById: loadStructure,
            loadPreviewData: loadPreviewData,
            loadComputationalPreviewData: loadComputationalPreviewData,
            getViewer: () => viewer,
            getStructures: () => [...structures],
        };

        await refreshStructures({
            autoLoad: true,
        });
    });
})();
