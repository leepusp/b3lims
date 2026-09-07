"""Regression tests for offline-capable static assets."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class OfflineStaticAssetsTests(SimpleTestCase):
    banned_static_hosts = {
        "cdn.jsdelivr.net",
        "cdn.quilljs.com",
        "cdn.plot.ly",
        "unpkg.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "cdnjs.cloudflare.com",
    }

    required_vendor_assets = {
        "vendor/bootstrap/5.3.2/bootstrap.min.css",
        "vendor/bootstrap/5.3.2/bootstrap.bundle.min.js",
        "vendor/bootstrap-icons/1.11.1/bootstrap-icons.css",
        "vendor/bootstrap-icons/1.13.1/bootstrap-icons.css",
        "vendor/fullcalendar/6.1.10/index.global.min.js",
        "vendor/leaflet/1.9.4/leaflet.css",
        "vendor/leaflet/1.9.4/leaflet.js",
        "vendor/quill/1.3.6/quill.snow.css",
        "vendor/quill/1.3.6/quill.js",
        "vendor/vis-network/10.1.2/vis-network.min.js",
        "vendor/plotly/2.35.2/plotly.min.js",
        "vendor/echarts/5.5.1/echarts.min.js",
        "vendor/echarts-maps/1.1.0/world.js",
        "vendor/inter/google-fonts-v20/inter.css",
        "vendor/inter/google-fonts-v20/inter-400.ttf",
        "vendor/inter/google-fonts-v20/inter-500.ttf",
        "vendor/inter/google-fonts-v20/inter-600.ttf",
        "vendor/inter/google-fonts-v20/inter-700.ttf",
        "vendor/inter/google-fonts-v20/inter-800.ttf",
        "vendor/inter/google-fonts-v20/OFL.txt",
        "vendor/THIRD_PARTY.md",
    }

    text_suffixes = {
        ".html",
        ".css",
        ".js",
    }

    def _iter_first_party_text_files(self):
        base_dir = Path(settings.BASE_DIR)

        interface_root = (
            base_dir
            / "core"
            / "interfaces"
        )

        static_root = (
            base_dir
            / "core"
            / "static"
        )

        for root in (
            interface_root,
            static_root,
        ):
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix not in self.text_suffixes:
                    continue

                if (
                    static_root in path.parents
                    and "vendor"
                    in path.relative_to(static_root).parts
                ):
                    continue

                yield path

    def test_first_party_sources_do_not_reference_static_cdns(self):
        violations = []

        for path in self._iter_first_party_text_files():
            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            for host in self.banned_static_hosts:
                if host in text:
                    violations.append(
                        f"{path}: {host}"
                    )

        self.assertFalse(
            violations,
            "Static CDN dependency detected:\n"
            + "\n".join(violations),
        )

    def test_required_vendor_assets_are_discoverable(self):
        missing = []

        for asset in sorted(
            self.required_vendor_assets
        ):
            if finders.find(asset) is None:
                missing.append(asset)

        self.assertFalse(
            missing,
            "Vendored static assets missing:\n"
            + "\n".join(missing),
        )

    def test_inter_stylesheet_is_fully_local(self):
        path = (
            Path(settings.BASE_DIR)
            / "core"
            / "static"
            / "vendor"
            / "inter"
            / "google-fonts-v20"
            / "inter.css"
        )

        text = path.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "http://",
            text,
        )

        self.assertNotIn(
            "https://",
            text,
        )

        for weight in (
            400,
            500,
            600,
            700,
            800,
        ):
            self.assertIn(
                f'inter-{weight}.ttf',
                text,
            )

    def test_vendor_manifest_matches_tree(self):
        vendor_root = (
            Path(settings.BASE_DIR)
            / "core"
            / "static"
            / "vendor"
        )

        manifest_path = (
            vendor_root
            / "SHA256SUMS"
        )

        self.assertTrue(
            manifest_path.is_file()
        )

        manifest = {}

        for line in manifest_path.read_text().splitlines():
            if not line.strip():
                continue

            digest, relative_path = (
                line.split(
                    None,
                    1,
                )
            )

            relative_path = (
                relative_path.strip()
            )

            if relative_path.startswith("./"):
                relative_path = (
                    relative_path[2:]
                )

            manifest[relative_path] = digest

        actual_files = {
            path.relative_to(
                vendor_root
            ).as_posix()
            for path in vendor_root.rglob("*")
            if (
                path.is_file()
                and path.name
                != "SHA256SUMS"
            )
        }

        self.assertEqual(
            set(manifest),
            actual_files,
        )

        mismatches = []

        for relative_path in sorted(
            actual_files
        ):
            path = (
                vendor_root
                / relative_path
            )

            actual_digest = (
                hashlib.sha256(
                    path.read_bytes()
                )
                .hexdigest()
            )

            expected_digest = (
                manifest[
                    relative_path
                ]
            )

            if (
                actual_digest
                != expected_digest
            ):
                mismatches.append(
                    relative_path
                )

        self.assertFalse(
            mismatches,
            "Vendor checksum mismatch:\n"
            + "\n".join(mismatches),
        )
