(() => {
    "use strict";

    const VERSION = (
        "20260808-rna-secondary-r1c-forna-v2"
    );

    let vendorPromise = null;

    function workspaceApi() {
        return (
            window.BiobankMolecularWorkspace
            || null
        );
    }

    function workspaceSnapshot() {
        return (
            workspaceApi()
                ?.getSnapshot?.()
            || null
        );
    }

    function normalizedSequence(
        sequence,
    ) {
        return String(
            sequence
            || ""
        )
            .replace(
                /\s+/g,
                "",
            )
            .toUpperCase();
    }

    function parseBoolean(
        value,
    ) {
        return (
            String(
                value
            ).toLowerCase()
            === "true"
        );
    }

    function createElement(
        tag,
        className = "",
        text = null,
    ) {
        const element = (
            document.createElement(
                tag
            )
        );

        if (className) {
            element.className = className;
        }

        if (
            text !== null
            && text !== undefined
        ) {
            element.textContent = (
                String(
                    text
                )
            );
        }

        return element;
    }

    function loadFornaVendor(
        url,
    ) {
        if (
            window.fornac
                ?.FornaContainer
        ) {
            return Promise.resolve(
                window.fornac
            );
        }

        if (vendorPromise) {
            return vendorPromise;
        }

        vendorPromise = new Promise(
            (
                resolve,
                reject,
            ) => {
                const script = (
                    document.createElement(
                        "script"
                    )
                );

                script.src = url;
                script.async = true;

                script.dataset
                    .biobankRnaFornaVendor = (
                        VERSION
                    );

                script.addEventListener(
                    "load",
                    () => {
                        if (
                            window.fornac
                                ?.FornaContainer
                        ) {
                            resolve(
                                window.fornac
                            );
                            return;
                        }

                        reject(
                            new Error(
                                (
                                    "Forna loaded but "
                                    + "FornaContainer was not exposed."
                                )
                            )
                        );
                    },
                    {
                        once: true,
                    },
                );

                script.addEventListener(
                    "error",
                    () => {
                        reject(
                            new Error(
                                (
                                    "Could not load the local "
                                    + "Forna RNA renderer."
                                )
                            )
                        );
                    },
                    {
                        once: true,
                    },
                );

                document.head.appendChild(
                    script
                );
            },
        );

        return vendorPromise;
    }

    function initialize() {
        const root = (
            document.getElementById(
                "molecular-workspace"
            )
        );

        if (
            !root
            || root.dataset.sequenceType
            !== "rna"
        ) {
            return;
        }

        const apiUrl = (
            root.dataset
                .rnaSecondaryStructuresUrl
            || ""
        );

        const vendorUrl = (
            root.dataset
                .rnaFornaVendorUrl
            || ""
        );

        const csrfToken = (
            root.dataset.csrfToken
            || ""
        );

        const canEdit = parseBoolean(
            root.dataset.canEdit
        );

        if (
            !apiUrl
            || !vendorUrl
        ) {
            console.error(
                (
                    "RNA secondary-structure "
                    + "workspace URLs are unavailable."
                )
            );
            return;
        }

        const initialSequence = (
            normalizedSequence(
                workspaceSnapshot()
                    ?.sequence
            )
        );

        let structures = [];
        let selectedId = null;
        let currentPayload = null;
        let currentForna = null;
        let currentSequenceDrift = false;
        let structuresLoaded = false;

        const card = (
            document.getElementById(
                "mw-rna-secondary-structure"
            )
        );

        if (!card) {
            console.error(
                "RNA secondary-structure main panel is unavailable."
            );
            return;
        }

        card.classList.add(
            "mrss-card",
            "mw-rna-secondary-view",
        );

        card.dataset
            .rnaSecondaryStructureVersion = (
                VERSION
            );

        card.replaceChildren();

        const header = createElement(
            "div",
            "mw-card-header mrss-header",
        );

        const headingWrap = createElement(
            "div",
            "mrss-heading",
        );

        headingWrap.append(
            createElement(
                "h2",
                "",
                "Secondary structure",
            ),
            createElement(
                "p",
                "",
                (
                    "Inspect persisted RNA secondary structures "
                    + "using the current RNA sequence as the "
                    + "single sequence source of truth."
                ),
            ),
        );

        const headerActions = createElement(
            "div",
            "mrss-header-actions",
        );

        const status = createElement(
            "span",
            "mrss-status",
            "Checking structures…",
        );

        status.setAttribute(
            "role",
            "status",
        );

        status.setAttribute(
            "aria-live",
            "polite",
        );

        headerActions.appendChild(
            status
        );

        const addButton = createElement(
            "button",
            "btn btn-sm btn-outline-primary",
            "Add structure",
        );

        addButton.type = "button";

        if (canEdit) {
            headerActions.appendChild(
                addButton
            );
        }

        header.append(
            headingWrap,
            headerActions,
        );

        const body = createElement(
            "div",
            "mrss-body",
        );

        const sidebar = createElement(
            "aside",
            "mrss-sidebar",
        );

        const listHeading = createElement(
            "div",
            "mrss-list-heading",
        );

        const count = createElement(
            "span",
            "mrss-count",
            "0",
        );

        listHeading.append(
            createElement(
                "strong",
                "",
                "Stored structures",
            ),
            count,
        );

        const list = createElement(
            "div",
            "mrss-list",
        );

        const listEmpty = createElement(
            "div",
            "mw-empty mrss-list-empty",
            (
                "No secondary structure is attached "
                + "to this RNA record yet."
            ),
        );

        sidebar.append(
            listHeading,
            list,
            listEmpty,
        );

        const main = createElement(
            "div",
            "mrss-main",
        );

        const sequenceWarning = createElement(
            "div",
            "mrss-sequence-warning",
            (
                "The RNA sequence has changed in the editor. "
                + "Reload the saved record before rendering "
                + "persisted secondary structures."
            ),
        );

        sequenceWarning.hidden = true;

        const metadata = createElement(
            "div",
            "mrss-metadata",
        );

        const toolbar = createElement(
            "div",
            "mrss-toolbar",
        );

        const schemeLabel = createElement(
            "label",
            "mrss-control",
        );

        schemeLabel.appendChild(
            createElement(
                "span",
                "",
                "Color scheme",
            )
        );

        const scheme = (
            document.createElement(
                "select"
            )
        );

        scheme.className = (
            "form-select form-select-sm"
        );

        for (
            const [
                value,
                label,
            ]
            of [
                [
                    "structure",
                    "Structure",
                ],
                [
                    "sequence",
                    "Sequence",
                ],
                [
                    "positions",
                    "Position",
                ],
            ]
        ) {
            const option = (
                document.createElement(
                    "option"
                )
            );

            option.value = value;
            option.textContent = label;

            scheme.appendChild(
                option
            );
        }

        schemeLabel.appendChild(
            scheme
        );

        const resetButton = createElement(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Reset view",
        );

        resetButton.type = "button";
        resetButton.disabled = true;

        const copyButton = createElement(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Copy source",
        );

        copyButton.type = "button";
        copyButton.disabled = true;

        const deleteButton = createElement(
            "button",
            "btn btn-sm btn-outline-danger",
            "Remove structure",
        );

        deleteButton.type = "button";
        deleteButton.hidden = !canEdit;
        deleteButton.disabled = true;

        toolbar.append(
            schemeLabel,
            resetButton,
            copyButton,
            deleteButton,
        );

        const structureCodeWrap = createElement(
            "div",
            "mrss-structure-code-wrap",
        );

        structureCodeWrap.hidden = true;

        structureCodeWrap.appendChild(
            createElement(
                "span",
                "mrss-field-label",
                "Dot-bracket",
            )
        );

        const structureCode = createElement(
            "code",
            "mrss-structure-code",
            "",
        );

        structureCodeWrap.appendChild(
            structureCode
        );

        const viewerShell = createElement(
            "div",
            "mrss-viewer-shell",
        );

        viewerShell.appendChild(
            createElement(
                "div",
                "mw-empty mrss-viewer-empty",
                (
                    "Choose a stored secondary structure "
                    + "to open the RNA renderer."
                ),
            )
        );

        const provenance = createElement(
            "details",
            "mrss-provenance",
        );

        provenance.hidden = true;

        provenance.appendChild(
            createElement(
                "summary",
                "",
                "Source / provenance",
            )
        );

        const provenanceBody = createElement(
            "div",
            "mrss-provenance-body",
        );

        const sourceText = createElement(
            "pre",
            "mrss-source-text",
            "",
        );

        provenanceBody.appendChild(
            sourceText
        );

        provenance.appendChild(
            provenanceBody
        );

        main.append(
            sequenceWarning,
            metadata,
            toolbar,
            structureCodeWrap,
            viewerShell,
            provenance,
        );

        body.append(
            sidebar,
            main,
        );

        const editor = createElement(
            "section",
            "mrss-editor",
        );

        editor.hidden = true;

        const editorHeader = createElement(
            "div",
            "mrss-editor-header",
        );

        editorHeader.appendChild(
            createElement(
                "div",
                "",
                "Add persisted secondary structure",
            )
        );

        const closeEditor = createElement(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Close",
        );

        closeEditor.type = "button";

        editorHeader.appendChild(
            closeEditor
        );

        const form = (
            document.createElement(
                "form"
            )
        );

        form.className = (
            "mrss-form"
        );

        const nameLabel = createElement(
            "label"
        );

        nameLabel.appendChild(
            createElement(
                "span",
                "",
                "Name",
            )
        );

        const nameInput = (
            document.createElement(
                "input"
            )
        );

        nameInput.type = "text";
        nameInput.className = (
            "form-control form-control-sm"
        );
        nameInput.maxLength = 255;
        nameInput.placeholder = (
            "e.g. MFE structure"
        );

        nameLabel.appendChild(
            nameInput
        );

        const methodLabel = createElement(
            "label"
        );

        methodLabel.appendChild(
            createElement(
                "span",
                "",
                "Source method",
            )
        );

        const methodInput = (
            document.createElement(
                "input"
            )
        );

        methodInput.type = "text";
        methodInput.className = (
            "form-control form-control-sm"
        );
        methodInput.maxLength = 255;

        /*
         * This is provenance text only. No prediction program is
         * executed by the frontend.
         */
        methodInput.placeholder = (
            "e.g. Imported RNAfold output"
        );

        methodLabel.appendChild(
            methodInput
        );

        const sourceLabel = createElement(
            "label",
            "mrss-form-wide",
        );

        sourceLabel.appendChild(
            createElement(
                "span",
                "",
                "Dot-bracket / DBN / RNAfold-style text",
            )
        );

        const sourceInput = (
            document.createElement(
                "textarea"
            )
        );

        sourceInput.className = (
            "form-control form-control-sm "
            + "mrss-source-input"
        );

        sourceInput.rows = 7;

        sourceInput.placeholder = (
            "(((...)))\n\n"
            + "or\n\n"
            + ">name\n"
            + "GGGAAACCC\n"
            + "(((...)))"
        );

        sourceLabel.appendChild(
            sourceInput
        );

        const fileLabel = createElement(
            "label"
        );

        fileLabel.appendChild(
            createElement(
                "span",
                "",
                "Source file",
            )
        );

        const fileInput = (
            document.createElement(
                "input"
            )
        );

        fileInput.type = "file";
        fileInput.className = (
            "form-control form-control-sm"
        );
        fileInput.accept = (
            ".dbn,.txt,text/plain"
        );

        fileLabel.appendChild(
            fileInput
        );

        const noteLabel = createElement(
            "label",
            "mrss-form-wide",
        );

        noteLabel.appendChild(
            createElement(
                "span",
                "",
                "Source note",
            )
        );

        const noteInput = (
            document.createElement(
                "textarea"
            )
        );

        noteInput.className = (
            "form-control form-control-sm"
        );
        noteInput.rows = 2;

        noteLabel.appendChild(
            noteInput
        );

        const formGuidance = createElement(
            "div",
            "mrss-form-guidance mrss-form-wide",
            (
                "Use either the text field or one source file, "
                + "not both. R1C accepts only canonical "
                + "dot-bracket '.', '(' and ')'."
            ),
        );

        const formStatus = createElement(
            "div",
            "mrss-form-status mrss-form-wide",
            "",
        );

        formStatus.setAttribute(
            "role",
            "status",
        );

        formStatus.setAttribute(
            "aria-live",
            "polite",
        );

        const formActions = createElement(
            "div",
            "mrss-form-actions mrss-form-wide",
        );

        const saveButton = createElement(
            "button",
            "btn btn-sm btn-primary",
            "Save structure",
        );

        saveButton.type = "submit";

        const clearButton = createElement(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Clear",
        );

        clearButton.type = "button";

        formActions.append(
            saveButton,
            clearButton,
        );

        form.append(
            nameLabel,
            methodLabel,
            sourceLabel,
            fileLabel,
            noteLabel,
            formGuidance,
            formStatus,
            formActions,
        );

        editor.append(
            editorHeader,
            form,
        );

        card.append(
            header,
            body,
            editor,
        );

        /*
         * R1D deliberately reuses the panel emitted by the
         * Molecular Workspace template. Do not insert a second
         * detached RNA card elsewhere in the page.
         */

        function setStatus(
            message,
            kind = "",
        ) {
            status.textContent = (
                message
            );

            status.dataset.kind = (
                kind
            );
        }

        function setFormStatus(
            message,
            kind = "",
        ) {
            formStatus.textContent = (
                message
            );

            formStatus.dataset.kind = (
                kind
            );
        }

        async function requestJson(
            url,
            options = {},
        ) {
            const response = await fetch(
                url,
                {
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                        ...(
                            options.headers
                            || {}
                        ),
                    },
                    ...options,
                },
            );

            let payload;

            try {
                payload = await response.json();
            } catch (_error) {
                throw new Error(
                    (
                        "The RNA secondary-structure endpoint "
                        + "returned an invalid response."
                    )
                );
            }

            if (!response.ok) {
                throw new Error(
                    payload.message
                    || (
                        "RNA secondary-structure request "
                        + `failed (${response.status}).`
                    )
                );
            }

            return payload;
        }

        function detailUrl(
            structureId,
        ) {
            const url = new URL(
                apiUrl,
                window.location.href,
            );

            url.searchParams.set(
                "structure_id",
                String(
                    structureId
                ),
            );

            return url.toString();
        }

        function currentSequence() {
            return normalizedSequence(
                workspaceSnapshot()
                    ?.sequence
            );
        }

        function sequenceIsSafeForRenderer(
            payload,
        ) {
            const current = (
                currentSequence()
            );

            if (!current) {
                return false;
            }

            if (
                initialSequence
                && current !== initialSequence
            ) {
                return false;
            }

            if (
                Number(
                    payload
                        ?.structure_length
                    || 0
                )
                !== current.length
            ) {
                return false;
            }

            return true;
        }

        function clearViewer(
            message,
        ) {
            currentForna = null;

            viewerShell.replaceChildren(
                createElement(
                    "div",
                    "mw-empty mrss-viewer-empty",
                    message,
                )
            );
        }

        function renderMetadata(
            payload,
        ) {
            metadata.replaceChildren();

            if (!payload) {
                return;
            }

            const items = [
                [
                    "Name",
                    (
                        payload.name
                        || "Secondary structure"
                    ),
                ],
                [
                    "Format",
                    (
                        payload.source_format_label
                        || payload.source_format
                    ),
                ],
                [
                    "Length",
                    `${payload.structure_length} nt`,
                ],
                [
                    "Base pairs",
                    payload.pair_count,
                ],
                [
                    "MFE",
                    (
                        payload.minimum_free_energy
                        !== null
                        && payload.minimum_free_energy
                        !== undefined
                            ? `${payload.minimum_free_energy}`
                            : "Not supplied"
                    ),
                ],
                [
                    "Method",
                    (
                        payload.source_method
                        || "Not supplied"
                    ),
                ],
                [
                    "File",
                    (
                        payload.original_filename
                        || "Direct text"
                    ),
                ],
            ];

            for (
                const [
                    label,
                    value,
                ]
                of items
            ) {
                const item = createElement(
                    "div",
                    "mrss-metadata-item",
                );

                item.append(
                    createElement(
                        "span",
                        "",
                        label,
                    ),
                    createElement(
                        "strong",
                        "",
                        value ?? "—",
                    ),
                );

                metadata.appendChild(
                    item
                );
            }
        }

        function updatePayloadUi(
            payload,
        ) {
            currentPayload = payload;

            renderMetadata(
                payload
            );

            structureCode.textContent = (
                payload.structure
                || ""
            );

            structureCodeWrap.hidden = (
                !payload.structure
            );

            sourceText.textContent = (
                payload.source_text
                || payload.structure
                || ""
            );

            provenance.hidden = false;

            copyButton.disabled = false;
            resetButton.disabled = false;

            if (canEdit) {
                deleteButton.disabled = false;
            }
        }

        async function renderStructure(
            payload,
        ) {
            updatePayloadUi(
                payload
            );

            if (
                !sequenceIsSafeForRenderer(
                    payload
                )
            ) {
                currentSequenceDrift = true;
                sequenceWarning.hidden = false;

                clearViewer(
                    (
                        "Rendering is paused because the current "
                        + "workspace sequence differs from the "
                        + "saved sequence state used when this "
                        + "secondary structure was loaded."
                    )
                );

                setStatus(
                    "Sequence changed — reload required",
                    "warning",
                );

                return;
            }

            currentSequenceDrift = false;
            sequenceWarning.hidden = true;

            clearViewer(
                "Loading local Forna renderer…"
            );

            setStatus(
                "Loading structure…",
                "busy",
            );

            const library = (
                await loadFornaVendor(
                    vendorUrl
                )
            );

            if (
                !library
                    ?.FornaContainer
            ) {
                throw new Error(
                    "FornaContainer is unavailable."
                );
            }

            const sequence = (
                currentSequence()
            );

            const mount = createElement(
                "div",
                "mrss-forna-mount",
            );

            mount.id = (
                "mrss-forna-mount"
            );

            viewerShell.replaceChildren(
                mount
            );

            const container = (
                new library.FornaContainer(
                    "#mrss-forna-mount",
                    {
                        applyForce: false,
                        allowPanningAndZooming: true,
                        resizeSvgOnResize: true,
                        transitionDuration: 0,
                    },
                )
            );

            /*
             * Forna contains optional keyboard editing behavior.
             * This integration is visualization-only.
             * Persisted dot-bracket remains authoritative.
             */
            container.deaf = true;

            container.addRNA(
                payload.structure,
                {
                    sequence,
                    name: (
                        payload.name
                        || "RNA"
                    ),
                    avoidOthers: true,
                },
            );

            container.changeColorScheme(
                scheme.value
            );

            container.setSize();

            currentForna = container;

            setStatus(
                (
                    `${payload.structure_length} nt · `
                    + `${payload.pair_count} base pairs`
                ),
                "ready",
            );
        }

        function renderList() {
            list.replaceChildren();

            count.textContent = String(
                structures.length
            );

            listEmpty.hidden = (
                structures.length > 0
            );

            for (
                const structure
                of structures
            ) {
                const button = createElement(
                    "button",
                    (
                        "mrss-list-item"
                        + (
                            structure.id
                            === selectedId
                                ? " is-active"
                                : ""
                        )
                    ),
                );

                button.type = "button";

                const title = createElement(
                    "strong",
                    "",
                    (
                        structure.name
                        || "Secondary structure"
                    ),
                );

                const detail = createElement(
                    "span",
                    "",
                    (
                        `${structure.structure_length} nt · `
                        + `${structure.pair_count} pairs · `
                        + (
                            structure.source_format_label
                            || structure.source_format
                        )
                    ),
                );

                button.append(
                    title,
                    detail,
                );

                button.addEventListener(
                    "click",
                    () => {
                        openStructure(
                            structure.id
                        );
                    },
                );

                list.appendChild(
                    button
                );
            }
        }

        async function openStructure(
            structureId,
        ) {
            selectedId = Number(
                structureId
            );

            renderList();

            setStatus(
                "Loading structure…",
                "busy",
            );

            try {
                const response = (
                    await requestJson(
                        detailUrl(
                            selectedId
                        )
                    )
                );

                await renderStructure(
                    response
                        .secondary_structure
                );

            } catch (error) {
                console.error(
                    error
                );

                clearViewer(
                    (
                        error.message
                        || "Could not open secondary structure."
                    )
                );

                setStatus(
                    (
                        error.message
                        || "Secondary-structure error"
                    ),
                    "error",
                );
            }
        }

        async function loadStructures() {
            setStatus(
                "Checking structures…",
                "busy",
            );

            try {
                const response = (
                    await requestJson(
                        apiUrl
                    )
                );

                structures = (
                    Array.isArray(
                        response
                            .secondary_structures
                    )
                        ? response
                            .secondary_structures
                        : []
                );

                renderList();

                if (structures.length) {
                    /*
                     * The Forna vendor remains lazy. It is not
                     * required for an RNA record with zero stored
                     * secondary structures.
                     */
                    await openStructure(
                        structures[0].id
                    );

                } else {
                    setStatus(
                        "No secondary structure attached",
                        "empty",
                    );
                }

            } catch (error) {
                console.error(
                    error
                );

                setStatus(
                    (
                        error.message
                        || "Could not load structures."
                    ),
                    "error",
                );
            }
        }

        function resetForm() {
            form.reset();

            setFormStatus(
                ""
            );
        }

        async function saveStructure(
            event,
        ) {
            event.preventDefault();

            if (!canEdit) {
                return;
            }

            const text = (
                sourceInput.value
                    .trim()
            );

            const file = (
                fileInput.files
                    ?.[0]
                || null
            );

            if (
                !text
                && !file
            ) {
                setFormStatus(
                    (
                        "Enter dot-bracket/DBN text "
                        + "or choose a source file."
                    ),
                    "error",
                );
                return;
            }

            if (
                text
                && file
            ) {
                setFormStatus(
                    (
                        "Use either source text or "
                        + "one source file, not both."
                    ),
                    "error",
                );
                return;
            }

            const data = new FormData();

            data.append(
                "action",
                "save",
            );

            if (text) {
                data.append(
                    "source_text",
                    sourceInput.value,
                );
            }

            if (file) {
                data.append(
                    "file",
                    file,
                );
            }

            if (
                nameInput.value.trim()
            ) {
                data.append(
                    "name",
                    nameInput.value.trim(),
                );
            }

            if (
                methodInput.value.trim()
            ) {
                data.append(
                    "source_method",
                    methodInput.value.trim(),
                );
            }

            if (
                noteInput.value.trim()
            ) {
                data.append(
                    "source_note",
                    noteInput.value.trim(),
                );
            }

            saveButton.disabled = true;

            setFormStatus(
                "Saving structure…",
                "busy",
            );

            setStatus(
                "Saving structure…",
                "busy",
            );

            try {
                const response = (
                    await requestJson(
                        apiUrl,
                        {
                            method: "POST",
                            headers: {
                                "X-CSRFToken": (
                                    csrfToken
                                ),
                            },
                            body: data,
                        },
                    )
                );

                const payload = (
                    response
                        .secondary_structure
                );

                structures = [
                    payload,
                    ...structures.filter(
                        item => (
                            item.id
                            !== payload.id
                        ),
                    ),
                ];

                selectedId = (
                    payload.id
                );

                renderList();

                resetForm();
                editor.hidden = true;

                await renderStructure(
                    payload
                );

            } catch (error) {
                console.error(
                    error
                );

                setFormStatus(
                    (
                        error.message
                        || "Could not save structure."
                    ),
                    "error",
                );

                setStatus(
                    (
                        error.message
                        || "Save failed"
                    ),
                    "error",
                );

            } finally {
                saveButton.disabled = false;
            }
        }

        async function deleteSelected() {
            if (
                !canEdit
                || !selectedId
            ) {
                return;
            }

            const selected = (
                structures.find(
                    item => (
                        item.id
                        === selectedId
                    )
                )
            );

            if (
                !window.confirm(
                    (
                        "Remove secondary structure "
                        + (
                            selected
                                ?.name
                            || selectedId
                        )
                        + " from this RNA record?"
                    )
                )
            ) {
                return;
            }

            const data = new FormData();

            data.append(
                "action",
                "delete",
            );

            data.append(
                "structure_id",
                String(
                    selectedId
                ),
            );

            deleteButton.disabled = true;

            setStatus(
                "Removing structure…",
                "busy",
            );

            try {
                await requestJson(
                    apiUrl,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": (
                                csrfToken
                            ),
                        },
                        body: data,
                    },
                );

                structures = (
                    structures.filter(
                        item => (
                            item.id
                            !== selectedId
                        ),
                    )
                );

                selectedId = null;
                currentPayload = null;
                currentForna = null;

                renderList();

                metadata.replaceChildren();

                structureCodeWrap.hidden = true;
                structureCode.textContent = "";

                provenance.hidden = true;
                sourceText.textContent = "";

                copyButton.disabled = true;
                resetButton.disabled = true;
                deleteButton.disabled = true;

                sequenceWarning.hidden = true;

                clearViewer(
                    (
                        "Choose a stored secondary structure "
                        + "to open the RNA renderer."
                    )
                );

                if (structures.length) {
                    await openStructure(
                        structures[0].id
                    );

                } else {
                    setStatus(
                        "No secondary structure attached",
                        "empty",
                    );
                }

            } catch (error) {
                console.error(
                    error
                );

                setStatus(
                    (
                        error.message
                        || "Could not remove structure."
                    ),
                    "error",
                );

                deleteButton.disabled = false;
            }
        }

        async function copySource() {
            if (!currentPayload) {
                return;
            }

            const text = (
                currentPayload
                    .source_text
                || currentPayload
                    .structure
                || ""
            );

            if (!text) {
                return;
            }

            try {
                await navigator
                    .clipboard
                    .writeText(
                        text
                    );

                setStatus(
                    "Source copied",
                    "ready",
                );

            } catch (_error) {
                const textarea = (
                    document.createElement(
                        "textarea"
                    )
                );

                textarea.value = text;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";

                document.body.appendChild(
                    textarea
                );

                textarea.select();

                document.execCommand(
                    "copy"
                );

                textarea.remove();

                setStatus(
                    "Source copied",
                    "ready",
                );
            }
        }

        addButton.addEventListener(
            "click",
            () => {
                editor.hidden = false;
                sourceInput.focus();
            },
        );

        closeEditor.addEventListener(
            "click",
            () => {
                editor.hidden = true;
            },
        );

        clearButton.addEventListener(
            "click",
            resetForm,
        );

        form.addEventListener(
            "submit",
            saveStructure,
        );

        scheme.addEventListener(
            "change",
            () => {
                if (
                    currentForna
                    && !currentSequenceDrift
                ) {
                    currentForna
                        .changeColorScheme(
                            scheme.value
                        );
                }
            },
        );

        resetButton.addEventListener(
            "click",
            () => {
                if (!currentPayload) {
                    return;
                }

                renderStructure(
                    currentPayload
                ).catch(
                    error => {
                        console.error(
                            error
                        );

                        setStatus(
                            (
                                error.message
                                || "Could not reset RNA view."
                            ),
                            "error",
                        );
                    },
                );
            },
        );

        copyButton.addEventListener(
            "click",
            () => {
                copySource().catch(
                    error => {
                        console.error(
                            error
                        );
                    },
                );
            },
        );

        deleteButton.addEventListener(
            "click",
            () => {
                deleteSelected().catch(
                    error => {
                        console.error(
                            error
                        );
                    },
                );
            },
        );

        root.addEventListener(
            "biobank:molecular-workspace-change",
            event => {
                const sequence = (
                    normalizedSequence(
                        event.detail
                            ?.snapshot
                            ?.sequence
                    )
                );

                const drift = (
                    Boolean(
                        initialSequence
                    )
                    && sequence
                    !== initialSequence
                );

                currentSequenceDrift = drift;

                if (
                    drift
                    && currentPayload
                ) {
                    sequenceWarning.hidden = false;

                    clearViewer(
                        (
                            "Rendering is paused because the RNA "
                            + "sequence has changed in the editor. "
                            + "Save/reload the record before using "
                            + "persisted secondary structures."
                        )
                    );

                    setStatus(
                        "Sequence changed — reload required",
                        "warning",
                    );
                }
            },
        );

        async function activateSecondaryStructureView() {
            if (structuresLoaded) {
                window.requestAnimationFrame(
                    () => currentForna?.setSize?.()
                );
                return;
            }

            structuresLoaded = true;
            await loadStructures();
        }

        root.addEventListener(
            "biobank:molecular-view-change",
            event => {
                if (
                    event.detail?.view
                    === "secondary-structure"
                ) {
                    void activateSecondaryStructureView();
                }
            }
        );

        if (
            root.dataset.workspaceView
            === "secondary-structure"
        ) {
            void activateSecondaryStructureView();
        } else {
            setStatus(
                "Open Secondary structure to load stored structures.",
                "ready",
            );
        }
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
