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
    override_settings,
)
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    MolecularStructure,
)


PDB_CONTENT = (
    b"HEADER    BIOBANK PROTEIN STRUCTURE QA\n"
    b"ATOM      1  N   ALA A   1      "
    b"11.104  13.207   8.100  1.00 20.00           N\n"
    b"ATOM      2  CA  ALA A   1      "
    b"12.560  13.407   8.200  1.00 20.00           C\n"
    b"END\n"
)

MMCIF_CONTENT = (
    b"data_biobank_structure_api\n"
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


def request_path(
    name,
    args=None,
):
    return reverse(
        name,
        args=args,
    )


def upload(
    filename="protein_model.pdb",
    content=PDB_CONTENT,
):
    return SimpleUploadedFile(
        filename,
        content,
        content_type="text/plain",
    )


@override_settings(
    FORCE_SCRIPT_NAME=None
)
class MolecularProteinStructureApiTests(
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
                username=(
                    "protein-structure-api-owner"
                ),
                password="test-password",
            )
        )

        self.other = (
            get_user_model()
            .objects.create_user(
                username=(
                    "protein-structure-api-other"
                ),
                password="test-password",
            )
        )

        self.protein = (
            MolecularSequence.objects.create(
                name=(
                    "Protein structure API QA"
                ),
                sequence_type="protein",
                topology="linear",
                sequence="MAAAAA",
                owner=self.user,
            )
        )

        self.dna = (
            MolecularSequence.objects.create(
                name="DNA structure API QA",
                sequence_type="dna",
                topology="linear",
                sequence="ATGCGC",
                owner=self.user,
            )
        )

        self.client.force_login(
            self.user
        )

    def url(
        self,
        molecule=None,
    ):
        target = (
            molecule
            or self.protein
        )

        return request_path(
            "molecular_sequence_structures_api",
            [
                target.id,
            ],
        )

    def upload_structure(
        self,
        *,
        filename="protein_model.pdb",
        content=PDB_CONTENT,
        label="QA model",
    ):
        return self.client.post(
            self.url(),
            {
                "file": upload(
                    filename,
                    content,
                ),
                "label": label,
            },
        )

    def test_list_initially_empty(self):
        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "structures"
            ],
            [],
        )

    def test_upload_pdb_and_list(self):
        response = (
            self.upload_structure()
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        payload = response.json()[
            "structure"
        ]

        self.assertEqual(
            payload[
                "label"
            ],
            "QA model",
        )

        self.assertEqual(
            payload[
                "source_format"
            ],
            "pdb",
        )

        self.assertEqual(
            payload[
                "original_filename"
            ],
            "protein_model.pdb",
        )

        self.assertEqual(
            payload[
                "checksum_sha256"
            ],
            hashlib.sha256(
                PDB_CONTENT
            ).hexdigest(),
        )

        self.assertEqual(
            self.protein.structures.count(),
            1,
        )

        listed_response = (
            self.client.get(
                self.url()
            )
        )

        self.assertEqual(
            listed_response.status_code,
            200,
        )

        listed = (
            listed_response.json()[
                "structures"
            ]
        )

        self.assertEqual(
            len(
                listed
            ),
            1,
        )

        self.assertEqual(
            listed[0][
                "id"
            ],
            payload[
                "id"
            ],
        )

    def test_upload_mmcif(self):
        response = (
            self.upload_structure(
                filename=(
                    "protein_model.cif"
                ),
                content=MMCIF_CONTENT,
            )
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        self.assertEqual(
            response.json()[
                "structure"
            ][
                "source_format"
            ],
            "mmcif",
        )

    def test_duplicate_file_is_rejected(self):
        first = (
            self.upload_structure()
        )

        self.assertEqual(
            first.status_code,
            201,
        )

        second = (
            self.upload_structure(
                label=(
                    "Duplicate model"
                ),
            )
        )

        self.assertEqual(
            second.status_code,
            409,
        )

        self.assertEqual(
            self.protein.structures.count(),
            1,
        )

    def test_nonprotein_upload_is_rejected(self):
        response = self.client.post(
            self.url(
                self.dna
            ),
            {
                "file": upload(),
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            MolecularStructure.objects.count(),
            0,
        )

    def test_detail_metadata(self):
        created = (
            self.upload_structure()
        )

        structure_id = (
            created.json()[
                "structure"
            ][
                "id"
            ]
        )

        response = self.client.get(
            self.url(),
            {
                "structure_id": (
                    structure_id
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()[
                "structure"
            ][
                "id"
            ],
            structure_id,
        )

    def test_raw_stream_is_inline(self):
        created = (
            self.upload_structure()
        )

        structure_id = (
            created.json()[
                "structure"
            ][
                "id"
            ]
        )

        response = self.client.get(
            self.url(),
            {
                "structure_id": (
                    structure_id
                ),
                "raw": "1",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = b"".join(
            response.streaming_content
        )

        self.assertEqual(
            body,
            PDB_CONTENT,
        )

        disposition = (
            response.headers.get(
                "Content-Disposition",
                "",
            )
        )

        self.assertIn(
            "inline",
            disposition.lower(),
        )

        self.assertEqual(
            response.headers[
                "Content-Type"
            ],
            "chemical/x-pdb",
        )

    def test_download_is_attachment(self):
        created = (
            self.upload_structure()
        )

        structure_id = (
            created.json()[
                "structure"
            ][
                "id"
            ]
        )

        response = self.client.get(
            self.url(),
            {
                "structure_id": (
                    structure_id
                ),
                "download": "1",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        disposition = (
            response.headers.get(
                "Content-Disposition",
                "",
            )
        )

        self.assertIn(
            "attachment",
            disposition.lower(),
        )

        self.assertIn(
            "protein_model.pdb",
            disposition,
        )

        body = b"".join(
            response.streaming_content
        )

        self.assertEqual(
            body,
            PDB_CONTENT,
        )

    def test_delete_removes_database_and_file(
        self,
    ):
        created = (
            self.upload_structure()
        )

        structure_id = (
            created.json()[
                "structure"
            ][
                "id"
            ]
        )

        structure = (
            MolecularStructure.objects.get(
                id=structure_id
            )
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

        response = self.client.post(
            self.url(),
            {
                "action": "delete",
                "structure_id": (
                    structure_id
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MolecularStructure.objects.filter(
                id=structure_id
            ).exists()
        )

        self.assertFalse(
            storage.exists(
                stored_name
            )
        )

    def test_invalid_structure_id_is_rejected(
        self,
    ):
        response = self.client.get(
            self.url(),
            {
                "structure_id": (
                    "not-an-id"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_unsupported_action_is_rejected(
        self,
    ):
        response = self.client.post(
            self.url(),
            {
                "action": "rename",
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_other_user_cannot_read_owner_structure(
        self,
    ):
        created = (
            self.upload_structure()
        )

        self.assertEqual(
            created.status_code,
            201,
        )

        self.client.force_login(
            self.other
        )

        response = self.client.get(
            self.url()
        )

        self.assertIn(
            response.status_code,
            {
                403,
                404,
            },
        )

    def test_other_user_cannot_upload_to_owner_record(
        self,
    ):
        self.client.force_login(
            self.other
        )

        response = self.client.post(
            self.url(),
            {
                "file": upload(),
            },
        )

        self.assertIn(
            response.status_code,
            {
                403,
                404,
            },
        )

        self.assertEqual(
            MolecularStructure.objects.count(),
            0,
        )

    def test_anonymous_access_requires_login(
        self,
    ):
        self.client.logout()

        response = self.client.get(
            self.url()
        )

        self.assertEqual(
            response.status_code,
            302,
        )


class MolecularProteinStructureFrontendContractTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        core_dir = (
            Path(__file__)
            .resolve()
            .parents[1]
        )

        repo_dir = (
            core_dir.parent
        )

        cls.template = (
            core_dir
            / "interfaces"
            / "internal"
            / "lab_tools"
            / "molecular_sequence_detail.html"
        ).read_text(
            encoding="utf-8"
        )

        cls.urls = (
            repo_dir
            / "biobank"
            / "urls.py"
        ).read_text(
            encoding="utf-8"
        )

    def test_template_exposes_structure_api_url(
        self,
    ):
        self.assertIn(
            (
                'data-protein-structures-url="'
                "{% url "
                "'molecular_sequence_structures_api' "
                "molecule.id %}"
                '"'
            ),
            self.template,
        )

    def test_canonical_structure_route_is_present(
        self,
    ):
        self.assertIn(
            (
                "api/records/<int:sequence_id>/"
                "structures/"
            ),
            self.urls,
        )

        self.assertIn(
            "molecular_sequence_structures_api",
            self.urls,
        )
