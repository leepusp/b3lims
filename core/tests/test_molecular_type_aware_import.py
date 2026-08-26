from __future__ import annotations

import warnings
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
)
from core.services.molecular_file_import import (
    parse_molecular_file,
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    )


def uploaded(
    name: str,
    content: bytes,
):
    return SimpleUploadedFile(
        name,
        content,
        content_type="text/plain",
    )


class MolecularTypeAwareParserTests(
    TestCase
):
    def test_faa_is_strong_protein_detection(
        self,
    ):
        record = parse_molecular_file(
            uploaded(
                "example.faa",
                (
                    b">protein\n"
                    b"MKTAYIAKQRQISFVKSHFSRQ\n"
                ),
            )
        )

        self.assertEqual(
            record["detected_content"],
            "protein",
        )

        self.assertEqual(
            record["suggested_sequence_type"],
            "protein",
        )

        self.assertEqual(
            record["detection_confidence"],
            "strong",
        )

        self.assertFalse(
            record[
                "requires_type_confirmation"
            ]
        )

        self.assertEqual(
            record[
                "compatible_sequence_types"
            ],
            [
                "protein",
                "other",
            ],
        )

    def test_frn_is_strong_rna_detection(
        self,
    ):
        record = parse_molecular_file(
            uploaded(
                "example.frn",
                (
                    b">rna\n"
                    b"AUGCUUACGGAU\n"
                ),
            )
        )

        self.assertEqual(
            record["detected_content"],
            "rna",
        )

        self.assertEqual(
            record["suggested_sequence_type"],
            "rna",
        )

        self.assertEqual(
            record["detection_confidence"],
            "strong",
        )

        self.assertIn(
            "rna",
            record[
                "compatible_sequence_types"
            ],
        )

    def test_generic_dna_fasta_requires_confirmation(
        self,
    ):
        record = parse_molecular_file(
            uploaded(
                "construct.fasta",
                (
                    b">construct\n"
                    b"ATGCGTACGTAGCTAGCTAA\n"
                ),
            )
        )

        self.assertEqual(
            record["detected_content"],
            "nucleotide",
        )

        self.assertEqual(
            record["suggested_sequence_type"],
            "dna",
        )

        self.assertEqual(
            record["detection_confidence"],
            "ambiguous",
        )

        self.assertTrue(
            record[
                "requires_type_confirmation"
            ]
        )

        for sequence_type in (
            "dna",
            "plasmid",
            "primer",
            "insert",
            "other",
        ):
            with self.subTest(
                sequence_type=sequence_type
            ):
                self.assertIn(
                    sequence_type,
                    record[
                        "compatible_sequence_types"
                    ],
                )

        self.assertNotIn(
            "rna",
            record[
                "compatible_sequence_types"
            ],
        )

    def test_nucleotide_without_t_or_u_can_be_rna_or_dna(
        self,
    ):
        record = parse_molecular_file(
            uploaded(
                "ambiguous.fa",
                (
                    b">ambiguous\n"
                    b"ACGACGACGACG\n"
                ),
            )
        )

        for sequence_type in (
            "dna",
            "rna",
            "plasmid",
            "primer",
            "insert",
            "other",
        ):
            with self.subTest(
                sequence_type=sequence_type
            ):
                self.assertIn(
                    sequence_type,
                    record[
                        "compatible_sequence_types"
                    ],
                )

    def test_leading_fasta_comments_are_normalized(
        self,
    ):
        with warnings.catch_warnings(
            record=True
        ) as caught:
            warnings.simplefilter(
                "always"
            )

            record = parse_molecular_file(
                uploaded(
                    "commented.fasta",
                    (
                        b"# legacy exporter comment\n"
                        b"; secondary comment\n"
                        b">sequence\n"
                        b"ATGCGTACGT\n"
                    ),
                )
            )

        self.assertEqual(
            record["length"],
            10,
        )

        messages = [
            str(
                warning.message
            )
            for warning in caught
        ]

        self.assertFalse(
            any(
                (
                    "FASTA parser silently ignored "
                    "comments at the beginning"
                )
                in message
                for message in messages
            )
        )

    def test_plain_text_sequence_skips_fasta_probe_warning(
        self,
    ):
        with warnings.catch_warnings(
            record=True
        ) as caught:
            warnings.simplefilter(
                "always"
            )

            record = parse_molecular_file(
                uploaded(
                    "sequence.txt",
                    b"ATGCGTACGT\n",
                )
            )

        self.assertEqual(
            record["format"],
            "raw",
        )

        self.assertEqual(
            record["sequence"],
            "ATGCGTACGT",
        )

        messages = [
            str(
                warning.message
            )
            for warning in caught
        ]

        self.assertFalse(
            any(
                (
                    "FASTA parser silently ignored "
                    "comments at the beginning"
                )
                in message
                for message in messages
            )
        )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularTypeAwareRegistryTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="type-aware-import-owner",
                password="test-password",
            )
        )

        self.client.force_login(
            self.user
        )

    def nucleotide_file(
        self,
        name="construct.fasta",
    ):
        return uploaded(
            name,
            (
                b">construct\n"
                b"ATGCGTACGTAGCTAGCTAA\n"
            ),
        )

    def protein_file(
        self,
    ):
        return uploaded(
            "protein.faa",
            (
                b">protein\n"
                b"MKTAYIAKQRQISFVKSHFSRQ\n"
            ),
        )

    def test_preview_exposes_detection_metadata(
        self,
    ):
        response = self.client.post(
            request_path(
                "molecular_registry_import_preview_api"
            ),
            {
                "file": (
                    self.nucleotide_file()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        record = response.json()[
            "record"
        ]

        for key in (
            "detected_content",
            "detected_content_label",
            "suggested_sequence_type",
            "suggested_sequence_type_label",
            "detection_confidence",
            "detection_confidence_label",
            "detection_reason",
            "requires_type_confirmation",
            "compatible_sequence_types",
        ):
            with self.subTest(
                key=key
            ):
                self.assertIn(
                    key,
                    record,
                )

    def test_ambiguous_import_requires_confirmation(
        self,
    ):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Unconfirmed primer",
                "sequence_type": "primer",
                "topology": "linear",
                "molecular_file": (
                    self.nucleotide_file()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MolecularSequence.objects.filter(
                name="Unconfirmed primer",
            ).exists()
        )

    def test_confirmed_primer_forces_linear(
        self,
    ):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Confirmed primer",
                "sequence_type": "primer",
                "topology": "circular",
                "type_confirmation": "confirmed",
                "molecular_file": (
                    self.nucleotide_file()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        molecule = (
            MolecularSequence.objects.get(
                name="Confirmed primer",
            )
        )

        self.assertEqual(
            molecule.sequence_type,
            "primer",
        )

        self.assertEqual(
            molecule.topology,
            "linear",
        )

    def test_confirmed_plasmid_forces_circular(
        self,
    ):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Confirmed plasmid",
                "sequence_type": "plasmid",
                "topology": "linear",
                "type_confirmation": "confirmed",
                "molecular_file": (
                    self.nucleotide_file()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        molecule = (
            MolecularSequence.objects.get(
                name="Confirmed plasmid",
            )
        )

        self.assertEqual(
            molecule.sequence_type,
            "plasmid",
        )

        self.assertEqual(
            molecule.topology,
            "circular",
        )

    def test_protein_file_cannot_be_created_as_dna(
        self,
    ):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Invalid protein DNA",
                "sequence_type": "dna",
                "topology": "linear",
                "molecular_file": (
                    self.protein_file()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MolecularSequence.objects.filter(
                name="Invalid protein DNA",
            ).exists()
        )


class MolecularTypeAwareFrontendTests(
    TestCase
):
    def setUp(self):
        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        self.registry_js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_registry_import.js'
        ).read_text(
            encoding="utf-8"
        )

        self.registry_css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_registry_import.css'
        ).read_text(
            encoding="utf-8"
        )

        self.registry_html = (
            base
            / "molecular_registry.html"
        ).read_text(
            encoding="utf-8"
        )

        self.workspace_js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js'
        ).read_text(
            encoding="utf-8"
        )

        self.detail_html = (
            base
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

    def test_registry_uploader_exposes_sequence_formats(
        self,
    ):
        for extension in (
            ".dna",
            ".gb",
            ".gbk",
            ".gbff",
            ".genbank",
            ".ape",
            ".embl",
            ".fa",
            ".fasta",
            ".fna",
            ".ffn",
            ".faa",
            ".frn",
            ".txt",
        ):
            with self.subTest(
                extension=extension
            ):
                self.assertIn(
                    extension,
                    self.registry_js,
                )

    def test_registry_has_type_confirmation_flow(
        self,
    ):
        for marker in (
            "mri-type-confirmation",
            "requires_type_confirmation",
            "compatible_sequence_types",
            "renderTypeAwareFields(",
            "renderDetection(",
            "applyTopologyPolicy(",
            'form.elements.namedItem(',
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.registry_js,
                )

    def test_registry_detection_styles_exist(
        self,
    ):
        for marker in (
            ".mri-detection",
            ".mri-detection-grid",
            ".mri-type-confirmation",
            "#molecule-type option:disabled",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.registry_css,
                )

    def test_detail_import_preserves_existing_type(
        self,
    ):
        for marker in (
            "assertImportedRecordCompatibility(",
            "importedCompatibleTypes(",
            "importedTopologyForType(",
            "Current record type:",
        ):
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.workspace_js,
                )

        self.assertNotIn(
            (
                "elements.type.value = String(\n"
                "                record.sequence_type"
            ),
            self.workspace_js,
        )

    def test_static_versions_are_bumped(
        self,
    ):
        for pattern in (
            (
                r"molecular_registry_import\.css' %}"
                r"\?v=[A-Za-z0-9._-]+"
            ),
            (
                r"molecular_registry_import\.js' %}"
                r"\?v=[A-Za-z0-9._-]+"
            ),
        ):
            with self.subTest(
                registry_asset_pattern=pattern
            ):
                self.assertRegex(
                    self.registry_html,
                    pattern,
                )

        self.assertRegex(
            self.detail_html,
            (
                r"molecular_workspace\.js' %}"
                r"\?v=[A-Za-z0-9._-]+"
            ),
        )

        self.assertNotIn(
            "?v=20260806-registry-file-import",
            self.registry_html,
        )
        self.assertNotIn(
            "?v=20260806-molecular-file-import",
            self.detail_html,
        )
