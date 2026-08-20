from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import (
    SimpleTestCase,
    TestCase,
)

from core.models.lab_tools.notebook import (
    MolecularSequence,
    MolecularStructure,
)
from core.services.molecular_structure import (
    MolecularStructureImportError,
    parse_molecular_structure,
)


PDB_CONTENT = (
    b"HEADER    BIOBANK QA STRUCTURE\n"
    b"ATOM      1  N   ALA A   1      "
    b"11.104  13.207   8.100  1.00 20.00           N\n"
    b"ATOM      2  CA  ALA A   1      "
    b"12.560  13.407   8.200  1.00 20.00           C\n"
    b"END\n"
)

MMCIF_CONTENT = (
    b"data_biobank_qa\n"
    b"#\n"
    b"loop_\n"
    b"_atom_site.group_PDB\n"
    b"_atom_site.id\n"
    b"_atom_site.type_symbol\n"
    b"_atom_site.label_atom_id\n"
    b"_atom_site.label_comp_id\n"
    b"_atom_site.label_asym_id\n"
    b"_atom_site.label_seq_id\n"
    b"_atom_site.Cartn_x\n"
    b"_atom_site.Cartn_y\n"
    b"_atom_site.Cartn_z\n"
    b"ATOM 1 N N ALA A 1 11.104 13.207 8.100\n"
    b"#\n"
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


class MolecularStructureParserTests(
    SimpleTestCase
):
    def test_pdb_is_recognized(self):
        parsed = parse_molecular_structure(
            upload(
                "model.pdb",
                PDB_CONTENT,
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "pdb",
        )

        self.assertEqual(
            parsed["original_filename"],
            "model.pdb",
        )

        self.assertEqual(
            parsed["size_bytes"],
            len(PDB_CONTENT),
        )

        self.assertEqual(
            parsed["checksum_sha256"],
            hashlib.sha256(
                PDB_CONTENT
            ).hexdigest(),
        )

    def test_cif_is_normalized_to_mmcif(self):
        parsed = parse_molecular_structure(
            upload(
                "model.cif",
                MMCIF_CONTENT,
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "mmcif",
        )

    def test_mmcif_extension_is_supported(self):
        parsed = parse_molecular_structure(
            upload(
                "model.mmcif",
                MMCIF_CONTENT,
            )
        )

        self.assertEqual(
            parsed["source_format"],
            "mmcif",
        )

    def test_unsupported_extension_is_rejected(self):
        with self.assertRaises(
            MolecularStructureImportError
        ):
            parse_molecular_structure(
                upload(
                    "model.xyz",
                    PDB_CONTENT,
                )
            )

    def test_fake_pdb_is_rejected(self):
        with self.assertRaises(
            MolecularStructureImportError
        ):
            parse_molecular_structure(
                upload(
                    "fake.pdb",
                    b"this is not a PDB file\n",
                )
            )

    def test_fake_mmcif_is_rejected(self):
        with self.assertRaises(
            MolecularStructureImportError
        ):
            parse_molecular_structure(
                upload(
                    "fake.cif",
                    b"data_fake\n_no_atoms_here 1\n",
                )
            )

    def test_empty_file_is_rejected(self):
        with self.assertRaises(
            MolecularStructureImportError
        ):
            parse_molecular_structure(
                upload(
                    "empty.pdb",
                    b"",
                )
            )


class MolecularStructureModelTests(
    TestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.storage_directory = (
            tempfile.TemporaryDirectory()
        )

        cls.file_field = (
            MolecularStructure
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
                username="protein-structure-owner",
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name="Structure QA Protein",
                sequence_type="protein",
                topology="linear",
                sequence="MAAAAA",
                owner=self.user,
            )
        )

    def create_structure(
        self,
        *,
        checksum="",
    ):
        return MolecularStructure.objects.create(
            molecule=self.protein,
            file=upload(
                "qa_model.pdb",
                PDB_CONTENT,
            ),
            label="QA model",
            original_filename="qa_model.pdb",
            source_format="pdb",
            checksum_sha256=checksum,
            uploaded_by=self.user,
        )

    def test_structure_relation_is_persisted(self):
        structure = self.create_structure(
            checksum=hashlib.sha256(
                PDB_CONTENT
            ).hexdigest()
        )

        self.assertEqual(
            self.protein.structures.count(),
            1,
        )

        self.assertEqual(
            self.protein.structures.get().id,
            structure.id,
        )

    def test_storage_path_is_record_scoped(self):
        structure = self.create_structure(
            checksum=hashlib.sha256(
                PDB_CONTENT
            ).hexdigest()
        )

        expected = (
            f"users/{self.user.username}/"
            f"molecular/records/{self.protein.id}/"
            "structures/"
        )

        self.assertIn(
            expected,
            structure.file.name,
        )

        self.assertEqual(
            Path(
                structure.file.name
            ).suffix,
            ".pdb",
        )

    def test_checksum_is_calculated_when_missing(self):
        structure = self.create_structure()

        self.assertEqual(
            structure.checksum_sha256,
            hashlib.sha256(
                PDB_CONTENT
            ).hexdigest(),
        )

    def test_deleting_record_deletes_stored_file(self):
        structure = self.create_structure(
            checksum=hashlib.sha256(
                PDB_CONTENT
            ).hexdigest()
        )

        stored_name = (
            structure.file.name
        )

        storage = (
            structure.file.storage
        )

        self.assertTrue(
            storage.exists(
                stored_name
            )
        )

        structure.delete()

        self.assertFalse(
            storage.exists(
                stored_name
            )
        )

    def test_string_prefers_label(self):
        structure = self.create_structure(
            checksum=hashlib.sha256(
                PDB_CONTENT
            ).hexdigest()
        )

        self.assertEqual(
            str(structure),
            "QA model",
        )
