from __future__ import annotations

import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularAlignment,
    MolecularSequence,
)
from core.services.molecular_alignment import (
    MolecularAlignmentImportError,
    parse_molecular_alignment,
)


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    )


def upload(
    filename,
    content,
):
    return SimpleUploadedFile(
        filename,
        content,
        content_type="text/plain",
    )


class MolecularAlignmentParserTests(
    SimpleTestCase
):
    def test_aligned_fasta(self):
        parsed = parse_molecular_alignment(
            upload(
                "example.afa",
                (
                    b">query\n"
                    b"MKTAYIAKQ-RQISFVK\n"
                    b">homolog\n"
                    b"MKTAYIAKQGRQISFVK\n"
                ),
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "aligned_fasta",
        )

        self.assertEqual(
            parsed["sequence_count"],
            2,
        )

        self.assertEqual(
            parsed["alignment_length"],
            17,
        )

        self.assertEqual(
            parsed["rows"][0]["name"],
            "query",
        )

    def test_clustal(self):
        parsed = parse_molecular_alignment(
            upload(
                "example.aln",
                (
                    b"CLUSTAL W\n\n"
                    b"query      MKTAYIAKQ-RQISFVK\n"
                    b"homolog    MKTAYIAKQGRQISFVK\n"
                ),
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "clustal",
        )

    def test_stockholm(self):
        parsed = parse_molecular_alignment(
            upload(
                "example.sto",
                (
                    b"# STOCKHOLM 1.0\n"
                    b"query MKTAYIAKQ-RQISFVK\n"
                    b"homolog MKTAYIAKQGRQISFVK\n"
                    b"//\n"
                ),
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "stockholm",
        )

    def test_a3m_is_explicitly_deferred(self):
        with self.assertRaises(
            MolecularAlignmentImportError
        ):
            parse_molecular_alignment(
                upload(
                    "example.a3m",
                    (
                        b">query\n"
                        b"MKTAYIAKQRQISFVK\n"
                        b">homolog\n"
                        b"MKTAYIaakQRQISFVK\n"
                    ),
                )
            )

    def test_single_sequence_is_rejected(self):
        with self.assertRaises(
            MolecularAlignmentImportError
        ):
            parse_molecular_alignment(
                upload(
                    "single.afa",
                    (
                        b">query\n"
                        b"MKTAYIAKQRQISFVK\n"
                    ),
                )
            )

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(
            MolecularAlignmentImportError
        ):
            parse_molecular_alignment(
                upload(
                    "duplicate.afa",
                    (
                        b">same\n"
                        b"MKTAYIAKQ-RQISFVK\n"
                        b">same\n"
                        b"MKTAYIAKQGRQISFVK\n"
                    ),
                )
            )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularAlignmentApiTests(
    TestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.storage_directory = (
            tempfile.TemporaryDirectory()
        )

        cls.file_field = (
            MolecularAlignment
            ._meta
            .get_field(
                "file"
            )
        )

        cls.original_storage = (
            cls.file_field.storage
        )

        cls.file_field.storage = (
            FileSystemStorage(
                location=(
                    cls.storage_directory.name
                )
            )
        )

    @classmethod
    def tearDownClass(cls):
        cls.file_field.storage = (
            cls.original_storage
        )

        cls.storage_directory.cleanup()

        super().tearDownClass()

    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="protein-msa-owner",
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username="protein-msa-other",
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="P2B protein",
                sequence_type="protein",
                topology="linear",
                sequence="MKTAYIAKQRQISFVK",
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="P2B DNA",
                sequence_type="dna",
                topology="linear",
                sequence="ATGCGTACGT",
                owner=self.user,
            )
        )

        self.client.force_login(
            self.user
        )

    def aligned_fasta(self):
        return upload(
            "protein_alignment.afa",
            (
                b">query\n"
                b"MKTAYIAKQ-RQISFVK\n"
                b">homolog\n"
                b"MKTAYIAKQGRQISFVK\n"
            ),
        )

    def test_list_initially_empty(self):
        response = self.client.get(
            request_path(
                "molecular_sequence_alignments_api",
                [
                    self.protein.id,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "alignments"
            ],
            [],
        )

    def test_upload_and_read_alignment(self):
        url = request_path(
            "molecular_sequence_alignments_api",
            [
                self.protein.id,
            ],
        )

        response = self.client.post(
            url,
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()[
            "alignment"
        ]

        self.assertEqual(
            payload["sequence_count"],
            2,
        )

        self.assertEqual(
            payload["query_match"]["name"],
            "query",
        )

        alignment_id = payload[
            "id"
        ]

        response = self.client.get(
            url,
            {
                "alignment_id": (
                    alignment_id
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()[
            "alignment"
        ]

        self.assertEqual(
            len(
                payload["rows"]
            ),
            2,
        )

        self.assertEqual(
            payload["rows"][0][
                "name"
            ],
            "query",
        )

    def test_duplicate_file_is_rejected(self):
        url = request_path(
            "molecular_sequence_alignments_api",
            [
                self.protein.id,
            ],
        )

        first = self.client.post(
            url,
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        self.assertEqual(
            first.status_code,
            201,
        )

        second = self.client.post(
            url,
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        self.assertEqual(
            second.status_code,
            409,
        )

        self.assertEqual(
            self.protein.alignments.count(),
            1,
        )

    def test_nonprotein_upload_is_rejected(self):
        response = self.client.post(
            request_path(
                "molecular_sequence_alignments_api",
                [
                    self.dna.id,
                ],
            ),
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            MolecularAlignment.objects.count(),
            0,
        )

    def test_other_user_cannot_access_private_alignment(self):
        url = request_path(
            "molecular_sequence_alignments_api",
            [
                self.protein.id,
            ],
        )

        created = self.client.post(
            url,
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        self.assertEqual(
            created.status_code,
            201,
        )

        self.client.force_login(
            self.other
        )

        response = self.client.get(
            url
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_delete_removes_database_and_file(self):
        url = request_path(
            "molecular_sequence_alignments_api",
            [
                self.protein.id,
            ],
        )

        created = self.client.post(
            url,
            {
                "file": (
                    self.aligned_fasta()
                ),
            },
        )

        payload = created.json()[
            "alignment"
        ]

        alignment = (
            MolecularAlignment.objects.get(
                id=payload[
                    "id"
                ]
            )
        )

        file_path = Path(
            alignment.file.path
        )

        self.assertTrue(
            file_path.exists()
        )

        response = self.client.post(
            url,
            {
                "action": "delete",
                "alignment_id": (
                    alignment.id
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MolecularAlignment.objects.filter(
                id=alignment.id
            ).exists()
        )

        self.assertFalse(
            file_path.exists()
        )


class MolecularAlignmentFrontendTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.base = (
            Path(__file__)
            .resolve()
            .parents[1]
            / "interfaces"
            / "internal"
            / "lab_tools"
        )

        cls.template = (
            cls.base
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

        cls.js = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_alignment.js'
        ).read_text(
            encoding="utf-8"
        )

        cls.css = (
            Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_alignment.css'
        ).read_text(
            encoding="utf-8"
        )

    def test_template_exposes_alignment_api_only(
        self,
    ):
        self.assertIn(
            "data-protein-alignments-url",
            self.template,
        )

        self.assertNotIn(
            "data-protein-msa-vendor-url",
            self.template,
        )

        self.assertNotIn(
            "nightingale-msa-5.6.0.min.js",
            self.template,
        )

    def test_frontend_uses_persisted_rows_as_text_msa(
        self,
    ):
        for marker in (
            "PROTEIN TEXT MSA V1 20260812",
            "payload.rows",
            "MSA_BLOCK_SIZE = 80",
            "makeResidueCell(",
            "mpa-residue",
            '"Consensus"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.js,
                )

        for forbidden in (
            "nightingale-msa",
            "vendorPromise",
            "loadVendor(",
            "viewer.data = rows",
            "viewer.colorScheme",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    self.js,
                )

        self.assertIn(
            "viewer.dataset.sequenceCount",
            self.js,
        )

        self.assertIn(
            "viewer.dataset.alignmentLength",
            self.js,
        )

    def test_alignment_styles_preserve_base_and_final_v1(
        self,
    ):
        for marker in (
            "Protein Alignment / MSA — P2B",
            "PROTEIN FINAL WORKSPACE V1 20260812",
            ".mpa-body",
            ".mpa-sidebar",
            ".mpa-list-item",
            ".mpa-metadata",
            ".mpa-alignment-block-scroll",
            ".mpa-alignment-matrix",
            ".mpa-residue",
            ".mpa-consensus-row",
            "overflow-x: auto;",
            "user-select: text;",
        ):
            with self.subTest(marker=marker):
                self.assertIn(
                    marker,
                    self.css,
                )

        for forbidden in (
            "PROTEIN ALIGNMENT RESPONSIVE V2 20260810",
            "PROTEIN WORKSPACE P3A 20260810",
            "PROTEIN WORKSPACE P3B 20260812",
            "nightingale-msa.mpa-viewer",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    self.css,
                )

    def test_alignment_presentation_does_not_show_sha256(
        self,
    ):
        self.assertNotIn(
            "payload.checksum_sha256",
            self.js,
        )
