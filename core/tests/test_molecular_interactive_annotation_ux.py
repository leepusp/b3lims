from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MolecularInteractiveAnnotationUxTests(
    SimpleTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        base = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools",
        )

        cls.template = (
            base
            / "molecular_sequence_detail.html"
        ).read_text()

        cls.workspace = (
            base
            / "molecular_workspace.js"
        ).read_text()

        cls.stylesheet = (
            base
            / "molecular_workspace.css"
        ).read_text()

    def test_selected_feature_uses_one_shared_editor(self):
        self.assertIn(
            "function ensureInteractiveAnnotationDrawer()",
            self.workspace,
        )

        self.assertIn(
            "body.append(\n"
            "                hint,\n"
            "                elements.featureForm\n"
            "            );",
            self.workspace,
        )

        self.assertIn(
            "openInteractiveAnnotationEditor(index);",
            self.workspace,
        )

        self.assertIn(
            'drawer.id = "mw-annotation-drawer";',
            self.workspace,
        )

        self.assertIn(
            "elements.featureRemove?.addEventListener",
            self.workspace,
        )

    def test_existing_unified_initializer_stays_disabled(self):
        self.assertIn(
            "function initializeUnifiedWorkspace()",
            self.workspace,
        )

        self.assertNotIn(
            "\n        initializeUnifiedWorkspace();\n",
            self.workspace,
        )

    def test_major_panels_have_expand_support(self):
        self.assertIn(
            "function initializeWorkspacePanelControls()",
            self.workspace,
        )

        self.assertIn(
            '"mw-panel-focus-toggle"',
            self.workspace,
        )

        self.assertIn(
            '"is-workspace-maximized"',
            self.workspace,
        )

        self.assertIn(
            "body.mw-workspace-focus-active",
            self.stylesheet,
        )

    def test_sequence_track_density_is_responsive(self):
        self.assertIn(
            "function responsivePreviewBasesPerRow()",
            self.workspace,
        )

        self.assertIn(
            "basesPerRow: responsivePreviewBasesPerRow(),",
            self.workspace,
        )

        self.assertNotIn(
            "basesPerRow: 60,",
            self.workspace,
        )

        self.assertIn(
            'id="mw-preview-density"',
            self.template,
        )

        self.assertNotIn(
            "<span>60 symbols per row</span>",
            self.template,
        )

    def test_feature_list_allows_wrapped_identity(self):
        self.assertIn(
            ".mw-feature-name {",
            self.stylesheet,
        )

        self.assertIn(
            "white-space: normal !important;",
            self.stylesheet,
        )

        self.assertIn(
            ".mw-feature-meta {",
            self.stylesheet,
        )
