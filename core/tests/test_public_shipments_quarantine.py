import uuid
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import (
    NoReverseMatch,
    URLPattern,
    URLResolver,
    get_resolver,
    reverse,
)


LEGACY_ROUTE_CASES = (
    (
        "public_shipments_portal",
        (),
    ),
    (
        "public_shipment_new",
        (),
    ),
    (
        "public_shipment_submitted",
        (uuid.UUID("11111111-1111-1111-1111-111111111111"),),
    ),
    (
        "public_shipment_track",
        (uuid.UUID("22222222-2222-2222-2222-222222222222"),),
    ),
    (
        "public_shipment_documents",
        (uuid.UUID("33333333-3333-3333-3333-333333333333"),),
    ),
    (
        "public_shipment_document_upload",
        (
            uuid.UUID("44444444-4444-4444-4444-444444444444"),
            1,
        ),
    ),
    (
        "public_shipment_document_file_download",
        (
            uuid.UUID("55555555-5555-5555-5555-555555555555"),
            1,
            "generated",
        ),
    ),
)


def iter_urls(patterns, prefix=""):
    for item in patterns:
        route = prefix + str(item.pattern)

        if isinstance(item, URLResolver):
            yield from iter_urls(
                item.url_patterns,
                route,
            )
        elif isinstance(item, URLPattern):
            yield route, item.name


class PublicShipmentsQuarantineTests(SimpleTestCase):
    def test_legacy_public_shipment_names_are_unregistered(self):
        for name, args in LEGACY_ROUTE_CASES:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(
                        name,
                        args=args,
                    )

    def test_url_graph_has_no_public_shipments_routes(self):
        matches = [
            (route, name)
            for route, name in iter_urls(
                get_resolver().url_patterns
            )
            if (
                "/" + route.lstrip("/")
            ).startswith(
                "/public/shipments/"
            )
        ]

        self.assertEqual(
            matches,
            [],
        )

    def test_legacy_public_shipment_paths_are_404_in_django(self):
        token = "66666666-6666-6666-6666-666666666666"

        cases = (
            (
                "get",
                "/public/shipments/",
            ),
            (
                "post",
                "/public/shipments/new/",
            ),
            (
                "get",
                f"/public/shipments/submitted/{token}/",
            ),
            (
                "get",
                f"/public/shipments/track/{token}/",
            ),
            (
                "get",
                f"/public/shipments/documents/{token}/",
            ),
            (
                "post",
                (
                    f"/public/shipments/documents/{token}/"
                    "upload/1/"
                ),
            ),
            (
                "get",
                (
                    f"/public/shipments/documents/{token}/"
                    "1/files/generated/download/"
                ),
            ),
        )

        for method, path in cases:
            with self.subTest(
                method=method,
                path=path,
            ):
                response = getattr(
                    self.client,
                    method,
                )(path)

                self.assertEqual(
                    response.status_code,
                    404,
                )

    def test_public_navigation_has_no_legacy_shipment_links(self):
        sources = (
            Path(
                "core/interfaces/public/base.html"
            ).read_text(),
            Path(
                "core/interfaces/public/index.html"
            ).read_text(),
        )

        combined = "\n".join(sources)

        for route_name, _args in LEGACY_ROUTE_CASES:
            with self.subTest(route_name=route_name):
                self.assertNotIn(
                    route_name,
                    combined,
                )

    def test_internal_package_labels_do_not_depend_on_public_tracking(self):
        view_source = Path(
            "core/views/internal/shipments/views.py"
        ).read_text()

        template_source = Path(
            "core/interfaces/internal/shipments/"
            "package_labels.html"
        ).read_text()

        self.assertNotIn(
            "public_shipment_track",
            view_source,
        )

        self.assertNotIn(
            "public_tracking_url",
            view_source,
        )

        self.assertNotIn(
            "public_tracking_url",
            template_source,
        )

        self.assertIn(
            "build_qr_data_uri(\n"
            "        shipment.shipment_code\n"
            "    )",
            view_source,
        )

        self.assertIn(
            "{{ shipment.shipment_code }}",
            template_source,
        )

    def test_legacy_source_is_retained_but_unrouted(self):
        self.assertTrue(
            Path(
                "core/views/public/shipments/views.py"
            ).is_file()
        )

        self.assertTrue(
            Path(
                "core/interfaces/public/shipments/"
                "portal.html"
            ).is_file()
        )
