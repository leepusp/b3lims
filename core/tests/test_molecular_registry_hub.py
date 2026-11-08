from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import MolecularSequence
from core.services.molecular_registry_overview import (
    attach_registry_context,
    duplicate_groups,
    type_counts,
)


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularRegistryHubTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="hub-owner", password="test-password"
        )
        self.other = user_model.objects.create_user(
            username="hub-other", password="test-password"
        )

        def make(name, kind, sequence, owner=None, topology="linear"):
            return MolecularSequence.objects.create(
                name=name,
                sequence_type=kind,
                topology=topology,
                sequence=sequence,
                owner=owner or self.owner,
            )

        self.a = make("Plasmid A", "plasmid", "ATGCATGC", topology="circular")
        self.b = make("Plasmid B", "plasmid", "ATGCATGC", topology="circular")
        self.linear = make("Same bases, linear", "dna", "ATGCATGC")
        self.primer = make("Primer 1", "primer", "ATGCAAAC")
        self.hidden = make("Foreign", "dna", "GGGGCCCC", owner=self.other)

    def test_type_counts_cover_every_type(self):
        rows = type_counts(MolecularSequence.objects.all())
        labels = {value: count for value, _label, count in rows}

        self.assertEqual(labels["plasmid"], 2)
        self.assertEqual(labels["primer"], 1)
        self.assertEqual(labels["rna"], 0)
        self.assertEqual(
            [value for value, _l, _c in rows],
            [v for v, _l in MolecularSequence.SEQUENCE_TYPE_CHOICES],
        )

    def test_duplicates_need_same_checksum_and_topology(self):
        groups = duplicate_groups(MolecularSequence.objects.all())

        self.assertEqual(set(groups), {self.a.id, self.b.id})
        self.assertEqual(groups[self.a.id], [(self.b.id, "Plasmid B")])
        self.assertNotIn(self.linear.id, groups)

    def test_context_counts_and_duplicates_are_attached(self):
        records = list(MolecularSequence.objects.filter(owner=self.owner))
        attach_registry_context(self.owner, records, records)
        by_name = {m.name: m for m in records}

        self.assertEqual(by_name["Plasmid A"].registry_context["features"], 0)
        self.assertEqual(len(by_name["Plasmid A"].duplicates), 1)
        self.assertEqual(by_name["Primer 1"].duplicates, [])

    def test_page_shows_counts_and_duplicate_note(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("molecular_registry_index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mr-hub-card")
        self.assertContains(response, "with an identical sequence")
        self.assertEqual(response.context["registry_total"], 4)
        self.assertEqual(response.context["duplicate_total"], 2)

    def test_duplicates_survive_a_search_filter(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("molecular_registry_index"), {"q": "Plasmid A"}
        )
        record = response.context["molecules"][0]

        self.assertEqual(len(response.context["molecules"]), 1)
        self.assertEqual(record.duplicates, [(self.b.id, "Plasmid B")])

    def test_other_users_records_never_leak_into_counts_or_duplicates(self):
        MolecularSequence.objects.create(
            name="Foreign copy of A",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCATGC",
            owner=self.other,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("molecular_registry_index"))

        self.assertEqual(response.context["registry_total"], 4)
        self.assertNotContains(response, "Foreign copy of A")


@override_settings(FORCE_SCRIPT_NAME=None)
class MolecularInspectorContextTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="insp-owner", password="test-password"
        )
        self.a = MolecularSequence.objects.create(
            name="Insp A",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCATGC",
            owner=self.owner,
        )
        self.b = MolecularSequence.objects.create(
            name="Insp B",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCATGC",
            owner=self.owner,
        )

    def test_detail_page_has_inspector_and_context(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("molecular_sequence_detail", args=[self.a.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="mw-inspector"')
        self.assertContains(response, "molecular_inspector_calc.js")
        self.assertContains(response, 'class="mw-factbar"')
        self.assertNotContains(response, 'id="mw-inspector-context"')

        context = response.context["inspector_context"]

        self.assertEqual(
            context["duplicates"],
            [
                {
                    "id": self.b.id,
                    "name": "Insp B",
                    "url": reverse(
                        "molecular_sequence_detail", args=[self.b.id]
                    ),
                }
            ],
        )
        self.assertIsNone(context["sample"])

    def test_inspector_context_never_names_records_the_user_cannot_see(self):
        stranger = get_user_model().objects.create_user(
            username="insp-stranger", password="test-password"
        )
        MolecularSequence.objects.create(
            name="Hidden twin",
            sequence_type="plasmid",
            topology="circular",
            sequence="ATGCATGC",
            owner=stranger,
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("molecular_sequence_detail", args=[self.a.id])
        )

        self.assertNotContains(response, "Hidden twin")
