import re

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Sample
from core.models.samples.sample import (
    SAMPLE_MICRO_QR_ALPHABET,
    SAMPLE_MICRO_QR_TOKEN_LENGTH,
    generate_sample_micro_qr_token,
)


TOKEN_PATTERN = re.compile(
    r"^[2-9A-HJ-NP-Z]{10}$"
)


class SampleMicroQrTokenTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="sample-micro-qr-owner",
            password="test-password",
        )

    def test_alphabet_contract(self):
        self.assertEqual(
            len(SAMPLE_MICRO_QR_ALPHABET),
            32,
        )

        self.assertEqual(
            len(set(SAMPLE_MICRO_QR_ALPHABET)),
            32,
        )

        for ambiguous in (
            "0",
            "1",
            "I",
            "O",
        ):
            self.assertNotIn(
                ambiguous,
                SAMPLE_MICRO_QR_ALPHABET,
            )

    def test_generator_contract(self):
        token = generate_sample_micro_qr_token()

        self.assertEqual(
            len(token),
            SAMPLE_MICRO_QR_TOKEN_LENGTH,
        )

        self.assertRegex(
            token,
            TOKEN_PATTERN,
        )

    def test_new_sample_receives_micro_qr_token(self):
        sample = Sample.objects.create(
            sample_id="MICRO-QR-TEST-0001",
            owner=self.owner,
        )

        self.assertEqual(
            len(sample.micro_qr_token),
            10,
        )

        self.assertRegex(
            sample.micro_qr_token,
            TOKEN_PATTERN,
        )

    def test_tokens_are_unique_across_new_samples(self):
        tokens = set()

        for index in range(25):
            sample = Sample.objects.create(
                sample_id=(
                    f"MICRO-QR-TEST-{index + 100:04d}"
                ),
                owner=self.owner,
            )

            tokens.add(
                sample.micro_qr_token
            )

        self.assertEqual(
            len(tokens),
            25,
        )

    def test_model_field_contract(self):
        field = Sample._meta.get_field(
            "micro_qr_token"
        )

        self.assertEqual(
            field.max_length,
            10,
        )

        self.assertTrue(
            field.unique,
        )

        self.assertFalse(
            field.editable,
        )

        self.assertFalse(
            field.null,
        )

        self.assertIs(
            field.default,
            generate_sample_micro_qr_token,
        )


class SampleMicroQrFunctionalTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import (
            AnonymousUser,
        )
        from django.test import RequestFactory

        self.AnonymousUser = AnonymousUser
        self.factory = RequestFactory()

        self.owner = User.objects.create_user(
            username="sample-micro-qr-functional-owner",
            password="test-password",
        )

        self.outsider = User.objects.create_user(
            username="sample-micro-qr-functional-outsider",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="MICRO-QR-FUNCTIONAL-0001",
            owner=self.owner,
            sample_type="Other",
        )

    def _request(
        self,
        path,
        user,
    ):
        request = self.factory.get(path)
        request.user = user
        return request

    def test_renderer_produces_fixed_m3_m_micro_qr(
        self,
    ):
        import base64

        from core.services.sample_micro_qr import (
            SAMPLE_MICRO_QR_BORDER,
            build_sample_micro_qr,
            sample_micro_qr_png_base64,
        )

        qr = build_sample_micro_qr(
            self.sample.micro_qr_token
        )

        self.assertTrue(
            qr.is_micro
        )
        self.assertEqual(
            qr.designator,
            "M3-M",
        )
        self.assertEqual(
            SAMPLE_MICRO_QR_BORDER,
            2,
        )
        self.assertEqual(
            qr.symbol_size(
                border=0
            ),
            (15, 15),
        )
        self.assertEqual(
            qr.symbol_size(
                border=2
            ),
            (19, 19),
        )

        png = base64.b64decode(
            sample_micro_qr_png_base64(
                self.sample.micro_qr_token
            )
        )

        self.assertTrue(
            png.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )

    def test_print_label_contains_micro_qr_and_token(
        self,
    ):
        from core.views.internal.samples.views import (
            print_sample_label,
        )

        request = self._request(
            (
                f"/samples/"
                f"{self.sample.pk}/print/"
            ),
            self.owner,
        )

        response = print_sample_label(
            request,
            self.sample.pk,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        body = response.content.decode()

        self.assertIn(
            "data:image/png;base64,",
            body,
        )
        self.assertIn(
            "Sample Micro QR",
            body,
        )
        self.assertIn(
            self.sample.micro_qr_token,
            body,
        )

    def test_owner_can_resolve_micro_qr_token(
        self,
    ):
        from core.views.internal.samples.views import (
            sample_micro_qr_resolve_view,
        )

        request = self._request(
            (
                "/samples/micro-qr/"
                f"{self.sample.micro_qr_token}/"
            ),
            self.owner,
        )

        response = sample_micro_qr_resolve_view(
            request,
            self.sample.micro_qr_token,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertIn(
            self.sample.sample_id,
            response.content.decode(),
        )

    def test_private_sample_micro_qr_requires_login(
        self,
    ):
        from core.views.internal.samples.views import (
            sample_micro_qr_resolve_view,
        )

        request = self._request(
            (
                "/samples/micro-qr/"
                f"{self.sample.micro_qr_token}/"
            ),
            self.AnonymousUser(),
        )

        response = sample_micro_qr_resolve_view(
            request,
            self.sample.micro_qr_token,
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertIn(
            "login",
            response["Location"],
        )
        self.assertIn(
            "next=",
            response["Location"],
        )

    def test_unauthorized_authenticated_user_is_denied(
        self,
    ):
        from django.core.exceptions import (
            PermissionDenied,
        )

        from core.views.internal.samples.views import (
            sample_micro_qr_resolve_view,
        )

        request = self._request(
            (
                "/samples/micro-qr/"
                f"{self.sample.micro_qr_token}/"
            ),
            self.outsider,
        )

        with self.assertRaises(
            PermissionDenied
        ):
            sample_micro_qr_resolve_view(
                request,
                self.sample.micro_qr_token,
            )

    def test_public_sample_micro_qr_allows_anonymous_access(
        self,
    ):
        from core.views.internal.samples.views import (
            sample_micro_qr_resolve_view,
        )

        self.sample.is_public = True
        self.sample.is_active = True
        self.sample.is_embargoed = False
        self.sample.save(
            update_fields=[
                "is_public",
                "is_active",
                "is_embargoed",
            ]
        )

        request = self._request(
            (
                "/samples/micro-qr/"
                f"{self.sample.micro_qr_token}/"
            ),
            self.AnonymousUser(),
        )

        response = sample_micro_qr_resolve_view(
            request,
            self.sample.micro_qr_token,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_invalid_micro_qr_token_returns_404(
        self,
    ):
        from django.http import Http404

        from core.views.internal.samples.views import (
            sample_micro_qr_resolve_view,
        )

        request = self._request(
            "/samples/micro-qr/INVALID01O/",
            self.owner,
        )

        with self.assertRaises(
            Http404
        ):
            sample_micro_qr_resolve_view(
                request,
                "INVALID01O",
            )

    def test_micro_qr_url_contract_and_legacy_url_remain(
        self,
    ):
        from django.urls import reverse

        micro_url = reverse(
            "sample_micro_qr_resolve",
            args=[
                self.sample.micro_qr_token,
            ],
        )

        legacy_url = reverse(
            "sample_qr_scan",
            args=[
                self.sample.uuid,
            ],
        )

        self.assertIn(
            (
                "/samples/micro-qr/"
                f"{self.sample.micro_qr_token}/"
            ),
            micro_url,
        )

        self.assertIn(
            "/samples/scan/",
            legacy_url,
        )


class SampleMicroQrLookupTests(TestCase):
    @staticmethod
    def _client_path(url):
        """
        Convert a reverse() URL containing FORCE_SCRIPT_NAME
        into PATH_INFO expected by Django's test client.
        """
        prefix = (
            settings.FORCE_SCRIPT_NAME
            or ""
        ).rstrip("/")

        if (
            prefix
            and url.startswith(
                prefix + "/"
            )
        ):
            return url[len(prefix):]

        return url

    def _lookup_path(self):
        return self._client_path(
            reverse(
                "sample_micro_qr_lookup"
            )
        )

    def setUp(self):
        self.owner = User.objects.create_user(
            username="sample-micro-qr-lookup-owner",
            password="test-password",
        )

        self.outsider = User.objects.create_user(
            username="sample-micro-qr-lookup-outsider",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="MICRO-QR-LOOKUP-0001",
            owner=self.owner,
        )

    def test_lookup_requires_authentication(self):
        response = self.client.get(
            self._lookup_path()
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_lookup_page_renders_for_authenticated_user(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self._lookup_path()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Sample Micro QR Lookup",
        )

        self.assertContains(
            response,
            'maxlength="10"',
        )

    def test_lookup_resolves_visible_sample(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self._lookup_path(),
            {
                "token":
                    self.sample.micro_qr_token.lower()
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            response.url,
            reverse(
                "sample_micro_qr_resolve",
                args=[
                    self.sample.micro_qr_token,
                ],
            ),
        )

    def test_lookup_rejects_invalid_token(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self._lookup_path(),
            {
                "token": "INVALID01O",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Enter a valid 10-character "
                "Sample Micro QR token."
            ),
        )

    def test_lookup_reports_unknown_token(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        candidates = (
            "23456789AB",
            "23456789AC",
            "23456789AD",
        )

        token = next(
            value
            for value in candidates
            if not Sample.objects.filter(
                micro_qr_token=value
            ).exists()
        )

        response = self.client.get(
            self._lookup_path(),
            {
                "token": token,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "No Sample was found for this "
                "Micro QR token."
            ),
        )

    def test_lookup_denies_hidden_sample(
        self,
    ):
        from django.core.exceptions import (
            PermissionDenied,
        )
        from django.test import RequestFactory

        from core.views.internal.samples.views import (
            sample_micro_qr_lookup_view,
        )

        request = RequestFactory().get(
            self._lookup_path(),
            {
                "token":
                    self.sample.micro_qr_token,
            },
        )

        request.user = self.outsider

        with self.assertRaises(
            PermissionDenied
        ):
            sample_micro_qr_lookup_view(
                request
            )
