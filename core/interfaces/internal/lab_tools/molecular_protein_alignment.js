(() => {
    "use strict";

    const VERSION = (
        "20260812-protein-final-v1"
    );


    function parseBoolean(value) {
        return String(value).toLowerCase() === "true";
    }

    function createElement(
        tag,
        className,
        text,
    ) {
        const element = document.createElement(
            tag
        );

        if (className) {
            element.className = className;
        }

        if (
            text !== undefined
            && text !== null
        ) {
            element.textContent = text;
        }

        return element;
    }

    function initialize() {
        const root = document.getElementById(
            "molecular-workspace"
        );

        if (
            !root
            || root.dataset.sequenceType
            !== "protein"
        ) {
            return;
        }

        const apiUrl = (
            root.dataset
                .proteinAlignmentsUrl
            || ""
        );

        if (!apiUrl) {
            console.error(
                "Protein Alignment URL is unavailable."
            );

            return;
        }


        const canEdit = parseBoolean(
            root.dataset.canEdit
        );

        const csrfToken = (
            root.dataset.csrfToken
            || ""
        );

        let alignments = [];
        let selectedAlignmentId = null;
        let currentPayload = null;

        const card = createElement(
            "section",
            "mw-card mpa-card",
        );

        card.id = "mw-protein-alignment";
        card.dataset.proteinAlignmentVersion = (
            VERSION
        );

        const header = createElement(
            "div",
            "mw-card-header mpa-header",
        );

        const headingWrap = createElement(
            "div",
            "mpa-heading",
        );

        const heading = createElement(
            "h2",
            "",
            "Protein alignment",
        );

        const description = createElement(
            "p",
            "",
            (
                "Inspect a persisted multiple-sequence alignment "
                + "without changing the Protein record or its annotations."
            ),
        );

        headingWrap.append(
            heading,
            description,
        );

        const actions = createElement(
            "div",
            "mpa-actions",
        );

        const status = createElement(
            "span",
            "mpa-status",
            "Checking alignments…",
        );

        actions.appendChild(
            status
        );

        const uploadButton = createElement(
            "button",
            "btn btn-sm btn-outline-primary",
            "Upload alignment",
        );

        uploadButton.type = "button";

        const fileInput = document.createElement(
            "input"
        );

        fileInput.type = "file";

        fileInput.accept = (
            ".afa,.fa,.fasta,.aln,.sto,.stk,text/plain"
        );

        fileInput.hidden = true;

        if (canEdit) {
            actions.appendChild(
                uploadButton
            );
        }

        actions.appendChild(
            fileInput
        );

        header.append(
            headingWrap,
            actions,
        );

        const body = createElement(
            "div",
            "mpa-body",
        );

        const sidebar = createElement(
            "aside",
            "mpa-sidebar",
        );

        const listHeading = createElement(
            "div",
            "mpa-list-heading",
        );

        listHeading.append(
            createElement(
                "strong",
                "",
                "Stored alignments",
            ),
            createElement(
                "span",
                "mpa-count",
                "0",
            ),
        );

        const list = createElement(
            "div",
            "mpa-list",
        );

        const empty = createElement(
            "div",
            "mw-empty mpa-empty",
            (
                "No Protein alignment is attached yet. "
                + "Upload aligned FASTA, CLUSTAL, or Stockholm."
            ),
        );

        sidebar.append(
            listHeading,
            list,
            empty,
        );

        const main = createElement(
            "div",
            "mpa-main",
        );

        const toolbar = createElement(
            "div",
            "mpa-toolbar",
        );

        const metadata = createElement(
            "div",
            "mpa-metadata",
        );

        const schemeLabel = createElement(
            "label",
            "mpa-control",
        );

        schemeLabel.appendChild(
            createElement(
                "span",
                "",
                "Color scheme",
            )
        );

        const scheme = document.createElement(
            "select"
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
                    "clustal",
                    "Clustal",
                ],
                [
                    "clustal2",
                    "Clustal 2",
                ],
                [
                    "conservation",
                    "Conservation",
                ],
            ]
        ) {
            const option = document.createElement(
                "option"
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

        const focusButton = createElement(
            "button",
            "btn btn-sm btn-outline-secondary",
            "Reload view",
        );

        focusButton.type = "button";
        focusButton.disabled = true;

        const downloadLink = createElement(
            "a",
            "btn btn-sm btn-outline-secondary",
            "Download source",
        );

        downloadLink.hidden = true;

        const deleteButton = createElement(
            "button",
            "btn btn-sm btn-outline-danger",
            "Remove alignment",
        );

        deleteButton.type = "button";
        deleteButton.hidden = !canEdit;
        deleteButton.disabled = true;

        toolbar.append(
            schemeLabel,
            focusButton,
            downloadLink,
            deleteButton,
        );

        const queryMatch = createElement(
            "div",
            "mpa-query-match",
            "",
        );

        const viewerShell = createElement(
            "div",
            "mpa-viewer-shell",
        );

        const viewerEmpty = createElement(
            "div",
            "mw-empty mpa-viewer-empty",
            (
                "Choose an alignment to inspect the "
                + "aligned amino-acid sequences."
            ),
        );

        viewerShell.appendChild(
            viewerEmpty
        );

        main.append(
            metadata,
            queryMatch,
            toolbar,
            viewerShell,
        );

        body.append(
            sidebar,
            main,
        );

        card.append(
            header,
            body,
        );

        /*
         * PROTEIN FINAL WORKSPACE V1 20260812
         *
         * The Protein workspace has exactly two primary views:
         *
         *   Overview
         *     - complete amino-acid sequence
         *     - synchronized MolecularFeature track
         *     - search/copy/edit sequence actions
         *     - annotation editor available in-place
         *
         *   Alignment
         *     - persisted multiple-sequence alignment
         *     - amino-acid characters rendered directly
         *
         * The old Nightingale Protein overview, separate Sequence
         * tab and separate Annotations tab are not part of the final
         * presentation.
         */
        const outerCard = (
            root.querySelector(
                ".mw-seqviz-card"
            )
        );

        const outerShell = (
            outerCard?.querySelector(
                ".mw-seqviz-shell"
            )
        );

        const sequenceCard = (
            root.querySelector(
                ".mw-sequence-card"
            )
        );

        if (
            !outerCard
            || !outerShell
            || !sequenceCard
        ) {
            console.error(
                "Could not initialize final Protein workspace."
            );

            return;
        }


        root.classList.add(
            "mw-protein-final-workspace"
        );


        /*
         * The generic Molecular workspace has already attached the
         * sequence/feature listeners. Move that existing DOM node;
         * never clone it.
         */
        sequenceCard.hidden = false;

        sequenceCard.removeAttribute(
            "data-mw-view-panel"
        );

        sequenceCard.classList.add(
            "mw-protein-overview-sequence"
        );


        const sequenceHeading = (
            sequenceCard.querySelector(
                ":scope > .mw-card-header h2"
            )
        );

        if (sequenceHeading) {
            sequenceHeading.textContent = (
                "Overview"
            );
        }


        const sequenceDescription = (
            sequenceCard.querySelector(
                ":scope > .mw-card-header p"
            )
        );

        if (sequenceDescription) {
            sequenceDescription.textContent = (
                "Complete amino-acid sequence with synchronized "
                + "feature annotations and interactive selection."
            );
        }


        const workspaceHeading = (
            outerCard.querySelector(
                ":scope > .mw-card-header h2"
            )
        );

        if (workspaceHeading) {
            workspaceHeading.textContent = (
                "Protein workspace"
            );
        }


        const workspaceDescription = (
            outerCard.querySelector(
                ":scope > .mw-card-header p"
            )
        );

        if (workspaceDescription) {
            workspaceDescription.textContent = (
                "Inspect the annotated Protein sequence "
                + "or its multiple-sequence alignment."
            );
        }


        /*
         * Old SeqViz controls are not the Protein primary navigation.
         * The outer Expand/Restore control belongs to the card header
         * and remains untouched.
         */
        const oldSeqvizControls = (
            outerCard.querySelector(
                ".mw-seqviz-controls"
            )
        );

        if (oldSeqvizControls) {
            oldSeqvizControls.hidden = true;

            oldSeqvizControls.setAttribute(
                "aria-hidden",
                "true"
            );
        }


        const tabs = (
            document.createElement(
                "nav"
            )
        );

        tabs.id = (
            "mw-protein-final-tabs"
        );

        tabs.className = (
            "mw-protein-final-tabs"
        );

        tabs.setAttribute(
            "role",
            "tablist"
        );

        tabs.setAttribute(
            "aria-label",
            "Protein workspace views"
        );


        const stage = (
            document.createElement(
                "div"
            )
        );

        stage.id = (
            "mw-protein-final-stage"
        );

        stage.className = (
            "mw-protein-final-stage"
        );


        const overviewPane = (
            document.createElement(
                "section"
            )
        );

        overviewPane.id = (
            "mw-protein-final-overview"
        );

        overviewPane.className = (
            "mw-protein-final-pane "
            + "mw-protein-final-overview"
        );

        overviewPane.setAttribute(
            "role",
            "tabpanel"
        );


        const alignmentPane = (
            document.createElement(
                "section"
            )
        );

        alignmentPane.id = (
            "mw-protein-final-alignment"
        );

        alignmentPane.className = (
            "mw-protein-final-pane "
            + "mw-protein-final-alignment"
        );

        alignmentPane.setAttribute(
            "role",
            "tabpanel"
        );

        alignmentPane.hidden = true;


        /*
         * The former Sequence presentation is now Overview.
         */
        overviewPane.appendChild(
            sequenceCard
        );


        /*
         * Preserve the shared MolecularFeature editor, but integrate it
         * into Overview instead of consuming a full primary tab.
         */
        const annotationEditor = (
            document.getElementById(
                "mw-unified-feature-editor"
            )
            || root.querySelector(
                ".mw-features-card"
            )
        );

        if (annotationEditor) {
            annotationEditor.hidden = false;

            annotationEditor.removeAttribute(
                "aria-hidden"
            );


            const annotationDetails = (
                document.createElement(
                    "details"
                )
            );

            annotationDetails.className = (
                "mw-protein-annotation-details"
            );


            const annotationSummary = (
                document.createElement(
                    "summary"
                )
            );

            annotationSummary.textContent = (
                "Edit annotations"
            );


            const annotationHelp = (
                document.createElement(
                    "p"
                )
            );

            annotationHelp.className = (
                "mw-protein-annotation-help"
            );

            annotationHelp.textContent = (
                "Edit the MolecularFeature records shown "
                + "on the synchronized Overview track."
            );


            annotationDetails.append(
                annotationSummary,
                annotationHelp,
                annotationEditor
            );


            overviewPane.appendChild(
                annotationDetails
            );
        }


        /*
         * Hide any now-empty legacy Features container that is not the
         * editor we just moved.
         */
        const legacyFeaturesCard = (
            root.querySelector(
                ".mw-features-card"
            )
        );

        if (
            legacyFeaturesCard
            && legacyFeaturesCard
                !== annotationEditor
            && (
                !annotationEditor
                || !legacyFeaturesCard.contains(
                    annotationEditor
                )
            )
        ) {
            legacyFeaturesCard.hidden = true;

            legacyFeaturesCard.setAttribute(
                "aria-hidden",
                "true"
            );
        }


        /*
         * Existing Alignment API/upload/download/delete controls stay
         * inside the same card; only its scientific renderer changes.
         */
        alignmentPane.appendChild(
            card
        );

        card.classList.add(
            "mpa-card-embedded"
        );


        stage.append(
            overviewPane,
            alignmentPane
        );


        function activateFinalProteinView(
            requested
        ) {
            const name = (
                requested === "alignment"
                    ? "alignment"
                    : "overview"
            );

            const alignmentActive = (
                name === "alignment"
            );

            overviewPane.hidden = (
                alignmentActive
            );

            alignmentPane.hidden = (
                !alignmentActive
            );

            root.dataset.proteinView = (
                name
            );


            tabs.querySelectorAll(
                ".mw-protein-final-tab"
            ).forEach(
                button => {
                    const active = (
                        button.dataset
                            .proteinView
                        === name
                    );

                    button.classList.toggle(
                        "is-active",
                        active
                    );

                    button.setAttribute(
                        "aria-selected",
                        active
                            ? "true"
                            : "false"
                    );

                    button.tabIndex = (
                        active
                            ? 0
                            : -1
                    );
                }
            );


            window.dispatchEvent(
                new Event(
                    "resize"
                )
            );

            requestAnimationFrame(
                () => {
                    window.dispatchEvent(
                        new Event(
                            "resize"
                        )
                    );
                }
            );
        }


        function makeFinalProteinTab(
            name,
            label
        ) {
            const button = (
                document.createElement(
                    "button"
                )
            );

            button.type = "button";

            button.id = (
                "mw-protein-final-tab-"
                + name
            );

            button.className = (
                "mw-protein-final-tab"
            );

            button.dataset.proteinView = (
                name
            );

            button.setAttribute(
                "role",
                "tab"
            );

            button.textContent = (
                label
            );


            button.addEventListener(
                "click",
                () => {
                    activateFinalProteinView(
                        name
                    );
                }
            );


            return button;
        }


        const overviewTab = (
            makeFinalProteinTab(
                "overview",
                "Overview"
            )
        );

        const alignmentTab = (
            makeFinalProteinTab(
                "alignment",
                "Alignment"
            )
        );


        overviewTab.setAttribute(
            "aria-controls",
            overviewPane.id
        );

        alignmentTab.setAttribute(
            "aria-controls",
            alignmentPane.id
        );


        overviewPane.setAttribute(
            "aria-labelledby",
            overviewTab.id
        );

        alignmentPane.setAttribute(
            "aria-labelledby",
            alignmentTab.id
        );


        tabs.append(
            overviewTab,
            alignmentTab
        );


        const outerHeader = (
            outerCard.querySelector(
                ":scope > .mw-card-header"
            )
        );

        if (outerHeader) {
            outerHeader.insertAdjacentElement(
                "afterend",
                tabs
            );
        } else {
            outerCard.prepend(
                tabs
            );
        }


        /*
         * Replace the obsolete Protein renderer area only after every
         * reusable node has been moved into the new stage.
         */
        outerShell.replaceChildren(
            stage
        );

        outerCard.hidden = false;


        activateFinalProteinView(
            "overview"
        );


        function setStatus(
            message,
            kind = "",
        ) {
            status.textContent = message;
            status.dataset.kind = kind;
        }

        async function requestJson(
            url,
            options = {},
        ) {
            const response = await fetch(
                url,
                {
                    credentials: "same-origin",
                    ...options,
                },
            );

            let data;

            try {
                data = await response.json();

            } catch (_error) {
                throw new Error(
                    (
                        "The Protein Alignment endpoint "
                        + "returned an invalid response."
                    )
                );
            }

            if (!response.ok) {
                throw new Error(
                    data.message
                    || (
                        "Protein Alignment request failed "
                        + `(${response.status}).`
                    )
                );
            }

            return data;
        }

        function alignmentUrl(
            alignmentId,
            download = false,
        ) {
            const url = new URL(
                apiUrl,
                window.location.href,
            );

            url.searchParams.set(
                "alignment_id",
                String(
                    alignmentId
                ),
            );

            if (download) {
                url.searchParams.set(
                    "download",
                    "1",
                );
            }

            return url.toString();
        }

        function updateMetadata(
            payload,
        ) {
            metadata.replaceChildren();

            if (!payload) {
                return;
            }

            const items = [
                [
                    "File",
                    payload.original_filename,
                ],
                [
                    "Format",
                    (
                        payload.source_format_label
                        || payload.source_format
                    ),
                ],
                [
                    "Sequences",
                    payload.sequence_count,
                ],
                [
                    "Columns",
                    payload.alignment_length,
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
                    "mpa-metadata-item",
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
                        String(
                            value ?? "—"
                        ),
                    ),
                );

                metadata.appendChild(
                    item
                );
            }

            if (payload.query_match) {
                queryMatch.textContent = (
                    "Exact Protein record match: "
                    + payload.query_match.name
                );

                queryMatch.dataset.match = (
                    "exact"
                );

            } else {
                queryMatch.textContent = (
                    "No alignment row exactly matches "
                    + "the current Protein sequence."
                );

                queryMatch.dataset.match = (
                    "none"
                );
            }

            downloadLink.href = alignmentUrl(
                payload.id,
                true,
            );

            downloadLink.hidden = false;
            focusButton.disabled = false;

            if (canEdit) {
                deleteButton.disabled = false;
            }
        }

        /*
         * PROTEIN TEXT MSA V1 20260812
         *
         * Display aligned amino acids as actual characters.  Residue
         * colors are secondary annotations, never substitutes for the
         * sequence itself.
         */
        const MSA_BLOCK_SIZE = 80;


        function normalizedResidue(
            value
        ) {
            const text = String(
                value
                || "-"
            ).toUpperCase();

            return (
                text.length
                    ? text[0]
                    : "-"
            );
        }


        function residueClass(
            residue
        ) {
            const aa = normalizedResidue(
                residue
            );

            if ("AILMFWV".includes(aa)) {
                return "mpa-aa-hydrophobic";
            }

            if ("KR".includes(aa)) {
                return "mpa-aa-positive";
            }

            if ("DE".includes(aa)) {
                return "mpa-aa-negative";
            }

            if ("STNQ".includes(aa)) {
                return "mpa-aa-polar";
            }

            if ("HY".includes(aa)) {
                return "mpa-aa-aromatic";
            }

            if ("CGP".includes(aa)) {
                return "mpa-aa-special";
            }

            if (
                aa === "-"
                || aa === "."
            ) {
                return "mpa-aa-gap";
            }

            return "mpa-aa-other";
        }


        function conservedColumnsFor(
            rows,
            alignmentLength
        ) {
            return Array.from(
                {
                    length: alignmentLength,
                },
                (
                    _unused,
                    columnIndex
                ) => {
                    const residues = (
                        rows
                            .map(
                                row => (
                                    normalizedResidue(
                                        row.sequence[
                                            columnIndex
                                        ]
                                    )
                                )
                            )
                            .filter(
                                residue => (
                                    residue !== "-"
                                    && residue !== "."
                                )
                            )
                    );

                    if (residues.length < 2) {
                        return false;
                    }

                    return (
                        new Set(
                            residues
                        ).size === 1
                    );
                }
            );
        }


        function makeResidueCell(
            residue,
            column,
            conserved
        ) {
            const aa = (
                normalizedResidue(
                    residue
                )
            );

            const cell = (
                document.createElement(
                    "span"
                )
            );

            cell.className = (
                "mpa-residue "
                + residueClass(
                    aa
                )
                + (
                    conserved
                        ? " is-conserved"
                        : ""
                )
            );

            cell.textContent = aa;

            cell.dataset.column = (
                String(
                    column
                )
            );

            cell.title = (
                `${aa} · alignment column ${column}`
            );

            return cell;
        }


        function makeSequenceRun(
            sequence,
            blockStart,
            blockEnd,
            conservedColumns
        ) {
            const run = (
                document.createElement(
                    "div"
                )
            );

            run.className = (
                "mpa-sequence-run"
            );


            for (
                let index = blockStart;
                index < blockEnd;
                index += 1
            ) {
                run.appendChild(
                    makeResidueCell(
                        sequence[index]
                            || "-",
                        index + 1,
                        Boolean(
                            conservedColumns[
                                index
                            ]
                        )
                    )
                );
            }


            return run;
        }


        function makeConsensusRun(
            blockStart,
            blockEnd,
            conservedColumns
        ) {
            const run = (
                document.createElement(
                    "div"
                )
            );

            run.className = (
                "mpa-sequence-run "
                + "mpa-consensus-run"
            );


            for (
                let index = blockStart;
                index < blockEnd;
                index += 1
            ) {
                const cell = (
                    document.createElement(
                        "span"
                    )
                );

                cell.className = (
                    "mpa-consensus-cell"
                );

                cell.textContent = (
                    conservedColumns[
                        index
                    ]
                        ? "*"
                        : " "
                );

                cell.title = (
                    `Alignment column ${index + 1}`
                );

                run.appendChild(
                    cell
                );
            }


            return run;
        }


        function updateScheme() {
            viewerShell.querySelectorAll(
                ".mpa-alignment-block"
            ).forEach(
                block => {
                    block.dataset.scheme = (
                        scheme.value
                        || "clustal"
                    );
                }
            );
        }


        async function renderViewer(
            payload
        ) {
            currentPayload = payload;


            updateMetadata(
                payload
            );


            const rows = (
                payload.rows
                || []
            ).map(
                row => ({
                    name: String(
                        row.name
                        || "sequence"
                    ),
                    sequence: String(
                        row.sequence
                        || ""
                    ).toUpperCase(),
                })
            );


            const alignmentLength = Math.max(
                0,
                Number(
                    payload.alignment_length
                )
                || 0,
                ...rows.map(
                    row => (
                        row.sequence.length
                    )
                )
            );


            if (
                !rows.length
                || alignmentLength <= 0
            ) {
                viewerShell.replaceChildren(
                    createElement(
                        "div",
                        "mw-empty mpa-viewer-empty",
                        (
                            "This alignment contains no "
                            + "renderable sequence rows."
                        )
                    )
                );

                setStatus(
                    "Empty alignment",
                    "error"
                );

                return;
            }


            const conservedColumns = (
                conservedColumnsFor(
                    rows,
                    alignmentLength
                )
            );


            const viewer = (
                document.createElement(
                    "div"
                )
            );

            viewer.className = (
                "mpa-text-msa"
            );

            viewer.dataset.sequenceCount = (
                String(
                    rows.length
                )
            );

            viewer.dataset.alignmentLength = (
                String(
                    alignmentLength
                )
            );


            const queryName = (
                payload.query_match?.name
                || ""
            );


            for (
                let blockStart = 0;
                blockStart < alignmentLength;
                blockStart += MSA_BLOCK_SIZE
            ) {
                const blockEnd = Math.min(
                    alignmentLength,
                    blockStart
                        + MSA_BLOCK_SIZE
                );


                const block = (
                    document.createElement(
                        "section"
                    )
                );

                block.className = (
                    "mpa-alignment-block"
                );

                block.dataset.scheme = (
                    scheme.value
                    || "clustal"
                );


                const blockHeader = (
                    document.createElement(
                        "div"
                    )
                );

                blockHeader.className = (
                    "mpa-alignment-block-header"
                );

                blockHeader.textContent = (
                    `Columns ${blockStart + 1}–${blockEnd}`
                );


                const scroll = (
                    document.createElement(
                        "div"
                    )
                );

                scroll.className = (
                    "mpa-alignment-block-scroll"
                );


                const matrix = (
                    document.createElement(
                        "div"
                    )
                );

                matrix.className = (
                    "mpa-alignment-matrix"
                );


                rows.forEach(
                    (
                        row,
                        rowIndex
                    ) => {
                        const line = (
                            document.createElement(
                                "div"
                            )
                        );

                        line.className = (
                            "mpa-alignment-row"
                        );

                        line.dataset.rowIndex = (
                            String(
                                rowIndex
                            )
                        );


                        if (
                            queryName
                            && row.name
                                === queryName
                        ) {
                            line.classList.add(
                                "is-query"
                            );
                        }


                        const label = (
                            document.createElement(
                                "div"
                            )
                        );

                        label.className = (
                            "mpa-alignment-label"
                        );

                        label.textContent = (
                            row.name
                        );

                        label.title = (
                            row.name
                        );


                        line.append(
                            label,
                            makeSequenceRun(
                                row.sequence,
                                blockStart,
                                blockEnd,
                                conservedColumns
                            )
                        );


                        matrix.appendChild(
                            line
                        );
                    }
                );


                const consensus = (
                    document.createElement(
                        "div"
                    )
                );

                consensus.className = (
                    "mpa-alignment-row "
                    + "mpa-consensus-row"
                );


                const consensusLabel = (
                    document.createElement(
                        "div"
                    )
                );

                consensusLabel.className = (
                    "mpa-alignment-label"
                );

                consensusLabel.textContent = (
                    "Consensus"
                );


                consensus.append(
                    consensusLabel,
                    makeConsensusRun(
                        blockStart,
                        blockEnd,
                        conservedColumns
                    )
                );


                matrix.appendChild(
                    consensus
                );

                scroll.appendChild(
                    matrix
                );

                block.append(
                    blockHeader,
                    scroll
                );

                viewer.appendChild(
                    block
                );
            }


            viewerShell.replaceChildren(
                viewer
            );


            setStatus(
                (
                    `${rows.length} sequences · `
                    + `${alignmentLength} columns`
                ),
                "ready"
            );
        }


        function renderList() {
            list.replaceChildren();

            const count = sidebar.querySelector(
                ".mpa-count"
            );

            count.textContent = String(
                alignments.length
            );

            empty.hidden = (
                alignments.length > 0
            );

            for (
                const alignment
                of alignments
            ) {
                const button = createElement(
                    "button",
                    (
                        "mpa-list-item"
                        + (
                            alignment.id
                            === selectedAlignmentId
                                ? " is-active"
                                : ""
                        )
                    ),
                );

                button.type = "button";

                const title = createElement(
                    "strong",
                    "",
                    alignment.original_filename,
                );

                const detail = createElement(
                    "span",
                    "",
                    (
                        `${alignment.sequence_count} seq · `
                        + `${alignment.alignment_length} columns · `
                        + (
                            alignment.source_format_label
                            || alignment.source_format
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
                        openAlignment(
                            alignment.id
                        );
                    },
                );

                list.appendChild(
                    button
                );
            }
        }

        async function openAlignment(
            alignmentId,
        ) {
            selectedAlignmentId = (
                Number(
                    alignmentId
                )
            );

            renderList();

            setStatus(
                "Loading alignment…",
                "busy",
            );

            try {
                const data = await requestJson(
                    alignmentUrl(
                        selectedAlignmentId
                    )
                );

                await renderViewer(
                    data.alignment
                );

            } catch (error) {
                console.error(
                    error
                );

                viewerShell.replaceChildren(
                    createElement(
                        "div",
                        "mw-empty",
                        (
                            error.message
                            || "Could not open alignment."
                        ),
                    )
                );

                setStatus(
                    (
                        error.message
                        || "Alignment error"
                    ),
                    "error",
                );
            }
        }

        async function loadAlignments() {
            setStatus(
                "Checking alignments…",
                "busy",
            );

            try {
                const data = await requestJson(
                    apiUrl
                );

                alignments = Array.isArray(
                    data.alignments
                )
                    ? data.alignments
                    : [];

                renderList();

                if (alignments.length) {
                    await openAlignment(
                        alignments[0].id
                    );

                } else {
                    setStatus(
                        "No alignment attached",
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
                        || "Could not load alignments."
                    ),
                    "error",
                );
            }
        }

        async function uploadAlignment(
            file,
        ) {
            const data = new FormData();

            data.append(
                "action",
                "upload",
            );

            data.append(
                "file",
                file,
            );

            setStatus(
                "Uploading alignment…",
                "busy",
            );

            try {
                const response = await requestJson(
                    apiUrl,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": csrfToken,
                        },
                        body: data,
                    },
                );

                const payload = (
                    response.alignment
                );

                alignments = [
                    payload,
                    ...alignments.filter(
                        item => (
                            item.id
                            !== payload.id
                        ),
                    ),
                ];

                selectedAlignmentId = (
                    payload.id
                );

                renderList();

                await renderViewer(
                    payload
                );

            } catch (error) {
                console.error(
                    error
                );

                setStatus(
                    (
                        error.message
                        || "Alignment upload failed."
                    ),
                    "error",
                );
            }
        }

        async function deleteSelectedAlignment() {
            if (
                !canEdit
                || !selectedAlignmentId
            ) {
                return;
            }

            const selected = alignments.find(
                item => (
                    item.id
                    === selectedAlignmentId
                )
            );

            const confirmed = window.confirm(
                (
                    "Remove alignment "
                    + (
                        selected
                            ?.original_filename
                        || selectedAlignmentId
                    )
                    + " from this Protein record?"
                )
            );

            if (!confirmed) {
                return;
            }

            const data = new FormData();

            data.append(
                "action",
                "delete",
            );

            data.append(
                "alignment_id",
                String(
                    selectedAlignmentId
                ),
            );

            setStatus(
                "Removing alignment…",
                "busy",
            );

            try {
                await requestJson(
                    apiUrl,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": csrfToken,
                        },
                        body: data,
                    },
                );

                alignments = (
                    alignments.filter(
                        item => (
                            item.id
                            !== selectedAlignmentId
                        ),
                    )
                );

                selectedAlignmentId = null;
                currentPayload = null;

                renderList();

                metadata.replaceChildren();
                queryMatch.textContent = "";

                viewerShell.replaceChildren(
                    createElement(
                        "div",
                        "mw-empty mpa-viewer-empty",
                        (
                            "Choose an alignment to open the "
                            + "aligned amino-acid viewer."
                        ),
                    )
                );

                downloadLink.hidden = true;
                focusButton.disabled = true;
                deleteButton.disabled = true;

                if (alignments.length) {
                    await openAlignment(
                        alignments[0].id
                    );

                } else {
                    setStatus(
                        "No alignment attached",
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
                        || "Could not remove alignment."
                    ),
                    "error",
                );
            }
        }

        uploadButton.addEventListener(
            "click",
            () => {
                fileInput.value = "";
                fileInput.click();
            },
        );

        fileInput.addEventListener(
            "change",
            () => {
                const file = fileInput.files?.[0];

                if (file) {
                    uploadAlignment(
                        file
                    );
                }
            },
        );

        scheme.addEventListener(
            "change",
            updateScheme,
        );

        focusButton.addEventListener(
            "click",
            () => {
                if (currentPayload) {
                    renderViewer(
                        currentPayload
                    ).catch(
                        error => {
                            console.error(
                                error
                            );
                        },
                    );
                }
            },
        );

        deleteButton.addEventListener(
            "click",
            deleteSelectedAlignment,
        );

        loadAlignments();
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


/* ------------------------------------------------------------
 * PROTEIN RESIDUE PALETTE V1 20260814
 * Adds a lightweight palette selector for the Overview track.
 * ------------------------------------------------------------ */

(() => {
    const ROOT_ID = "molecular-workspace";
    const CONTROL_ID = "mw-protein-residue-palette";
    const STORAGE_KEY = "mw-protein-residue-palette";
    const DEFAULT_PALETTE = "contrast";
    const VALID = new Set([
        "soft",
        "contrast",
        "mono",
    ]);

    function proteinRoot() {
        const root = document.getElementById(ROOT_ID);

        if (
            !root
            || !root.classList.contains(
                "mw-protein-final-workspace"
            )
        ) {
            return null;
        }

        return root;
    }

    function storedPalette() {
        try {
            return (
                window.localStorage.getItem(
                    STORAGE_KEY
                )
                || DEFAULT_PALETTE
            );
        } catch (error) {
            return DEFAULT_PALETTE;
        }
    }

    function normalizePalette(value) {
        return VALID.has(value)
            ? value
            : DEFAULT_PALETTE;
    }

    function applyPalette(value) {
        const root = proteinRoot();

        if (!root) {
            return;
        }

        const normalized = normalizePalette(value);

        root.dataset.residuePalette = normalized;

        try {
            window.localStorage.setItem(
                STORAGE_KEY,
                normalized
            );
        } catch (error) {
            /* ignore localStorage failures */
        }
    }

    function buildControl() {
        if (
            document.getElementById(CONTROL_ID)
        ) {
            return;
        }

        const search = document.getElementById(
            "mw-search"
        );

        if (
            !search
            || !search.parentElement
        ) {
            return;
        }

        const wrapper =
            document.createElement("label");

        wrapper.className =
            "mw-protein-palette-control";

        wrapper.innerHTML = [
            '<span class="mw-protein-palette-label">',
            "Residue colors",
            "</span>",
            '<select id="',
            CONTROL_ID,
            '" class="mw-protein-palette-select">',
            '<option value="soft">Soft</option>',
            '<option value="contrast">High contrast</option>',
            '<option value="mono">Monochrome</option>',
            "</select>",
        ].join("");

        search.parentElement.insertBefore(
            wrapper,
            search
        );

        const select = wrapper.querySelector(
            "select"
        );

        if (select) {
            select.value = normalizePalette(
                storedPalette()
            );

            select.addEventListener(
                "change",
                (event) => {
                    applyPalette(
                        event.target.value
                    );
                }
            );
        }
    }

    function ensurePaletteUi() {
        const root = proteinRoot();

        if (!root) {
            return;
        }

        buildControl();
        applyPalette(storedPalette());
    }

    function observeFinalWorkspace() {
        const root = proteinRoot();

        if (!root) {
            return;
        }

        const observer =
            new MutationObserver(() => {
                ensurePaletteUi();
            });

        observer.observe(root, {
            childList: true,
            subtree: true,
        });
    }

    function initProteinResiduePalette() {
        ensurePaletteUi();
        observeFinalWorkspace();
    }

    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initProteinResiduePalette,
            { once: true }
        );
    } else {
        initProteinResiduePalette();
    }
})();
