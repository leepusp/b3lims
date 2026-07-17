import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularFeature,
    MolecularSequence,
)


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularWorkspaceAtomicTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="molecular-atomic-owner",
            password="test-password",
        )
        self.molecule = MolecularSequence.objects.create(
            name="Original molecule",
            sequence_type="dna",
            topology="linear",
            sequence="ATGC",
            owner=self.user,
        )
        self.original_feature = MolecularFeature.objects.create(
            molecule=self.molecule,
            name="Original feature",
            feature_type="custom",
            start=1,
            end=2,
            strand="+",
            color="#8f96a3",
            order=0,
        )
        self.client.force_login(self.user)

    def test_atomic_update_saves_sequence_and_features(self):
        response = self.client.post(
            request_path(
                "molecular_sequence_update_api",
                [self.molecule.id],
            ),
            data=json.dumps(
                {
                    "name": "Updated molecule",
                    "sequence_type": "dna",
                    "topology": "linear",
                    "description": "Transactional update",
                    "sequence": "ATGCGG",
                    "features": [
                        {
                            "name": "Validated CDS",
                            "type": "cds",
                            "start": 2,
                            "end": 6,
                            "strand": "+",
                            "color": "#4f8cff",
                            "notes": "Saved atomically",
                            "qualifiers": {},
                            "order": 0,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        self.molecule.refresh_from_db()
        self.assertEqual(
            self.molecule.name,
            "Updated molecule",
        )
        self.assertEqual(
            self.molecule.sequence,
            "ATGCGG",
        )
        self.assertEqual(
            self.molecule.features.count(),
            1,
        )
        self.assertEqual(
            self.molecule.features.get().name,
            "Validated CDS",
        )

    def test_invalid_feature_rolls_back_entire_update(self):
        response = self.client.post(
            request_path(
                "molecular_sequence_update_api",
                [self.molecule.id],
            ),
            data=json.dumps(
                {
                    "name": "Should not persist",
                    "sequence_type": "dna",
                    "topology": "linear",
                    "description": "Invalid transaction",
                    "sequence": "ATGCGGTT",
                    "features": [
                        {
                            "name": "Invalid crossing feature",
                            "type": "custom",
                            "start": 8,
                            "end": 2,
                            "strand": "+",
                            "color": "#8f96a3",
                            "notes": "",
                            "qualifiers": {},
                            "order": 0,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        self.molecule.refresh_from_db()
        self.assertEqual(
            self.molecule.name,
            "Original molecule",
        )
        self.assertEqual(
            self.molecule.sequence,
            "ATGC",
        )
        self.assertEqual(
            self.molecule.features.count(),
            1,
        )
        self.assertEqual(
            self.molecule.features.get().name,
            "Original feature",
        )
