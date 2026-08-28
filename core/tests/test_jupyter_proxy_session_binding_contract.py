import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(settings.BASE_DIR)

BROKER = (
    ROOT
    / "deploy"
    / "sbin"
    / "biobank-jupyter-server-broker"
)

RECONCILER = (
    ROOT
    / "deploy"
    / "sbin"
    / "biobank-jupyter-proxy-reconciler"
)

SERVICE = (
    ROOT
    / "deploy"
    / "systemd"
    / "biobank-jupyter-proxy-reconciler.service"
)

TIMER = (
    ROOT
    / "deploy"
    / "systemd"
    / "biobank-jupyter-proxy-reconciler.timer"
)

APACHE_ROOT = (
    ROOT
    / "deploy"
    / "apache"
)

MAIN_CONF = (
    APACHE_ROOT
    / "biobank.conf"
)

PROXY_CONF = (
    APACHE_ROOT
    / "biobank-jupyter.conf"
)

PROXY_LUA = (
    APACHE_ROOT
    / "biobank_jupyter_proxy.lua"
)

JUPYTER_SERVICE = (
    ROOT
    / "core"
    / "services"
    / "jupyter_server.py"
)

JUPYTER_VIEW = (
    ROOT
    / "core"
    / "views"
    / "internal"
    / "lab_tools"
    / "jupyter.py"
)


class JupyterIndependentProxyContractTests(
    SimpleTestCase
):
    def test_authoritative_broker_uses_root_binding(
        self,
    ):
        source = BROKER.read_text()

        self.assertIn(
            'PROXY_BINDING_ROOT='
            '"/run/biobank-jupyter-proxy"',
            source,
        )
        self.assertIn(
            'PROXY_BINDING_GROUP='
            '"biobank-proxy"',
            source,
        )
        self.assertIn(
            "sync_proxy_binding",
            source,
        )
        self.assertIn(
            "remove_proxy_binding",
            source,
        )

    def test_binding_removal_uses_shell_owner_parser(
        self,
    ):
        source = BROKER.read_text()

        start = source.index(
            "remove_proxy_binding() {"
        )
        end = source.index(
            "\n}\n\nwrite_proxy_lease()",
            start,
        )

        block = source[
            start:end
        ]

        self.assertNotIn(
            "/usr/bin/awk",
            block,
        )
        self.assertIn(
            "while IFS= read -r line",
            block,
        )
        self.assertIn(
            'owner_marker="${line#owner=}"',
            block,
        )
        self.assertIn(
            "owner_seen=1",
            block,
        )
        self.assertIn(
            "Jupyter proxy binding owner is duplicated.",
            block,
        )
        self.assertIn(
            'test "$owner_marker" = "$APP_USER"',
            block,
        )

    def test_broker_shell_source_is_parseable(
        self,
    ):
        import subprocess

        result = subprocess.run(
            [
                "/usr/bin/bash",
                "-n",
                str(BROKER),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr,
        )

    def test_broker_validates_slurm_identity_and_node(
        self,
    ):
        source = BROKER.read_text()

        self.assertIn(
            "active_job_owner",
            source,
        )
        self.assertIn(
            "active_job_state",
            source,
        )
        self.assertIn(
            "active_job_node",
            source,
        )
        self.assertIn(
            "Only a running Slurm job may "
            "receive a proxy binding.",
            source,
        )
        self.assertIn(
            "Slurm job owner does not match "
            "proxy binding.",
            source,
        )
        self.assertIn(
            "Allocated Slurm node does not match "
            "Jupyter host.",
            source,
        )

    def test_proxy_is_biobank_owned_not_ood_owned(
        self,
    ):
        def active_source(path):
            active_lines = []

            for line in path.read_text().splitlines():
                stripped = line.strip()

                if (
                    not stripped
                    or stripped.startswith("#")
                    or stripped.startswith("--")
                ):
                    continue

                active_lines.append(line)

            return "\n".join(active_lines)

        combined = "\n".join(
            (
                active_source(MAIN_CONF),
                active_source(PROXY_CONF),
                active_source(PROXY_LUA),
            )
        )

        for forbidden in (
            "node_proxy.lua",
            "OOD_USER_ENV",
            "BIOBANK_JUPYTER_PROXY_USER",
            "mod_ood_proxy",
            "/etc/ood/",
            "require 'ood.",
            'require "ood.',
        ):
            self.assertNotIn(
                forbidden,
                combined,
            )

        self.assertFalse(
            (
                ROOT
                / "deploy"
                / "ood"
                / "biobank-node-proxy.conf"
            ).exists()
        )
        self.assertFalse(
            (
                ROOT
                / "deploy"
                / "ood"
                / "biobank_jupyter_session_authz.lua"
            ).exists()
        )
        self.assertFalse(
            (
                ROOT
                / "deploy"
                / "ood"
                / "biobank-ood-log-hygiene.yml"
            ).exists()
        )

    def test_data_plane_has_no_basic_pam_auth(
        self,
    ):
        source = PROXY_CONF.read_text()

        for forbidden in (
            "AuthType Basic",
            "AuthBasicProvider",
            "AuthPAMService",
            "Require valid-user",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

        self.assertIn(
            "Require biobank-jupyter-session",
            source,
        )
        self.assertIn(
            "AuthzSendForbiddenOnFailure On",
            source,
        )

    def test_main_pam_boundary_excludes_only_valid_node_route(
        self,
    ):
        source = MAIN_CONF.read_text()

        self.assertIn(
            "internal/lab-tools/jupyter/"
            "[0-9]+/node/",
            source,
        )

        pam_pattern = re.compile(
            r"^/b3lims"
            r"($|/(?!"
            r"static/"
            r"|internal/lab-tools/jupyter/"
            r"[0-9]+/node/"
            r"(?:gn01|gn02|gn03|n01)/"
            r"[0-9]+/"
            r").*)"
        )

        protected = (
            "/b3lims",
            "/b3lims/",
            "/b3lims/internal/lab-tools/jupyter/19/",
            "/b3lims/internal/lab-tools/jupyter/19/connect",
            "/b3lims/internal/lab-tools/jupyter/19/node/bad/51993/",
            "/b3lims/internal/lab-tools/jupyter/19/node/gn02/notaport/",
            "/b3lims/internal/lab-tools/jupyter/19/node/gn02/51993",
        )

        excluded = (
            "/b3lims/internal/lab-tools/jupyter/19/node/gn02/51993/",
            "/b3lims/internal/lab-tools/jupyter/19/node/gn02/51993/api",
        )

        for path in protected:
            self.assertIsNotNone(
                pam_pattern.match(path),
                path,
            )

        for path in excluded:
            self.assertIsNone(
                pam_pattern.match(path),
                path,
            )

    def test_lua_requires_exact_binding_and_fresh_lease(
        self,
    ):
        source = PROXY_LUA.read_text()

        self.assertIn(
            'BINDING_ROOT = '
            '"/run/biobank-jupyter-proxy"',
            source,
        )
        self.assertIn(
            "MAX_LEASE_AGE = 120",
            source,
        )
        self.assertIn(
            "MAX_FUTURE_SKEW = 10",
            source,
        )

        for field in (
            "notebook_id",
            "owner",
            "run_id",
            "job_id",
            "host",
            "port",
            "validated_at",
        ):
            self.assertIn(
                field,
                source,
            )

        self.assertIn(
            "binding_is_authorized",
            source,
        )
        self.assertIn(
            "apache2.AUTHZ_GRANTED",
            source,
        )
        self.assertIn(
            "apache2.AUTHZ_DENIED",
            source,
        )

    def test_lua_requires_path_scoped_proxy_cookie(
        self,
    ):
        source = PROXY_LUA.read_text()

        self.assertIn(
            "__Secure-biobank-jupyter-token",
            source,
        )
        self.assertIn(
            "extract_proxy_cookie",
            source,
        )
        self.assertIn(
            "valid_proxy_token",
            source,
        )

    def test_proxy_injects_native_authorization_server_side(
        self,
    ):
        source = PROXY_LUA.read_text()

        self.assertIn(
            'r.headers_in["Authorization"]',
            source,
        )
        self.assertIn(
            '"token " .. token',
            source,
        )
        self.assertIn(
            'r.headers_in["Cookie"]',
            source,
        )

    def test_proxy_supports_http_and_websocket(
        self,
    ):
        source = PROXY_LUA.read_text()

        self.assertIn(
            '"websocket"',
            source,
        )
        self.assertIn(
            '"ws://"',
            source,
        )
        self.assertIn(
            '"http://"',
            source,
        )
        self.assertIn(
            'r.handler = (',
            source,
        )
        self.assertIn(
            'r.filename = uri',
            source,
        )

    def test_lua_does_not_execute_external_commands(
        self,
    ):
        source = PROXY_LUA.read_text()

        for forbidden in (
            "os.execute",
            "io.popen",
            "package.loadlib",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_jupyter_bootstrap_token_is_not_put_in_url(
        self,
    ):
        service = JUPYTER_SERVICE.read_text()
        view = JUPYTER_VIEW.read_text()

        self.assertNotIn(
            "?token=",
            service,
        )
        self.assertNotIn(
            "?token=",
            view,
        )
        self.assertIn(
            "__Secure-biobank-jupyter-token",
            service,
        )
        self.assertIn(
            "response.set_cookie(",
            view,
        )

    def test_bootstrap_cookie_security_flags_are_explicit(
        self,
    ):
        source = JUPYTER_VIEW.read_text()

        self.assertIn(
            "secure=True",
            source,
        )
        self.assertIn(
            "httponly=True",
            source,
        )
        self.assertIn(
            'samesite="Strict"',
            source,
        )
        self.assertIn(
            "path=target.cookie_path",
            source,
        )

    def test_location_scoped_lua_info_logging_is_suppressed(
        self,
    ):
        source = PROXY_CONF.read_text()

        self.assertIn(
            "LogLevel lua_module:warn",
            source,
        )

    def test_proxy_uses_absolute_biobank_lua_path(
        self,
    ):
        source = PROXY_CONF.read_text()

        self.assertIn(
            "/etc/httpd/biobank/"
            "biobank_jupyter_proxy.lua",
            source,
        )

    def test_node_allowlist_is_consistent(
        self,
    ):
        source = PROXY_LUA.read_text()

        for host in (
            "n01",
            "gn01",
            "gn02",
            "gn03",
        ):
            self.assertIn(
                host,
                source,
            )


class JupyterProxyLeaseContractTests(
    SimpleTestCase
):
    def test_reconciler_renews_matching_lease(
        self,
    ):
        source = RECONCILER.read_text()

        self.assertIn(
            "write_lease",
            source,
        )
        self.assertIn(
            "validated_at",
            source,
        )
        self.assertIn(
            "binding_unchanged",
            source,
        )

    def test_reconciler_checks_owner_state_and_node(
        self,
    ):
        source = RECONCILER.read_text()

        for value in (
            "owner",
            "RUNNING",
            "host",
            "job_id",
        ):
            self.assertIn(
                value,
                source,
            )

    def test_reconciler_is_root_controlled(
        self,
    ):
        source = SERVICE.read_text()

        self.assertIn(
            "User=root",
            source,
        )
        self.assertIn(
            "Group=root",
            source,
        )
        self.assertIn(
            "ProtectSystem=strict",
            source,
        )
        self.assertIn(
            "ReadWritePaths="
            "-/run/biobank-jupyter-proxy",
            source,
        )

    def test_timer_is_inside_lease_ttl(
        self,
    ):
        source = TIMER.read_text()

        self.assertIn(
            "OnUnitActiveSec=30s",
            source,
        )

        lua = PROXY_LUA.read_text()

        self.assertIn(
            "MAX_LEASE_AGE = 120",
            lua,
        )
