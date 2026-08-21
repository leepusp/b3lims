from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from core.services.shipment_cibio_templates import (
    cibio_template_catalog,
    get_cibio_template,
)
from core.views.internal.shipments.views import (
    shipment_cibio_template_download_view,
)


class ShipmentCibioTemplateTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_authenticated=True,
            username="ccalomeno",
        )
        self.shipment = SimpleNamespace(id=68)
        self.document = SimpleNamespace(
            id=150,
            shipment=self.shipment,
            document_type="cibio_authorization",
        )

    def test_catalog_contains_only_reviewed_bbams_template(self):
        templates = cibio_template_catalog()

        self.assertEqual(len(templates), 1)
        self.assertEqual(
            templates[0].key,
            "bbams-gmo-transport-notification",
        )

        template, template_path = get_cibio_template(
            "bbams-gmo-transport-notification"
        )

        self.assertEqual(template.institution, "BBAMS")
        self.assertTrue(template_path.is_file())
        self.assertEqual(template_path.suffix.lower(), ".docx")
        self.assertIn(
            "docs/transport/source_templates/ogm_cibio",
            template_path.as_posix(),
        )

    def test_unknown_template_is_rejected(self):
        with self.assertRaises(KeyError):
            get_cibio_template("unknown-institution")

    def test_download_route_resolves_to_protected_view(self):
        url = reverse(
            "shipment_cibio_template_download",
            args=[
                self.shipment.id,
                self.document.id,
                "bbams-gmo-transport-notification",
            ],
        )

        script_name = settings.FORCE_SCRIPT_NAME or ""

        if script_name and url.startswith(script_name):
            resolver_path = url[len(script_name):] or "/"
        else:
            resolver_path = url

        self.assertIs(
            resolve(resolver_path).func,
            shipment_cibio_template_download_view,
        )

    def test_anonymous_download_redirects_to_login(self):
        request = self.factory.get("/protected-download/")
        request.user = AnonymousUser()

        response = shipment_cibio_template_download_view(
            request,
            self.shipment.id,
            self.document.id,
            "bbams-gmo-transport-notification",
        )

        self.assertEqual(response.status_code, 302)

    def test_download_is_private_and_attachment_only(self):
        request = self.factory.get("/protected-download/")
        request.user = self.user

        with (
            patch(
                "core.views.internal.shipments.views."
                "visible_shipments_for_user",
                return_value=object(),
            ),
            patch(
                "core.views.internal.shipments.views.get_object_or_404",
                side_effect=[
                    self.shipment,
                    self.document,
                ],
            ),
        ):
            response = shipment_cibio_template_download_view(
                request,
                self.shipment.id,
                self.document.id,
                "bbams-gmo-transport-notification",
            )

        try:
            content = b"".join(response.streaming_content)
        finally:
            response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Cache-Control"],
            "private, no-store",
        )
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertIn(
            "attachment",
            response["Content-Disposition"],
        )
        self.assertIn(
            "BBAMS_GMO_Transport_Notification.docx",
            response["Content-Disposition"],
        )
        self.assertTrue(content.startswith(b"PK"))

    def test_non_cibio_document_cannot_download_template(self):
        request = self.factory.get("/protected-download/")
        request.user = self.user

        non_cibio_document = SimpleNamespace(
            id=151,
            shipment=self.shipment,
            document_type="content_declaration",
        )

        with (
            patch(
                "core.views.internal.shipments.views."
                "visible_shipments_for_user",
                return_value=object(),
            ),
            patch(
                "core.views.internal.shipments.views.get_object_or_404",
                side_effect=[
                    self.shipment,
                    non_cibio_document,
                ],
            ),
        ):
            with self.assertRaises(Http404):
                shipment_cibio_template_download_view(
                    request,
                    self.shipment.id,
                    non_cibio_document.id,
                    "bbams-gmo-transport-notification",
                )

    def test_wizard_contains_cibio_only_template_component(self):
        template = get_template(
            "internal/shipments/document_workspace_wizard.html"
        )
        self.assertIsNotNone(template)

        source_path = (
            Path(__file__).resolve().parents[1]
            / "interfaces"
            / "internal"
            / "shipments"
            / "document_workspace_wizard.html"
        )
        source = source_path.read_text(encoding="utf-8")

        self.assertIn(
            '{% if document.document_type == "cibio_authorization" %}',
            source,
        )
        self.assertIn(
            "shipment_cibio_template_download",
            source,
        )
        self.assertIn(
            "BBAMS — GMO Transport Notification",
            source,
        )
        self.assertNotIn(
            "CIBIO.pdf",
            source,
        )
