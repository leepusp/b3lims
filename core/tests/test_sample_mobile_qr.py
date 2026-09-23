import base64
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.services.sample_micro_qr import (
    SAMPLE_MOBILE_QR_BORDER,
    build_sample_mobile_qr,
    sample_mobile_qr_png_base64,
)


COMPACT_SAMPLE_URL = (
    "HTTPS://DAVINCI.ICB.USP.BR/"
    "METZUTFDUQ"
)


class SampleMobileQrRendererTests(
    SimpleTestCase
):
    def test_compact_url_produces_version_2_m_qr(self):
        qr = build_sample_mobile_qr(
            COMPACT_SAMPLE_URL
        )

        self.assertFalse(qr.is_micro)

        self.assertEqual(
            qr.version,
            2,
        )

        self.assertEqual(
            qr.designator,
            "2-M",
        )

        self.assertEqual(
            qr.symbol_size(border=0),
            (25, 25),
        )

        self.assertEqual(
            qr.symbol_size(
                border=SAMPLE_MOBILE_QR_BORDER
            ),
            (33, 33),
        )

    def test_mobile_renderer_produces_png(self):
        png = base64.b64decode(
            sample_mobile_qr_png_base64(
                COMPACT_SAMPLE_URL
            )
        )

        self.assertTrue(
            png.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )


class SampleMobileQrApacheContractTests(
    SimpleTestCase
):
    def test_compact_sample_url_redirect_is_versioned(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            (
                'RedirectMatch 302 '
                '"^/([2-9A-HJ-NP-Z]{10})/?$" '
                '"/b3lims/samples/micro-qr/$1/"'
            ),
            apache,
        )
