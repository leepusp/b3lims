from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import (
    get_script_prefix,
    reverse,
    set_script_prefix,
)

from biobank import settings as production_settings


class C3LimsUrlStaticContractTests(SimpleTestCase):
    def test_canonical_url_prefix(self):
        # The production settings own the external mount.
        # test_settings.py intentionally clears FORCE_SCRIPT_NAME
        # so most unit tests can exercise unprefixed paths.
        self.assertEqual(
            production_settings.C3_LIMS_URL_PREFIX,
            "/c3-lims",
        )
        self.assertEqual(
            production_settings.FORCE_SCRIPT_NAME,
            "/c3-lims",
        )
        self.assertEqual(
            settings.C3_LIMS_URL_PREFIX,
            "/c3-lims",
        )
        self.assertEqual(
            settings.STATIC_URL,
            "/c3-lims/static/",
        )
        self.assertEqual(
            settings.MEDIA_URL,
            "/c3-lims/data/",
        )
        self.assertEqual(
            settings.LOGIN_URL,
            "/c3-lims/login/",
        )
        self.assertEqual(
            settings.LOGOUT_URL,
            "/c3-lims/logout/",
        )
        self.assertEqual(
            settings.LOGIN_REDIRECT_URL,
            "/c3-lims/workspace/",
        )

    def test_canonical_reversed_routes(self):
        previous_prefix = get_script_prefix()

        try:
            set_script_prefix("/c3-lims/")

            self.assertEqual(
                reverse("root_redirect"),
                "/c3-lims/",
            )
            self.assertEqual(
                reverse("workspace"),
                "/c3-lims/workspace/",
            )
            self.assertEqual(
                reverse("public_home"),
                "/c3-lims/public/",
            )
            self.assertEqual(
                reverse("public_about"),
                "/c3-lims/public/about/",
            )
            self.assertEqual(
                reverse("public_collections"),
                "/c3-lims/public/collections/",
            )
        finally:
            set_script_prefix(previous_prefix)

    def test_template_tree_contains_only_templates(self):
        interfaces = (
            Path(settings.BASE_DIR)
            / "core"
            / "interfaces"
        )

        invalid = sorted(
            str(path.relative_to(interfaces))
            for path in interfaces.rglob("*")
            if path.is_file()
            and path.suffix.lower()
            not in {".html", ".htm"}
        )

        self.assertEqual(
            invalid,
            [],
        )

    def test_application_static_tree_contains_no_templates(self):
        static_root = (
            Path(settings.BASE_DIR)
            / "core"
            / "static"
        )

        invalid = sorted(
            str(path.relative_to(static_root))
            for path in static_root.rglob("*")
            if path.is_file()
            and path.suffix.lower()
            in {".html", ".htm"}
        )

        self.assertEqual(
            invalid,
            [],
        )

    def test_template_tree_is_not_a_staticfiles_directory(self):
        interfaces = (
            Path(settings.BASE_DIR)
            / "core"
            / "interfaces"
        ).resolve()

        configured = {
            Path(path).resolve()
            for path in settings.STATICFILES_DIRS
        }

        self.assertNotIn(
            interfaces,
            configured,
        )

    def test_apache_mount_uses_c3_lims_prefix(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            "Alias /c3-lims/static/",
            apache,
        )
        self.assertIn(
            "ProxyPass        /c3-lims/",
            apache,
        )
        self.assertIn(
            'AuthName "C3 LIMS Authentication"',
            apache,
        )

        # The PAM service namespace is intentionally unchanged
        # during the public informational boundary phase.
        self.assertIn(
            "AuthPAMService galaxy",
            apache,
        )

    def test_public_informational_boundary_is_explicit(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            '<LocationMatch "^/c3-lims(?:$|/)">',
            apache,
        )
        self.assertIn(
            "RequestHeader unset X-Biobank-Pam-User",
            apache,
        )
        self.assertIn(
            "public/(?:$|about/$|governance/$|"
            "collections/$|collections/[0-9]+/$)",
            apache,
        )

        # Shipment routes must not be part of the anonymous
        # informational whitelist.
        self.assertNotIn(
            "public/shipments",
            apache.split(
                "<LocationMatch",
            )[2].split(
                ">",
                1,
            )[0],
        )

    def test_public_boundary_sanitizes_before_authentication(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        sanitize = apache.index(
            '<LocationMatch "^/c3-lims(?:$|/)">'
        )
        unset_identity = apache.index(
            "RequestHeader unset X-Biobank-Pam-User",
            sanitize,
        )
        authenticated = apache.index(
            "AuthType Basic",
            unset_identity,
        )
        set_identity = apache.index(
            'RequestHeader set X-Biobank-Pam-User '
            '"expr=%{REMOTE_USER}"',
            authenticated,
        )

        self.assertLess(
            sanitize,
            unset_identity,
        )
        self.assertLess(
            unset_identity,
            authenticated,
        )
        self.assertLess(
            authenticated,
            set_identity,
        )

    def test_public_shipments_remain_pam_protected(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        authentication_match = next(
            line
            for line in apache.splitlines()
            if line.startswith(
                '<LocationMatch "^/c3-lims($|/'
            )
        )

        self.assertIn(
            "public/(?:$|about/$|governance/$|"
            "collections/$|collections/[0-9]+/$)",
            authentication_match,
        )
        self.assertNotIn(
            "shipments",
            authentication_match,
        )
        self.assertIn(
            "AuthPAMService galaxy",
            apache,
        )

    def test_only_controlled_old_navigation_redirects_remain(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            'RedirectMatch 308 "^/biobank/?$"',
            apache,
        )
        self.assertIn(
            'RedirectMatch 308 "^/biobank/public(/.*)?$"',
            apache,
        )

    def test_jupyter_public_prefix_is_c3_lims(self):
        base = Path(settings.BASE_DIR)

        jupyter_conf = (
            base
            / "deploy"
            / "apache"
            / "biobank-jupyter.conf"
        ).read_text()

        lua = (
            base
            / "deploy"
            / "apache"
            / "biobank_jupyter_proxy.lua"
        ).read_text()

        runtime = (
            base
            / "deploy"
            / "runtime"
            / "notebook_server.sh"
        ).read_text()

        self.assertIn(
            "^/c3-lims/internal/lab-tools/jupyter/",
            jupyter_conf,
        )
        self.assertIn(
            "^/c3%-lims/internal/lab%-tools/jupyter/",
            lua,
        )
        self.assertIn(
            'BASE_URL="/c3-lims/internal/lab-tools/jupyter/',
            runtime,
        )
