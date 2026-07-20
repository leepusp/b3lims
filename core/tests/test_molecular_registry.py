from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)



def request_path(name, args=None):
    """Return a test-client path without the Apache prefix."""
    return reverse(
        name,
        args=args,
    ).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularRegistryTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="registry-owner",
            password="test-password",
        )
        self.other = user_model.objects.create_user(
            username="registry-other",
            password="test-password",
        )
        self.admin = user_model.objects.create_superuser(
            username="registry-admin",
            password="test-password",
            email="admin@example.test",
        )

        self.owned = MolecularSequence.objects.create(
            name="Owned plasmid",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCGCAT",
            owner=self.owner,
        )
        self.foreign = MolecularSequence.objects.create(
            name="Foreign sequence",
            sequence_type="dna",
            topology="linear",
            sequence="ATGC",
            owner=self.other,
        )

        self.url = request_path(
            "molecular_registry_index"
        )

    def test_registry_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_owner_sees_only_visible_records(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owned plasmid")
        self.assertNotContains(
            response,
            "Foreign sequence",
        )

    def test_superuser_sees_all_records(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owned plasmid")
        self.assertContains(response, "Foreign sequence")

    def test_registry_filters_by_type(self):
        self.client.force_login(self.owner)

        MolecularSequence.objects.create(
            name="Owner protein",
            sequence_type="protein",
            topology="linear",
            sequence="MKWVTF",
            owner=self.owner,
        )

        response = self.client.get(
            self.url,
            {"type": "protein"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner protein")
        self.assertNotContains(response, "Owned plasmid")

    def test_registry_searches_by_name(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            self.url,
            {"q": "plasmid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owned plasmid")

    def test_owner_can_create_standalone_record(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            self.url,
            {
                "name": "Registered construct",
                "sequence_type": "dna",
                "topology": "linear",
                "sequence": ">construct\nATGC ATGC",
                "description": "Standalone construct",
            },
        )

        molecule = MolecularSequence.objects.get(
            name="Registered construct"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(molecule.owner, self.owner)
        self.assertIsNone(molecule.source_entry)
        self.assertIsNone(molecule.linked_sample)
        self.assertEqual(molecule.sequence, "ATGCATGC")
        self.assertEqual(molecule.length, 8)

    def test_invalid_sequence_is_not_created(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            self.url,
            {
                "name": "Invalid DNA",
                "sequence_type": "dna",
                "topology": "linear",
                "sequence": "ATGC!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            MolecularSequence.objects.filter(
                name="Invalid DNA"
            ).exists()
        )

    def test_registry_detail_link_preserves_origin(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        expected_url = (
            reverse(
                "molecular_sequence_detail",
                args=[self.owned.id],
            )
            + "?from=registry"
        )

        self.assertContains(
            response,
            expected_url,
        )

    def test_standalone_detail_returns_to_registry(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.owned.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                'data-back-url="'
                + reverse(
                    "molecular_registry_index"
                )
                + '"'
            ),
        )
        self.assertContains(
            response,
            "Molecular Registry",
        )

    def test_standalone_delete_returns_to_registry(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            (
                request_path(
                    "molecular_sequence_delete_api",
                    [self.owned.id],
                )
                + "?from=registry"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["redirect_url"],
            reverse(
                "molecular_registry_index"
            ),
        )
        self.assertFalse(
            MolecularSequence.objects.filter(
                id=self.owned.id
            ).exists()
        )

    def test_sidebar_contains_registry_navigation(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        self.assertContains(
            response,
            "Molecular Registry",
        )
        self.assertContains(
            response,
            "bi-bezier2",
        )
