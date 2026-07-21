from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    MolecularSequence,
    NotebookEntry,
)


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularWorkspaceFrontendTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="molecular-ui-owner",
            password="test-password",
        )
        self.viewer = get_user_model().objects.create_user(
            username="molecular-ui-viewer",
            password="test-password",
        )
        self.entry = NotebookEntry.objects.create(
            title="Shared molecular notebook",
            author=self.owner,
            visibility="lab",
        )
        self.molecule = MolecularSequence.objects.create(
            name="Validated plasmid",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCGTACGAATTC",
            source_entry=self.entry,
            owner=self.owner,
        )

    def test_owner_receives_clean_editable_workspace(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "internal/lab_tools/molecular_workspace.js",
        )
        self.assertContains(
            response,
            'data-can-edit="true"',
        )
        self.assertNotContains(response, "unpkg.com")
        self.assertNotContains(response, "localStorage")
        self.assertNotContains(response, "buildDemoFeatures")
        self.assertContains(response, "SeqViz interactive viewer")
        self.assertContains(
            response,
            "internal/lab_tools/vendor/seqviz-3.10.22.min.js",
        )
        self.assertContains(
            response,
            "internal/lab_tools/molecular_seqviz.js",
        )

    def test_workspace_offers_synchronized_visualization_modes(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertContains(response, 'data-mw-view="seqviz"')
        self.assertContains(response, 'data-mw-view="construction"')
        self.assertContains(response, 'data-mw-view="sequence"')
        self.assertContains(response, 'data-mw-view="split"')
        self.assertContains(response, 'data-mw-view="all"')
        self.assertContains(response, 'id="mw-map-tool"')
        self.assertContains(response, 'id="mw-construction-track"')
        self.assertContains(response, 'id="mw-selection-summary"')

        script = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/molecular_workspace.js",
        ).read_text()

        for function_name in (
            "applyWorkspaceView",
            "renderConstructionTrack",
            "moveFeatureFromDrag",
            "appendInteractiveSequence",
            "createFeatureFromSelection",
        ):
            self.assertIn(f"function {function_name}(", script)

        self.assertNotIn("localStorage", script)

        adapter = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/molecular_seqviz.js",
        ).read_text()
        self.assertIn("window.seqviz.Viewer", adapter)
        self.assertIn("BiobankMolecularWorkspace", adapter)
        self.assertNotIn("unpkg", adapter)
        self.assertNotIn("localStorage", adapter)

    def test_classification_and_sequence_editor_are_explicit(self):
        template = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_sequence_detail.html",
        ).read_text()
        workspace = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_workspace.js",
        ).read_text()
        adapter = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_seqviz.js",
        ).read_text()

        self.assertIn(
            'id="mw-type-display"',
            template,
        )
        self.assertIn(
            'id="mw-type"',
            template,
        )
        self.assertIn(
            'type="hidden"',
            template,
        )
        self.assertNotIn(
            '<select id="mw-type"',
            template,
        )
        self.assertNotIn(
            "data-classification-control",
            template,
        )
        self.assertIn(
            "Fixed after creation",
            template,
        )
        self.assertIn(
            "data-mw-open-sequence-editor",
            template,
        )
        self.assertIn(
            'id="mw-seqviz-colors"',
            template,
        )
        self.assertIn(
            'applyWorkspaceView("sequence")',
            workspace,
        )
        self.assertIn(
            "bpColors: symbolColorsFor(data)",
            adapter,
        )
        self.assertIn(
            "NUCLEOTIDE_COLORS",
            adapter,
        )
        self.assertIn(
            "AMINO_ACID_COLORS",
            adapter,
        )

    def test_feature_colors_refresh_all_molecular_views(self):
        script = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_workspace.js",
        ).read_text()

        palette_start = script.index(
            "const FEATURE_COLORS"
        )
        palette_end = script.index(
            "const ENZYMES"
        )
        palette = script[
            palette_start:palette_end
        ]

        for feature_type in (
            "promoter",
            "rbs",
            "cds",
            "terminator",
            "ori",
            "antibiotic",
            "primer",
            "domain",
            "utr",
            "custom",
        ):
            self.assertIn(
                f"{feature_type}:",
                palette,
            )

        self.assertIn(
            "feature.type",
            script,
        )
        self.assertIn(
            "feature.feature_type",
            script,
        )
        self.assertIn(
            "biobank_auto_color",
            script,
        )
        self.assertIn(
            "options.typeChanged === true",
            script,
        )
        self.assertIn(
            "options.colorChanged === true",
            script,
        )
        self.assertIn(
            'notifyWorkspaceChange("feature")',
            script,
        )
        self.assertIn(
            'notifyWorkspaceChange("feature-remove")',
            script,
        )

        adapter = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_seqviz.js",
        ).read_text()

        self.assertIn(
            "biobank:molecular-workspace-change",
            adapter,
        )

    def test_notebook_exposes_one_linked_molecular_workspace_flow(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}&tab=items"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Molecular Workspace")
        self.assertContains(response, 'id="molecular-workspace-creator"')
        self.assertContains(response, "Create and open")
        self.assertContains(response, "insertRelevantItemIntoMainNote(data, false)")
        self.assertContains(response, "window.location.href = data.detail_url")
        self.assertContains(response, "ql-biobank-molecular")

    def test_notebook_exposes_integrated_jupyter_workspace(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}&tab=items"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jupyter analysis")
        self.assertContains(response, "Open workspace")
        self.assertContains(
            response,
            "integrated full-width cell workspace",
        )
        self.assertContains(response, "Slurm cluster")
        self.assertContains(
            response,
            reverse(
                "notebook_jupyter_workspace",
                args=[self.entry.id],
            ),
        )
        self.assertContains(
            response,
            "data-jupyter-launch",
        )

    def test_lab_viewer_receives_read_only_workspace(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            request_path(
                "molecular_sequence_detail",
                [self.molecule.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-can-edit="false"',
        )
        self.assertContains(response, "Read only")
        self.assertNotContains(
            response,
            'id="mw-save"',
        )
        self.assertNotContains(
            response,
            'id="mw-delete"',
        )
