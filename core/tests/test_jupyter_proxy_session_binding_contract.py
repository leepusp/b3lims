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

AUTHZ = (
    ROOT
    / "deploy"
    / "ood"
    / "biobank_jupyter_session_authz.lua"
)

PROXY_CONF = (
    ROOT
    / "deploy"
    / "ood"
    / "biobank-node-proxy.conf"
)


class JupyterProxySessionBindingContractTests(
    SimpleTestCase
):
    def test_authoritative_broker_uses_root_runtime_binding(
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
            "sync_proxy_binding()",
            source,
        )
        self.assertIn(
            "remove_proxy_binding()",
            source,
        )
        self.assertIn(
            'test "$owner" = "$APP_USER"',
            source,
        )
        self.assertIn(
            'test "$state" = "RUNNING"',
            source,
        )
        self.assertIn(
            'test "$node" = "$host"',
            source,
        )
        self.assertIn(
            'root:"$PROXY_BINDING_GROUP"',
            source,
        )

    def test_broker_validates_exact_connection_base_url(
        self,
    ):
        source = BROKER.read_text()

        self.assertIn(
            "expected_base = (",
            source,
        )
        self.assertIn(
            "if base_url != expected_base:",
            source,
        )
        self.assertIn(
            '"Jupyter base URL does not match "',
            source,
        )

    def test_broker_binding_lifecycle_is_closed(
        self,
    ):
        source = BROKER.read_text()

        self.assertGreaterEqual(
            source.count(
                'remove_proxy_binding "$notebook_id"'
            ),
            4,
        )

        self.assertIn(
            "sync_proxy_binding \\",
            source,
        )

    def test_lua_provider_requires_exact_bound_tuple(
        self,
    ):
        source = AUTHZ.read_text()

        self.assertIn(
            "binding.notebook_id ~= notebook_id",
            source,
        )
        self.assertIn(
            "binding.host ~= host",
            source,
        )
        self.assertIn(
            "binding.port ~= port",
            source,
        )
        self.assertIn(
            "binding.owner",
            source,
        )
        self.assertIn(
            "apache2.AUTHZ_GRANTED",
            source,
        )

    def test_lua_provider_does_not_depend_on_basic_user(
        self,
    ):
        source = AUTHZ.read_text()

        self.assertNotIn(
            "AUTHZ_DENIED_NO_USER",
            source,
        )
        self.assertNotIn(
            "binding.owner ~= r.user",
            source,
        )

    def test_lua_provider_does_not_execute_commands(
        self,
    ):
        source = AUTHZ.read_text()

        self.assertNotIn(
            "os.execute",
            source,
        )
        self.assertNotIn(
            "io.popen",
            source,
        )

    def test_proxy_uses_binding_not_http_basic_auth(
        self,
    ):
        source = PROXY_CONF.read_text()

        self.assertIn(
            "LuaAuthzProvider",
            source,
        )
        self.assertIn(
            "Require biobank-jupyter-session",
            source,
        )

        for forbidden in (
            "AuthType Basic",
            "AuthBasicProvider PAM",
            "AuthPAMService",
            "Require valid-user",
            "Require all granted",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_proxy_preserves_jupyter_authorization_header(
        self,
    ):
        source = PROXY_CONF.read_text()

        self.assertNotIn(
            "RequestHeader unset Authorization",
            source,
        )
        self.assertNotIn(
            "RequestHeader set Authorization",
            source,
        )

    def test_proxy_node_allowlist_remains_scoped(
        self,
    ):
        source = PROXY_CONF.read_text()

        self.assertIn(
            "(?<host>gn01|gn02|gn03|n01)",
            source,
        )
        self.assertNotIn(
            "|localhost",
            source,
        )
        self.assertNotIn(
            "127\\.0\\.0\\.1",
            source,
        )


class JupyterProxyLeaseContractTests(
    SimpleTestCase
):
    def test_broker_creates_matching_runtime_lease(
        self,
    ):
        source = BROKER.read_text()

        self.assertIn(
            "proxy_lease_path()",
            source,
        )
        self.assertIn(
            "write_proxy_lease()",
            source,
        )
        self.assertIn(
            '"validated_at=${validated_at}"',
            source,
        )
        self.assertIn(
            "write_proxy_lease \\",
            source,
        )

    def test_lua_requires_fresh_matching_lease(
        self,
    ):
        source = AUTHZ.read_text()

        self.assertIn(
            "local MAX_LEASE_AGE = 120",
            source,
        )
        self.assertIn(
            "validated_at",
            source,
        )
        self.assertIn(
            "local now = os.time()",
            source,
        )
        self.assertIn(
            "lease[key] ~= binding[key]",
            source,
        )
        self.assertIn(
            "> MAX_LEASE_AGE",
            source,
        )

    def test_lua_still_does_not_execute_commands(
        self,
    ):
        source = AUTHZ.read_text()

        self.assertNotIn(
            "os.execute",
            source,
        )
        self.assertNotIn(
            "io.popen",
            source,
        )

    def test_reconciler_uses_single_read_only_squeue_snapshot(
        self,
    ):
        source = (
            ROOT
            / "deploy"
            / "sbin"
            / "biobank-jupyter-proxy-reconciler"
        ).read_text()

        self.assertEqual(
            source.count(
                '"/usr/bin/squeue"'
            ),
            1,
        )

        self.assertIn(
            '"--states=RUNNING"',
            source,
        )
        self.assertIn(
            '"--format=%i|%u|%N"',
            source,
        )

        self.assertNotIn(
            "shell=True",
            source,
        )

    def test_reconciler_matches_job_owner_and_node(
        self,
    ):
        source = (
            ROOT
            / "deploy"
            / "sbin"
            / "biobank-jupyter-proxy-reconciler"
        ).read_text()

        self.assertIn(
            'job[0] == values["owner"]',
            source,
        )
        self.assertIn(
            'job[1] == values["host"]',
            source,
        )
        self.assertIn(
            "remove_lease(",
            source,
        )

    def test_reconciler_timer_is_bounded_well_inside_ttl(
        self,
    ):
        timer = (
            ROOT
            / "deploy"
            / "systemd"
            / "biobank-jupyter-proxy-reconciler.timer"
        ).read_text()

        self.assertIn(
            "OnUnitActiveSec=30s",
            timer,
        )
        self.assertIn(
            "AccuracySec=5s",
            timer,
        )
        self.assertIn(
            "WantedBy=timers.target",
            timer,
        )

    def test_reconciler_service_is_root_controlled(
        self,
    ):
        unit = (
            ROOT
            / "deploy"
            / "systemd"
            / "biobank-jupyter-proxy-reconciler.service"
        ).read_text()

        self.assertIn(
            "User=root",
            unit,
        )
        self.assertIn(
            "NoNewPrivileges=yes",
            unit,
        )
        self.assertIn(
            "ProtectHome=yes",
            unit,
        )
        self.assertIn(
            "ProtectSystem=strict",
            unit,
        )
        self.assertIn(
            "ReadWritePaths=-/run/biobank-jupyter-proxy",
            unit,
        )

class JupyterProxyLogHygieneContractTests(
    SimpleTestCase
):
    def test_jupyter_proxy_suppresses_ood_info_request_logger(
        self,
    ):
        proxy = (
            ROOT
            / "deploy"
            / "ood"
            / "biobank-node-proxy.conf"
        ).read_text()

        self.assertIn(
            "LogLevel lua_module:warn",
            proxy,
        )

        # Keep the suppression scoped to the Biobank Jupyter
        # LocationMatch rather than modifying the OOD vendor logger.
        location_start = proxy.index(
            '<LocationMatch "^/biobank/internal/'
            'lab-tools/jupyter/'
        )
        location_end = proxy.index(
            "</LocationMatch>",
            location_start,
        )

        location = proxy[
            location_start:location_end
        ]

        self.assertIn(
            "LogLevel lua_module:warn",
            location,
        )

        self.assertNotRegex(
            location,
            r"(?m)^[ \\t]*LuaHookLog\\b",
        )

    def test_ood_access_log_contract_omits_query_string(
        self,
    ):
        contract = (
            ROOT
            / "deploy"
            / "ood"
            / "biobank-ood-log-hygiene.yml"
        ).read_text()

        self.assertIn(
            "%m %U %H",
            contract,
        )

        self.assertNotIn(
            "%r",
            contract.split(
                "logformat:",
                1,
            )[1],
        )

        self.assertNotIn(
            "%q",
            contract.split(
                "logformat:",
                1,
            )[1],
        )

        self.assertNotIn(
            "QUERY_STRING",
            contract.split(
                "logformat:",
                1,
            )[1],
        )

        self.assertIn(
            "%{Referer}i",
            contract,
        )

        self.assertIn(
            "%{User-Agent}i",
            contract,
        )
