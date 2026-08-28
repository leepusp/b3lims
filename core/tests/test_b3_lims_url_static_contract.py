from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import (
    get_script_prefix,
    reverse,
    set_script_prefix,
)

from biobank import settings as production_settings


class B3LimsUrlStaticContractTests(SimpleTestCase):
    def test_canonical_url_prefix(self):
        # The production settings own the external mount.
        # test_settings.py intentionally clears FORCE_SCRIPT_NAME
        # so most unit tests can exercise unprefixed paths.
        self.assertEqual(
            production_settings.B3_LIMS_URL_PREFIX,
            "/b3lims",
        )
        self.assertEqual(
            production_settings.FORCE_SCRIPT_NAME,
            "/b3lims",
        )
        self.assertEqual(
            settings.B3_LIMS_URL_PREFIX,
            "/b3lims",
        )
        self.assertEqual(
            settings.STATIC_URL,
            "/b3lims/static/",
        )
        self.assertEqual(
            settings.MEDIA_URL,
            "/b3lims/data/",
        )
        self.assertEqual(
            settings.LOGIN_URL,
            "/b3lims/login/",
        )
        self.assertEqual(
            settings.LOGOUT_URL,
            "/b3lims/logout/",
        )
        self.assertEqual(
            settings.LOGIN_REDIRECT_URL,
            "/b3lims/workspace/",
        )

    def test_canonical_reversed_routes(self):
        previous_prefix = get_script_prefix()

        try:
            set_script_prefix("/b3lims/")

            self.assertEqual(
                reverse("root_redirect"),
                "/b3lims/",
            )
            self.assertEqual(
                reverse("workspace"),
                "/b3lims/workspace/",
            )
            self.assertEqual(
                reverse("public_home"),
                "/b3lims/public/",
            )
            self.assertEqual(
                reverse("public_about"),
                "/b3lims/public/about/",
            )
            self.assertEqual(
                reverse("public_collections"),
                "/b3lims/public/collections/",
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

    def test_apache_mount_uses_b3_lims_prefix(self):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            "Alias /b3lims/static/",
            apache,
        )
        self.assertIn(
            "ProxyPass        /b3lims/",
            apache,
        )
        self.assertIn(
            'AuthName "B3 LIMS Authentication"',
            apache,
        )

        # B3 LIMS uses its own PAM service namespace while
        # preserving the validated PAM policy stack.
        self.assertIn(
            "AuthPAMService biobank",
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
            '<LocationMatch "^/b3lims(?:$|/)">',
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
            '<LocationMatch "^/b3lims(?:$|/)">'
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
                '<LocationMatch "^/b3lims($|/'
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
            "AuthPAMService biobank",
            apache,
        )

    def test_b3_lims_uses_dedicated_pam_service(self):
        base = Path(settings.BASE_DIR)

        apache = (
            base
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        pam_service = (
            base
            / "deploy"
            / "pam"
            / "biobank"
        )

        self.assertIn(
            "AuthPAMService biobank",
            apache,
        )
        self.assertNotIn(
            "AuthPAMService galaxy",
            apache,
        )

        self.assertTrue(
            pam_service.is_file(),
        )

        pam = pam_service.read_text()

        for directive in (
            "auth       substack     system-auth",
            "auth       include      postlogin",
            "account    required     pam_nologin.so",
            "account    include      system-auth",
            "password   include      system-auth",
            "session    include      system-auth",
            "session    include      postlogin",
        ):
            self.assertIn(
                directive,
                pam,
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

    def test_jupyter_public_prefix_is_b3_lims(self):
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
            "^/b3lims/internal/lab-tools/jupyter/",
            jupyter_conf,
        )
        self.assertIn(
            "^/b3lims/internal/lab%-tools/jupyter/",
            lua,
        )
        self.assertIn(
            'BASE_URL="/b3lims/internal/lab-tools/jupyter/',
            runtime,
        )


    def test_legacy_c3_lims_namespace_redirects_to_b3_lims(
        self,
    ):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            'RedirectMatch 308 "^/c3-lims$" "/b3lims/"',
            apache,
        )

        self.assertIn(
            'RedirectMatch 308 "^/c3-lims/(.*)$" "/b3lims/$1"',
            apache,
        )

        self.assertNotIn(
            "Alias /c3-lims/",
            apache,
        )

        self.assertNotIn(
            "ProxyPass        /c3-lims/",
            apache,
        )

        self.assertNotIn(
            '<LocationMatch "^/c3-lims',
            apache,
        )

        self.assertIn(
            "Alias /b3lims/static/",
            apache,
        )

        self.assertIn(
            "ProxyPass        /b3lims/",
            apache,
        )

        self.assertIn(
            '<LocationMatch "^/b3lims',
            apache,
        )


    def test_legacy_hyphenated_b3_namespace_redirects_to_b3lims(
        self,
    ):
        apache = (
            Path(settings.BASE_DIR)
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        self.assertIn(
            'RedirectMatch 308 "^/b3-lims$" "/b3lims/"',
            apache,
        )

        self.assertIn(
            'RedirectMatch 308 "^/b3-lims/(.*)$" "/b3lims/$1"',
            apache,
        )

        self.assertNotIn(
            "Alias /b3-lims/",
            apache,
        )

        self.assertNotIn(
            "ProxyPass        /b3-lims/",
            apache,
        )

        self.assertNotIn(
            "ProxyPassReverse /b3-lims/",
            apache,
        )

        self.assertNotIn(
            '<LocationMatch "^/b3-lims',
            apache,
        )

        self.assertIn(
            "Alias /b3lims/static/",
            apache,
        )

        self.assertIn(
            "ProxyPass        /b3lims/",
            apache,
        )

        self.assertIn(
            '<LocationMatch "^/b3lims',
            apache,
        )
