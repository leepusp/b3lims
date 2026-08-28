from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class InternalShellBrandingTests(SimpleTestCase):
    def source(self, relative):
        return (
            Path(settings.BASE_DIR)
            / relative
        ).read_text(
            encoding="utf-8"
        )

    def test_internal_sources_use_b3_lims_brand(self):
        internal_root = (
            Path(settings.BASE_DIR)
            / "core/interfaces/internal"
        )

        source = "\n".join(
            path.read_text(
                encoding="utf-8"
            )
            for path in sorted(
                internal_root.rglob("*")
            )
            if path.is_file()
            and path.suffix in {
                ".html",
                ".css",
                ".js",
            }
        )

        self.assertNotIn(
            "Biobank LIMS",
            source,
        )
        self.assertNotIn(
            "Biobank Portal",
            source,
        )
        self.assertIn(
            "B3 LIMS",
            source,
        )

    def test_internal_shell_uses_english_b3_branding(self):
        source = self.source(
            "core/interfaces/internal/common/base.html"
        )

        self.assertIn(
            '<html lang="en">',
            source,
        )
        self.assertIn(
            '<div class="logo">B3</div>',
            source,
        )
        self.assertIn(
            '<div class="logo-sub">LIMS</div>',
            source,
        )
        self.assertIn(
            "{% url 'user_profile' %}",
            source,
        )
        self.assertIn(
            "Profile",
            source,
        )

    def test_pam_user_menu_does_not_offer_django_logout(self):
        source = self.source(
            "core/interfaces/internal/common/base.html"
        )

        self.assertNotIn(
            "{% url 'logout' %}",
            source,
        )
        self.assertNotIn(
            "Logout",
            source,
        )
        self.assertNotIn(
            "bi-box-arrow-right",
            source,
        )

    def test_public_institutional_brand_is_preserved(self):
        source = self.source(
            "core/interfaces/public/base.html"
        )

        self.assertIn(
            "Biobank CEPID B3",
            source,
        )

    def test_technical_logout_route_is_retained(self):
        settings_source = self.source(
            "biobank/settings.py"
        )
        urls_source = self.source(
            "biobank/urls.py"
        )

        self.assertIn(
            'LOGOUT_URL = f"{B3_LIMS_URL_PREFIX}/logout/"',
            settings_source,
        )
        self.assertIn(
            'path("logout/", logout_user, name="logout")',
            urls_source,
        )
