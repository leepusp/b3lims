from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)


def request_path(name, args=None):
    path = reverse(name, args=args)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNStartShortcutsAndRegistryDeleteTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="shortcut-registry-owner",
            password="test-password",
        )
        self.other = user_model.objects.create_user(
            username="shortcut-registry-other",
            password="test-password",
        )
        self.admin = user_model.objects.create_superuser(
            username="shortcut-registry-admin",
            password="test-password",
            email="admin@example.test",
        )

        self.owned = MolecularSequence.objects.create(
            name="Owner deletable construct",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGC",
            owner=self.owner,
        )
        self.foreign = MolecularSequence.objects.create(
            name="Foreign protected construct",
            sequence_type="dna",
            topology="linear",
            sequence="ATGC",
            owner=self.other,
        )

    def test_empty_eln_exposes_all_primary_shortcuts(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="eln-start-shortcuts"',
        )

        expected_destinations = [
            reverse("samples_list"),
            reverse("chemicals_list"),
            reverse("molecular_registry_index"),
            reverse("jupyter_index"),
        ]

        for destination in expected_destinations:
            with self.subTest(destination=destination):
                self.assertContains(
                    response,
                    destination,
                )

        for label in [
            "Browse samples",
            "Browse reagents",
            "Molecular Registry",
            "Launch Jupyter",
        ]:
            with self.subTest(label=label):
                self.assertContains(
                    response,
                    label,
                )

    def test_owner_sees_delete_for_owned_registry_record(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("molecular_registry_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Owner deletable construct",
        )
        self.assertContains(
            response,
            "data-delete-molecular-record",
        )
        self.assertContains(
            response,
            (
                reverse(
                    "molecular_sequence_delete_api",
                    args=[self.owned.id],
                )
                + "?from=registry"
            ),
        )
        self.assertContains(
            response,
            "Delete",
        )

    def test_superuser_sees_delete_for_all_registry_records(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            request_path("molecular_registry_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "data-delete-molecular-record",
            count=2,
        )

    def test_user_cannot_delete_foreign_registry_record(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            (
                request_path(
                    "molecular_sequence_delete_api",
                    [self.foreign.id],
                )
                + "?from=registry"
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            MolecularSequence.objects.filter(
                id=self.foreign.id
            ).exists()
        )
