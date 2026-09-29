from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import (
    Bacteria,
    Event,
    HostRange,
    Phage,
    Plasmid,
    Sample,
    SampleOrigin,
)


class NormalizeSampleAliquotsCommandTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="aliquot-normalizer-owner",
            password="test-password",
        )

    def make_bacteria(
        self,
        sample_id="LEGACY-BAC",
        aliquot_count=2,
    ):
        return Bacteria.objects.create(
            sample_id=sample_id,
            sample_type="Bacterium (Host)",
            biosafety_level="NB-2",
            organism_name="P. aeruginosa Legacy",
            owner=self.owner,
            status="available",
            is_public=True,
            aliquot_count=aliquot_count,
            official_name="P. aeruginosa Legacy",
            aliases="LEGACY",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            strain="LEGACY",
            genotype="WT",
            resistance_markers=[],
            isolation_source="Clinical isolate",
        )

    def make_phage(
        self,
        sample_id="LEGACY-PHA",
        aliquot_count=2,
    ):
        return Phage.objects.create(
            sample_id=sample_id,
            sample_type="Phage (Virus)",
            biosafety_level="NB-2",
            organism_name="Pseudomonas Phage Legacy",
            owner=self.owner,
            status="available",
            is_public=True,
            aliquot_count=aliquot_count,
            official_name="Pseudomonas Phage Legacy",
            aliases="LEGACY-PHA",
            strain="LPH1",
            genus="Pbunavirus",
            morphotype="myovirus",
            lifestyle="lytic",
            isolation_source="Environmental sample",
            isolation_method="Enrichment",
            genome_type="dsDNA",
            temp_C="37.0",
        )

    def make_plasmid(
        self,
        sample_id="LEGACY-PLA",
        aliquot_count=2,
    ):
        return Plasmid.objects.create(
            sample_id=sample_id,
            sample_type="Plasmid",
            organism_name="Legacy plasmid",
            owner=self.owner,
            status="available",
            is_public=True,
            aliquot_count=aliquot_count,
            backbone_name="pLegacy",
            backbone_aliases="pLegacy alias",
            vector_type="cloning",
            induction_system="T7",
            origin_of_replication="pUC",
            backbone_size_bp=1234,
            backbone_resistance_markers=[
                "kanamycin",
            ],
            is_empty_vector=False,
            insert_name="legacy-insert",
            purpose="Historical test construct",
            insert_size_bp=321,
            insert_resistance_markers=[
                "ampicillin",
            ],
            construction_name="pLegacy-insert",
            total_size_bp=1555,
        )

    def add_origin(self, sample):
        return SampleOrigin.objects.create(
            sample=sample,
            culture_status="cultured",
            acquisition_source="collaborator",
            source_collection_name="Legacy collection",
            source_collection_accession="LEGACY-001",
            collection_site_name="Legacy site",
            geo_loc_name="São Paulo",
            country_or_ocean="Brasil",
            coordinate_source="other",
            habitat="",
            environmental_medium="",
            env_broad_scale="",
            env_local_scale="",
            ecosystem="",
            ecosystem_category="",
            ecosystem_type="",
            ecosystem_subtype="",
            specific_ecosystem="",
            collection_method="",
            notes="Legacy origin",
            location_visibility="internal",
        )

    def dry_run_plan_sha(self):
        output = StringIO()

        call_command(
            "normalize_sample_aliquots",
            stdout=output,
        )

        for line in output.getvalue().splitlines():
            if line.startswith(
                "plan_sha256="
            ):
                return line.split(
                    "=",
                    1,
                )[1].strip()

        self.fail(
            "Dry-run did not emit plan_sha256."
        )

    def test_default_mode_is_dry_run_and_writes_nothing(self):
        source = self.make_bacteria()
        self.add_origin(source)

        before = (
            source.pk,
            source.uuid,
            source.micro_qr_token,
            source.sample_id,
            source.aliquot_count,
        )

        output = StringIO()

        call_command(
            "normalize_sample_aliquots",
            stdout=output,
        )

        source.refresh_from_db()

        after = (
            source.pk,
            source.uuid,
            source.micro_qr_token,
            source.sample_id,
            source.aliquot_count,
        )

        self.assertEqual(
            before,
            after,
        )

        self.assertFalse(
            Sample.objects.filter(
                sample_id="LEGACY-BAC_1.1",
            ).exists()
        )

        self.assertFalse(
            Sample.objects.filter(
                sample_id="LEGACY-BAC_1.2",
            ).exists()
        )

        text = output.getvalue()

        self.assertIn(
            "MODE=DRY_RUN",
            text,
        )

        self.assertIn(
            "candidate_records=1",
            text,
        )

        self.assertIn(
            "LEGACY-BAC_1.1",
            text,
        )

        self.assertIn(
            "LEGACY-BAC_1.2",
            text,
        )

        self.assertIn(
            "DRY_RUN_COMPLETE=PASS",
            text,
        )

    def test_apply_preserves_first_identity_and_materializes_second(self):
        source = self.make_bacteria()

        origin = self.add_origin(
            source
        )

        legacy_event = Event.objects.create(
            sample=source,
            event_type="entry",
            notes="Legacy historical event",
            performed_by=self.owner,
        )

        original_pk = source.pk
        original_uuid = source.uuid
        original_token = source.micro_qr_token
        original_origin_pk = origin.pk

        output = StringIO()

        call_command(
            "normalize_sample_aliquots",
            apply=True,
            expected_candidates=1,
            expected_plan_sha256=(
                self.dry_run_plan_sha()
            ),
            stdout=output,
        )

        source.refresh_from_db()

        self.assertEqual(
            source.pk,
            original_pk,
        )

        self.assertEqual(
            source.uuid,
            original_uuid,
        )

        self.assertEqual(
            source.micro_qr_token,
            original_token,
        )

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC_1.1",
        )

        self.assertEqual(
            source.aliquot_count,
            1,
        )

        second = Bacteria.objects.get(
            sample_id="LEGACY-BAC_1.2",
        )

        self.assertEqual(
            second.aliquot_count,
            1,
        )

        self.assertNotEqual(
            second.pk,
            source.pk,
        )

        self.assertNotEqual(
            second.uuid,
            source.uuid,
        )

        self.assertNotEqual(
            second.micro_qr_token,
            source.micro_qr_token,
        )

        self.assertEqual(
            second.organism_name,
            source.organism_name,
        )

        self.assertEqual(
            second.species,
            source.bacteria.species,
        )

        self.assertEqual(
            second.strain,
            source.bacteria.strain,
        )

        self.assertEqual(
            second.origin.collection_site_name,
            source.origin.collection_site_name,
        )

        self.assertNotEqual(
            second.origin.pk,
            original_origin_pk,
        )

        self.assertTrue(
            source.events.filter(
                pk=legacy_event.pk,
            ).exists()
        )

        self.assertFalse(
            second.events.filter(
                pk=legacy_event.pk,
            ).exists()
        )

        normalization_events = second.events.filter(
            event_type="entry",
            notes__icontains="historical aliquot normalization",
        )

        self.assertEqual(
            normalization_events.count(),
            1,
        )

        self.assertEqual(
            Sample.objects.filter(
                aliquot_count__gt=1,
            ).count(),
            0,
        )

        text = output.getvalue()

        self.assertIn(
            "MODE=APPLY",
            text,
        )

        self.assertIn(
            "NORMALIZATION_APPLIED=PASS",
            text,
        )

    def test_apply_clones_phage_subtype(self):
        source = self.make_phage()

        call_command(
            "normalize_sample_aliquots",
            apply=True,
            expected_candidates=1,
            expected_plan_sha256=(
                self.dry_run_plan_sha()
            ),
            stdout=StringIO(),
        )

        source.refresh_from_db()

        second = Phage.objects.get(
            sample_id="LEGACY-PHA_1.2",
        )

        self.assertEqual(
            source.sample_id,
            "LEGACY-PHA_1.1",
        )

        self.assertEqual(
            source.aliquot_count,
            1,
        )

        self.assertEqual(
            second.official_name,
            source.phage.official_name,
        )

        self.assertEqual(
            second.genus,
            source.phage.genus,
        )

        self.assertEqual(
            second.morphotype,
            source.phage.morphotype,
        )

        self.assertEqual(
            second.genome_type,
            source.phage.genome_type,
        )


    def test_apply_clones_plasmid_subtype(
        self,
    ):
        source = self.make_plasmid()

        original_pk = source.pk
        original_uuid = source.uuid
        original_token = (
            source.micro_qr_token
        )

        call_command(
            "normalize_sample_aliquots",
            apply=True,
            expected_candidates=1,
            expected_plan_sha256=(
                self.dry_run_plan_sha()
            ),
            stdout=StringIO(),
        )

        source.refresh_from_db()

        second = Plasmid.objects.get(
            sample_id="LEGACY-PLA_1.2"
        )

        self.assertEqual(
            source.pk,
            original_pk,
        )

        self.assertEqual(
            source.uuid,
            original_uuid,
        )

        self.assertEqual(
            source.micro_qr_token,
            original_token,
        )

        self.assertEqual(
            source.sample_id,
            "LEGACY-PLA_1.1",
        )

        self.assertEqual(
            source.aliquot_count,
            1,
        )

        self.assertEqual(
            second.aliquot_count,
            1,
        )

        self.assertNotEqual(
            second.pk,
            source.pk,
        )

        self.assertNotEqual(
            second.uuid,
            source.uuid,
        )

        self.assertNotEqual(
            second.micro_qr_token,
            source.micro_qr_token,
        )

        fields = (
            "backbone_name",
            "backbone_aliases",
            "vector_type",
            "induction_system",
            "origin_of_replication",
            "backbone_size_bp",
            "backbone_resistance_markers",
            "is_empty_vector",
            "insert_name",
            "purpose",
            "insert_size_bp",
            "insert_resistance_markers",
            "construction_name",
            "total_size_bp",
        )

        for field in fields:
            self.assertEqual(
                getattr(
                    second,
                    field,
                ),
                getattr(
                    source.plasmid,
                    field,
                ),
                field,
            )

    def test_plan_sha256_tracks_hostrange_topology_and_metadata(
        self,
    ):
        bacteria = self.make_bacteria()

        phage = self.make_phage(
            aliquot_count=1
        )

        sha_without_relation = (
            self.dry_run_plan_sha()
        )

        relation = HostRange.objects.create(
            phage=phage,
            bacteria=bacteria,
            is_isolation_host=True,
            efficiency_eop=0.25,
            plaque_morphology=(
                "plaque_images/legacy.png"
            ),
            notes="Legacy infection",
        )

        sha_with_relation = (
            self.dry_run_plan_sha()
        )

        self.assertNotEqual(
            sha_without_relation,
            sha_with_relation,
        )

        relation.notes = (
            "Legacy infection updated"
        )

        relation.save(
            update_fields=[
                "notes",
            ]
        )

        sha_with_metadata_change = (
            self.dry_run_plan_sha()
        )

        self.assertNotEqual(
            sha_with_relation,
            sha_with_metadata_change,
        )

    def test_apply_materializes_hostrange_for_one_split_endpoint(
        self,
    ):
        bacteria = self.make_bacteria()

        phage = self.make_phage(
            aliquot_count=1
        )

        original = HostRange.objects.create(
            phage=phage,
            bacteria=bacteria,
            is_isolation_host=True,
            efficiency_eop=0.5,
            plaque_morphology=(
                "plaque_images/legacy.png"
            ),
            notes="One endpoint",
        )

        original_pk = original.pk

        call_command(
            "normalize_sample_aliquots",
            apply=True,
            expected_candidates=1,
            expected_plan_sha256=(
                self.dry_run_plan_sha()
            ),
            stdout=StringIO(),
        )

        pairs = set(
            HostRange.objects
            .values_list(
                "phage__sample_id",
                "bacteria__sample_id",
            )
        )

        self.assertEqual(
            pairs,
            {
                (
                    "LEGACY-PHA",
                    "LEGACY-BAC_1.1",
                ),
                (
                    "LEGACY-PHA",
                    "LEGACY-BAC_1.2",
                ),
            },
        )

        self.assertEqual(
            HostRange.objects.count(),
            2,
        )

        original.refresh_from_db()

        self.assertEqual(
            original.pk,
            original_pk,
        )

        self.assertEqual(
            original.phage.sample_id,
            "LEGACY-PHA",
        )

        self.assertEqual(
            original.bacteria.sample_id,
            "LEGACY-BAC_1.1",
        )

        for relation in (
            HostRange.objects.all()
        ):
            self.assertTrue(
                relation.is_isolation_host
            )

            self.assertEqual(
                relation.efficiency_eop,
                0.5,
            )

            self.assertEqual(
                relation.plaque_morphology.name,
                "plaque_images/legacy.png",
            )

            self.assertEqual(
                relation.notes,
                "One endpoint",
            )

    def test_apply_materializes_cartesian_hostrange_when_both_split(
        self,
    ):
        bacteria = self.make_bacteria()
        phage = self.make_phage()

        original = HostRange.objects.create(
            phage=phage,
            bacteria=bacteria,
            is_isolation_host=False,
            efficiency_eop=0.75,
            notes="Both endpoints",
        )

        original_pk = original.pk

        call_command(
            "normalize_sample_aliquots",
            apply=True,
            expected_candidates=2,
            expected_plan_sha256=(
                self.dry_run_plan_sha()
            ),
            stdout=StringIO(),
        )

        pairs = set(
            HostRange.objects
            .values_list(
                "phage__sample_id",
                "bacteria__sample_id",
            )
        )

        self.assertEqual(
            pairs,
            {
                (
                    "LEGACY-PHA_1.1",
                    "LEGACY-BAC_1.1",
                ),
                (
                    "LEGACY-PHA_1.1",
                    "LEGACY-BAC_1.2",
                ),
                (
                    "LEGACY-PHA_1.2",
                    "LEGACY-BAC_1.1",
                ),
                (
                    "LEGACY-PHA_1.2",
                    "LEGACY-BAC_1.2",
                ),
            },
        )

        self.assertEqual(
            HostRange.objects.count(),
            4,
        )

        original.refresh_from_db()

        self.assertEqual(
            original.pk,
            original_pk,
        )

        self.assertEqual(
            original.phage.sample_id,
            "LEGACY-PHA_1.1",
        )

        self.assertEqual(
            original.bacteria.sample_id,
            "LEGACY-BAC_1.1",
        )

        for relation in (
            HostRange.objects.all()
        ):
            self.assertFalse(
                relation.is_isolation_host
            )

            self.assertEqual(
                relation.efficiency_eop,
                0.75,
            )

            self.assertEqual(
                relation.notes,
                "Both endpoints",
            )

    def test_apply_requires_expected_candidate_count(self):
        source = self.make_bacteria()

        with self.assertRaisesRegex(
            CommandError,
            "expected-candidates",
        ):
            call_command(
                "normalize_sample_aliquots",
                apply=True,
                stdout=StringIO(),
            )

        source.refresh_from_db()

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC",
        )

        self.assertEqual(
            source.aliquot_count,
            2,
        )

    def test_apply_requires_expected_plan_sha256(self):
        source = self.make_bacteria()

        with self.assertRaisesRegex(
            CommandError,
            "expected-plan-sha256",
        ):
            call_command(
                "normalize_sample_aliquots",
                apply=True,
                expected_candidates=1,
                stdout=StringIO(),
            )

        source.refresh_from_db()

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC",
        )

        self.assertEqual(
            source.aliquot_count,
            2,
        )

    def test_plan_sha256_mismatch_blocks_apply(self):
        source = self.make_bacteria()

        with self.assertRaisesRegex(
            CommandError,
            "Expected plan SHA256",
        ):
            call_command(
                "normalize_sample_aliquots",
                apply=True,
                expected_candidates=1,
                expected_plan_sha256=(
                    "0" * 64
                ),
                stdout=StringIO(),
            )

        source.refresh_from_db()

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC",
        )

        self.assertEqual(
            source.aliquot_count,
            2,
        )

    def test_expected_candidate_mismatch_blocks_apply(self):
        source = self.make_bacteria()

        with self.assertRaisesRegex(
            CommandError,
            "Expected 2 candidate",
        ):
            call_command(
                "normalize_sample_aliquots",
                apply=True,
                expected_candidates=2,
                expected_plan_sha256=(
                    "0" * 64
                ),
                stdout=StringIO(),
            )

        source.refresh_from_db()

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC",
        )

        self.assertEqual(
            source.aliquot_count,
            2,
        )

    def test_target_collision_aborts_without_partial_write(self):
        source = self.make_bacteria()

        collision = Sample.objects.create(
            sample_id="LEGACY-BAC_1.2",
            sample_type="Other",
            organism_name="Collision",
            owner=self.owner,
            aliquot_count=1,
        )

        with self.assertRaisesRegex(
            CommandError,
            "collision",
        ):
            call_command(
                "normalize_sample_aliquots",
                apply=True,
                expected_candidates=1,
                expected_plan_sha256=(
                    "0" * 64
                ),
                stdout=StringIO(),
            )

        source.refresh_from_db()
        collision.refresh_from_db()

        self.assertEqual(
            source.sample_id,
            "LEGACY-BAC",
        )

        self.assertEqual(
            source.aliquot_count,
            2,
        )

        self.assertEqual(
            collision.sample_id,
            "LEGACY-BAC_1.2",
        )

        self.assertFalse(
            Sample.objects.filter(
                sample_id="LEGACY-BAC_1.1",
            ).exists()
        )
