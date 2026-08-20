from __future__ import annotations

import json

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
from core.services.molecular_restriction_sites import (
    MolecularRestrictionSiteError,
    analyze_restriction_sites,
    restriction_enzyme_metadata,
)


def request_path(
    name,
    args=None,
):
    """
    Normalize the production FORCE_SCRIPT_NAME prefix for
    Django's in-process test client.

    Production reverse() may expose /biobank even while tests
    dispatch against the root URLconf directly.
    """
    return reverse(
        name,
        args=args,
    ).removeprefix("/biobank")


class MolecularRestrictionSiteServiceTests(
    SimpleTestCase
):
    def test_selected_enzymes_are_reported_with_cut_metadata(
        self,
    ):
        analysis = analyze_restriction_sites(
            "AAAAGAATTCTTTTGGATCC",
            topology="linear",
            mode="selected",
            selected_enzymes=[
                "EcoRI",
                "BamHI",
            ],
        )

        self.assertEqual(
            analysis["sequence_length"],
            20,
        )

        self.assertEqual(
            analysis["site_count"],
            2,
        )

        sites = {
            item["enzyme"]: item
            for item in analysis["sites"]
        }

        self.assertEqual(
            sites["EcoRI"]["position"],
            6,
        )

        self.assertEqual(
            sites["BamHI"]["position"],
            16,
        )

        self.assertEqual(
            sites["EcoRI"]["recognition_sequence"],
            "GAATTC",
        )

        self.assertEqual(
            sites["EcoRI"]["overhang_type"],
            "5_prime",
        )

        self.assertEqual(
            sites["EcoRI"]["overhang_length"],
            4,
        )

        self.assertTrue(
            sites["EcoRI"]["unique"]
        )

    def test_circular_analysis_detects_site_across_origin(
        self,
    ):
        sequence = (
            "TTC"
            + ("A" * 20)
            + "GAA"
        )

        linear = analyze_restriction_sites(
            sequence,
            topology="linear",
            mode="selected",
            selected_enzymes=["EcoRI"],
        )

        circular = analyze_restriction_sites(
            sequence,
            topology="circular",
            mode="selected",
            selected_enzymes=["EcoRI"],
        )

        self.assertEqual(
            linear["site_count"],
            0,
        )

        self.assertEqual(
            circular["site_count"],
            1,
        )

        self.assertEqual(
            circular["sites"][0]["enzyme"],
            "EcoRI",
        )

        self.assertEqual(
            circular["sites"][0]["position"],
            25,
        )

    def test_enzyme_names_are_case_insensitive(
        self,
    ):
        analysis = analyze_restriction_sites(
            "AAAAGAATTCTTTT",
            mode="selected",
            selected_enzymes=["ecori"],
        )

        self.assertEqual(
            analysis["sites"][0]["enzyme"],
            "EcoRI",
        )

    def test_unknown_enzyme_is_rejected(
        self,
    ):
        with self.assertRaises(
            MolecularRestrictionSiteError
        ):
            analyze_restriction_sites(
                "ATGCATGC",
                mode="selected",
                selected_enzymes=[
                    "DefinitelyNotAnEnzyme",
                ],
            )

    def test_enzyme_metadata_exposes_cut_properties(
        self,
    ):
        metadata = restriction_enzyme_metadata(
            [
                "EcoRI",
                "NotI",
            ]
        )

        by_name = {
            item["name"]: item
            for item in metadata
        }

        self.assertEqual(
            by_name["NotI"]["recognition_sequence"],
            "GCGGCCGC",
        )

        self.assertEqual(
            by_name["NotI"]["recognition_length"],
            8,
        )

        self.assertTrue(
            by_name["EcoRI"]["commercial_common"]
        )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularRestrictionSiteApiTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="restriction-map-owner",
            password="test-password",
        )

        self.other_user = User.objects.create_user(
            username="restriction-map-other",
            password="test-password",
        )

        self.molecule = (
            MolecularSequence.objects.create(
                name="Restriction map plasmid",
                sequence_type="plasmid",
                topology="circular",
                sequence="ATGC",
                owner=self.user,
            )
        )

        self.client.force_login(
            self.user
        )

    def endpoint(
        self,
        molecule=None,
    ):
        target = (
            molecule
            or self.molecule
        )

        return request_path(
            "molecular_sequence_restriction_sites_api",
            args=[target.id],
        )

    def test_api_analyzes_unsaved_workspace_sequence_without_persisting_it(
        self,
    ):
        response = self.client.post(
            self.endpoint(),
            data=json.dumps(
                {
                    "sequence": (
                        "AAAAGAATTCTTTTGGATCC"
                    ),
                    "topology": "linear",
                    "mode": "selected",
                    "selected_enzymes": [
                        "EcoRI",
                        "BamHI",
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()

        self.assertEqual(
            payload["status"],
            "success",
        )

        analysis = payload["analysis"]

        self.assertEqual(
            analysis["sequence_length"],
            20,
        )

        self.assertEqual(
            analysis["site_count"],
            2,
        )

        self.assertEqual(
            [
                (
                    item["enzyme"],
                    item["position"],
                )
                for item
                in analysis["sites"]
            ],
            [
                ("EcoRI", 6),
                ("BamHI", 16),
            ],
        )

        self.molecule.refresh_from_db()

        self.assertEqual(
            self.molecule.sequence,
            "ATGC",
        )

    def test_api_supports_unique_common_catalog(
        self,
    ):
        response = self.client.post(
            self.endpoint(),
            data=json.dumps(
                {
                    "sequence": (
                        "AAAAGAATTCTTTTGGATCC"
                    ),
                    "topology": "linear",
                    "mode": "unique",
                    "catalog": "common",
                    "minimum_site_length": 6,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        analysis = response.json()["analysis"]

        self.assertEqual(
            analysis["mode"],
            "unique",
        )

        self.assertEqual(
            analysis["catalog"],
            "common",
        )

        self.assertTrue(
            all(
                item["unique"]
                for item in analysis["enzymes"]
            )
        )

        self.assertIn(
            "EcoRI",
            {
                item["enzyme"]
                for item in analysis["sites"]
            },
        )

    def test_api_rejects_non_post_requests(
        self,
    ):
        response = self.client.get(
            self.endpoint()
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_api_rejects_non_dna_record_types(
        self,
    ):
        protein = (
            MolecularSequence.objects.create(
                name="Protein record",
                sequence_type="protein",
                topology="linear",
                sequence="MPEPTIDE",
                owner=self.user,
            )
        )

        response = self.client.post(
            self.endpoint(protein),
            data=json.dumps(
                {
                    "mode": "unique",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "DNA",
            response.json()["message"],
        )

    def test_api_does_not_expose_another_users_record(
        self,
    ):
        hidden = (
            MolecularSequence.objects.create(
                name="Hidden plasmid",
                sequence_type="plasmid",
                topology="circular",
                sequence="GAATTC",
                owner=self.other_user,
            )
        )

        response = self.client.post(
            self.endpoint(hidden),
            data=json.dumps(
                {
                    "mode": "selected",
                    "selected_enzymes": [
                        "EcoRI",
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_detail_template_exposes_restriction_analysis_url(
        self,
    ):
        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                args=[self.molecule.id],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "data-restriction-sites-url=",
        )

        self.assertContains(
            response,
            request_path(
                "molecular_sequence_restriction_sites_api",
                args=[self.molecule.id],
            ),
        )
