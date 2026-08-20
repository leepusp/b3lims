(() => {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener(
                "DOMContentLoaded",
                callback,
                {once: true}
            );
        } else {
            callback();
        }
    }

    function csrfToken(form) {
        return form.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        )?.value || "";
    }

    function formatNumber(value) {
        return Number(value || 0).toLocaleString();
    }

    function fieldValue(field) {
        return field?.value || "";
    }

    ready(() => {
        const form = document.getElementById(
            "molecular-registry-create-form"
        );

        if (!form) {
            return;
        }

        const fields = {
            name: document.getElementById(
                "molecule-name"
            ),
            type: document.getElementById(
                "molecule-type"
            ),
            topology: document.getElementById(
                "molecule-topology"
            ),
            sequence: document.getElementById(
                "molecule-sequence"
            ),
            description: document.getElementById(
                "molecule-description"
            ),
            submit: form.querySelector(
                'button[type="submit"]'
            ),
        };

        const cardBody = (
            form.querySelector(".card-body")
            || form
        );

        const section = document.createElement(
            "section"
        );

        section.className = "mri-import";
        section.setAttribute(
            "aria-label",
            "Molecular record creation mode"
        );

        section.innerHTML = `
            <div class="mri-mode-switch"
                 role="group"
                 aria-label="Creation mode">
                <button type="button"
                        class="mri-mode-button is-active"
                        data-mri-mode="blank"
                        aria-pressed="true">
                    <i class="bi bi-pencil-square"></i>
                    Blank record
                </button>

                <button type="button"
                        class="mri-mode-button"
                        data-mri-mode="import"
                        aria-pressed="false">
                    <i class="bi bi-upload"></i>
                    Import sequence file
                </button>
            </div>

            <div class="mri-import-panel" hidden>
                <input type="file"
                       id="molecular-registry-file"
                       name="molecular_file"
                       accept=".dna,.gb,.gbk,.gbff,.genbank,.ape,.embl,.fa,.fasta,.fna,.ffn,.faa,.frn,.txt,application/octet-stream,text/plain"
                       accept=".dna,.gb,.gbk,.gbff,.genbank,.ape,.embl,.fa,.fasta,.fna,.ffn,.faa,.frn,.txt,application/octet-stream,text/plain"
                       hidden>

                <button type="button"
                        class="mri-drop-zone"
                        id="molecular-registry-drop-zone">
                    <span class="mri-drop-icon">
                        <i class="bi bi-file-earmark-arrow-up"></i>
                    </span>

                    <span class="mri-drop-copy">
                        <strong>
                            Drop a molecular file here or browse
                        </strong>
                        <small>
                            SnapGene .dna, GenBank, ApE, EMBL,
                            FASTA or plain sequence text
                        </small>
                    </span>
                </button>

                <div class="mri-import-status"
                     role="status"
                     aria-live="polite"></div>

                <div class="mri-import-summary"
                     hidden>
                    <div class="mri-summary-header">
                        <div>
                            <strong class="mri-summary-name"></strong>
                            <span class="mri-summary-file"></span>
                        </div>

                        <button type="button"
                                class="btn btn-sm btn-outline-secondary"
                                data-mri-remove-file>
                            Remove file
                        </button>
                    </div>

                    <dl class="mri-summary-grid">
                        <div>
                            <dt>Format</dt>
                            <dd data-mri-summary="format">—</dd>
                        </div>
                        <div>
                            <dt>Record type</dt>
                            <dd data-mri-summary="type">—</dd>
                        </div>
                        <div>
                            <dt>Topology</dt>
                            <dd data-mri-summary="topology">—</dd>
                        </div>
                        <div>
                            <dt>Length</dt>
                            <dd data-mri-summary="length">—</dd>
                        </div>
                        <div>
                            <dt>Annotations</dt>
                            <dd data-mri-summary="features">—</dd>
                        </div>
                        <div>
                            <dt>Warnings</dt>
                            <dd data-mri-summary="warnings">—</dd>
                        </div>
                    </dl>

                    <div class="mri-warning-list"
                         hidden></div>

                    <div class="mri-detection"
                         data-mri-detection
                         hidden>
                        <dl class="mri-detection-grid">
                            <div>
                                <dt>Detected content</dt>
                                <dd data-mri-detection-value="content">—</dd>
                            </div>

                            <div>
                                <dt>Suggested type</dt>
                                <dd data-mri-detection-value="suggested">—</dd>
                            </div>

                            <div>
                                <dt>Confidence</dt>
                                <dd data-mri-detection-value="confidence">—</dd>
                            </div>

                            <div class="mri-detection-reason">
                                <dt>Why</dt>
                                <dd data-mri-detection-value="reason">—</dd>
                            </div>
                        </dl>

                        <label class="mri-type-confirmation"
                               data-mri-type-confirmation
                               hidden>
                            <input type="checkbox"
                                   name="type_confirmation"
                                   value="confirmed"
                                   disabled>

                            <span>
                                I confirm that the selected record type
                                correctly represents this nucleotide sequence.
                            </span>
                        </label>
                    </div>

                    <p class="mri-import-note">
                        Review the populated fields below. The record
                        and its annotations are created only after
                        clicking <strong>Create imported record</strong>.
                    </p>
                </div>
            </div>
        `;

        cardBody.prepend(section);

        const modeButtons = [
            ...section.querySelectorAll(
                "[data-mri-mode]"
            ),
        ];

        const importPanel = section.querySelector(
            ".mri-import-panel"
        );

        const fileInput = section.querySelector(
            "#molecular-registry-file"
        );

        const dropZone = section.querySelector(
            "#molecular-registry-drop-zone"
        );

        const status = section.querySelector(
            ".mri-import-status"
        );

        const summary = section.querySelector(
            ".mri-import-summary"
        );

        const summaryName = section.querySelector(
            ".mri-summary-name"
        );

        const summaryFile = section.querySelector(
            ".mri-summary-file"
        );

        const warningList = section.querySelector(
            ".mri-warning-list"
        );

        const removeFile = section.querySelector(
            "[data-mri-remove-file]"
        );

        const summaryFields = Object.fromEntries(
            [
                ...section.querySelectorAll(
                    "[data-mri-summary]"
                ),
            ].map(
                node => [
                    node.dataset.mriSummary,
                    node,
                ]
            )
        );

        let mode = "blank";
        let manualSnapshot = null;
        let importedRecord = null;
        let previewRequest = 0;
        const detectionPanel = section.querySelector(
            "[data-mri-detection]"
        );

        const detectionValues = {
            content: section.querySelector(
                '[data-mri-detection-value="content"]'
            ),
            suggested: section.querySelector(
                '[data-mri-detection-value="suggested"]'
            ),
            confidence: section.querySelector(
                '[data-mri-detection-value="confidence"]'
            ),
            reason: section.querySelector(
                '[data-mri-detection-value="reason"]'
            ),
        };

        const typeConfirmation = section.querySelector(
            "[data-mri-type-confirmation]"
        );

        const typeConfirmationInput = (
            typeConfirmation
                ?.querySelector(
                    'input[name="type_confirmation"]'
                )
        );

        const sequenceTypeField = (
            form.elements.namedItem(
                "sequence_type"
            )
        );


        function snapshotFields() {
            return {
                name: fieldValue(fields.name),
                type: fieldValue(fields.type),
                topology: fieldValue(
                    fields.topology
                ),
                sequence: fieldValue(
                    fields.sequence
                ),
                description: fieldValue(
                    fields.description
                ),
            };
        }

        function restoreFields(snapshot) {
            if (!snapshot) {
                return;
            }

            fields.name.value = snapshot.name;
            fields.type.value = snapshot.type;
            fields.topology.value = snapshot.topology;
            fields.sequence.value = snapshot.sequence;
            fields.description.value = (
                snapshot.description
            );
        }

        function setStatus(
            message,
            state = ""
        ) {
            status.textContent = message;
            status.classList.remove(
                "is-error",
                "is-success",
                "is-loading"
            );

            if (state) {
                status.classList.add(
                    `is-${state}`
                );
            }
        }

        function setMode(nextMode) {
            const resolved = (
                nextMode === "import"
                    ? "import"
                    : "blank"
            );

            if (
                resolved === "import"
                && mode !== "import"
            ) {
                manualSnapshot = snapshotFields();
            }

            mode = resolved;

            modeButtons.forEach(button => {
                const active = (
                    button.dataset.mriMode
                    === resolved
                );

                button.classList.toggle(
                    "is-active",
                    active
                );

                button.setAttribute(
                    "aria-pressed",
                    String(active)
                );
            });

            importPanel.hidden = (
                resolved !== "import"
            );

            if (fields.submit) {
                fields.submit.textContent = (
                    resolved === "import"
                        ? "Create imported record"
                        : "Create record"
                );
            }

            if (resolved === "blank") {
                previewRequest += 1;
                importedRecord = null;
                fileInput.value = "";
                summary.hidden = true;
                warningList.hidden = true;
                warningList.replaceChildren();
                setStatus("");
                restoreFields(manualSnapshot);
            }
        }

        function compatibleTypes(record) {
            return Array.isArray(
                record
                    ?.compatible_sequence_types
            )
                ? record
                    .compatible_sequence_types
                    .map(
                        value => String(
                            value
                        )
                    )
                : [];
        }

        function typeLabel(value) {
            const option = (
                sequenceTypeField
                    ? [
                        ...sequenceTypeField.options,
                    ].find(
                        item => (
                            item.value
                            === value
                        ),
                    )
                    : null
            );

            return (
                option
                    ?.textContent
                    ?.trim()
                || value
                || "Molecular"
            );
        }

        function topologyForType(
            sequenceType,
            suggestedTopology,
        ) {
            if (
                sequenceType === "plasmid"
            ) {
                return "circular";
            }

            if (
                [
                    "protein",
                    "primer",
                    "insert",
                ].includes(
                    sequenceType
                )
            ) {
                return "linear";
            }

            return (
                suggestedTopology
                === "circular"
                    ? "circular"
                    : "linear"
            );
        }

        function applyTopologyPolicy(
            sequenceType,
            suggestedTopology,
        ) {
            if (!fields.topology) {
                return;
            }

            const resolved = (
                topologyForType(
                    sequenceType,
                    suggestedTopology,
                )
            );

            fields.topology.value = (
                resolved
            );

            [
                ...fields.topology.options,
            ].forEach(
                option => {
                    if (
                        sequenceType
                        === "plasmid"
                    ) {
                        option.disabled = (
                            option.value
                            !== "circular"
                        );

                        return;
                    }

                    if (
                        [
                            "protein",
                            "primer",
                            "insert",
                        ].includes(
                            sequenceType
                        )
                    ) {
                        option.disabled = (
                            option.value
                            !== "linear"
                        );

                        return;
                    }

                    option.disabled = false;
                },
            );

            fields.topology.dataset
                .typeAwarePolicy = (
                    sequenceType
                );
        }

        function refreshCreateButtonLabel() {
            const submit = form.querySelector(
                'button[type="submit"]'
            );

            if (
                !submit
                || mode !== "import"
                || !importedRecord
            ) {
                return;
            }

            const chosen = (
                sequenceTypeField
                    ?.value
                || importedRecord
                    .suggested_sequence_type
                || importedRecord
                    .sequence_type
                || "dna"
            );

            submit.textContent = (
                `Create ${typeLabel(chosen)} record`
            );
        }

        function resetTypeAwareImport() {
            if (detectionPanel) {
                detectionPanel.hidden = true;
            }

            if (typeConfirmation) {
                typeConfirmation.hidden = true;
            }

            if (typeConfirmationInput) {
                typeConfirmationInput.checked = false;
                typeConfirmationInput.disabled = true;
            }

            if (sequenceTypeField) {
                [
                    ...sequenceTypeField.options,
                ].forEach(
                    option => {
                        option.disabled = false;
                    },
                );
            }

            if (fields.topology) {
                [
                    ...fields.topology.options,
                ].forEach(
                    option => {
                        option.disabled = false;
                    },
                );
            }
        }

        function renderDetection(record) {
            if (!detectionPanel) {
                return;
            }

            detectionPanel.hidden = false;

            detectionValues.content.textContent = (
                record
                    .detected_content_label
                || record
                    .detected_content
                || "Unknown"
            );

            detectionValues.suggested.textContent = (
                record
                    .suggested_sequence_type_label
                || typeLabel(
                    record
                        .suggested_sequence_type
                    || record
                        .sequence_type
                )
            );

            detectionValues.confidence.textContent = (
                record
                    .detection_confidence_label
                || record
                    .detection_confidence
                || "Unknown"
            );

            detectionValues.reason.textContent = (
                record
                    .detection_reason
                || "No detection explanation was provided."
            );

            const requiresConfirmation = Boolean(
                record
                    .requires_type_confirmation
            );

            if (typeConfirmation) {
                typeConfirmation.hidden = (
                    !requiresConfirmation
                );
            }

            if (typeConfirmationInput) {
                typeConfirmationInput.checked = false;

                typeConfirmationInput.disabled = (
                    !requiresConfirmation
                );
            }
        }

        function renderTypeAwareFields(
            record,
        ) {
            const compatible = (
                compatibleTypes(
                    record
                )
            );

            const suggested = String(
                record
                    .suggested_sequence_type
                || record
                    .sequence_type
                || "dna"
            );

            if (sequenceTypeField) {
                [
                    ...sequenceTypeField.options,
                ].forEach(
                    option => {
                        option.disabled = (
                            compatible.length > 0
                            && !compatible.includes(
                                option.value
                            )
                        );
                    },
                );

                const usableSuggested = (
                    compatible.length === 0
                    || compatible.includes(
                        suggested
                    )
                )
                    ? suggested
                    : compatible[0];

                sequenceTypeField.value = (
                    usableSuggested
                );

                applyTopologyPolicy(
                    usableSuggested,
                    record.topology,
                );
            }

            renderDetection(
                record
            );

            refreshCreateButtonLabel();
        }

        function fillImportedFields(record) {
            fields.name.value = String(
                record.name || ""
            );

            renderTypeAwareFields(record);



            fields.sequence.value = String(
                record.sequence || ""
            );

            fields.description.value = String(
                record.description || ""
            );
        }

        function renderWarnings(warnings) {
            warningList.replaceChildren();

            if (!warnings.length) {
                warningList.hidden = true;
                return;
            }

            const heading = document.createElement(
                "strong"
            );

            heading.textContent = "Import warnings";

            const list = document.createElement(
                "ul"
            );

            warnings.slice(0, 10).forEach(
                warning => {
                    const item = (
                        document.createElement("li")
                    );

                    item.textContent = String(
                        warning
                    );

                    list.appendChild(item);
                }
            );

            warningList.append(
                heading,
                list
            );

            warningList.hidden = false;
        }

        function renderSummary(
            record,
            file
        ) {
            const warnings = Array.isArray(
                record.warnings
            )
                ? record.warnings
                : [];

            summaryName.textContent = (
                record.name
                || "Imported molecular sequence"
            );

            summaryFile.textContent = file.name;

            summaryFields.format.textContent = (
                record.format_label
                || record.format
                || "Unknown"
            );

            summaryFields.type.textContent = (
                record.sequence_type_label
                || record.sequence_type
                || "Unknown"
            );

            summaryFields.topology.textContent = (
                record.topology === "circular"
                    ? "Circular"
                    : "Linear"
            );

            summaryFields.length.textContent = (
                `${formatNumber(record.length)} symbols`
            );

            summaryFields.features.textContent = (
                formatNumber(
                    record.feature_count
                )
            );

            summaryFields.warnings.textContent = (
                formatNumber(warnings.length)
            );

            renderWarnings(warnings);

            summary.hidden = false;
        }

        async function previewFile(file) {
            resetTypeAwareImport();

            if (!file) {
                return;
            }

            if (
                file.size > 20 * 1024 * 1024
            ) {
                setStatus(
                    "The selected file exceeds the 20 MiB limit.",
                    "error"
                );
                fileInput.value = "";
                return;
            }

            const requestId = ++previewRequest;
            const formData = new FormData();

            formData.append(
                "file",
                file,
                file.name
            );

            setStatus(
                `Reading ${file.name}...`,
                "loading"
            );

            summary.hidden = true;

            try {
                const response = await fetch(
                    form.dataset.importPreviewUrl,
                    {
                        method: "POST",
                        headers: {
                            Accept: "application/json",
                            "X-CSRFToken": (
                                csrfToken(form)
                            ),
                        },
                        credentials: "same-origin",
                        body: formData,
                    }
                );

                const data = await response.json();

                if (
                    !response.ok
                    || data.status === "error"
                ) {
                    throw new Error(
                        data.message
                        || `HTTP ${response.status}`
                    );
                }

                if (requestId !== previewRequest) {
                    return;
                }

                importedRecord = data.record;

                fillImportedFields(
                    importedRecord
                );

                renderSummary(
                    importedRecord,
                    file
                );

                setStatus(
                    (
                        `${file.name} loaded. `
                        + "Review the record before creation."
                    ),
                    "success"
                );
            } catch (error) {
                if (requestId !== previewRequest) {
                    return;
                }

                importedRecord = null;
                summary.hidden = true;

                setStatus(
                    error.message,
                    "error"
                );
            }
        }

        function assignDroppedFile(file) {
            const transfer = new DataTransfer();

            transfer.items.add(file);
            fileInput.files = transfer.files;
        }

        modeButtons.forEach(button => {
            button.addEventListener(
                "click",
                () => {
                    setMode(
                        button.dataset.mriMode
                    );
                }
            );
        });

        dropZone.addEventListener(
            "click",
            () => fileInput.click()
        );

        fileInput.addEventListener(
            "change",
            () => {
                const file = (
                    fileInput.files?.[0]
                );

                if (file) {
                    previewFile(file);
                }
            }
        );

        [
            "dragenter",
            "dragover",
        ].forEach(eventName => {
            dropZone.addEventListener(
                eventName,
                event => {
                    event.preventDefault();

                    dropZone.classList.add(
                        "is-dragging"
                    );
                }
            );
        });

        [
            "dragleave",
            "drop",
        ].forEach(eventName => {
            dropZone.addEventListener(
                eventName,
                event => {
                    event.preventDefault();

                    dropZone.classList.remove(
                        "is-dragging"
                    );
                }
            );
        });

        dropZone.addEventListener(
            "drop",
            event => {
                const file = (
                    event.dataTransfer
                        ?.files?.[0]
                );

                if (!file) {
                    return;
                }

                assignDroppedFile(file);
                previewFile(file);
            }
        );

        removeFile.addEventListener(
            "click",
            () => {
                previewRequest += 1;
                importedRecord = null;
                fileInput.value = "";
                summary.hidden = true;
                warningList.hidden = true;
                warningList.replaceChildren();

                setStatus(
                    "Select another molecular file."
                );
            }
        );

        sequenceTypeField?.addEventListener(
            "change",
            () => {
                if (
                    mode !== "import"
                    || !importedRecord
                ) {
                    return;
                }

                applyTopologyPolicy(
                    sequenceTypeField.value,
                    importedRecord.topology,
                );

                if (
                    importedRecord
                        .requires_type_confirmation
                    && typeConfirmationInput
                ) {
                    typeConfirmationInput.checked = false;
                }

                refreshCreateButtonLabel();
            },
        );

        removeFile.addEventListener(
            "click",
            resetTypeAwareImport,
        );

        section.querySelectorAll(
            "[data-mri-mode]"
        ).forEach(
            button => {
                button.addEventListener(
                    "click",
                    () => {
                        if (
                            button.dataset.mriMode
                            !== "import"
                        ) {
                            resetTypeAwareImport();
                        }
                    },
                );
            },
        );

        form.addEventListener(
            "submit",
            event => {
                if (
                    mode !== "import"
                    || !importedRecord
                ) {
                    return;
                }

                const selectedType = (
                    sequenceTypeField
                        ?.value
                    || ""
                );

                const compatible = (
                    compatibleTypes(
                        importedRecord
                    )
                );

                if (
                    compatible.length > 0
                    && !compatible.includes(
                        selectedType
                    )
                ) {
                    event.preventDefault();
                    event.stopImmediatePropagation();

                    setStatus(
                        (
                            `${typeLabel(selectedType)} is not `
                            + "compatible with the detected sequence."
                        ),
                        "error",
                    );

                    return;
                }

                if (
                    importedRecord
                        .requires_type_confirmation
                    && !typeConfirmationInput
                        ?.checked
                ) {
                    event.preventDefault();
                    event.stopImmediatePropagation();

                    setStatus(
                        (
                            "Confirm the selected record type "
                            + "before creating this ambiguous "
                            + "nucleotide import."
                        ),
                        "error",
                    );

                    return;
                }

                applyTopologyPolicy(
                    selectedType,
                    importedRecord.topology,
                );
            },
            true,
        );

        form.addEventListener(
            "submit",
            event => {
                if (mode !== "import") {
                    fileInput.value = "";
                    return;
                }

                const file = (
                    fileInput.files?.[0]
                );

                if (!file) {
                    event.preventDefault();

                    setStatus(
                        (
                            "Select and preview a molecular "
                            + "file before creating the record."
                        ),
                        "error"
                    );

                    return;
                }

                if (!importedRecord) {
                    event.preventDefault();

                    setStatus(
                        (
                            "Wait for the file preview to "
                            + "finish before creating the record."
                        ),
                        "error"
                    );

                    return;
                }

                if (fields.submit) {
                    fields.submit.disabled = true;
                    fields.submit.textContent = (
                        "Creating imported record..."
                    );
                }
            }
        );

        setMode("blank");
    });
})();
