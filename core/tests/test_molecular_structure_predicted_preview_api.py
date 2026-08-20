from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import (
    RequestFactory,
    SimpleTestCase,
)
from django.urls import reverse

from core.services.structure_search.preview import (
    StructurePreviewFetchError,
    StructurePreviewQueryError,
)
from core.views.internal.lab_tools import (
    notebook,
)


def expected_url(
    path,
):
    prefix = str(
        settings.FORCE_SCRIPT_NAME
        or ""
    ).rstrip(
        "/"
    )

    if not path.startswith(
        "/"
    ):
        path = (
            "/"
            + path
        )

    return (
        prefix
        + path
    )


class PredictedStructurePreviewApiTests(
    SimpleTestCase
):
    def setUp(
        self,
    ):
        self.factory = (
            RequestFactory()
        )

        self.user = (
            SimpleNamespace(
                is_authenticated=True,
            )
        )

        self.molecule = (
            SimpleNamespace(
                id=103,
                sequence_type="protein",
                sequence="MALWMRLL",
            )
        )

    def request(
        self,
        *,
        method="get",
        params=None,
    ):
        url = reverse(
            "molecular_sequence_structure_preview_api",
            args=[
                103,
            ],
        )

        factory_method = getattr(
            self.factory,
            method,
        )

        request = factory_method(
            url,
            data=(
                params
                or {}
            ),
        )

        request.user = (
            self.user
        )

        return request

    def test_route(
        self,
    ):
        actual = reverse(
            "molecular_sequence_structure_preview_api",
            args=[
                103,
            ],
        )

        expected = expected_url(
            (
                "/internal/lab-tools/"
                "molecular-registry/api/"
                "records/103/structure-preview/"
            )
        )

        self.assertEqual(
            actual,
            expected,
        )

    def test_get_required(
        self,
    ):
        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(
                    method="post"
                ),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    @patch.object(
        notebook,
        "_get_molecular_sequence_for_user",
    )
    def test_protein_required(
        self,
        get_molecule,
    ):
        get_molecule.return_value = (
            SimpleNamespace(
                id=103,
                sequence_type="dna",
                sequence="ATGC",
            )
        )

        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(
                    params={
                        "canonical_key":
                            "alphafold:test",
                    }
                ),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch.object(
        notebook,
        "_get_molecular_sequence_for_user",
    )
    def test_canonical_key_required(
        self,
        get_molecule,
    ):
        get_molecule.return_value = (
            self.molecule
        )

        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "core.services.structure_search.preview."
        "fetch_computational_structure_preview"
    )
    @patch.object(
        notebook,
        "_get_molecular_sequence_for_user",
    )
    def test_success_returns_controlled_mmcif(
        self,
        get_molecule,
        fetch_preview,
    ):
        get_molecule.return_value = (
            self.molecule
        )

        fetch_preview.return_value = {
            "content":
                b"data_AF-P01308-F1\n#\n",

            "filename":
                "AF-P01308-F1.cif",

            "canonical_key":
                "alphafold:AF-P01308-F1",

            "provider":
                "alphafold-db",

            "provider_name":
                "AlphaFold DB",

            "accession":
                "AF-P01308-F1",

            "coordinate_format":
                "mmcif",
        }

        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(
                    params={
                        "canonical_key":
                            "alphafold:AF-P01308-F1",
                    }
                ),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.content,
            b"data_AF-P01308-F1\n#\n",
        )

        self.assertTrue(
            response[
                "Content-Type"
            ].startswith(
                "chemical/x-cif"
            )
        )

        self.assertEqual(
            response[
                "X-Biobank-Structure-Preview"
            ],
            "alphafold:AF-P01308-F1",
        )

        self.assertEqual(
            response[
                "X-Biobank-Structure-Provider"
            ],
            "alphafold-db",
        )

        fetch_preview.assert_called_once_with(
            "MALWMRLL",
            "alphafold:AF-P01308-F1",
        )

    @patch(
        "core.services.structure_search.preview."
        "fetch_computational_structure_preview"
    )
    @patch.object(
        notebook,
        "_get_molecular_sequence_for_user",
    )
    def test_query_error_is_400(
        self,
        get_molecule,
        fetch_preview,
    ):
        get_molecule.return_value = (
            self.molecule
        )

        fetch_preview.side_effect = (
            StructurePreviewQueryError(
                "Unknown predicted model."
            )
        )

        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(
                    params={
                        "canonical_key":
                            "alphafold:missing",
                    }
                ),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "core.services.structure_search.preview."
        "fetch_computational_structure_preview"
    )
    @patch.object(
        notebook,
        "_get_molecular_sequence_for_user",
    )
    def test_fetch_error_is_502(
        self,
        get_molecule,
        fetch_preview,
    ):
        get_molecule.return_value = (
            self.molecule
        )

        fetch_preview.side_effect = (
            StructurePreviewFetchError(
                "Provider unavailable."
            )
        )

        response = (
            notebook
            .molecular_sequence_structure_preview_api(
                self.request(
                    params={
                        "canonical_key":
                            "alphafold:test",
                    }
                ),
                103,
            )
        )

        self.assertEqual(
            response.status_code,
            502,
        )
