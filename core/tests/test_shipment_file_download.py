from datetime import timedelta
from pathlib import Path
import tempfile
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Shipment,
    ShipmentAccessToken,
    ShipmentDocument,
    ShipmentDocumentFormData,
)


def request_path(name, args=None):
    path = reverse(
        name,
        args=args,
    )

    prefix = (
        settings.FORCE_SCRIPT_NAME or ""
    ).rstrip("/")

    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix):]

    return path


class ShipmentFileDownloadSecurityTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)

        self.media_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
        )
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        user_model = get_user_model()

        self.requester = user_model.objects.create_user(
            username="shipment-file-requester",
            password="test-password",
        )

        self.outsider = user_model.objects.create_user(
            username="shipment-file-outsider",
            password="test-password",
        )

        self.shipment = Shipment.objects.create(
            requested_by=self.requester,
            flow_type="outgoing_shipment",
        )

        self.other_shipment = Shipment.objects.create(
            requested_by=self.outsider,
            flow_type="outgoing_shipment",
        )

        self.document = ShipmentDocument.objects.create(
            shipment=self.shipment,
            document_type="content_declaration",
            generated_file=SimpleUploadedFile(
                "generated.pdf",
                b"generated-shipment-document",
                content_type="application/pdf",
            ),
            signed_file=SimpleUploadedFile(
                "signed.pdf",
                b"signed-shipment-document",
                content_type="application/pdf",
            ),
        )

        self.other_document = ShipmentDocument.objects.create(
            shipment=self.other_shipment,
            document_type="content_declaration",
            signed_file=SimpleUploadedFile(
                "other-signed.pdf",
                b"other-shipment-document",
                content_type="application/pdf",
            ),
        )

        self.public_edit_token = ShipmentAccessToken.objects.create(
            shipment=self.shipment,
            access_type="public_edit",
            is_active=True,
            created_by=self.requester,
        )

    def internal_url(
        self,
        document=None,
        *,
        shipment=None,
        file_kind="signed",
    ):
        document = document or self.document
        shipment = shipment or self.shipment

        return request_path(
            "shipment_document_file_download",
            args=[
                shipment.id,
                document.id,
                file_kind,
            ],
        )

    def public_url(
        self,
        token=None,
        document=None,
        *,
        file_kind="signed",
    ):
        token = token or self.public_edit_token
        document = document or self.document

        return request_path(
            "public_shipment_document_file_download",
            args=[
                token.token,
                document.id,
                file_kind,
            ],
        )

    def assert_private_file_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Cache-Control"],
            "private, no-store",
        )
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertEqual(
            response["Referrer-Policy"],
            "no-referrer",
        )
        self.assertIn(
            "attachment;",
            response["Content-Disposition"],
        )

    def test_internal_visible_user_can_download_signed_file(self):
        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(),
        )

        self.assert_private_file_response(response)

        body = b"".join(response.streaming_content)

        self.assertEqual(
            body,
            b"signed-shipment-document",
        )

    def test_internal_visible_user_can_download_generated_file(self):
        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(
                file_kind="generated",
            ),
        )

        self.assert_private_file_response(response)

        body = b"".join(response.streaming_content)

        self.assertEqual(
            body,
            b"generated-shipment-document",
        )

    def test_internal_unrelated_user_cannot_download_file(self):
        self.client.force_login(self.outsider)

        response = self.client.get(
            self.internal_url(),
        )

        self.assertEqual(response.status_code, 404)

    def test_internal_document_cannot_cross_shipment_boundary(self):
        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(
                document=self.other_document,
                shipment=self.shipment,
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_internal_invalid_file_kind_is_rejected(self):
        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(
                file_kind="arbitrary-path",
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_internal_missing_physical_file_is_rejected(self):
        missing_document = ShipmentDocument.objects.create(
            shipment=self.shipment,
            document_type="other",
            signed_file=(
                "shipment_documents/"
                "missing-private-document.pdf"
            ),
        )

        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(
                document=missing_document,
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_internal_signed_file_can_be_served_from_form_data(self):
        document = ShipmentDocument.objects.create(
            shipment=self.shipment,
            document_type="mta_ttm",
        )

        ShipmentDocumentFormData.objects.create(
            shipment=self.shipment,
            document=document,
            document_type=document.document_type,
            signed_file=SimpleUploadedFile(
                "workspace-signed.pdf",
                b"workspace-signed-shipment-document",
                content_type="application/pdf",
            ),
        )

        self.client.force_login(self.requester)

        response = self.client.get(
            self.internal_url(
                document=document,
            ),
        )

        self.assert_private_file_response(response)

        body = b"".join(response.streaming_content)

        self.assertEqual(
            body,
            b"workspace-signed-shipment-document",
        )

    def test_public_edit_token_can_download_its_signed_file(self):
        response = self.client.get(
            self.public_url(),
        )

        self.assert_private_file_response(response)

        body = b"".join(response.streaming_content)

        self.assertEqual(
            body,
            b"signed-shipment-document",
        )

    def test_public_edit_token_can_download_its_generated_file(self):
        response = self.client.get(
            self.public_url(
                file_kind="generated",
            ),
        )

        self.assert_private_file_response(response)

        body = b"".join(response.streaming_content)

        self.assertEqual(
            body,
            b"generated-shipment-document",
        )

    def test_expired_public_edit_token_is_denied(self):
        expired_token = ShipmentAccessToken.objects.create(
            shipment=self.shipment,
            access_type="public_edit",
            is_active=True,
            expires_at=(
                timezone.now()
                - timedelta(minutes=1)
            ),
        )

        response = self.client.get(
            self.public_url(
                token=expired_token,
            ),
        )

        self.assertEqual(response.status_code, 403)

    def test_inactive_public_edit_token_is_not_accepted(self):
        inactive_token = ShipmentAccessToken.objects.create(
            shipment=self.shipment,
            access_type="public_edit",
            is_active=False,
        )

        response = self.client.get(
            self.public_url(
                token=inactive_token,
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_tracking_token_cannot_download_public_edit_file(self):
        tracking_token = ShipmentAccessToken.objects.create(
            shipment=self.shipment,
            access_type="public_tracking",
            is_active=True,
        )

        response = self.client.get(
            self.public_url(
                token=tracking_token,
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_public_token_cannot_cross_shipment_boundary(self):
        response = self.client.get(
            self.public_url(
                document=self.other_document,
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_public_invalid_file_kind_is_rejected(self):
        response = self.client.get(
            self.public_url(
                file_kind="filesystem-path",
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_unknown_public_token_is_rejected(self):
        url = request_path(
            "public_shipment_document_file_download",
            args=[
                uuid.uuid4(),
                self.document.id,
                "signed",
            ],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


class ShipmentPrivateMediaSourceRegressionTests(TestCase):
    def test_shipment_ui_does_not_emit_filefield_urls(self):
        paths = [
            Path(
                "core/interfaces/internal/shipments/"
                "documents_review.html"
            ),
            Path(
                "core/interfaces/public/shipments/"
                "documents.html"
            ),
            Path(
                "core/interfaces/public/shipments/"
                "upload_document.html"
            ),
            Path(
                "core/views/internal/shipments/"
                "views.py"
            ),
        ]

        combined = "\n".join(
            path.read_text()
            for path in paths
        )

        forbidden = [
            "document.generated_file.url",
            "document.signed_file.url",
            "document.form_data.signed_file.url",
            "document_signed_file(document).url",
        ]

        for expression in forbidden:
            with self.subTest(expression=expression):
                self.assertNotIn(
                    expression,
                    combined,
                )

    def test_protected_download_route_names_are_used(self):
        internal_template = Path(
            "core/interfaces/internal/shipments/"
            "documents_review.html"
        ).read_text()

        public_template = Path(
            "core/interfaces/public/shipments/"
            "documents.html"
        ).read_text()

        self.assertIn(
            "shipment_document_file_download",
            internal_template,
        )
        self.assertIn(
            "public_shipment_document_file_download",
            public_template,
        )
