"""ELN tags/keywords use the biobank vocabulary; favourites; step groups."""

import importlib
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from core.models import Keyword, KeywordValue, Tag
from core.models.lab_tools.notebook import NotebookEntry
from core.models.lab_tools.notebook_composer import (
    NotebookFavoriteTag,
    NotebookStep,
    NotebookTag,
)
from core.services import notebook_composer as composer
from core.services import notebook_search, notebook_templates


class VocabularyBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="vocab-owner", password="x")
        cls.other = User.objects.create_user(username="vocab-other", password="x")
        cls.entry = NotebookEntry.objects.create(title="Gel", author=cls.owner)

    def setUp(self):
        self.client.force_login(self.owner)

    def post(self, name, payload, entry=None):
        return self.client.post(
            reverse(name, args=[(entry or self.entry).pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )


class SharedTagTests(VocabularyBase):
    def test_tags_land_in_the_biobank_vocabulary_and_reuse_existing_ones(self):
        existing = Tag.objects.create(name="BSL2")
        composer.update_header(self.entry, tags=["bsl2", "new-tag"])
        names = sorted(self.entry.shared_tags.values_list("name", flat=True))
        self.assertEqual(names, ["BSL2", "new-tag"])  # spelling of the existing tag wins
        self.assertEqual(Tag.objects.filter(name__iexact="bsl2").count(), 1)
        self.assertIn(existing, self.entry.shared_tags.all())
        self.assertEqual(NotebookTag.objects.count(), 0)  # legacy list untouched

    def test_inactive_tag_cannot_be_assigned(self):
        Tag.objects.create(name="retired", is_active=False)
        with self.assertRaises(ValidationError):
            composer.update_header(self.entry, tags=["retired"])

    def test_search_and_filters_see_shared_tags(self):
        composer.update_header(self.entry, tags=["PCR"])
        qs = NotebookEntry.objects.all()
        for query in ("tag:pcr", "tag:PCR", "pcr"):
            found = qs.filter(notebook_search.build_query(query, self.owner)[0]).distinct()
            self.assertEqual(list(found), [self.entry], query)
        self.assertFalse(qs.filter(notebook_search.build_query("tag:nope", self.owner)[0]).exists())


class KeywordTests(VocabularyBase):
    def test_keywords_use_keyword_values(self):
        composer.update_header(self.entry, keywords=["Organism: E. coli", "Strain=DH5a"])
        self.assertEqual(
            sorted(composer.keyword_labels(self.entry)),
            ["Organism: E. coli", "Strain: DH5a"],
        )
        self.assertTrue(Keyword.objects.filter(name="Organism").exists())
        self.assertTrue(KeywordValue.objects.filter(value="E. coli").exists())

    def test_keyword_needs_name_and_value(self):
        with self.assertRaises(ValidationError):
            composer.update_header(self.entry, keywords=["just-a-word"])

    def test_header_api_returns_keywords_in_state(self):
        response = self.post("notebook_header_api", {"keywords": ["Organism: E. coli"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["keywords"], ["Organism: E. coli"])
        self.post("notebook_header_api", {"keywords": []})
        self.assertEqual(composer.keyword_labels(self.entry), [])

    def test_search_by_keyword(self):
        composer.update_header(self.entry, keywords=["Organism: E. coli"])
        other = NotebookEntry.objects.create(title="Other", author=self.owner)
        composer.update_header(other, keywords=["Organism: Bacillus"])
        for query, expected in (("keyword:organism:coli", {self.entry.pk}), ("keyword:organism", {self.entry.pk, other.pk}), ("keyword:bacillus", {other.pk})):
            found = NotebookEntry.objects.filter(notebook_search.build_query(query, self.owner)[0]).distinct()
            self.assertEqual(set(found.values_list("pk", flat=True)), expected, query)


class FavouriteTagTests(VocabularyBase):
    def test_toggle_favourite_through_api(self):
        response = self.post("notebook_favorite_tags_api", {"tag": "pcr", "favorite": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["favorite_tags"], ["pcr"])
        self.assertTrue(Tag.objects.filter(name="pcr").exists())
        self.post("notebook_favorite_tags_api", {"tag": "PCR", "favorite": True})  # no duplicate
        self.assertEqual(NotebookFavoriteTag.objects.filter(user=self.owner).count(), 1)
        response = self.post("notebook_favorite_tags_api", {"tag": "pcr", "favorite": False})
        self.assertEqual(response.json()["state"]["favorite_tags"], [])

    def test_favourites_belong_to_the_user(self):
        composer.set_favorite_tag(self.owner, "mine")
        self.assertEqual(composer.favorite_tag_names(self.other), [])

    def test_limit_and_invalid_names(self):
        for i in range(composer.MAX_FAVORITE_TAGS):
            composer.set_favorite_tag(self.owner, f"t{i}")
        with self.assertRaises(ValidationError):
            composer.set_favorite_tag(self.owner, "one-too-many")
        with self.assertRaises(ValidationError):
            composer.set_favorite_tag(self.other, "bad tag<")

    def test_a_reader_can_star_a_tag_but_stranger_cannot_reach_the_entry(self):
        self.client.force_login(self.other)
        response = self.post("notebook_favorite_tags_api", {"tag": "x"})
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(composer.favorite_tag_names(self.other), [])


class StepGroupTests(VocabularyBase):
    def test_add_steps_with_groups_and_serialize(self):
        composer.add_step(self.entry, "Weigh agarose", group="Preparation")
        composer.add_step(self.entry, "Pour gel", group="Preparation")
        composer.add_step(self.entry, "Image gel")
        steps = composer.serialize_steps(self.entry)
        self.assertEqual([s["group"] for s in steps], ["Preparation", "Preparation", ""])

    def test_api_add_rename_and_complete_group(self):
        self.post("notebook_steps_api", {"action": "add", "body": "A", "group": "Prep"})
        self.post("notebook_steps_api", {"action": "add", "body": "B", "group": "Prep"})
        self.post("notebook_steps_api", {"action": "add", "body": "C"})
        self.post("notebook_steps_api", {"action": "complete_group", "group": "Prep", "finished": True})
        done = list(self.entry.steps.values_list("finished", flat=True))
        self.assertEqual(done, [True, True, False])
        self.post("notebook_steps_api", {"action": "rename_group", "group": "Prep", "new_name": "Setup"})
        self.assertEqual(set(self.entry.steps.values_list("group", flat=True)), {"Setup", ""})
        self.post("notebook_steps_api", {"action": "complete_group", "group": "Setup", "finished": False})
        self.assertFalse(self.entry.steps.filter(finished=True).exists())
        response = self.post("notebook_steps_api", {"action": "rename_group", "group": "Nope", "new_name": "x"})
        self.assertEqual(response.status_code, 400)

    def test_update_step_group(self):
        step = composer.add_step(self.entry, "A")
        composer.update_step(step, self.owner, group="Imaging")
        step.refresh_from_db()
        self.assertEqual(step.group, "Imaging")
        composer.update_step(step, self.owner, body="A2")  # group untouched
        step.refresh_from_db()
        self.assertEqual(step.group, "Imaging")

    def test_group_survives_template_round_trip_and_copy(self):
        composer.add_step(self.entry, "A", group="Prep")
        composer.add_step(self.entry, "B")
        template = notebook_templates.save_entry_as_template(
            entry=self.entry, user=self.owner, name="Gel run"
        )
        self.assertEqual(template.structure["steps"], [{"body": "A", "group": "Prep"}, "B"])
        new = notebook_templates.create_entry_from_template(user=self.owner, template=template)
        self.assertEqual(list(new.steps.values_list("body", "group")), [("A", "Prep"), ("B", "")])

    def test_group_length_limit(self):
        with self.assertRaises(ValidationError):
            composer.add_step(self.entry, "A", group="x" * 81)


class MigrationCopyTests(TestCase):
    def test_old_notebook_tags_move_to_the_vocabulary(self):
        user = get_user_model().objects.create_user(username="mig", password="x")
        entry = NotebookEntry.objects.create(title="Old", author=user)
        entry.tags.add(NotebookTag.objects.create(name="pcr"), NotebookTag.objects.create(name="western"))
        Tag.objects.create(name="PCR")
        migration = importlib.import_module("core.migrations.0100_notebook_favorite_tags_step_groups")
        migration.copy_notebook_tags(apps, None)
        migration.copy_notebook_tags(apps, None)  # idempotent
        self.assertEqual(sorted(entry.shared_tags.values_list("name", flat=True)), ["PCR", "western"])
        self.assertEqual(Tag.objects.filter(name__iexact="pcr").count(), 1)
