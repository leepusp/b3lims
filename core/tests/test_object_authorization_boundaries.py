import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Biobank,
    BiobankUserRole,
    Chemical,
    Sample,
    SampleImportBatch,
    SampleIntakeRecord,
    SampleRelationship,
)
from core.models.lab_tools.notebook import (
    NotebookChemicalLink,
    NotebookEntry,
)


class ObjectAuthorizationBoundaryTests(
    TestCase
):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="authz-actor",
        )
        self.owner = User.objects.create_user(
            username="authz-owner",
        )
        self.collaborator = User.objects.create_user(
            username="authz-collaborator",
        )

        self.client.force_login(
            self.actor
        )

    def _sample_create_payload(
        self,
        *,
        sample_id,
        intake_record,
    ):
        return {
            "action": "add_sample",
            "sample_id": sample_id,
            "sample_type": "Other",
            "custom_organism_name": (
                "Authorization test sample"
            ),
            "owner": str(
                self.actor.pk
            ),
            "aliquot_count": "1",
            "intake_record_id": str(
                intake_record.pk
            ),
        }

    def test_biobank_role_update_is_scoped_to_current_biobank(
        self,
    ):
        local_biobank = Biobank.objects.create(
            name="Local authorization Biobank",
            owner=self.actor,
        )
        foreign_biobank = Biobank.objects.create(
            name="Foreign authorization Biobank",
            owner=self.owner,
        )

        foreign_role = (
            BiobankUserRole.objects.create(
                user=self.collaborator,
                biobank=foreign_biobank,
                role=BiobankUserRole.VIEWER,
            )
        )

        response = self.client.post(
            reverse(
                "biobank_members",
                args=[
                    local_biobank.pk
                ],
            ),
            {
                "action": "update_role",
                "role_id": str(
                    foreign_role.pk
                ),
                "role": BiobankUserRole.EDITOR,
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        foreign_role.refresh_from_db()

        self.assertEqual(
            foreign_role.role,
            BiobankUserRole.VIEWER,
        )

    def test_biobank_role_update_still_allows_local_role(
        self,
    ):
        biobank = Biobank.objects.create(
            name="Managed authorization Biobank",
            owner=self.actor,
        )

        role = BiobankUserRole.objects.create(
            user=self.collaborator,
            biobank=biobank,
            role=BiobankUserRole.VIEWER,
        )

        response = self.client.post(
            reverse(
                "biobank_members",
                args=[
                    biobank.pk
                ],
            ),
            {
                "action": "update_role",
                "role_id": str(
                    role.pk
                ),
                "role": BiobankUserRole.EDITOR,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        role.refresh_from_db()

        self.assertEqual(
            role.role,
            BiobankUserRole.EDITOR,
        )

    def test_notebook_context_excludes_hidden_chemical(
        self,
    ):
        entry = NotebookEntry.objects.create(
            title="Authorization ELN",
            author=self.actor,
            visibility="private",
        )

        hidden = Chemical.objects.create(
            name="Hidden authorization reagent",
            quantity="1 g",
            created_by=self.owner,
            is_public=False,
        )

        visible = Chemical.objects.create(
            name="Visible authorization reagent",
            quantity="1 g",
            created_by=self.owner,
            is_public=True,
        )

        response = self.client.get(
            reverse(
                "notebook_index"
            ),
            {
                "entry_id": entry.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        protocol_chemicals = list(
            response.context[
                "protocol_chemicals"
            ]
        )

        self.assertNotIn(
            hidden,
            protocol_chemicals,
        )
        self.assertIn(
            visible,
            protocol_chemicals,
        )

    def test_notebook_search_excludes_hidden_chemical(
        self,
    ):
        hidden = Chemical.objects.create(
            name="Hidden search authorization reagent",
            quantity="1 g",
            created_by=self.owner,
            is_public=False,
        )

        response = self.client.get(
            reverse(
                "search_chemicals_api"
            ),
            {
                "q": (
                    "Hidden search authorization"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        returned_ids = {
            row["id"]
            for row in response.json()[
                "results"
            ]
        }

        self.assertNotIn(
            hidden.pk,
            returned_ids,
        )

    def test_notebook_cannot_link_hidden_chemical(
        self,
    ):
        entry = NotebookEntry.objects.create(
            title="Authorization link ELN",
            author=self.actor,
            visibility="private",
        )

        hidden = Chemical.objects.create(
            name="Hidden link authorization reagent",
            quantity="1 g",
            created_by=self.owner,
            is_public=False,
        )

        response = self.client.post(
            reverse(
                "notebook_link_chemical_api",
                args=[
                    entry.pk
                ],
            ),
            data=json.dumps(
                {
                    "chemical_id": hidden.pk,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.assertFalse(
            NotebookChemicalLink.objects.filter(
                entry=entry,
                chemical=hidden,
            ).exists()
        )

    def test_notebook_can_link_visible_chemical(
        self,
    ):
        entry = NotebookEntry.objects.create(
            title="Visible chemical ELN",
            author=self.actor,
            visibility="private",
        )

        visible = Chemical.objects.create(
            name="Visible link authorization reagent",
            quantity="1 g",
            created_by=self.owner,
            is_public=True,
        )

        response = self.client.post(
            reverse(
                "notebook_link_chemical_api",
                args=[
                    entry.pk
                ],
            ),
            data=json.dumps(
                {
                    "chemical_id": visible.pk,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            NotebookChemicalLink.objects.filter(
                entry=entry,
                chemical=visible,
            ).exists()
        )

    def test_sample_relationship_rejects_hidden_target(
        self,
    ):
        current = Sample.objects.create(
            sample_id="AUTHZ-REL-CURRENT",
            owner=self.actor,
            is_public=False,
        )

        hidden_target = Sample.objects.create(
            sample_id="AUTHZ-REL-HIDDEN",
            owner=self.owner,
            is_public=False,
        )

        response = self.client.post(
            reverse(
                "sample_relate",
                args=[
                    current.pk
                ],
            ),
            {
                "target_ids": str(
                    hidden_target.pk
                ),
                "relationship_type": "other",
                "direction": "out",
                "notes": (
                    "Authorization regression test"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            SampleRelationship.objects.filter(
                source_sample=current,
                target_sample=hidden_target,
            ).exists()
        )

    def test_sample_relationship_allows_visible_target(
        self,
    ):
        current = Sample.objects.create(
            sample_id="AUTHZ-REL-OWNER",
            owner=self.actor,
            is_public=False,
        )

        visible_target = Sample.objects.create(
            sample_id="AUTHZ-REL-PUBLIC",
            owner=self.owner,
            is_public=True,
        )

        response = self.client.post(
            reverse(
                "sample_relate",
                args=[
                    current.pk
                ],
            ),
            {
                "target_ids": str(
                    visible_target.pk
                ),
                "relationship_type": "other",
                "direction": "out",
                "notes": (
                    "Authorization positive control"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            SampleRelationship.objects.filter(
                source_sample=current,
                target_sample=visible_target,
                relationship_type="other",
            ).exists()
        )

    def test_foreign_intake_record_cannot_be_consumed(
        self,
    ):
        batch = SampleImportBatch.objects.create(
            uploaded_by=self.owner,
            original_file=(
                "sample_imports/"
                "foreign-authz.tsv"
            ),
            original_filename=(
                "foreign-authz.tsv"
            ),
        )

        intake = SampleIntakeRecord.objects.create(
            batch=batch,
            row_number=1,
        )

        response = self.client.post(
            reverse(
                "sample_add"
            ),
            self._sample_create_payload(
                sample_id=(
                    "AUTHZ-FOREIGN-INTAKE"
                ),
                intake_record=intake,
            ),
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.assertFalse(
            Sample.objects.filter(
                sample_id=(
                    "AUTHZ-FOREIGN-INTAKE"
                )
            ).exists()
        )

        intake.refresh_from_db()

        self.assertIsNone(
            intake.sample_id
        )
        self.assertEqual(
            intake.status,
            "waiting_review",
        )

    def test_own_intake_record_can_be_consumed(
        self,
    ):
        batch = SampleImportBatch.objects.create(
            uploaded_by=self.actor,
            original_file=(
                "sample_imports/"
                "own-authz.tsv"
            ),
            original_filename=(
                "own-authz.tsv"
            ),
        )

        intake = SampleIntakeRecord.objects.create(
            batch=batch,
            row_number=1,
        )

        response = self.client.post(
            reverse(
                "sample_add"
            ),
            self._sample_create_payload(
                sample_id=(
                    "AUTHZ-OWN-INTAKE"
                ),
                intake_record=intake,
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        sample = Sample.objects.get(
            sample_id="AUTHZ-OWN-INTAKE"
        )

        intake.refresh_from_db()

        self.assertEqual(
            intake.sample_id,
            sample.pk,
        )
        self.assertEqual(
            intake.status,
            "used_for_sample",
        )
