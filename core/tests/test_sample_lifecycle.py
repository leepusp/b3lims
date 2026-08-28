from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models.biobanks.biobank import Biobank
from core.models.events.model import Event
from core.models.research_groups.model import ResearchGroup
from core.models.samples.sample import (
    Sample,
    SampleDeletionAudit,
)
from core.permissions.samples import (
    can_delete_sample,
    can_edit_sample,
    can_view_sample,
)
from core.services.sample_lifecycle import (
    move_sample_to_trash,
)


class SampleLifecycleTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="samplelifeowner",
            password="test-password",
        )

        self.member = user_model.objects.create_user(
            username="samplelifemember",
            password="test-password",
        )

        self.outsider = user_model.objects.create_user(
            username="samplelifeoutsider",
            password="test-password",
        )

        self.group = ResearchGroup.objects.create(
            name="Sample Lifecycle Group",
            coordinator=self.owner,
        )
        self.group.members.add(
            self.member
        )

        self.biobank = Biobank.objects.create(
            name="Lifecycle Biobank A",
            owner=self.owner,
            research_group=self.group,
            is_public=False,
            is_active=True,
        )

        self.biobank_2 = Biobank.objects.create(
            name="Lifecycle Biobank B",
            owner=self.owner,
            research_group=self.group,
            is_public=False,
            is_active=True,
        )

        self.sample = Sample.objects.create(
            sample_id="LIFE-2026-001",
            sample_type="Other",
            organism_name="Lifecycle sample",
            biosafety_level="NB-2",
            owner=self.owner,
            research_group=self.group,
            biobank=self.biobank,
            status="available",
            is_public=False,
            is_active=True,
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if (
            prefix
            and url.startswith(
                prefix
            )
        ):
            path = url[
                len(prefix):
            ]
            return path or "/"

        return url

    def create_payload(
        self,
        sample_id,
        **overrides,
    ):
        data = {
            "action": "add_sample",
            "sample_id": sample_id,
            "sample_type": "Other",
            "custom_organism_name": "Created test sample",
            "biosafety_level": "NB-2",
            "aliquot_count": "1",
            "owner": str(
                self.owner.pk
            ),
            "research_group": str(
                self.group.pk
            ),
            "storage_location": "",
            "scientific_notes": "",
            "collaborator": "",
        }
        data.update(
            overrides
        )
        return data

    def test_new_sample_lifecycle_defaults(self):
        self.assertEqual(
            self.sample.aliquot_count,
            1,
        )
        self.assertFalse(
            self.sample.is_embargoed
        )
        self.assertIsNone(
            self.sample.deactivated_at
        )
        self.assertIsNone(
            self.sample.deletion_requested_at
        )
        self.assertIsNone(
            self.sample.purge_after
        )

    def test_aliquot_count_rejects_zero(self):
        self.sample.aliquot_count = 0

        with self.assertRaises(
            ValidationError
        ):
            self.sample.full_clean()

    def test_embargo_overrides_public_access(self):
        self.sample.is_public = True
        self.sample.is_embargoed = True
        self.sample.save(
            update_fields=[
                "is_public",
                "is_embargoed",
            ]
        )

        self.assertTrue(
            can_view_sample(
                self.owner,
                self.sample,
            )
        )
        self.assertTrue(
            can_view_sample(
                self.member,
                self.sample,
            )
        )
        self.assertFalse(
            can_view_sample(
                self.outsider,
                self.sample,
            )
        )
        self.assertFalse(
            can_view_sample(
                AnonymousUser(),
                self.sample,
            )
        )

        scan_url = reverse(
            "sample_qr_scan",
            args=[
                self.sample.uuid,
            ],
        )

        response = self.client.get(
            self.client_path(
                scan_url
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.is_embargoed = False
        self.sample.save(
            update_fields=[
                "is_embargoed",
            ]
        )

        self.assertTrue(
            can_view_sample(
                self.outsider,
                self.sample,
            )
        )

    def test_create_without_biobank_creates_one_sample(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_add"
                )
            ),
            self.create_payload(
                "LIFE-CREATE-NOBB",
                aliquot_count="2",
                is_embargoed="on",
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        created = Sample.objects.get(
            sample_id="LIFE-CREATE-NOBB"
        )

        self.assertIsNone(
            created.biobank_id
        )
        self.assertEqual(
            created.aliquot_count,
            2,
        )
        self.assertTrue(
            created.is_embargoed
        )
        self.assertEqual(
            created.research_group_id,
            self.group.pk,
        )
        self.assertEqual(
            created.owner_id,
            self.owner.pk,
        )

    def test_quantity_two_in_one_biobank_creates_one_record(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_add"
                )
            ),
            self.create_payload(
                "LIFE-CREATE-BB",
                **{
                    "dist_biobank_id[]": [
                        str(
                            self.biobank.pk
                        ),
                    ],
                    "dist_quantity[]": [
                        "2",
                    ],
                },
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        created = Sample.objects.filter(
            sample_id__startswith=(
                "LIFE-CREATE-BB"
            )
        )

        self.assertEqual(
            created.count(),
            1,
        )

        record = created.get()

        self.assertEqual(
            record.sample_id,
            "LIFE-CREATE-BB",
        )
        self.assertEqual(
            record.aliquot_count,
            2,
        )
        self.assertEqual(
            record.biobank_id,
            self.biobank.pk,
        )

    def test_multiple_biobanks_create_one_record_per_biobank(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_add"
                )
            ),
            self.create_payload(
                "LIFE-MULTIBB",
                **{
                    "dist_biobank_id[]": [
                        str(
                            self.biobank.pk
                        ),
                        str(
                            self.biobank_2.pk
                        ),
                    ],
                    "dist_quantity[]": [
                        "2",
                        "3",
                    ],
                },
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        records = list(
            Sample.objects
            .filter(
                sample_id__startswith=(
                    "LIFE-MULTIBB"
                )
            )
            .order_by(
                "sample_id"
            )
        )

        self.assertEqual(
            len(records),
            2,
        )

        self.assertEqual(
            [
                record.sample_id
                for record in records
            ],
            [
                "LIFE-MULTIBB_1",
                "LIFE-MULTIBB_2",
            ],
        )

        self.assertEqual(
            [
                record.aliquot_count
                for record in records
            ],
            [
                2,
                3,
            ],
        )

    def test_edit_exposes_and_persists_biosafety_and_aliquot_count(self):
        self.client.force_login(
            self.owner
        )

        edit_url = reverse(
            "sample_edit",
            args=[
                self.sample.pk,
            ],
        )

        response = self.client.get(
            self.client_path(
                edit_url
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        form = response.context[
            "form"
        ]

        self.assertIn(
            "biosafety_level",
            form.fields,
        )
        self.assertIn(
            "aliquot_count",
            form.fields,
        )
        self.assertEqual(
            form["biosafety_level"].value(),
            "NB-2",
        )
        self.assertEqual(
            form["aliquot_count"].value(),
            1,
        )

        response = self.client.post(
            self.client_path(
                edit_url
            ),
            {
                "sample_id": self.sample.sample_id,
                "sample_type": self.sample.sample_type,
                "organism_name": self.sample.organism_name,
                "biosafety_level": "NB-1",
                "status": "available",
                "aliquot_count": "2",
                "is_embargoed": "on",
                "owner": str(
                    self.owner.pk
                ),
                "research_group": str(
                    self.group.pk
                ),
                "biobank": str(
                    self.biobank.pk
                ),
                "collections": [],
                "storage_location": "",
                "scientific_notes": "Updated note",
                "collaborator": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.refresh_from_db()

        self.assertEqual(
            self.sample.biosafety_level,
            "NB-1",
        )
        self.assertEqual(
            self.sample.aliquot_count,
            2,
        )
        self.assertTrue(
            self.sample.is_embargoed
        )

    def test_group_member_can_deactivate_but_cannot_trash(self):
        self.assertTrue(
            can_edit_sample(
                self.member,
                self.sample,
            )
        )
        self.assertFalse(
            can_delete_sample(
                self.member,
                self.sample,
            )
        )

        self.client.force_login(
            self.member
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_deactivate",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.refresh_from_db()

        self.assertFalse(
            self.sample.is_active
        )
        self.assertIsNotNone(
            self.sample.deactivated_at
        )
        self.assertEqual(
            self.sample.deactivated_by_id,
            self.member.pk,
        )
        self.assertIsNone(
            self.sample.deletion_requested_at
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_move_to_trash",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_list_deactivate_action_redirects_to_lifecycle(self):
        self.client.force_login(
            self.member
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_deactivate",
                    args=[
                        self.sample.pk,
                    ],
                )
            ),
            {
                "next": "lifecycle",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            response.url,
            reverse(
                "samples_lifecycle"
            ),
        )

        self.sample.refresh_from_db()

        self.assertFalse(
            self.sample.is_active
        )

        self.assertIsNone(
            self.sample.deletion_requested_at
        )

        self.assertEqual(
            self.sample.deactivated_by_id,
            self.member.pk,
        )

    def test_sample_list_exposes_deactivate_action_to_group_editor(
        self,
    ):
        self.client.force_login(
            self.member
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "samples_list"
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Deactivate Sample",
        )

        self.assertContains(
            response,
            reverse(
                "sample_deactivate",
                args=[
                    self.sample.pk,
                ],
            ),
        )

        self.assertContains(
            response,
            'name="next"',
            html=False,
        )

        self.assertContains(
            response,
            'value="lifecycle"',
            html=False,
        )


    def test_owner_can_trash_and_restore_sample(self):
        self.client.force_login(
            self.owner
        )

        before = timezone.now()

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_move_to_trash",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.refresh_from_db()

        self.assertFalse(
            self.sample.is_active
        )
        self.assertIsNotNone(
            self.sample.deletion_requested_at
        )
        self.assertEqual(
            self.sample.deletion_requested_by_id,
            self.owner.pk,
        )
        self.assertIsNotNone(
            self.sample.purge_after
        )

        self.assertGreaterEqual(
            self.sample.purge_after,
            before
            + timedelta(
                days=29,
                hours=23,
            ),
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_restore",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.refresh_from_db()

        self.assertTrue(
            self.sample.is_active
        )
        self.assertIsNone(
            self.sample.deletion_requested_at
        )
        self.assertIsNone(
            self.sample.deletion_requested_by_id
        )
        self.assertIsNone(
            self.sample.purge_after
        )

    def test_purge_is_blocked_before_retention_deadline(self):
        move_sample_to_trash(
            self.sample,
            self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_purge",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            Sample.objects.filter(
                pk=self.sample.pk
            ).exists()
        )
        self.assertFalse(
            SampleDeletionAudit.objects.filter(
                original_sample_pk=self.sample.pk
            ).exists()
        )

    def test_due_purge_preserves_independent_audit_snapshot(self):
        Event.objects.create(
            sample=self.sample,
            performed_by=self.owner,
            event_type="entry",
            notes="Pre-purge audit event.",
        )

        move_sample_to_trash(
            self.sample,
            self.owner,
        )

        sample_pk = self.sample.pk
        sample_id = self.sample.sample_id

        Sample.objects.filter(
            pk=sample_pk
        ).update(
            purge_after=(
                timezone.now()
                - timedelta(
                    seconds=1
                )
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_purge",
                    args=[
                        sample_pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            Sample.objects.filter(
                pk=sample_pk
            ).exists()
        )

        audit = SampleDeletionAudit.objects.get(
            original_sample_pk=sample_pk
        )

        self.assertEqual(
            audit.original_sample_id,
            sample_id,
        )

        self.assertGreaterEqual(
            len(
                audit.snapshot.get(
                    "events",
                    [],
                )
            ),
            2,
        )

        self.assertEqual(
            audit.storage_cleanup_errors,
            [],
        )
