from pathlib import Path

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from core.models import Bacteria, Phage
from core.models.samples.subtypes import (
    format_bacterial_taxonomic_name,
)
from core.views.internal.samples.views import (
    sample_qr_scan_view,
)


class SampleMetadataRefinementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username=(
                "sample-metadata-refinement-owner"
            ),
            password="test-password",
        )

        self.factory = RequestFactory()

    def test_full_species_does_not_repeat_genus(self):
        self.assertEqual(
            format_bacterial_taxonomic_name(
                "Klebsiella",
                "Klebsiella pneumoniae",
                "KH1",
            ),
            "Klebsiella pneumoniae KH1",
        )

    def test_species_epithet_still_receives_genus(self):
        self.assertEqual(
            format_bacterial_taxonomic_name(
                "Pseudomonas",
                "aeruginosa",
                "PA14",
            ),
            "Pseudomonas aeruginosa PA14",
        )

    def test_bacteria_taxonomic_display_property(self):
        bacterium = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-TEST-META-0001",
            sample_type="Bacterium (Host)",
            organism_name=(
                "Klebsiella pneumoniae KH1"
            ),
            genus="Klebsiella",
            species="Klebsiella pneumoniae",
            strain="KH1",
        )

        self.assertEqual(
            bacterium.taxonomic_display_name,
            "Klebsiella pneumoniae KH1",
        )

    def test_qr_biological_view_does_not_duplicate_genus(
        self,
    ):
        bacterium = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-TEST-META-0002",
            sample_type="Bacterium (Host)",
            organism_name=(
                "Klebsiella pneumoniae KH1"
            ),
            genus="Klebsiella",
            species="Klebsiella pneumoniae",
            strain="KH1",
        )

        request = self.factory.get(
            f"/samples/scan/{bacterium.uuid}/"
        )
        request.user = self.owner

        response = sample_qr_scan_view(
            request,
            bacterium.uuid,
        )

        body = response.content.decode(
            "utf-8"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            "Klebsiella pneumoniae KH1",
            body,
        )

        self.assertNotIn(
            "Klebsiella Klebsiella pneumoniae",
            body,
        )

    def test_phage_has_new_strain_field(self):
        field = Phage._meta.get_field(
            "strain"
        )

        self.assertEqual(
            field.max_length,
            100,
        )
        self.assertTrue(
            field.blank
        )
        self.assertTrue(
            field.null
        )

    def test_legacy_phage_name_is_not_editable(self):
        field = Phage._meta.get_field(
            "phage_name"
        )

        self.assertFalse(
            field.editable
        )

    def test_phage_strain_persists(self):
        phage = Phage.objects.create(
            owner=self.owner,
            sample_id="PHA-TEST-META-0001",
            sample_type="Phage (Virus)",
            organism_name="ZC99",
            official_name="ZC99",
            strain="Laboratory isolate A",
        )

        phage.refresh_from_db()

        self.assertEqual(
            phage.strain,
            "Laboratory isolate A",
        )

    def test_phage_create_ui_uses_strain_not_legacy_name(
        self,
    ):
        source = (Path(__file__).resolve().parents[2] / 'core/static/internal/samples/samples.js').read_text()

        phage_template = next(
            line
            for line in source.splitlines()
            if '"Phage (Virus)"' in line
        )

        self.assertIn(
            '"strain"',
            phage_template,
        )

        self.assertNotIn(
            '"phage_name"',
            phage_template,
        )

        self.assertIn(
            '"morphotype"',
            phage_template,
        )

        self.assertIn(
            '"taxonomy"',
            phage_template,
        )

    def test_print_label_uses_45_character_limit(self):
        source = Path(
            "core/interfaces/internal/samples/"
            "print_label.html"
        ).read_text()

        self.assertIn(
            "truncatechars:45",
            source,
        )

        self.assertNotIn(
            "truncatechars:35",
            source,
        )


class PhageFormMetadataRefinementTests(TestCase):
    def test_phage_form_exposes_strain_not_legacy_name(
        self,
    ):
        from core.forms import PhageForm

        form = PhageForm()

        self.assertIn(
            "strain",
            form.fields,
        )

        self.assertNotIn(
            "phage_name",
            form.fields,
        )

        self.assertIn(
            "morphotype",
            form.fields,
        )

        self.assertIn(
            "taxonomy",
            form.fields,
        )
