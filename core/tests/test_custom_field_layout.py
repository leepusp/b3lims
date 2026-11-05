"""Rename of the stored custom-field keys (expand phase)."""

import importlib

from django.test import SimpleTestCase, TestCase

from core.models import NotebookEntry, NotebookTemplate
from core.services import custom_field_layout as layout

FIELDS = {"Medium": {"type": "text", "value": "TSB", "position": 0}}
GROUPS = [{"id": 1, "name": "Culture"}]
OLD = {"extra_fields": FIELDS, "elabftw": {"extra_fields_groups": GROUPS}}
NEW = {"custom_fields": FIELDS, "custom_field_groups": GROUPS}


class ReadWriteTests(SimpleTestCase):
    def test_reads_new_keys(self):
        self.assertEqual(layout.fields_of(NEW), FIELDS)
        self.assertEqual(layout.groups_of(NEW), GROUPS)

    def test_falls_back_to_old_keys(self):
        self.assertEqual(layout.fields_of(OLD), FIELDS)
        self.assertEqual(layout.groups_of(OLD), GROUPS)

    def test_new_keys_win_when_both_exist(self):
        both = {**OLD, "custom_fields": {}, "custom_field_groups": []}
        self.assertEqual(layout.fields_of(both), {})
        self.assertEqual(layout.groups_of(both), [])

    def test_bad_shapes_read_as_empty(self):
        for data in (None, "x", [], {"custom_fields": 3, "extra_fields": "x"}):
            self.assertEqual(layout.fields_of(data), {})
            self.assertEqual(layout.groups_of(data), [])

    def test_write_stores_both_layouts_and_keeps_other_keys(self):
        result = layout.with_layout({"other": 1, "elabftw": {"keep": True}}, FIELDS, GROUPS)
        self.assertEqual(result["custom_fields"], FIELDS)
        self.assertEqual(result["extra_fields"], FIELDS)
        self.assertEqual(result["elabftw"], {"keep": True, "extra_fields_groups": GROUPS})
        self.assertEqual(result["other"], 1)

    def test_contract_mode_drops_old_keys(self):
        layout.WRITE_LEGACY_KEYS = False
        try:
            result = layout.with_layout(OLD, FIELDS, GROUPS)
        finally:
            layout.WRITE_LEGACY_KEYS = True
        self.assertEqual(result, NEW)

    def test_migrated_is_idempotent(self):
        once = layout.migrated(OLD)
        self.assertEqual(once["custom_fields"], FIELDS)
        self.assertIsNone(layout.migrated(once))
        self.assertIsNone(layout.migrated({"title": "no fields"}))

    def test_forced_prefers_old_keys(self):
        stale = {**OLD, "custom_fields": {}, "custom_field_groups": []}
        fixed = layout.migrated_forced(stale)
        self.assertEqual(fixed["custom_fields"], FIELDS)
        self.assertEqual(fixed["custom_field_groups"], GROUPS)


class MigrationTests(TestCase):
    def test_data_migration_copies_entries_and_templates(self):
        from django.contrib.auth import get_user_model
        from django.apps import apps as real_apps

        user = get_user_model().objects.create_user("mig", password="x")
        entry = NotebookEntry.objects.create(title="Old", author=user, metadata=OLD)
        plain = NotebookEntry.objects.create(title="Plain", author=user, metadata={})
        template = NotebookTemplate.objects.create(
            name="T", owner=user, structure={**OLD, "steps": ["a"]}
        )
        module = importlib.import_module("core.migrations.0101_custom_field_layout")
        module.copy_to_new_keys(real_apps, None)

        entry.refresh_from_db()
        template.refresh_from_db()
        plain.refresh_from_db()
        self.assertEqual(entry.metadata["custom_fields"], FIELDS)
        self.assertEqual(entry.metadata["extra_fields"], FIELDS)
        self.assertEqual(entry.metadata["custom_field_groups"], GROUPS)
        self.assertEqual(template.structure["custom_fields"], FIELDS)
        self.assertEqual(template.structure["steps"], ["a"])
        self.assertEqual(plain.metadata, {})

    def test_search_finds_rows_in_either_layout(self):
        from django.contrib.auth import get_user_model
        from core.services.notebook_search import build_query

        user = get_user_model().objects.create_user("srch", password="x")
        old_only = {"extra_fields": {"Medium": {"type": "text", "value": "TSB"}}}
        new_only = {"custom_fields": {"Medium": {"type": "text", "value": "TSB"}}}
        NotebookEntry.objects.create(title="old", author=user, metadata=old_only)
        NotebookEntry.objects.create(title="new", author=user, metadata=new_only)
        NotebookEntry.objects.create(title="none", author=user, metadata={})
        for text in ("extrafield:Medium:TSB", "extrafield:Medium:=TSB", "extrafield:Medium"):
            query, _ = build_query(text, user)
            titles = sorted(NotebookEntry.objects.filter(query).values_list("title", flat=True))
            self.assertEqual(titles, ["new", "old"], text)
