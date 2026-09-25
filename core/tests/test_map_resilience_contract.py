"""Regression contract for resilient B3 LIMS geographic maps."""

from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase


class MapResilienceContractTests(SimpleTestCase):
    map_templates = (
        "internal/biobanks/biobank_create.html",
        "internal/biobanks/biobank_dashboard.html",
        "internal/collections/detail.html",
        "internal/samples/dashboard.html",
        "internal/samples/detail.html",
        "internal/samples/edit.html",
        "internal/samples/origin_map.html",
        "internal/samples/samples.html",
        "internal/shipments/dashboard.html",
        "public/biobanks/detail.html",
        "public/biobanks/list.html",
    )

    required_assets = (
        "vendor/leaflet/1.9.4/leaflet.css",
        "vendor/leaflet/1.9.4/leaflet.js",
        "vendor/leaflet/1.9.4/images/marker-icon.png",
        "vendor/leaflet/1.9.4/images/marker-icon-2x.png",
        "vendor/leaflet/1.9.4/images/marker-shadow.png",
        "maps/world_countries.js",
        "common/b3_map.js",
        "common/b3_map.css",
    )

    def _source(self, relative):
        return (
            Path(settings.BASE_DIR)
            / relative
        ).read_text()

    def test_map_assets_are_local_and_discoverable(self):
        missing = [
            asset
            for asset in self.required_assets
            if finders.find(asset) is None
        ]

        self.assertFalse(
            missing,
            "Missing local map assets:\n"
            + "\n".join(missing),
        )

    def test_local_world_basemap_is_packaged(self):
        path = (
            Path(settings.BASE_DIR)
            / "core/static/maps/world_countries.js"
        )

        text = path.read_text()

        self.assertIn(
            "window.B3_WORLD_COUNTRIES=",
            text,
        )
        self.assertIn(
            '"FeatureCollection"',
            text,
        )
        self.assertGreater(
            path.stat().st_size,
            50_000,
        )

    def test_all_map_templates_compile(self):
        failures = []

        for template_name in self.map_templates:
            try:
                get_template(template_name)
            except Exception as exc:
                failures.append(
                    f"{template_name}: {exc}"
                )

        self.assertFalse(
            failures,
            "Map template compilation failures:\n"
            + "\n".join(failures),
        )

    def test_map_templates_use_shared_local_asset_stack(self):
        failures = []

        for template_name in self.map_templates:
            path = (
                Path(settings.BASE_DIR)
                / "core/interfaces"
                / template_name
            )

            text = path.read_text()

            if (
                'include "common/map_assets_css.html"'
                not in text
            ):
                failures.append(
                    f"{template_name}: missing CSS partial"
                )

            if (
                'include "common/map_assets_js.html"'
                not in text
            ):
                failures.append(
                    f"{template_name}: missing JS partial"
                )

        self.assertFalse(
            failures,
            "Shared map asset stack missing:\n"
            + "\n".join(failures),
        )

    def test_leaflet_cdn_is_absent_from_first_party_templates(self):
        interface_root = (
            Path(settings.BASE_DIR)
            / "core/interfaces"
        )

        banned = (
            "unpkg.com/leaflet",
            "cdn.jsdelivr.net/npm/leaflet",
        )

        violations = []

        for path in interface_root.rglob("*.html"):
            text = path.read_text(
                errors="ignore"
            )

            for host in banned:
                if host in text:
                    violations.append(
                        f"{path}: {host}"
                    )

        self.assertFalse(
            violations,
            "Remote Leaflet CDN dependency detected:\n"
            + "\n".join(violations),
        )

    def test_osm_tile_provider_is_centralized(self):
        root = Path(settings.BASE_DIR)

        search_roots = (
            root / "core/interfaces",
            root / "core/static",
        )

        allowed = (
            root
            / "core/static/common/b3_map.js"
        ).resolve()

        violations = []
        total = 0

        for search_root in search_roots:
            for path in search_root.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix not in {
                    ".html",
                    ".js",
                }:
                    continue

                if "vendor" in path.parts:
                    continue

                text = path.read_text(
                    errors="ignore"
                )

                count = text.count(
                    "tile.openstreetmap.org"
                )

                if not count:
                    continue

                total += count

                if path.resolve() != allowed:
                    violations.append(
                        str(path)
                    )

        self.assertFalse(
            violations,
            "OSM tile provider escaped B3Map:\n"
            + "\n".join(violations),
        )

        self.assertEqual(
            total,
            1,
        )

    def test_shared_controller_has_local_fallback_and_timeout(self):
        text = self._source(
            "core/static/common/b3_map.js"
        )

        for marker in (
            '"tileerror"',
            "addLocalBasemap",
            "b3:basemapfallback",
            "startup-timeout",
            "navigator.onLine",
            "ERROR_THRESHOLD",
            "STARTUP_TIMEOUT_MS",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_all_functional_map_scripts_use_b3map(self):
        files = (
            "core/static/internal/samples/sample_origin_map.js",
            "core/static/internal/biobanks/biobank.js",
            "core/static/internal/shipments/route_map.js",
            "core/static/public/biobanks.js",
            "core/interfaces/internal/biobanks/biobank_dashboard.html",
        )

        failures = []

        for relative in files:
            text = self._source(relative)

            if (
                "B3Map.addResilientBasemap"
                not in text
            ):
                failures.append(relative)

        self.assertFalse(
            failures,
            "Map implementation bypasses B3Map:\n"
            + "\n".join(failures),
        )

    def test_osm_standard_tile_url_is_canonical(self):
        text = self._source(
            "core/static/common/b3_map.js"
        )

        self.assertIn(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            text,
        )

        self.assertNotIn(
            "{s}.tile.openstreetmap.org",
            text,
        )

    def test_public_nominatim_is_not_used_for_autocomplete(self):
        root = Path(__file__).resolve().parents[2]

        browser_source = (
            root
            / "core"
            / "static"
            / "internal"
            / "biobanks"
            / "biobank.js"
        ).read_text(
            encoding="utf-8"
        )

        service_source = (
            root
            / "core"
            / "services"
            / "geocoding.py"
        ).read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            "nominatim.openstreetmap.org",
            browser_source,
        )

        self.assertEqual(
            service_source.count(
                "nominatim.openstreetmap.org"
            ),
            1,
        )

        self.assertIn(
            "locationSearchButton",
            browser_source,
        )

        self.assertIn(
            'event.key !== "Enter"',
            browser_source,
        )

    def test_nominatim_failure_does_not_block_coordinate_capture(self):
        root = Path(__file__).resolve().parents[2]

        text = (
            root
            / "core"
            / "static"
            / "internal"
            / "biobanks"
            / "biobank.js"
        ).read_text(
            encoding="utf-8"
        )

        click_start = text.index(
            '    map.on(\n'
            '        "click",'
        )

        click_end = text.index(
            "    labelInput.addEventListener(",
            click_start,
        )

        click_block = text[
            click_start:click_end
        ]

        self.assertIn(
            "updateInputs(",
            click_block,
        )

        self.assertIn(
            "placeMarker(",
            click_block,
        )

        self.assertIn(
            "reverseGeocode(",
            click_block,
        )

        self.assertLess(
            click_block.index(
                "updateInputs("
            ),
            click_block.index(
                "reverseGeocode("
            ),
        )

        self.assertIn(
            '"Coordinates saved. "',
            text,
        )

        self.assertIn(
            '"temporarily unavailable."',
            text,
        )
