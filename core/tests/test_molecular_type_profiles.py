from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    )


class MolecularTypeProfileStaticTests(
    SimpleTestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_type_profiles.js'
        ).read_text(
            encoding="utf-8"
        )

        self.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_type_profiles.css'
        ).read_text(
            encoding="utf-8"
        )

        self.registry = (
            base
            / "molecular_registry.html"
        ).read_text(
            encoding="utf-8"
        )

        self.detail = (
            base
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

    def test_all_sequence_types_have_profiles(
        self,
    ):
        for sequence_type in (
            "dna",
            "rna",
            "protein",
            "plasmid",
            "primer",
            "insert",
            "other",
        ):
            with self.subTest(
                sequence_type=sequence_type
            ):
                self.assertIn(
                    f'{sequence_type}: Object.freeze(',
                    self.js,
                )

    def test_profile_contract_separates_ready_and_planned(
        self,
    ):
        for marker in (
            "ready: Object.freeze([",
            "planned: Object.freeze([",
            "topologyMeaningful:",
            "registrySummary:",
            "profileFor",
            "normalizeType",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.js,
                )

    def test_profile_module_has_no_network_or_persistence(
        self,
    ):
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "localStorage.setItem",
            "sessionStorage.setItem",
        ):
            with self.subTest(
                forbidden=forbidden
            ):
                self.assertNotIn(
                    forbidden,
                    self.js,
                )

    def test_registry_uses_shared_profile_module(
        self,
    ):
        for marker in (
            "molecular_type_profiles.css",
            "molecular_type_profiles.js",
            (
                'data-molecular-record-type='
                '"{{ molecule.sequence_type }}"'
            ),
            "data-molecular-workspace-summary",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.registry,
                )

    def test_detail_uses_shared_profile_module(
        self,
    ):
        for marker in (
            "molecular_type_profiles.css",
            "molecular_type_profiles.js",
            (
                'data-sequence-type='
                '"{{ molecule.sequence_type }}"'
            ),
            "data-molecular-workspace-label",
            "data-molecular-workspace-description",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.detail,
                )

    def test_current_dna_plasmid_views_are_preserved(
        self,
    ):
        for marker in (
            'data-mw-view="seqviz"',
            'data-mw-view="construction"',
            'data-mw-view="sequence"',
            "molecular_plasmid_map.js",
            "molecular_plasmid_layout.js",
            "molecular_linear_browser.js",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.detail,
                )

    def test_type_profile_styles_exist(
        self,
    ):
        for marker in (
            ".mtr-registry-flow",
            ".mtr-registry-workspace-label",
            ".mtr-registry-workspace-detail",
            ".mtr-workspace-label",
            ".mtr-semantic-secondary",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.css,
                )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularTypeProfileRenderingTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username=(
                    "molecular-type-profile-owner"
                ),
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence
            .objects
            .create(
                name="Protein profile QA",
                sequence_type="protein",
                topology="linear",
                sequence="MKTAYIAKQRQISFVKSHFSRQ",
                owner=self.user,
            )
        )

        self.plasmid = (
            MolecularSequence
            .objects
            .create(
                name="Plasmid profile QA",
                sequence_type="plasmid",
                topology="circular",
                sequence="ATGC" * 50,
                owner=self.user,
            )
        )

        self.client.force_login(
            self.user
        )

    def test_registry_exposes_type_markers(
        self,
    ):
        response = self.client.get(
            request_path(
                "molecular_registry_index",
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                'data-molecular-record-type='
                '"protein"'
            ),
        )

        self.assertContains(
            response,
            (
                'data-molecular-record-type='
                '"plasmid"'
            ),
        )

        self.assertContains(
            response,
            "molecular_type_profiles.js",
        )

    def test_protein_detail_exposes_type_profile_hook(
        self,
    ):
        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                args=[
                    self.protein.id,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                'data-sequence-type='
                '"protein"'
            ),
        )

        self.assertContains(
            response,
            "data-molecular-workspace-label",
        )

        self.assertContains(
            response,
            "molecular_type_profiles.js",
        )
