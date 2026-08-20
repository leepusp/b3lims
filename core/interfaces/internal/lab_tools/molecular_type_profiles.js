(() => {
    "use strict";

    const PROFILE_VERSION =
        "20260808-molecular-type-profiles-v2-protein";

    /*
     * This is presentation/capability metadata only.
     *
     * MolecularSequence and MolecularFeature remain the source
     * of truth. No molecular data is stored here.
     *
     * "ready" describes capabilities already available today.
     * "planned" describes the specialized lightweight views
     * that can be attached later.
     */
    const PROFILES = Object.freeze({
        dna: Object.freeze({
            key: "dna",
            label: "DNA workspace",
            registrySummary:
                "Sequence · annotations · linear browser",
            description:
                "Inspect DNA sequence, annotations and linear context.",
            unit: "bp",
            topologyMeaningful: true,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
                "linear-browser",
            ]),
            planned: Object.freeze([]),
        }),

        plasmid: Object.freeze({
            key: "plasmid",
            label: "Plasmid workspace",
            registrySummary:
                "SeqViz · detailed map · restrictions",
            description:
                "Inspect the plasmid with SeqViz, detailed map, linear browser and restriction-site analysis.",
            unit: "bp",
            topologyMeaningful: true,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
                "detailed-map",
                "linear-browser",
                "restriction-sites",
            ]),
            planned: Object.freeze([]),
        }),

        insert: Object.freeze({
            key: "insert",
            label: "Insert workspace",
            registrySummary:
                "Sequence · linear browser · assembly next",
            description:
                "Inspect the insert as DNA now; assembly and junction context can be added as a specialized view.",
            unit: "bp",
            topologyMeaningful: true,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
                "linear-browser",
            ]),
            planned: Object.freeze([
                "assembly-context",
            ]),
        }),

        primer: Object.freeze({
            key: "primer",
            label: "Primer workspace",
            registrySummary:
                "Sequence · primer analysis next",
            description:
                "Inspect the oligonucleotide sequence now; primer metrics and amplicon context are the next specialized views.",
            unit: "bp",
            topologyMeaningful: false,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
            ]),
            planned: Object.freeze([
                "primer-analysis",
                "amplicon-context",
            ]),
        }),

        rna: Object.freeze({
            key: "rna",
            label: "RNA workspace",
            registrySummary:
                "Sequence · secondary structure",
            description:
                "Inspect RNA sequence, annotations and persisted secondary structures; alignment remains planned.",
            unit: "nt",
            topologyMeaningful: true,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
                "secondary-structure",
            ]),
            planned: Object.freeze([
                "alignment",
            ]),
        }),

        protein: Object.freeze({
            key: "protein",
            label: "Protein workspace",
            registrySummary:
                "Overview · sequence · alignment · structure",
            description:
                "Inspect protein domains, annotated regions, amino-acid sequence, persisted multiple-sequence alignments and available protein structures.",
            unit: "aa",
            topologyMeaningful: false,
            ready: Object.freeze([
                "seqviz",
                "sequence",
                "annotations",
                "protein-overview",
                "alignment",
                "structure",
            ]),
            planned: Object.freeze([]),
        }),

        other: Object.freeze({
            key: "other",
            label: "Sequence workspace",
            registrySummary:
                "Generic sequence · annotations",
            description:
                "Inspect the registered sequence and its structured annotations.",
            unit: "symbols",
            topologyMeaningful: true,
            ready: Object.freeze([
                "sequence",
                "annotations",
            ]),
            planned: Object.freeze([]),
        }),
    });

    function normalizeType(value) {
        const normalized = String(
            value
            || "",
        )
            .trim()
            .toLowerCase();

        return Object.prototype
            .hasOwnProperty
            .call(
                PROFILES,
                normalized,
            )
            ? normalized
            : "other";
    }

    function profileFor(value) {
        return PROFILES[
            normalizeType(
                value,
            )
        ];
    }

    function renderRegistrySummary(
        row,
    ) {
        const target = (
            row.querySelector(
                "[data-molecular-workspace-summary]",
            )
        );

        if (!target) {
            return;
        }

        const profile = profileFor(
            row.dataset
                .molecularRecordType,
        );

        row.dataset
            .molecularWorkspaceProfile = (
                profile.key
            );

        target.replaceChildren();

        const label = (
            document.createElement(
                "span",
            )
        );

        label.className = (
            "mtr-registry-workspace-label"
        );

        label.textContent = (
            profile.label
        );

        const detail = (
            document.createElement(
                "span",
            )
        );

        detail.className = (
            "mtr-registry-workspace-detail"
        );

        detail.textContent = (
            profile.registrySummary
        );

        target.append(
            label,
            detail,
        );
    }

    function renderRegistry() {
        document.querySelectorAll(
            "[data-molecular-record-type]",
        ).forEach(
            renderRegistrySummary,
        );
    }

    function currentDetailType(
        root,
    ) {
        return (
            root.dataset.sequenceType
            || document
                .getElementById(
                    "mw-type",
                )
                ?.value
            || "other"
        );
    }

    function renderDetail() {
        const root = (
            document.getElementById(
                "molecular-workspace",
            )
        );

        if (!root) {
            return;
        }

        const profile = profileFor(
            currentDetailType(
                root,
            ),
        );

        root.dataset
            .molecularWorkspaceProfile = (
                profile.key
            );

        root.dataset
            .molecularWorkspaceUnit = (
                profile.unit
            );

        root.dataset
            .molecularTopologyMeaningful = (
                String(
                    profile
                        .topologyMeaningful,
                )
            );

        const label = (
            root.querySelector(
                "[data-molecular-workspace-label]",
            )
        );

        if (label) {
            label.textContent = (
                profile.label
            );
        }

        const description = (
            root.querySelector(
                "[data-molecular-workspace-description]",
            )
        );

        if (description) {
            description.textContent = (
                profile.description
            );
        }

        const topologyBadge = (
            document.getElementById(
                "mw-topology-badge",
            )
        );

        if (topologyBadge) {
            topologyBadge.classList.toggle(
                "mtr-semantic-secondary",
                !profile
                    .topologyMeaningful,
            );

            if (
                !profile
                    .topologyMeaningful
            ) {
                topologyBadge.title = (
                    "Topology is stored for compatibility "
                    + "but is not a primary semantic property "
                    + `of a ${profile.key} record.`
                );
            } else {
                topologyBadge.removeAttribute(
                    "title",
                );
            }
        }

        root.dispatchEvent(
            new CustomEvent(
                (
                    "biobank:"
                    + "molecular-type-profile-applied"
                ),
                {
                    detail: {
                        profile,
                        version:
                            PROFILE_VERSION,
                    },
                },
            ),
        );
    }

    function apply() {
        renderRegistry();
        renderDetail();
    }

    window.BiobankMolecularTypeProfiles = (
        Object.freeze({
            version:
                PROFILE_VERSION,
            profiles:
                PROFILES,
            normalizeType,
            profileFor,
            apply,
        })
    );

    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            apply,
            {
                once: true,
            },
        );
    } else {
        apply();
    }

    const root = (
        document.getElementById(
            "molecular-workspace",
        )
    );

    if (root) {
        root.addEventListener(
            (
                "biobank:"
                + "molecular-workspace-change"
            ),
            renderDetail,
        );
    }
})();
