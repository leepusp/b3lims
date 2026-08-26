from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class C3LimsBruteForceContractTests(
    SimpleTestCase
):
    def setUp(self):
        self.base = Path(
            settings.BASE_DIR
        )

    def test_fail2ban_jail_is_path_local(self):
        jail = (
            self.base
            / "deploy"
            / "fail2ban"
            / "jail.d"
            / "biobank-auth.local"
        ).read_text()

        self.assertIn(
            "[biobank-auth]",
            jail,
        )
        self.assertIn(
            "backend = systemd",
            jail,
        )
        self.assertIn(
            "maxretry = 5",
            jail,
        )
        self.assertIn(
            "findtime = 600",
            jail,
        )
        self.assertIn(
            "bantime = 3600",
            jail,
        )
        self.assertIn(
            "ignoreip = 127.0.0.0/8 ::1",
            jail,
        )
        self.assertIn(
            "action = biobank-path-state",
            jail,
        )

        active = "\n".join(
            line.strip()
            for line in jail.splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
        )

        for forbidden in (
            "firewall-cmd",
            "iptables",
            "nftables",
            "port = 443",
            "port = https",
        ):
            self.assertNotIn(
                forbidden,
                active,
            )

    def test_fail2ban_filter_is_biobank_specific(self):
        filter_text = (
            self.base
            / "deploy"
            / "fail2ban"
            / "filter.d"
            / "biobank-auth.conf"
        ).read_text()

        self.assertIn(
            r"pam_unix\(biobank:auth\): "
            r"authentication failure;",
            filter_text,
        )
        self.assertIn(
            r"rhost=<HOST>",
            filter_text,
        )
        self.assertIn(
            "_SYSTEMD_UNIT=httpd.service + "
            "_COMM=httpd",
            filter_text,
        )

        self.assertNotIn(
            "pam_unix\\(galaxy:auth\\)",
            filter_text,
        )

    def test_fail2ban_action_has_no_shared_firewall_effect(self):
        action = (
            self.base
            / "deploy"
            / "fail2ban"
            / "action.d"
            / "biobank-path-state.conf"
        ).read_text()

        helper = (
            "/usr/local/sbin/"
            "biobank-auth-guard-state"
        )

        for command in (
            f"actionstart = {helper} start",
            f"actionflush = {helper} flush",
            f"actionstop = {helper} stop",
            f"actioncheck = {helper} check",
            (
                f"actionban = {helper} ban "
                "<ip> <time> <bantime>"
            ),
            f"actionunban = {helper} unban <ip>",
        ):
            self.assertIn(
                command,
                action,
            )

        active = "\n".join(
            line.strip()
            for line in action.splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
        )

        for forbidden in (
            "firewall-cmd",
            "iptables",
            "nftables",
        ):
            self.assertNotIn(
                forbidden,
                active,
            )

    def test_apache_guard_is_private_only(self):
        apache = (
            self.base
            / "deploy"
            / "apache"
            / "biobank.conf"
        ).read_text()

        hook = (
            "LuaHookAccessChecker \\\n"
            "        /etc/httpd/biobank/"
            "biobank_auth_guard.lua \\\n"
            "        biobank_auth_guard early"
        )

        self.assertEqual(
            apache.count(
                hook
            ),
            1,
        )

        private_match = next(
            line
            for line in apache.splitlines()
            if line.startswith(
                '<LocationMatch "^/c3-lims($|/'
            )
        )

        self.assertIn(
            "public/(?:$|about/$|governance/$|"
            "collections/$|collections/[0-9]+/$)",
            private_match,
        )
        self.assertIn(
            "internal/lab-tools/jupyter/",
            private_match,
        )
        self.assertIn(
            "static/",
            private_match,
        )

    def test_lua_guard_enforces_expiring_root_state(self):
        lua = (
            self.base
            / "deploy"
            / "apache"
            / "biobank_auth_guard.lua"
        ).read_text()

        self.assertIn(
            '"/run/biobank-auth-guard"',
            lua,
        )
        self.assertIn(
            "r.useragent_ip",
            lua,
        )
        self.assertIn(
            "io.open(",
            lua,
        )
        self.assertIn(
            "expires_at=(%d+)",
            lua,
        )
        self.assertIn(
            "expiry <= os.time()",
            lua,
        )
        self.assertIn(
            "return apache2.DECLINED",
            lua,
        )
        self.assertIn(
            'r:custom_response(\n'
            '            403,\n'
            '            "Forbidden"',
            lua,
        )

        for forbidden in (
            "os.execute",
            "io.popen",
            "X-Forwarded-For",
            "X-Real-IP",
        ):
            self.assertNotIn(
                forbidden,
                lua,
            )

    def test_state_helper_validates_ip_permissions_and_expiry(self):
        helper = (
            self.base
            / "deploy"
            / "sbin"
            / "biobank-auth-guard-state"
        ).read_text()

        self.assertIn(
            "ipaddress.ip_address(",
            helper,
        )
        self.assertIn(
            '"/run/biobank-auth-guard"',
            helper,
        )
        self.assertIn(
            '"apache"',
            helper,
        )
        self.assertIn(
            "DIRECTORY_MODE = 0o750",
            helper,
        )
        self.assertIn(
            "FILE_MODE = 0o640",
            helper,
        )
        self.assertIn(
            "expires_at = int(",
            helper,
        )
        self.assertIn(
            ".to_integral_value(",
            helper,
        )
        self.assertIn(
            "rounding=ROUND_CEILING",
            helper,
        )
        self.assertIn(
            "banned_at",
            helper,
        )
        self.assertIn(
            "bantime",
            helper,
        )
        self.assertIn(
            "SAFE_TIMESTAMP",
            helper,
        )
        self.assertIn(
            "Decimal(",
            helper,
        )
        self.assertIn(
            "ROUND_CEILING",
            helper,
        )
        self.assertIn(
            "parse_timestamp(",
            helper,
        )
        self.assertIn(
            "os.replace(",
            helper,
        )
        self.assertIn(
            "prune_expired()",
            helper,
        )
