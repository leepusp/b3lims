from __future__ import annotations

import hashlib
from pathlib import Path

from django.test import SimpleTestCase


BASE = Path(
    "core/interfaces/internal/lab_tools"
)

EXPECTED_FORNA_SHA256 = (
    "1775620a1455bda0529a9e4e7b3fd17d"
    "48ccfd22f986de14ce0f49f8904a9246"
)


class MolecularRnaSecondaryStructureFrontendTests(
    SimpleTestCase
):
    def setUp(self):
        self.template = (
            BASE
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8",
        )

        self.javascript = (
            BASE
            / "molecular_rna_secondary_structure.js"
        ).read_text(
            encoding="utf-8",
        )

        self.styles = (
            BASE
            / "molecular_rna_secondary_structure.css"
        ).read_text(
            encoding="utf-8",
        )

        self.profile = (
            BASE
            / "molecular_type_profiles.js"
        ).read_text(
            encoding="utf-8",
        )

        self.vendor_path = (
            BASE
            / "vendor"
            / "fornac-1.1.8.min.js"
        )

        self.notices = (
            BASE
            / "vendor"
            / "fornac-1.1.8.LICENSES.txt"
        ).read_text(
            encoding="utf-8",
        )

    def rna_profile_block(self):
        start = self.profile.index(
            "rna: Object.freeze({"
        )

        end = self.profile.index(
            "protein: Object.freeze({",
            start,
        )

        return self.profile[
            start:end
        ]

    def test_template_exposes_rna_api_and_lazy_vendor_url(self):
        self.assertIn(
            "data-rna-secondary-structures-url",
            self.template,
        )

        self.assertIn(
            "data-rna-forna-vendor-url",
            self.template,
        )

        self.assertIn(
            "molecular_rna_secondary_structure.css",
            self.template,
        )

        self.assertIn(
            "molecular_rna_secondary_structure.js",
            self.template,
        )

        self.assertNotIn(
            (
                '<script src="{% static '
                "'internal/lab_tools/vendor/"
                "fornac-1.1.8.min.js'"
            ),
            self.template,
        )

    def test_frontend_uses_forna_only_through_lazy_loader(self):
        for marker in (
            "loadFornaVendor(",
            'document.createElement(\n                        "script"',
            "window.fornac",
            "FornaContainer",
            ".addRNA(",
            ".changeColorScheme(",
            "container.deaf = true",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.javascript,
                )

    def test_frontend_preserves_workspace_sequence_as_sequence_source(self):
        for marker in (
            "workspaceSnapshot()",
            "initialSequence",
            "currentSequence()",
            "sequenceIsSafeForRenderer(",
            "biobank:molecular-workspace-change",
            "Sequence changed — reload required",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.javascript,
                )

        self.assertNotIn(
            "replace(/T/g,",
            self.javascript,
        )

        # RNAfold-style text is accepted as imported provenance.
        # What must remain absent is any prediction/invocation path.
        for forbidden in (
            "runRNAfold",
            "runRnafold",
            "executeRNAfold",
            "executeRnafold",
            "predictSecondaryStructure",
            "rnafoldUrl",
            "predictionUrl",
        ):
            with self.subTest(
                forbidden=forbidden
            ):
                self.assertNotIn(
                    forbidden,
                    self.javascript,
                )

        self.assertIn(
            "RNAfold-style text",
            self.javascript,
        )

        self.assertIn(
            "Imported RNAfold output",
            self.javascript,
        )

    def test_frontend_supports_persisted_structure_workflow(self):
        for marker in (
            "Stored structures",
            "Add structure",
            "Save structure",
            "Remove structure",
            "Copy source",
            "source_text",
            "source_method",
            "source_note",
            ".dbn,.txt,text/plain",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.javascript,
                )

    def test_rna_profile_marks_secondary_structure_ready(self):
        block = self.rna_profile_block()

        ready_start = block.index(
            "ready: Object.freeze(["
        )

        planned_start = block.index(
            "planned: Object.freeze(["
        )

        ready = block[
            ready_start:planned_start
        ]

        planned = block[
            planned_start:
        ]

        self.assertIn(
            '"secondary-structure"',
            ready,
        )

        self.assertNotIn(
            '"secondary-structure"',
            planned,
        )

        self.assertIn(
            '"alignment"',
            planned,
        )

        self.assertIn(
            '"Sequence · secondary structure"',
            block,
        )

    def test_rna_styles_are_scoped(self):
        for marker in (
            ".mrss-card",
            ".mrss-body",
            ".mrss-list-item.is-active",
            ".mrss-viewer-shell",
            ".mrss-forna-mount",
            ".mrss-editor",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.styles,
                )

    def test_exact_forna_release_and_notices_are_vendored(self):
        vendor = self.vendor_path.read_bytes()

        self.assertEqual(
            hashlib.sha256(
                vendor
            ).hexdigest(),
            EXPECTED_FORNA_SHA256,
        )

        self.assertEqual(
            len(vendor),
            199632,
        )

        self.assertIn(
            b"FornaContainer",
            vendor,
        )

        self.assertIn(
            "fornac@1.1.8",
            self.notices,
        )

        self.assertIn(
            "Apache License",
            self.notices,
        )

        self.assertIn(
            EXPECTED_FORNA_SHA256,
            self.notices,
        )

    def test_rnacanvas_is_not_part_of_r1c_runtime(self):
        combined = (
            self.template
            + self.javascript
            + self.styles
        ).lower()

        self.assertNotIn(
            "rnacanvas",
            combined,
        )

    def test_no_automatic_prediction_runtime_exists(self):
        lower = self.javascript.lower()

        self.assertNotIn(
            "subprocess",
            lower,
        )

        self.assertNotIn(
            "/rnafold",
            lower,
        )

        self.assertNotIn(
            "prediction_endpoint",
            lower,
        )

        self.assertNotIn(
            "predict_structure",
            lower,
        )
