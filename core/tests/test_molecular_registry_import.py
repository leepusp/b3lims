from __future__ import annotations

from io import StringIO
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import (
    FeatureLocation,
    SeqFeature,
)
from Bio.SeqRecord import SeqRecord
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularFeature,
    MolecularSequence,
)


def request_path(name, args=None):
    return reverse(
        name,
        args=args,
    ).removeprefix("/biobank")


def registry_genbank_payload() -> bytes:
    record = SeqRecord(
        Seq(
            "ATGCGTACGTTAGCCGATCGATGCTAGCTAGG"
            "CTAACGATCGATCGTACGATCGATGCATGCTA"
            "GCTAGCTAGCATCGATCGATGCTAGCTAACGT"
        ),
        id="RegistryImportVector",
        name="RegistryImportVector",
        description="Registry imported plasmid",
    )

    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"

    record.features = [
        SeqFeature(
            FeatureLocation(
                3,
                38,
                strand=1,
            ),
            type="CDS",
            qualifiers={
                "label": ["Imported CDS"],
                "product": ["Synthetic reporter"],
                "note": [
                    "color: #4F46E5; direction: RIGHT"
                ],
            },
        ),
        SeqFeature(
            FeatureLocation(
                50,
                76,
                strand=-1,
            ),
            type="primer_bind",
            qualifiers={
                "label": ["Imported reverse primer"],
                "note": [
                    "color: green; sequence: AACCGGTT"
                ],
            },
        ),
    ]

    handle = StringIO()

    SeqIO.write(
        record,
        handle,
        "genbank",
    )

    return handle.getvalue().encode(
        "utf-8"
    )


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularRegistryFileImportTests(TestCase):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username="registry-import-owner",
                password="test-password",
            )
        )

        self.client.force_login(
            self.user
        )

    def uploaded_genbank(self):
        return SimpleUploadedFile(
            "registry_vector.gbk",
            registry_genbank_payload(),
            content_type="text/plain",
        )

    def test_preview_endpoint_returns_structure_without_creating(self):
        response = self.client.post(
            request_path(
                "molecular_registry_import_preview_api"
            ),
            {
                "file": self.uploaded_genbank(),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertEqual(
            data["status"],
            "ok",
        )
        self.assertEqual(
            data["record"]["format"],
            "genbank",
        )
        self.assertEqual(
            data["record"]["sequence_type"],
            "plasmid",
        )
        self.assertEqual(
            data["record"]["topology"],
            "circular",
        )
        self.assertEqual(
            data["record"]["feature_count"],
            2,
        )
        self.assertEqual(
            MolecularSequence.objects.count(),
            0,
        )

    def test_registry_upload_creates_record_and_features(self):
        sequence = str(
            SeqIO.read(
                StringIO(
                    registry_genbank_payload()
                    .decode("utf-8")
                ),
                "genbank",
            ).seq
        )

        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Reviewed imported vector",
                "sequence_type": "plasmid",
                "topology": "circular",
                "sequence": sequence,
                "description": (
                    "Reviewed before registry creation"
                ),
                "molecular_file": (
                    self.uploaded_genbank()
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        molecule = (
            MolecularSequence.objects.get()
        )

        self.assertEqual(
            molecule.name,
            "Reviewed imported vector",
        )
        self.assertEqual(
            molecule.sequence_type,
            "plasmid",
        )
        self.assertEqual(
            molecule.topology,
            "circular",
        )
        self.assertEqual(
            molecule.owner,
            self.user,
        )
        self.assertEqual(
            molecule.features.count(),
            2,
        )

        imported_cds = (
            molecule.features.get(
                name="Imported CDS"
            )
        )

        self.assertEqual(
            imported_cds.feature_type,
            "cds",
        )
        self.assertEqual(
            imported_cds.start,
            4,
        )
        self.assertEqual(
            imported_cds.end,
            38,
        )
        self.assertEqual(
            imported_cds.color,
            "#4F46E5",
        )
        self.assertIn(
            "biobank_import",
            imported_cds.qualifiers_json,
        )

        imported_primer = (
            molecule.features.get(
                feature_type="primer"
            )
        )

        self.assertEqual(
            imported_primer.strand,
            "-",
        )

    def test_manual_registry_creation_remains_supported(self):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Manual DNA",
                "sequence_type": "dna",
                "topology": "linear",
                "sequence": "ATGCATGC",
                "description": "Manual record",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        molecule = (
            MolecularSequence.objects.get()
        )

        self.assertEqual(
            molecule.name,
            "Manual DNA",
        )
        self.assertEqual(
            molecule.features.count(),
            0,
        )

    def test_invalid_upload_does_not_create_partial_record(self):
        response = self.client.post(
            request_path(
                "molecular_registry_index"
            ),
            {
                "name": "Invalid imported record",
                "sequence_type": "plasmid",
                "topology": "circular",
                "sequence": "ATGC",
                "molecular_file": (
                    SimpleUploadedFile(
                        "broken.dna",
                        b"not-a-snapgene-file",
                        content_type=(
                            "application/octet-stream"
                        ),
                    )
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            MolecularSequence.objects.count(),
            0,
        )
        self.assertEqual(
            MolecularFeature.objects.count(),
            0,
        )

    def test_registry_template_exposes_import_workflow(self):
        response = self.client.get(
            request_path(
                "molecular_registry_index"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            'id="molecular-registry-create-form"',
        )
        self.assertContains(
            response,
            'enctype="multipart/form-data"',
        )
        self.assertContains(
            response,
            "data-import-preview-url=",
        )
        self.assertContains(
            response,
            "molecular_registry_import.css",
        )
        self.assertContains(
            response,
            "molecular_registry_import.js",
        )
        self.assertContains(
            response,
            "registry-type-aware-import-u1",
        )

        script = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_registry_import.js",
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Import sequence file",
            script,
        )
        self.assertIn(
            "Create imported record",
            script,
        )
        self.assertIn(
            "new FormData()",
            script,
        )
        self.assertIn(
            "molecular_file",
            script,
        )
