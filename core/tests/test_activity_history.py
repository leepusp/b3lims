from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.activity import ActivityLog
from core.models.lab_tools.notebook import MolecularSequence, NotebookEntry
from core.services import activity


class ActivityHistoryTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.boss = User.objects.create_user("boss", password="x", is_superuser=True)

    def test_creating_an_entry_and_a_record_is_logged_with_entity_and_actor(self):
        entry = NotebookEntry.objects.create(title="Gel run", author=self.ana)
        MolecularSequence.objects.create(
            name="pUC19", sequence_type="plasmid", topology="circular", sequence="ATGC", owner=self.ana
        )

        rows = {r.entity_type: r for r in ActivityLog.objects.all()}

        self.assertEqual(rows["eln_entry"].verb, "created")
        self.assertEqual(rows["eln_entry"].entity_label, "Gel run")
        self.assertEqual(rows["eln_entry"].actor, self.ana)
        self.assertEqual(rows["eln_entry"].entity_id, entry.pk)
        self.assertIn("molecular_plasmid", rows)
        self.assertTrue(rows["molecular_plasmid"].url.endswith(f"/{rows['molecular_plasmid'].entity_id}/"))

    def test_repeated_updates_fold_into_one_row_and_delete_is_logged(self):
        entry = NotebookEntry.objects.create(title="Notes", author=self.ana)

        for i in range(4):
            entry.content = f"v{i}"
            entry.save()

        updates = ActivityLog.objects.filter(verb="updated", entity_id=entry.pk)

        self.assertEqual(updates.count(), 1)
        self.assertEqual(updates.get().count, 4)

        entry.delete()

        gone = ActivityLog.objects.get(verb="deleted", entity_type="eln_entry")

        self.assertEqual(gone.entity_label, "Notes")
        self.assertEqual(gone.url, "")

    def test_current_user_wins_over_the_record_owner(self):
        activity.set_current_user(self.boss)
        try:
            NotebookEntry.objects.create(title="By admin", author=self.ana)
        finally:
            activity.set_current_user(None)

        self.assertEqual(ActivityLog.objects.get().actor, self.boss)

    def test_people_see_their_own_history_and_superusers_see_everything(self):
        NotebookEntry.objects.create(title="Ana entry", author=self.ana)
        NotebookEntry.objects.create(title="Bia entry", author=self.bia)

        self.client.force_login(self.ana)
        mine = self.client.get(reverse("activity_history"))

        self.assertContains(mine, "Ana entry")
        self.assertNotContains(mine, "Bia entry")

        self.client.force_login(self.boss)
        everything = self.client.get(reverse("activity_history"))

        self.assertContains(everything, "Ana entry")
        self.assertContains(everything, "Bia entry")

    def test_filters_by_entity_text_action_and_person(self):
        NotebookEntry.objects.create(title="Alpha", author=self.ana)
        MolecularSequence.objects.create(
            name="Beta", sequence_type="dna", topology="linear", sequence="ATGC", owner=self.bia
        )
        self.client.force_login(self.boss)
        url = reverse("activity_history")

        by_entity = self.client.get(url, {"entity": "molecular_dna"})
        self.assertContains(by_entity, "Beta")
        self.assertNotContains(by_entity, "Alpha")

        by_text = self.client.get(url, {"q": "alp"})
        self.assertContains(by_text, "Alpha")
        self.assertNotContains(by_text, "Beta")

        by_actor = self.client.get(url, {"actor": self.bia.pk})
        self.assertContains(by_actor, "Beta")
        self.assertNotContains(by_actor, "Alpha")

        self.assertNotContains(self.client.get(url, {"verb": "deleted"}), "Alpha")

    def test_csv_export_and_calendar_link(self):
        NotebookEntry.objects.create(title="Csv entry", author=self.ana)
        self.client.force_login(self.ana)

        csv_response = self.client.get(reverse("activity_history"), {"format": "csv"})

        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn("Csv entry", csv_response.content.decode())
        self.assertContains(self.client.get(reverse("lab_calendar")), reverse("activity_history"))

    def test_history_requires_login(self):
        self.assertEqual(self.client.get(reverse("activity_history")).status_code, 302)
