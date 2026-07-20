import json

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularFeature,
    MolecularSequence,
    NotebookEntry,
)


def request_path(name, args=None):
    """Return a test-client path without the Apache script prefix."""
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="molecular-owner",
            password="test-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="molecular-viewer",
            password="test-password",
        )
        self.entry = NotebookEntry.objects.create(
            title="Molecular workspace test",
            author=self.user,
        )
        self.client.force_login(self.user)

    def create_molecule(
        self,
        *,
        name="Test plasmid",
        sequence_type="plasmid",
        topology="circular",
        sequence="ATGCGTACGT",
    ):
        response = self.client.post(
            request_path(
                "notebook_create_molecular_sequence_api",
                [self.entry.id],
            ),
            data=json.dumps(
                {
                    "name": name,
                    "sequence_type": sequence_type,
                    "topology": topology,
                    "sequence": sequence,
                    "description": "Test molecular record",
                }
            ),
            content_type="application/json",
        )
        return response

    def test_create_normalizes_single_fasta_record(self):
        response = self.create_molecule(
            name="FASTA plasmid",
            sequence=">plasmid\nATGC RYSW\nKMBDHVN\n",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["sequence_type"], "plasmid")
        self.assertEqual(payload["topology"], "circular")
        self.assertEqual(payload["source_entry_id"], self.entry.id)
        self.assertEqual(payload["description"], "Test molecular record")
        self.assertTrue(payload["detail_url"])

        molecule = MolecularSequence.objects.get()
        self.assertEqual(molecule.sequence, "ATGCRYSWKMBDHVN")
        self.assertEqual(molecule.length, 15)
        self.assertEqual(molecule.owner, self.user)
        self.assertEqual(molecule.source_entry, self.entry)
        self.assertTrue(molecule.checksum_sha256)

    def test_create_rejects_invalid_dna(self):
        response = self.create_molecule(
            sequence_type="dna",
            topology="linear",
            sequence="ATUGC",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("Invalid character", response.json()["message"])
        self.assertFalse(MolecularSequence.objects.exists())

    def test_create_rejects_multiple_fasta_records(self):
        response = self.create_molecule(
            sequence=(
                ">first\nATGC\n"
                ">second\nATGC\n"
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Only one FASTA record",
            response.json()["message"],
        )
        self.assertFalse(MolecularSequence.objects.exists())

    def test_circular_feature_may_cross_origin(self):
        create_response = self.create_molecule()
        molecule = MolecularSequence.objects.get(
            id=create_response.json()["id"]
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_features_api",
                [molecule.id],
            ),
            data=json.dumps(
                {
                    "features": [
                        {
                            "name": "Origin-spanning feature",
                            "type": "custom",
                            "start": 8,
                            "end": 2,
                            "strand": "+",
                            "color": "#3366CC",
                            "notes": "Crosses coordinate 1",
                            "qualifiers": {
                                "label": "origin-spanning",
                            },
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        feature = MolecularFeature.objects.get(
            molecule=molecule
        )
        self.assertEqual(feature.start, 8)
        self.assertEqual(feature.end, 2)
        self.assertEqual(
            feature.qualifiers_json["label"],
            "origin-spanning",
        )

    def test_linear_feature_cannot_cross_origin(self):
        create_response = self.create_molecule(
            sequence_type="dna",
            topology="linear",
        )
        molecule = MolecularSequence.objects.get(
            id=create_response.json()["id"]
        )
        existing = MolecularFeature.objects.create(
            molecule=molecule,
            name="Existing feature",
            feature_type="custom",
            start=1,
            end=3,
            color="#868E96",
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_features_api",
                [molecule.id],
            ),
            data=json.dumps(
                {
                    "features": [
                        {
                            "name": "Invalid feature",
                            "type": "custom",
                            "start": 8,
                            "end": 2,
                            "strand": "+",
                            "color": "#3366CC",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "crosses the origin",
            response.json()["message"],
        )
        self.assertTrue(
            MolecularFeature.objects.filter(
                pk=existing.pk
            ).exists()
        )

    def test_update_rejects_sequence_classification_change(self):
        create_response = self.create_molecule(
            sequence_type="dna",
            topology="linear",
            sequence="ATGCGT",
        )
        molecule = MolecularSequence.objects.get(
            id=create_response.json()["id"]
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_update_api",
                [molecule.id],
            ),
            data=json.dumps(
                {
                    "name": molecule.name,
                    "sequence_type": "protein",
                    "topology": "linear",
                    "sequence": molecule.sequence,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "classification is fixed",
            response.json()["message"],
        )

        molecule.refresh_from_db()

        self.assertEqual(
            molecule.sequence_type,
            "dna",
        )
        self.assertEqual(
            molecule.sequence,
            "ATGCGT",
        )

    def test_update_rejects_invalid_sequence_without_modifying_record(self):
        create_response = self.create_molecule(
            sequence_type="dna",
            topology="linear",
            sequence="ATGCGT",
        )
        molecule = MolecularSequence.objects.get(
            id=create_response.json()["id"]
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_update_api",
                [molecule.id],
            ),
            data=json.dumps(
                {
                    "name": "Changed name",
                    "sequence_type": "dna",
                    "topology": "linear",
                    "sequence": "ATUGC",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        molecule.refresh_from_db()
        self.assertEqual(molecule.name, "Test plasmid")
        self.assertEqual(molecule.sequence, "ATGCGT")

    def test_other_user_cannot_access_private_molecule(self):
        create_response = self.create_molecule()
        molecule_id = create_response.json()["id"]

        self.client.force_login(self.other_user)

        detail = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [molecule_id],
            )
        )
        features = self.client.get(
            request_path(
                "molecular_sequence_features_api",
                [molecule_id],
            )
        )

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(features.status_code, 404)

    def test_legacy_features_json_field_is_removed(self):
        with self.assertRaises(FieldDoesNotExist):
            MolecularSequence._meta.get_field("features_json")
