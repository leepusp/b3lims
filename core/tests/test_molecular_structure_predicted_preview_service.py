from unittest.mock import patch

from django.test import SimpleTestCase

from core.services.structure_search.preview import (
    MAX_PREDICTED_PREVIEW_BYTES,
    StructurePreviewFetchError,
    StructurePreviewQueryError,
    _download_mmcif,
    _normalize_canonical_key,
    _safe_filename,
    _validated_coordinate_url,
    fetch_computational_structure_preview,
)


class FakeResult:
    def __init__(
        self,
        hits,
    ):
        self.hits = hits

    def to_dict(
        self,
    ):
        return {
            "hits":
                self.hits,
        }


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        headers=None,
        chunks=(),
    ):
        self.status_code = status_code

        self.headers = dict(
            headers
            or {}
        )

        self._chunks = list(
            chunks
        )

        self.closed = False

    def iter_content(
        self,
        chunk_size,
    ):
        del chunk_size

        yield from self._chunks

    def close(
        self,
    ):
        self.closed = True


class FakeSession:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []
        self.closed = False

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (
                url,
                kwargs,
            )
        )

        return self.responses.pop(
            0
        )

    def close(
        self,
    ):
        self.closed = True


class PredictedStructurePreviewServiceTests(
    SimpleTestCase
):
    def test_requires_canonical_key(
        self,
    ):
        with self.assertRaises(
            StructurePreviewQueryError
        ):
            _normalize_canonical_key(
                ""
            )

    def test_allows_only_known_https_hosts(
        self,
    ):
        self.assertEqual(
            _validated_coordinate_url(
                (
                    "https://alphafold.ebi.ac.uk/"
                    "files/AF-P01308-F1-model_v6.cif"
                )
            ),
            (
                "https://alphafold.ebi.ac.uk/"
                "files/AF-P01308-F1-model_v6.cif"
            ),
        )

        self.assertEqual(
            _validated_coordinate_url(
                (
                    "https://swissmodel.expasy.org/"
                    "3d-beacons/example.cif"
                )
            ),
            (
                "https://swissmodel.expasy.org/"
                "3d-beacons/example.cif"
            ),
        )

        for invalid in (
            "http://alphafold.ebi.ac.uk/test.cif",
            "https://example.org/test.cif",
            (
                "https://user:pass@"
                "alphafold.ebi.ac.uk/test.cif"
            ),
            (
                "https://alphafold.ebi.ac.uk:"
                "444/test.cif"
            ),
        ):
            with self.assertRaises(
                StructurePreviewFetchError
            ):
                _validated_coordinate_url(
                    invalid
                )

    def test_safe_filename(
        self,
    ):
        self.assertEqual(
            _safe_filename(
                "AF-P01308-F1"
            ),
            "AF-P01308-F1.cif",
        )

        self.assertEqual(
            _safe_filename(
                "a/b:c"
            ),
            "a_b_c.cif",
        )

    def test_download_accepts_mmcif(
        self,
    ):
        response = FakeResponse(
            status_code=200,
            headers={
                "Content-Length":
                    "14",
            },
            chunks=[
                b"data_model\n#\n",
            ],
        )

        session = FakeSession(
            [
                response,
            ]
        )

        content = _download_mmcif(
            (
                "https://alphafold.ebi.ac.uk/"
                "files/test.cif"
            ),
            session=session,
        )

        self.assertEqual(
            content,
            b"data_model\n#\n",
        )

        self.assertTrue(
            response.closed
        )

        self.assertFalse(
            session.closed
        )

        self.assertFalse(
            session.calls[
                0
            ][
                1
            ][
                "allow_redirects"
            ]
        )

    def test_redirect_host_is_revalidated(
        self,
    ):
        first = FakeResponse(
            status_code=302,
            headers={
                "Location":
                    "https://example.org/evil.cif",
            },
        )

        session = FakeSession(
            [
                first,
            ]
        )

        with self.assertRaises(
            StructurePreviewFetchError
        ):
            _download_mmcif(
                (
                    "https://alphafold.ebi.ac.uk/"
                    "files/test.cif"
                ),
                session=session,
            )

    def test_advertised_oversize_is_rejected(
        self,
    ):
        response = FakeResponse(
            status_code=200,
            headers={
                "Content-Length":
                    str(
                        MAX_PREDICTED_PREVIEW_BYTES
                        + 1
                    ),
            },
            chunks=[],
        )

        session = FakeSession(
            [
                response,
            ]
        )

        with self.assertRaises(
            StructurePreviewFetchError
        ):
            _download_mmcif(
                (
                    "https://alphafold.ebi.ac.uk/"
                    "files/test.cif"
                ),
                session=session,
            )

    def test_streamed_oversize_is_rejected(
        self,
    ):
        response = FakeResponse(
            status_code=200,
            chunks=[
                b"x" * 11,
            ],
        )

        session = FakeSession(
            [
                response,
            ]
        )

        with self.assertRaises(
            StructurePreviewFetchError
        ):
            _download_mmcif(
                (
                    "https://alphafold.ebi.ac.uk/"
                    "files/test.cif"
                ),
                session=session,
                max_bytes=10,
            )

    def test_non_mmcif_body_is_rejected(
        self,
    ):
        response = FakeResponse(
            status_code=200,
            chunks=[
                b"<html>not cif</html>",
            ],
        )

        session = FakeSession(
            [
                response,
            ]
        )

        with self.assertRaises(
            StructurePreviewFetchError
        ):
            _download_mmcif(
                (
                    "https://alphafold.ebi.ac.uk/"
                    "files/test.cif"
                ),
                session=session,
            )

    @patch(
        "core.services.structure_search.preview."
        "_download_mmcif"
    )
    @patch(
        "core.services.structure_search.preview."
        "search_structures_by_sequence"
    )
    def test_preview_revalidates_canonical_key_server_side(
        self,
        search,
        download,
    ):
        search.return_value = FakeResult(
            [
                {
                    "provider":
                        "alphafold-db",

                    "provider_name":
                        "AlphaFold DB",

                    "source_type":
                        "computational",

                    "accession":
                        "AF-P01308-F1",

                    "canonical_key":
                        "alphafold:AF-P01308-F1",

                    "coordinate_format":
                        "MMCIF",

                    "coordinate_url":
                        (
                            "https://alphafold.ebi.ac.uk/"
                            "files/AF-P01308-F1-model_v6.cif"
                        ),
                },
            ]
        )

        download.return_value = (
            b"data_AF-P01308-F1\n#\n"
        )

        preview = (
            fetch_computational_structure_preview(
                "MALWMRLL",
                "alphafold:AF-P01308-F1",
            )
        )

        self.assertEqual(
            preview[
                "canonical_key"
            ],
            "alphafold:AF-P01308-F1",
        )

        self.assertEqual(
            preview[
                "provider"
            ],
            "alphafold-db",
        )

        self.assertEqual(
            preview[
                "filename"
            ],
            "AF-P01308-F1.cif",
        )

        search.assert_called_once()

        args, kwargs = search.call_args

        self.assertEqual(
            args,
            (
                "MALWMRLL",
            ),
        )

        self.assertEqual(
            kwargs[
                "rows"
            ],
            100,
        )

        providers = kwargs[
            "providers"
        ]

        self.assertEqual(
            len(
                providers
            ),
            1,
        )

        provider = providers[
            0
        ]

        self.assertNotIsInstance(
            provider,
            str,
        )

        self.assertTrue(
            callable(
                getattr(
                    provider,
                    "search_by_sequence",
                    None,
                )
            )
        )

        from core.services.structure_search.search import (
            _provider_key,
        )

        self.assertEqual(
            _provider_key(
                provider
            ),
            "beacons3d-exact",
        )

        download.assert_called_once()

    @patch(
        "core.services.structure_search.preview."
        "search_structures_by_sequence"
    )
    def test_unknown_model_is_rejected(
        self,
        search,
    ):
        search.return_value = (
            FakeResult(
                []
            )
        )

        with self.assertRaises(
            StructurePreviewQueryError
        ):
            fetch_computational_structure_preview(
                "MALWMRLL",
                "alphafold:NOT-THERE",
            )
