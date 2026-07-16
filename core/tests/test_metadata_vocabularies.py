from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Keyword, KeywordValue, Sample, Tag
from core.services.metadata_vocabularies import (
    active_tags_from_ids,
    get_or_create_active_keyword_value,
    get_or_create_active_tag,
)


def request_path(name, args=None):
    """Return a test-client path without the production Apache prefix."""
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class MetadataVocabularyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.admin = user_model.objects.create_superuser(
            username="metadata-admin",
            email="metadata-admin@example.test",
            password="test-password",
        )
        self.user = user_model.objects.create_user(
            username="metadata-user",
            password="test-password",
        )
        self.sample = Sample.objects.create(
            sample_id="METADATA-TEST-001",
            owner=self.user,
        )

    def test_services_normalize_and_reuse_case_insensitive_entries(self):
        tag, tag_created = get_or_create_active_tag(
            "  Clinical   Review  ",
            description="Validated metadata",
        )
        same_tag, same_tag_created = get_or_create_active_tag(
            "clinical review",
        )

        self.assertTrue(tag_created)
        self.assertFalse(same_tag_created)
        self.assertEqual(tag.name, "Clinical Review")
        self.assertEqual(same_tag.pk, tag.pk)
        self.assertEqual(Tag.objects.count(), 1)

        value, value_created = get_or_create_active_keyword_value(
            "  Organism  ",
            "  Leptospira   interrogans  ",
        )
        same_value, same_value_created = (
            get_or_create_active_keyword_value(
                "organism",
                "leptospira interrogans",
            )
        )

        self.assertTrue(value_created)
        self.assertFalse(same_value_created)
        self.assertEqual(value.keyword.name, "Organism")
        self.assertEqual(value.value, "Leptospira interrogans")
        self.assertEqual(same_value.pk, value.pk)
        self.assertEqual(Keyword.objects.count(), 1)
        self.assertEqual(KeywordValue.objects.count(), 1)

    def test_services_reject_inactive_entries(self):
        tag = Tag.objects.create(name="Archived Tag")
        tag.is_active = False
        tag.save(update_fields=["is_active"])

        with self.assertRaisesMessage(ValidationError, "inactive"):
            get_or_create_active_tag("archived tag")

        value, _ = get_or_create_active_keyword_value(
            "Status",
            "Archived",
        )
        value.is_active = False
        value.save(update_fields=["is_active"])

        with self.assertRaisesMessage(ValidationError, "inactive"):
            get_or_create_active_keyword_value(
                "status",
                "archived",
            )

    def test_active_tags_from_ids_excludes_inactive_tags(self):
        active = Tag.objects.create(name="Active Tag")
        inactive = Tag.objects.create(
            name="Inactive Tag",
            is_active=False,
        )

        selected_ids = set(
            active_tags_from_ids(
                [active.pk, inactive.pk],
            ).values_list("pk", flat=True)
        )

        self.assertEqual(selected_ids, {active.pk})

    def test_management_pages_require_superuser(self):
        self.client.force_login(self.user)

        self.assertEqual(
            self.client.get(request_path("tags_view")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(request_path("keywords_view")).status_code,
            403,
        )

        self.client.force_login(self.admin)

        tags_response = self.client.get(request_path("tags_view"))
        keywords_response = self.client.get(
            request_path("keywords_view")
        )

        self.assertEqual(tags_response.status_code, 200)
        self.assertEqual(keywords_response.status_code, 200)
        self.assertContains(tags_response, "Manage Tags")
        self.assertContains(keywords_response, "Manage Keywords")

    def test_ajax_tag_creation_requires_login_and_reuses_tag(self):
        ajax_path = request_path("ajax_add_tag")

        anonymous_response = self.client.post(
            ajax_path,
            {"name": "Clinical Review"},
        )
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn("/login/", anonymous_response.url)

        self.client.force_login(self.user)

        first_response = self.client.post(
            ajax_path,
            {"name": "  Clinical   Review  "},
        )
        second_response = self.client.post(
            ajax_path,
            {"name": "clinical review"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(Tag.objects.count(), 1)
        self.assertEqual(
            Tag.objects.get().name,
            "Clinical Review",
        )

    def test_tag_deactivation_preserves_sample_relationship(self):
        tag = Tag.objects.create(name="Preserved Tag")
        self.sample.tags.add(tag)

        self.client.force_login(self.admin)
        response = self.client.post(
            request_path("tag_deactivate"),
            {"id": tag.pk},
        )

        self.assertEqual(response.status_code, 302)

        tag.refresh_from_db()
        self.assertFalse(tag.is_active)
        self.assertTrue(Tag.objects.filter(pk=tag.pk).exists())
        self.assertTrue(
            self.sample.tags.filter(pk=tag.pk).exists()
        )

    def test_keyword_deactivation_preserves_values_and_relationships(self):
        value, _ = get_or_create_active_keyword_value(
            "Organism",
            "Leptospira interrogans",
        )
        keyword = value.keyword
        self.sample.keywords.add(value)

        self.client.force_login(self.admin)
        response = self.client.post(
            request_path("keyword_deactivate"),
            {"id": keyword.pk},
        )

        self.assertEqual(response.status_code, 302)

        keyword.refresh_from_db()
        value.refresh_from_db()

        self.assertFalse(keyword.is_active)
        self.assertTrue(
            KeywordValue.objects.filter(pk=value.pk).exists()
        )
        self.assertTrue(
            self.sample.keywords.filter(pk=value.pk).exists()
        )

    def test_keyword_value_deactivation_preserves_relationship(self):
        value, _ = get_or_create_active_keyword_value(
            "Sample Source",
            "Environmental",
        )
        self.sample.keywords.add(value)

        self.client.force_login(self.admin)
        response = self.client.post(
            request_path("keyword_value_deactivate"),
            {"id": value.pk},
        )

        self.assertEqual(response.status_code, 302)

        value.refresh_from_db()
        self.assertFalse(value.is_active)
        self.assertTrue(
            self.sample.keywords.filter(pk=value.pk).exists()
        )

    def test_mutating_routes_reject_get_requests(self):
        self.client.force_login(self.admin)

        route_names = [
            "tag_create",
            "tag_edit",
            "tag_deactivate",
            "keyword_create",
            "keyword_edit",
            "keyword_deactivate",
            "keyword_value_deactivate",
        ]

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(
                    request_path(route_name)
                )
                self.assertEqual(response.status_code, 405)
