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
    return reverse(name, args=args)


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
            "internal/lab_tools/molecular_sequence_track.js",
        )
        self.assertContains(
            response,
            "internal/lab_tools/molecular_sequence_track.css",
        )
        self.assertContains(
            response,
            'data-can-edit="true"',
        )
        self.assertNotContains(
            response,
            "molecular_sequence_track.css}",
        )
        self.assertNotContains(
            response,
            "molecular_sequence_track.js}",
        )
        self.assertNotContains(response, "unpkg.com")
        self.assertNotContains(response, "localStorage")
        self.assertNotContains(response, "buildDemoFeatures")
        self.assertContains(response, "Sequence viewer")
        self.assertContains(
            response,
            "internal/lab_tools/vendor/seqviz-3.10.22.min.js",
        )
        self.assertContains(
            response,
            "internal/lab_tools/molecular_seqviz.js",
        )
        self.assertContains(
            response,
            'id="mw-seqviz-create-feature"',
        )
        self.assertContains(
            response,
            'id="mw-seqviz-feature-form"',
        )

    def test_seqviz_is_primary_and_secondary_tools_are_separate(self):
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
        self.assertNotContains(response, 'data-mw-view="split"')
        self.assertNotContains(response, 'data-mw-view="all"')
        self.assertContains(response, 'id="mw-seqviz-viewer"')
        self.assertContains(response, 'class="mw-seqviz-inspector"')
        self.assertContains(response, 'id="mw-map-tool"')
        self.assertContains(response, 'id="mw-construction-track"')
        self.assertContains(response, 'id="mw-selection-summary"')

        script = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()

        for function_name in (
            "applyWorkspaceView",
            "renderConstructionTrack",
            "moveFeatureFromDrag",
            "restrictionSitesForTrack",
            "createFeatureFromSelection",
        ):
            self.assertIn(f"function {function_name}(", script)

        self.assertNotIn("localStorage", script)
        self.assertIn(
            "window.BiobankSequenceTrack.render",
            script,
        )
        self.assertNotIn(
            "function appendInteractiveSequence(",
            script,
        )

        track = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_sequence_track.js').read_text()
        track_styles = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_sequence_track.css').read_text()
        self.assertIn(
            "window.BiobankSequenceTrack",
            track,
        )
        self.assertIn(
            "data-feature-bar",
            track,
        )
        self.assertIn(
            ".mw-seq-track",
            track_styles,
        )

        adapter = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_seqviz.js').read_text()
        self.assertIn("window.seqviz.Viewer", adapter)
        self.assertIn("BiobankMolecularWorkspace", adapter)
        self.assertIn('zoom: {linear: Number(zoom.value || 50)}', adapter)
        self.assertIn("mismatch: Number(mismatch.value || 0)", adapter)
        self.assertIn("showComplement.checked", adapter)
        self.assertIn("showIndex.checked", adapter)
        self.assertIn('{source: "seqviz"}', adapter)
        self.assertIn(
            'event.detail?.source === "seqviz"',
            adapter,
        )
        self.assertIn(
            "createFeatureFromSelection?.({",
            adapter,
        )
        self.assertNotIn("unpkg", adapter)
        self.assertNotIn("localStorage", adapter)

        self.assertIn(
            "createFeatureFromSelection,",
            script,
        )
        self.assertIn(
            'options.source === "seqviz"',
            script,
        )

        self.assertIn(': "seqviz";', script)
        self.assertIn('? view : "seqviz";', script)

    def test_classification_and_sequence_editor_are_explicit(self):
        template = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_sequence_detail.html",
        ).read_text()
        workspace = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()
        adapter = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_seqviz.js').read_text()

        self.assertIn(
            'id="mw-type-display"',
            template,
        )

        display_start = template.index(
            'id="mw-type-display"'
        )
        display_end = template.index(
            ">",
            display_start,
        )
        display_control = template[
            display_start:display_end
        ]

        self.assertIn(
            'type="text"',
            display_control,
        )
        self.assertIn(
            "readonly",
            display_control,
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
            "data-mw-open-sequence-editor",
            template,
        )
        self.assertIn(
            'id="mw-seqviz-colors"',
            template,
        )
        for control_id in (
            "mw-seqviz-mode",
            "mw-seqviz-zoom",
            "mw-seqviz-enzymes",
            "mw-seqviz-search",
            "mw-seqviz-mismatch",
            "mw-seqviz-show-complement",
            "mw-seqviz-show-index",
            "mw-seqviz-reset",
        ):
            self.assertIn(
                f'id="{control_id}"',
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
        self.assertIn(
            'data.sequenceType === "protein"',
            adapter,
        )
        self.assertIn(
            "return AMINO_ACID_COLORS;",
            adapter,
        )
        self.assertIn(
            "return NUCLEOTIDE_COLORS;",
            adapter,
        )

    def test_statistics_supports_readonly_classification_control(self):
        script = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()

        start = script.index(
            "function syncStatistics()"
        )
        end = script.index(
            "\n        function ",
            start + 1,
        )
        statistics = script[start:end]

        self.assertIn(
            "elements.type?.selectedOptions?.[0]?.text",
            statistics,
        )
        self.assertIn(
            "elements.type?.value",
            statistics,
        )
        self.assertIn(
            "elements.topology?.selectedOptions?.[0]?.text",
            statistics,
        )
        self.assertIn(
            "elements.topology?.value",
            statistics,
        )
        self.assertNotIn(
            "elements.type.options[",
            statistics,
        )
        self.assertNotIn(
            "elements.topology.options[",
            statistics,
        )

    def test_unified_molecular_workspace_layout(self):
        template = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "molecular_sequence_detail.html",
        ).read_text()

        workspace = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()

        adapter = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_seqviz.js').read_text()

        stylesheet = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.css').read_text()

        self.assertIn(
            "function initializeUnifiedWorkspace()",
            workspace,
        )
        self.assertIn(
            'root.classList.add("mw-unified-workspace")',
            workspace,
        )
        self.assertIn(
            'featureEditor.id = "mw-unified-feature-editor"',
            workspace,
        )
        self.assertIn(
            "featureEditor.appendChild(elements.featureForm)",
            workspace,
        )
        self.assertIn(
            'sequenceDetails.id = "mw-unified-sequence-details"',
            workspace,
        )
        self.assertIn(
            'labelMode.id = "mw-unified-label-mode"',
            workspace,
        )
        self.assertIn(
            '["selected", "Selected"]',
            workspace,
        )
        self.assertIn(
            "mw-unified-color-swatch",
            workspace,
        )
        self.assertIn(
            'event.target.closest(',
            workspace,
        )
        self.assertIn(
            '"[data-coordinate]"',
            workspace,
        )
        self.assertNotIn(
            "initializeUnifiedWorkspace();",
            workspace,
        )
        self.assertIn(
            "applyWorkspaceView(preferredView());",
            workspace,
        )
        self.assertNotIn(
            'applyWorkspaceView("seqviz");',
            workspace,
        )
        self.assertIn(
            'const labelMode = document.getElementById(',
            adapter,
        )
        self.assertIn(
            '(labelMode?.value || "selected")',
            adapter,
        )
        self.assertIn(
            "featureIndex === data.selectedFeature",
            adapter,
        )
        self.assertIn(
            "UNIFIED MOLECULAR WORKSPACE 20260806",
            stylesheet,
        )
        self.assertRegex(
            template,
            r"molecular_workspace\.css' %}\?v=[A-Za-z0-9._-]+",
        )
        self.assertRegex(
            template,
            r"molecular_workspace\.js' %}\?v=[A-Za-z0-9._-]+",
        )
        self.assertRegex(
            template,
            r"molecular_seqviz\.js' %}\?v=[A-Za-z0-9._-]+",
        )

    def test_feature_colors_refresh_all_molecular_views(self):
        script = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_workspace.js').read_text()

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

        adapter = (Path(__file__).resolve().parents[2] / 'core/static/internal/lab_tools/molecular_seqviz.js').read_text()

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
        self.assertContains(response, "New record")
        self.assertContains(response, "insertRelevantItemIntoMainNote(data, false)")
        self.assertContains(response, "window.location.href = data.detail_url")
        self.assertContains(response, "ql-biobank-molecular")

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
        self.assertNotContains(
            response,
            'id="mw-seqviz-create-feature"',
        )
        self.assertNotContains(
            response,
            'id="mw-seqviz-feature-form"',
        )
