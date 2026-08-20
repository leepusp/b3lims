from pathlib import Path
import re

from django.test import SimpleTestCase


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

BASE = (
    ROOT
    / "core/interfaces/internal/lab_tools"
)

PROFILE = (
    BASE
    / "molecular_type_profiles.js"
)

DETAIL = (
    BASE
    / "molecular_sequence_detail.html"
)

REGISTRY = (
    BASE
    / "molecular_registry.html"
)


class ProteinTypeProfileStructureReadyTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(
        cls,
    ):
        super().setUpClass()

        cls.profile = PROFILE.read_text(
            encoding="utf-8"
        )

        cls.detail = DETAIL.read_text(
            encoding="utf-8"
        )

        cls.registry = REGISTRY.read_text(
            encoding="utf-8"
        )

        start = cls.profile.find(
            "protein: Object.freeze({"
        )

        if start < 0:
            raise AssertionError(
                "Protein profile not found."
            )

        end = cls.profile.find(
            "\n        }),",
            start,
        )

        if end < 0:
            raise AssertionError(
                "Protein profile end not found."
            )

        cls.protein_block = cls.profile[
            start:
            end + len(
                "\n        }),"
            )
        ]

    @staticmethod
    def array_values(
        block,
        name,
    ):
        match = re.search(
            rf"""
            {re.escape(name)}
            \s*:
            \s*
            Object\.freeze
            \s*
            \(
            \s*
            \[
            (?P<body>.*?)
            \]
            \s*
            \)
            """,
            block,
            re.DOTALL | re.VERBOSE,
        )

        if match is None:
            if (
                name == "planned"
                and "planned: Object.freeze([])"
                in block
            ):
                return []

            raise AssertionError(
                f"{name} array not found."
            )

        return re.findall(
            r'["\']([^"\']+)["\']',
            match.group(
                "body"
            ),
        )

    def test_structure_is_ready(
        self,
    ):
        ready = self.array_values(
            self.protein_block,
            "ready",
        )

        self.assertEqual(
            ready,
            [
                "seqviz",
                "sequence",
                "annotations",
                "protein-overview",
                "alignment",
                "structure",
            ],
        )

    def test_protein_has_no_planned_capabilities(
        self,
    ):
        planned = self.array_values(
            self.protein_block,
            "planned",
        )

        self.assertEqual(
            planned,
            [],
        )

        self.assertIn(
            "planned: Object.freeze([])",
            self.protein_block,
        )

    def test_summary_reports_structure(
        self,
    ):
        self.assertIn(
            (
                '"Overview · sequence · '
                'alignment · structure"'
            ),
            self.protein_block,
        )

        self.assertNotIn(
            '"Overview · sequence · alignment"',
            self.protein_block,
        )

    def test_description_reports_current_capabilities(
        self,
    ):
        self.assertIn(
            (
                '"Inspect protein domains, annotated regions, '
                'amino-acid sequence, persisted multiple-sequence '
                'alignments and available protein structures."'
            ),
            self.protein_block,
        )

        self.assertNotIn(
            "structure remains planned",
            self.protein_block,
        )

    def test_rna_planned_alignment_is_preserved(
        self,
    ):
        self.assertEqual(
            self.profile.count(
                (
                    "Inspect RNA sequence, annotations and "
                    "persisted secondary structures; "
                    "alignment remains planned."
                )
            ),
            1,
        )

        self.assertIn(
            '"secondary-structure",',
            self.profile,
        )

    def test_detail_uses_new_profile_js_cache(
        self,
    ):
        new_marker = (
            "molecular_type_profiles.js' %}"
            "?v=20260819-protein-profile-"
            "structure-ready-v1"
        )

        old_marker = (
            "molecular_type_profiles.js' %}"
            "?v=20260808-rna-secondary-r1c-forna-v2"
        )

        self.assertEqual(
            self.detail.count(
                new_marker
            ),
            1,
        )

        self.assertNotIn(
            old_marker,
            self.detail,
        )

    def test_registry_uses_new_profile_js_cache(
        self,
    ):
        new_marker = (
            "molecular_type_profiles.js' %}"
            "?v=20260819-protein-profile-"
            "structure-ready-v1"
        )

        old_marker = (
            "molecular_type_profiles.js' %}"
            "?v=20260808-rna-secondary-r1c-forna-v2"
        )

        self.assertEqual(
            self.registry.count(
                new_marker
            ),
            1,
        )

        self.assertNotIn(
            old_marker,
            self.registry,
        )

    def test_historical_detail_cache_token_is_not_globally_replaced(
        self,
    ):
        #
        # Detail had two occurrences before D2H:
        # one belonged to molecular_type_profiles.js.
        #
        # Only the exact JS marker is bumped.
        #

        self.assertEqual(
            self.detail.count(
                "20260808-rna-secondary-r1c-forna-v2"
            ),
            1,
        )

        self.assertEqual(
            self.detail.count(
                (
                    "20260819-protein-profile-"
                    "structure-ready-v1"
                )
            ),
            1,
        )

    def test_registry_old_cache_token_is_absent(
        self,
    ):
        self.assertNotIn(
            "20260808-rna-secondary-r1c-forna-v2",
            self.registry,
        )

        self.assertEqual(
            self.registry.count(
                (
                    "20260819-protein-profile-"
                    "structure-ready-v1"
                )
            ),
            1,
        )
