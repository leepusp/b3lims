from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    molecular_alignment_upload_to,
)


class _FakeUser:
    def __init__(self, username):
        self.username = username

    def get_username(self):
        return self.username


class MolecularRegistryRoutingStorageTests(
    SimpleTestCase
):
    def test_registry_routes_are_canonical(self):
        routes = (
            (
                "molecular_sequence_detail",
                "/internal/lab-tools/"
                "molecular-registry/87/",
            ),
            (
                "molecular_sequence_import_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/import/",
            ),
            (
                "molecular_sequence_update_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/update/",
            ),
            (
                "molecular_sequence_alignments_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/alignments/",
            ),
            (
                "molecular_sequence_secondary_structures_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/secondary-structures/",
            ),
            (
                "molecular_sequence_restriction_sites_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/restriction-sites/",
            ),
            (
                "molecular_sequence_features_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/features/",
            ),
            (
                "molecular_sequence_delete_api",
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/87/delete/",
            ),
        )

        for name, expected_suffix in routes:
            with self.subTest(name=name):
                url = reverse(name, args=(87,))

                self.assertTrue(
                    url.endswith(expected_suffix),
                    url,
                )

                self.assertNotIn(
                    "/lab-tools/notebook/",
                    url,
                )

    def test_notebook_owned_operations_remain_under_notebook(
        self,
    ):
        for name in (
            "notebook_link_molecular_sequence_api",
            "notebook_create_molecular_sequence_api",
        ):
            with self.subTest(name=name):
                url = reverse(
                    name,
                    args=(12,),
                )

                self.assertIn(
                    "/lab-tools/notebook/",
                    url,
                )

    def test_legacy_routes_remain_available(self):
        names = (
            "legacy_molecular_sequence_detail",
            "legacy_molecular_sequence_import_api",
            "legacy_molecular_sequence_update_api",
            "legacy_molecular_sequence_alignments_api",
            "legacy_molecular_sequence_secondary_structures_api",
            "legacy_molecular_sequence_restriction_sites_api",
            "legacy_molecular_sequence_features_api",
            "legacy_molecular_sequence_delete_api",
        )

        for name in names:
            with self.subTest(name=name):
                url = reverse(
                    name,
                    args=(87,),
                )

                self.assertIn(
                    "/lab-tools/notebook/",
                    url,
                )

    def test_alignment_uses_molecular_record_storage(
        self,
    ):
        instance = SimpleNamespace(
            molecule_id=87,
            uploaded_by_id=1,
            uploaded_by=_FakeUser(
                "ccalomeno"
            ),
        )

        name = molecular_alignment_upload_to(
            instance,
            "alignment.a3m",
        )

        self.assertTrue(
            name.startswith(
                "users/ccalomeno/"
                "molecular/records/87/"
                "alignments/"
            ),
            name,
        )

        self.assertTrue(
            name.endswith(
                "_alignment.a3m"
            ),
            name,
        )

        self.assertNotIn(
            "/eln/",
            name,
        )
        self.assertNotIn(
            "/notebook/",
            name,
        )
        self.assertNotIn(
            "/molecular/sequences/",
            name,
        )
