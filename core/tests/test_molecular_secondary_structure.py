from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSecondaryStructure,
    MolecularSequence,
)
from core.services.molecular_secondary_structure import (
    MolecularSecondaryStructureImportError,
    parse_secondary_structure_source,
    validate_dot_bracket,
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    ).removeprefix(
        "/biobank"
    )


class MolecularSecondaryStructureParserTests(
    SimpleTestCase
):
    def test_canonical_dot_bracket(self):
        parsed = parse_secondary_structure_source(
            "(((...)))",
            molecule_sequence="GGGAAACCC",
        )

        self.assertEqual(
            parsed["source_format"],
            "dot_bracket",
        )

        self.assertEqual(
            parsed["structure"],
            "(((...)))",
        )

        self.assertEqual(
            parsed["structure_length"],
            9,
        )

        self.assertEqual(
            parsed["pair_count"],
            3,
        )

        self.assertIsNone(
            parsed["minimum_free_energy"]
        )

    def test_simple_dbn(self):
        parsed = parse_secondary_structure_source(
            (
                ">hairpin\n"
                "GGGAAACCC\n"
                "(((...)))\n"
            ),
            molecule_sequence="GGGAAACCC",
            filename="hairpin.dbn",
        )

        self.assertEqual(
            parsed["source_format"],
            "dbn",
        )

        self.assertEqual(
            parsed["name"],
            "hairpin",
        )

        self.assertEqual(
            parsed["original_filename"],
            "hairpin.dbn",
        )

        self.assertTrue(
            parsed["source_sequence_present"]
        )

    def test_rnafold_style_preserves_explicit_mfe(self):
        parsed = parse_secondary_structure_source(
            (
                "GGGAAACCC\n"
                "(((...))) (-1.20)\n"
            ),
            molecule_sequence="GGGAAACCC",
        )

        self.assertEqual(
            parsed["source_format"],
            "rnafold",
        )

        self.assertEqual(
            parsed["minimum_free_energy"],
            Decimal("-1.20"),
        )

    def test_two_line_sequence_structure_without_mfe(self):
        parsed = parse_secondary_structure_source(
            (
                "GGGAAACCC\n"
                "(((...)))\n"
            ),
            molecule_sequence="GGGAAACCC",
        )

        self.assertEqual(
            parsed["source_format"],
            "sequence_dot_bracket",
        )

        self.assertIsNone(
            parsed["minimum_free_energy"]
        )

    def test_sequence_mismatch_is_rejected_without_t_u_conversion(self):
        with self.assertRaises(
            MolecularSecondaryStructureImportError
        ):
            parse_secondary_structure_source(
                (
                    "ATGC\n"
                    "(())\n"
                ),
                molecule_sequence="AUGC",
            )

    def test_pseudoknot_brackets_are_deferred(self):
        with self.assertRaises(
            MolecularSecondaryStructureImportError
        ):
            parse_secondary_structure_source(
                "[[..]]",
                molecule_sequence="AUGCAU",
            )

    def test_unbalanced_structure_is_rejected(self):
        with self.assertRaises(
            MolecularSecondaryStructureImportError
        ):
            validate_dot_bracket(
                "((....)",
                expected_length=7,
            )

    def test_length_mismatch_is_rejected(self):
        with self.assertRaises(
            MolecularSecondaryStructureImportError
        ):
            parse_secondary_structure_source(
                "((...))",
                molecule_sequence="GGGAAACCC",
            )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularSecondaryStructureApiTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="rna-structure-owner",
            password="test-password",
        )

        self.other = User.objects.create_user(
            username="rna-structure-other",
            password="test-password",
        )

        self.rna = MolecularSequence.objects.create(
            name="R1B RNA",
            sequence_type="rna",
            topology="linear",
            sequence="GGGAAACCC",
            owner=self.user,
        )

        self.dna = MolecularSequence.objects.create(
            name="R1B DNA",
            sequence_type="dna",
            topology="linear",
            sequence="GGGAAACCC",
            owner=self.user,
        )

        self.client.force_login(
            self.user
        )

    @property
    def rna_url(self):
        return request_path(
            "molecular_sequence_secondary_structures_api",
            [
                self.rna.id,
            ],
        )

    def test_list_initially_empty(self):
        response = self.client.get(
            self.rna_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "secondary_structures"
            ],
            [],
        )

    def test_save_direct_structure_and_read_detail(self):
        response = self.client.post(
            self.rna_url,
            {
                "name": "Canonical hairpin",
                "source_text": "(((...)))",
                "source_method": "Imported",
                "source_note": "Controlled R1B test.",
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()[
            "secondary_structure"
        ]

        self.assertEqual(
            payload["name"],
            "Canonical hairpin",
        )

        self.assertEqual(
            payload["structure"],
            "(((...)))",
        )

        self.assertEqual(
            payload["pair_count"],
            3,
        )

        self.assertEqual(
            payload["source_format"],
            "dot_bracket",
        )

        self.assertIsNone(
            payload["minimum_free_energy"]
        )

        structure_id = payload["id"]

        response = self.client.get(
            self.rna_url,
            {
                "structure_id": structure_id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        detail = response.json()[
            "secondary_structure"
        ]

        self.assertEqual(
            detail["source_text"],
            "(((...)))",
        )

    def test_upload_dbn(self):
        file = SimpleUploadedFile(
            "hairpin.dbn",
            (
                b">hairpin\n"
                b"GGGAAACCC\n"
                b"(((...)))\n"
            ),
            content_type="text/plain",
        )

        response = self.client.post(
            self.rna_url,
            {
                "file": file,
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()[
            "secondary_structure"
        ]

        self.assertEqual(
            payload["name"],
            "hairpin",
        )

        self.assertEqual(
            payload["original_filename"],
            "hairpin.dbn",
        )

        self.assertEqual(
            payload["source_format"],
            "dbn",
        )

    def test_upload_rnafold_style_preserves_mfe(self):
        file = SimpleUploadedFile(
            "rnafold.txt",
            (
                b"GGGAAACCC\n"
                b"(((...))) (-1.20)\n"
            ),
            content_type="text/plain",
        )

        response = self.client.post(
            self.rna_url,
            {
                "file": file,
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()[
            "secondary_structure"
        ]

        self.assertEqual(
            payload["minimum_free_energy"],
            "-1.2000",
        )

        self.assertEqual(
            payload["source_format"],
            "rnafold",
        )

        structure_id = payload["id"]

        response = self.client.get(
            self.rna_url,
            {
                "structure_id": structure_id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "secondary_structure"
            ][
                "minimum_free_energy"
            ],
            "-1.2000",
        )

    def test_exact_duplicate_source_is_rejected(self):
        first = self.client.post(
            self.rna_url,
            {
                "source_text": "(((...)))",
            },
        )

        self.assertEqual(
            first.status_code,
            201,
        )

        second = self.client.post(
            self.rna_url,
            {
                "source_text": "(((...)))",
            },
        )

        self.assertEqual(
            second.status_code,
            409,
        )

        self.assertEqual(
            self.rna
            .secondary_structures
            .count(),
            1,
        )

    def test_non_rna_api_is_rejected(self):
        response = self.client.post(
            request_path(
                "molecular_sequence_secondary_structures_api",
                [
                    self.dna.id,
                ],
            ),
            {
                "source_text": "(((...)))",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            MolecularSecondaryStructure
            .objects
            .count(),
            0,
        )

    def test_other_user_cannot_access_private_rna(self):
        self.client.force_login(
            self.other
        )

        response = self.client.get(
            self.rna_url
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_delete(self):
        created = self.client.post(
            self.rna_url,
            {
                "source_text": "(((...)))",
            },
        )

        self.assertEqual(
            created.status_code,
            201,
        )

        structure_id = created.json()[
            "secondary_structure"
        ][
            "id"
        ]

        response = self.client.post(
            self.rna_url,
            {
                "action": "delete",
                "structure_id": structure_id,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MolecularSecondaryStructure
            .objects
            .filter(
                id=structure_id
            )
            .exists()
        )

    def test_file_and_source_text_together_are_rejected(self):
        file = SimpleUploadedFile(
            "hairpin.dbn",
            (
                b">hairpin\n"
                b"GGGAAACCC\n"
                b"(((...)))\n"
            ),
            content_type="text/plain",
        )

        response = self.client.post(
            self.rna_url,
            {
                "file": file,
                "source_text": "(((...)))",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_model_rejects_non_rna_parent(self):
        structure = MolecularSecondaryStructure(
            molecule=self.dna,
            name="Invalid",
            structure=".........",
            source_format="dot_bracket",
            source_text=".........",
            checksum_sha256=(
                "0" * 64
            ),
            created_by=self.user,
        )

        with self.assertRaises(
            ValidationError
        ):
            structure.save()
