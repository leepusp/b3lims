from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import (
    CompoundLocation,
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


def genbank_payload() -> bytes:
    sequence = Seq(
        "ATGCGTACGTTAGCCGATCGATGCTAGCTAGGCTAACG"
        * 6
    )

    record = SeqRecord(
        sequence,
        id="ImportedVector",
        name="ImportedVector",
        description=(
            "Complete GenBank molecular import test"
        ),
    )

    record.annotations["molecule_type"] = "DNA"
    record.annotations["topology"] = "circular"

    record.features = [
        SeqFeature(
            FeatureLocation(
                3,
                45,
                strand=1,
            ),
            type="CDS",
            qualifiers={
                "label": ["Reporter CDS"],
                "product": ["Synthetic reporter"],
                "note": [
                    "Imported biological note.",
                    "color: #4F46E5; direction: RIGHT",
                ],
            },
        ),
        SeqFeature(
            FeatureLocation(
                60,
                82,
                strand=-1,
            ),
            type="primer_bind",
            qualifiers={
                "label": ["Reverse primer"],
                "note": [
                    "color: green; "
                    "sequence: AACCGGTTAACCGGTT"
                ],
            },
        ),
        SeqFeature(
            CompoundLocation(
                [
                    FeatureLocation(
                        190,
                        len(sequence),
                        strand=1,
                    ),
                    FeatureLocation(
                        0,
                        15,
                        strand=1,
                    ),
                ],
                operator="join",
            ),
            type="misc_feature",
            qualifiers={
                "label": [
                    "Origin-spanning feature"
                ],
                "ApEinfo_fwdcolor": [
                    "#E84393"
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
class MolecularFileImportTests(TestCase):
    def setUp(self):
        self.owner = (
            get_user_model()
            .objects
            .create_user(
                username="molecular-import-owner",
                password="test-password",
            )
        )

        self.other_user = (
            get_user_model()
            .objects
            .create_user(
                username="molecular-import-other",
                password="test-password",
            )
        )

        self.molecule = (
            MolecularSequence.objects.create(
                name="Existing molecule",
                sequence_type="dna",
                topology="linear",
                sequence="ATGCATGC",
                owner=self.owner,
            )
        )

    def test_genbank_parser_preserves_structure(self):
        uploaded = SimpleUploadedFile(
            "complete_vector.gb",
            genbank_payload(),
            content_type="text/plain",
        )

        imported = parse_molecular_file(
            uploaded
        )

        self.assertEqual(
            imported["format"],
            "genbank",
        )
        self.assertEqual(
            imported["sequence_type"],
            "plasmid",
        )
        self.assertEqual(
            imported["topology"],
            "circular",
        )
        self.assertEqual(
            imported["feature_count"],
            3,
        )

        reporter = imported["features"][0]

        self.assertEqual(
            reporter["name"],
            "Reporter CDS",
        )
        self.assertEqual(
            reporter["type"],
            "cds",
        )
        self.assertEqual(
            reporter["start"],
            4,
        )
        self.assertEqual(
            reporter["end"],
            45,
        )
        self.assertEqual(
            reporter["strand"],
            "+",
        )
        self.assertEqual(
            reporter["color"],
            "#4F46E5",
        )

        primer = imported["features"][1]

        self.assertEqual(
            primer["type"],
            "primer",
        )
        self.assertEqual(
            primer["strand"],
            "-",
        )
        self.assertEqual(
            primer["color"],
            "#27AE60",
        )

        compound = imported["features"][2]

        self.assertGreater(
            len(
                compound["qualifiers"]
                ["biobank_import"]
                ["segments"]
            ),
            1,
        )
        self.assertGreater(
            compound["start"],
            compound["end"],
        )
        self.assertTrue(
            imported["warnings"]
        )

    def test_plain_text_sequence_remains_supported(self):
        uploaded = SimpleUploadedFile(
            "sequence.txt",
            b"ATGC ATGC\nAATT\n",
            content_type="text/plain",
        )

        imported = parse_molecular_file(
            uploaded
        )

        self.assertEqual(
            imported["format"],
            "raw",
        )
        self.assertEqual(
            imported["sequence"],
            "ATGCATGCAATT",
        )
        self.assertEqual(
            imported["feature_count"],
            0,
        )

    def test_import_endpoint_returns_preview_without_saving(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_import_api",
                [self.molecule.id],
            ),
            {
                "file": SimpleUploadedFile(
                    "complete_vector.gbk",
                    genbank_payload(),
                    content_type="text/plain",
                ),
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
            data["record"]["feature_count"],
            3,
        )
        self.assertEqual(
            data["record"]["topology"],
            "circular",
        )

        self.molecule.refresh_from_db()

        self.assertEqual(
            self.molecule.sequence,
            "ATGCATGC",
        )
        self.assertEqual(
            self.molecule.topology,
            "linear",
        )

    def test_import_endpoint_requires_edit_permission(self):
        self.client.force_login(
            self.other_user
        )

        response = self.client.post(
            request_path(
                "molecular_sequence_import_api",
                [self.molecule.id],
            ),
            {
                "file": SimpleUploadedFile(
                    "complete_vector.gb",
                    genbank_payload(),
                    content_type="text/plain",
                ),
            },
        )

        self.assertIn(
            response.status_code,
            {403, 404},
        )

    def test_snapgene_extension_uses_snapgene_reader(self):
        record = SeqRecord(
            Seq("ATGCATGC"),
            id="SnapGeneVector",
            name="SnapGeneVector",
        )

        record.annotations["molecule_type"] = "DNA"
        record.annotations["topology"] = "circular"

        uploaded = SimpleUploadedFile(
            "vector.dna",
            b"\x09\x00synthetic-snapgene-test",
            content_type="application/octet-stream",
        )

        with patch(
            "core.services.molecular_file_import."
            "SeqIO.read",
            return_value=record,
        ) as mocked_read:
            imported = parse_molecular_file(
                uploaded
            )

        self.assertEqual(
            mocked_read.call_args.args[1],
            "snapgene",
        )
        self.assertEqual(
            imported["format"],
            "snapgene",
        )
        self.assertEqual(
            imported["sequence_type"],
            "plasmid",
        )

    def test_frontend_exposes_structured_import(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            'data-import-url="',
        )
        self.assertContains(
            response,
            "Import sequence file",
        )
        self.assertContains(
            response,
            ".dna,.gb,.gbk,.gbff,.genbank,.ape,.embl",
        )
        self.assertContains(
            response,
            "molecular_workspace.js?v=",
        )

        workspace = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()

        self.assertIn(
            "async function importMolecularFile(file)",
            workspace,
        )
        self.assertIn(
            "function applyImportedMolecularRecord(record)",
            workspace,
        )
        self.assertIn(
            "root.dataset.importUrl",
            workspace,
        )
        self.assertIn(
            "new FormData()",
            workspace,
        )
        self.assertIn(
            "Nothing will be persisted until you click Save.",
            workspace,
        )
        self.assertNotIn(
            "new FileReader()",
            workspace,
        )
        self.assertNotIn(
            "function importFastaFile(file)",
            workspace,
        )
