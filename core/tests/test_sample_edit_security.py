from django.contrib.auth import get_user_model
from django.forms import CheckboxInput
from django.test import (
    RequestFactory,
    TestCase,
)

from core.forms import SampleForm
from core.models import (
    Collection,
    ResearchGroup,
    Sample,
    SampleRelationship,
)
from core.permissions.samples import (
    can_edit_sample,
    can_manage_sample_sharing,
)
from core.services.sample_sharing import (
    grant_sample_access,
)
from core.views.internal.samples.views import (
    _sync_sample_edit_relationships,
)


User = get_user_model()


class SampleEditSecurityTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="sample-security-owner",
        )

        cls.editor = User.objects.create_user(
            username="sample-security-editor",
        )

        cls.member = User.objects.create_user(
            username="sample-security-member",
        )

        cls.other_owner = User.objects.create_user(
            username="sample-security-other-owner",
        )

        cls.group = ResearchGroup.objects.create(
            name="Sample Edit Security Group",
            coordinator=cls.owner,
        )

        cls.group.members.add(
            cls.member
        )

    def sample(
        self,
        sample_id,
        *,
        owner=None,
        sample_type="Other",
        research_group=None,
        is_public=False,
        is_embargoed=False,
    ):
        return Sample.objects.create(
            sample_id=sample_id,
            sample_type=sample_type,
            organism_name=sample_id,
            owner=owner or self.owner,
            research_group=research_group,
            status="available",
            aliquot_count=1,
            is_active=True,
            is_public=is_public,
            is_embargoed=is_embargoed,
        )

    def grant_edit(
        self,
        sample,
        user=None,
    ):
        user = user or self.editor

        grant_sample_access(
            sample=sample,
            user=user,
            access_level="edit",
            granted_by=self.owner,
        )

    def form_data(
        self,
        sample,
        user,
    ):
        form = SampleForm(
            instance=sample,
            user=user,
        )

        data = {}

        for name, field in form.fields.items():
            if field.disabled:
                continue

            value = form[
                name
            ].value()

            if isinstance(
                field.widget,
                CheckboxInput,
            ):
                if value:
                    data[name] = "on"

                continue

            if isinstance(
                value,
                (
                    list,
                    tuple,
                ),
            ):
                data[name] = [
                    str(item)
                    for item in value
                    if item not in (
                        None,
                        "",
                    )
                ]

            elif value is None:
                data[name] = ""

            else:
                data[name] = str(
                    value
                )

        return data

    def test_existing_identity_fields_are_server_side_disabled(
        self,
    ):
        sample = self.sample(
            "SEC-ID-LOCK"
        )

        self.grant_edit(
            sample
        )

        form = SampleForm(
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            form.fields[
                "sample_id"
            ].disabled
        )

        self.assertTrue(
            form.fields[
                "sample_type"
            ].disabled
        )

        self.assertTrue(
            form.fields[
                "owner"
            ].disabled
        )

    def test_crafted_post_cannot_change_sample_id_or_sample_type(
        self,
    ):
        sample = self.sample(
            "SEC-ID-TAMPER",
            sample_type="Other",
        )

        self.grant_edit(
            sample
        )

        data = self.form_data(
            sample,
            self.editor,
        )

        data[
            "sample_id"
        ] = "SEC-ID-TAMPERED"

        data[
            "sample_type"
        ] = "Bacterium"

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertEqual(
            sample.sample_id,
            "SEC-ID-TAMPER",
        )

        self.assertEqual(
            sample.sample_type,
            "Other",
        )

    def test_direct_edit_grantee_cannot_change_visibility_or_embargo(
        self,
    ):
        sample = self.sample(
            "SEC-VIS-EDIT",
            is_public=False,
            is_embargoed=True,
        )

        self.grant_edit(
            sample
        )

        self.assertTrue(
            can_edit_sample(
                self.editor,
                sample,
            )
        )

        self.assertFalse(
            can_manage_sample_sharing(
                self.editor,
                sample,
            )
        )

        probe = SampleForm(
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            probe.fields[
                "is_public"
            ].disabled
        )

        self.assertTrue(
            probe.fields[
                "is_embargoed"
            ].disabled
        )

        data = self.form_data(
            sample,
            self.editor,
        )

        data[
            "is_public"
        ] = "on"

        data.pop(
            "is_embargoed",
            None,
        )

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertFalse(
            sample.is_public
        )

        self.assertTrue(
            sample.is_embargoed
        )

    def test_group_member_cannot_change_visibility_or_embargo(
        self,
    ):
        sample = self.sample(
            "SEC-VIS-GROUP",
            research_group=self.group,
            is_public=False,
            is_embargoed=True,
        )

        self.assertTrue(
            can_edit_sample(
                self.member,
                sample,
            )
        )

        self.assertFalse(
            can_manage_sample_sharing(
                self.member,
                sample,
            )
        )

        data = self.form_data(
            sample,
            self.member,
        )

        data[
            "is_public"
        ] = "on"

        data.pop(
            "is_embargoed",
            None,
        )

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.member,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertFalse(
            sample.is_public
        )

        self.assertTrue(
            sample.is_embargoed
        )

    def test_owner_can_change_visibility_and_embargo(
        self,
    ):
        sample = self.sample(
            "SEC-VIS-OWNER",
            is_public=False,
            is_embargoed=True,
        )

        self.assertTrue(
            can_manage_sample_sharing(
                self.owner,
                sample,
            )
        )

        probe = SampleForm(
            instance=sample,
            user=self.owner,
        )

        self.assertFalse(
            probe.fields[
                "is_public"
            ].disabled
        )

        self.assertFalse(
            probe.fields[
                "is_embargoed"
            ].disabled
        )

        data = self.form_data(
            sample,
            self.owner,
        )

        data[
            "is_public"
        ] = "on"

        data.pop(
            "is_embargoed",
            None,
        )

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.owner,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertTrue(
            sample.is_public
        )

        self.assertFalse(
            sample.is_embargoed
        )

    def test_hidden_relationship_target_cannot_be_linked(
        self,
    ):
        source = self.sample(
            "SEC-REL-SOURCE",
            sample_type="Bacterium",
        )

        hidden_target = self.sample(
            "SEC-REL-HIDDEN",
            owner=self.other_owner,
            sample_type="Plasmid",
        )

        self.grant_edit(
            source
        )

        request = RequestFactory().post(
            "/",
            {
                "stored_plasmids[]": [
                    hidden_target.sample_id,
                ],
            },
        )

        _sync_sample_edit_relationships(
            base_sample=source,
            request=request,
            user=self.editor,
        )

        self.assertFalse(
            SampleRelationship.objects.filter(
                source_sample=source,
                target_sample=hidden_target,
                relationship_type="STORAGE",
            ).exists()
        )

    def test_visible_relationship_target_can_still_be_linked(
        self,
    ):
        source = self.sample(
            "SEC-REL-VISIBLE-SOURCE",
            sample_type="Bacterium",
        )

        visible_target = self.sample(
            "SEC-REL-VISIBLE-TARGET",
            owner=self.editor,
            sample_type="Plasmid",
        )

        self.grant_edit(
            source
        )

        request = RequestFactory().post(
            "/",
            {
                "stored_plasmids[]": [
                    visible_target.sample_id,
                ],
            },
        )

        _sync_sample_edit_relationships(
            base_sample=source,
            request=request,
            user=self.editor,
        )

        self.assertTrue(
            SampleRelationship.objects.filter(
                source_sample=source,
                target_sample=visible_target,
                relationship_type="STORAGE",
            ).exists()
        )

    def test_noneditable_current_collection_cannot_be_detached(
        self,
    ):
        collection = Collection.objects.create(
            name="Protected Sample Collection",
            description="Security test",
            owner=self.other_owner,
            is_public=False,
            is_active=True,
        )

        sample = self.sample(
            "SEC-COL-PROTECTED"
        )

        sample.collections.add(
            collection
        )

        self.grant_edit(
            sample
        )

        probe = SampleForm(
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            probe.fields[
                "collections"
            ].queryset.filter(
                pk=collection.pk,
            ).exists()
        )

        data = self.form_data(
            sample,
            self.editor,
        )

        data[
            "collections"
        ] = []

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.editor,
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "collections",
            form.errors,
        )

        sample.refresh_from_db()

        self.assertTrue(
            sample.collections.filter(
                pk=collection.pk,
            ).exists()
        )

    def test_editable_current_collection_can_be_detached(
        self,
    ):
        collection = Collection.objects.create(
            name="Editable Sample Collection",
            description="Security positive control",
            owner=self.editor,
            is_public=False,
            is_active=True,
        )

        sample = self.sample(
            "SEC-COL-EDITABLE"
        )

        sample.collections.add(
            collection
        )

        self.grant_edit(
            sample
        )

        data = self.form_data(
            sample,
            self.editor,
        )

        data[
            "collections"
        ] = []

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertFalse(
            sample.collections.filter(
                pk=collection.pk,
            ).exists()
        )

    def test_protected_collection_can_be_preserved_while_metadata_changes(
        self,
    ):
        collection = Collection.objects.create(
            name="Preserved Sample Collection",
            description="Security preservation control",
            owner=self.other_owner,
            is_public=False,
            is_active=True,
        )

        sample = self.sample(
            "SEC-COL-PRESERVE"
        )

        sample.collections.add(
            collection
        )

        self.grant_edit(
            sample
        )

        data = self.form_data(
            sample,
            self.editor,
        )

        data[
            "notes"
        ] = "Allowed metadata update."

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.editor,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertEqual(
            sample.notes,
            "Allowed metadata update.",
        )

        self.assertTrue(
            sample.collections.filter(
                pk=collection.pk,
            ).exists()
        )
