from pathlib import Path
import hashlib

from django.test import SimpleTestCase


BASE = (
    Path(__file__).resolve().parents[1]
    / "interfaces"
    / "internal"
    / "lab_tools"
)

TEMPLATE = (
    BASE
    / "molecular_sequence_detail.html"
)

SCRIPT = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure.js'
)

STYLE = (
    Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_protein_structure.css'
)

VENDOR = (
    Path(__file__).resolve().parents[2]
    / "core/static/internal/lab_tools/vendor"
)


class MolecularProteinStructureFrontendTests(
    SimpleTestCase
):
    def test_template_loads_molstar_only_for_protein_surface(self):
        text = TEMPLATE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "vendor/molstar-5.11.0.css",
            text,
        )

        self.assertIn(
            "vendor/molstar-5.11.0.js",
            text,
        )

        self.assertIn(
            "molecular_protein_structure.css",
            text,
        )

        self.assertIn(
            "molecular_protein_structure.js",
            text,
        )

        self.assertIn(
            "data-protein-structures-url=",
            text,
        )

    def test_structure_script_uses_existing_overview(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            ".mw-protein-final-overview",
            ".mw-protein-overview-sequence",
            "mps-overview-grid",
            "mw-protein-structure",
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_structure_script_uses_protected_api(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        for marker in (
            "proteinStructuresUrl",
            '"raw"',
            '"download"',
            '"upload"',
            '"delete"',
            'credentials: "same-origin"',
            '"X-CSRFToken"',
        ):
            self.assertIn(
                marker,
                text,
            )

    def test_structure_script_uses_compiled_molstar_viewer(self):
        text = SCRIPT.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "window.molstar.Viewer.create",
            text,
        )

        self.assertIn(
            "loadStructureFromData",
            text,
        )

        self.assertIn(
            "window.BiobankProteinStructure",
            text,
        )

    def test_structure_css_places_viewer_beside_sequence(self):
        text = STYLE.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".mps-overview-grid",
            text,
        )

        self.assertIn(
            "grid-template-columns",
            text,
        )

        self.assertIn(
            ".mps-viewer-shell",
            text,
        )

    def test_vendored_molstar_hashes(self):
        expected = {
            "molstar-5.11.0.js":
                "7fad5561c74bc900930fb57d6ab028d1aafdda82223a901bf932b1098e84f1f3",
            "molstar-5.11.0.css":
                "5b68ceb6d3642549b4e9b2c071e58e41b98a5350ae269180587b39da86925d55",
            "molstar-5.11.0.LICENSE.txt":
                "eabd1831ed605a29cf9d7e60221c019c1bc026add81e3c0686ce5f24b3d4d500",
        }

        for filename, checksum in expected.items():
            content = (
                VENDOR
                / filename
            ).read_bytes()

            self.assertEqual(
                hashlib.sha256(
                    content
                ).hexdigest(),
                checksum,
            )
