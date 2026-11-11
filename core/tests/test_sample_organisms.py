import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Sample, SampleOrganism
from core.services import sample_organisms, taxonomy_local
from core.tests.test_submissions import write_taxdump


def add_virus(directory: Path):
    with (directory / "nodes.dmp").open("a") as nodes:
        nodes.write("10239\t|\t1\t|\tdomain\t|\t\t|\n12333\t|\t10239\t|\tspecies\t|\t\t|\n")
    with (directory / "names.dmp").open("a") as names:
        names.write("10239\t|\tViruses\t|\t\t|\tscientific name\t|\n12333\t|\tEscherichia phage T4\t|\t\t|\tscientific name\t|\n")


class OrganismBase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "repo").mkdir()
        self.dump = self.tmp / "taxonomy"
        write_taxdump(self.dump)
        add_virus(self.dump)

        override = override_settings(BIOBANK_REPOSITORY_ROOT=str(self.tmp / "repo"), BIOBANK_TAXONOMY_DIR=str(self.dump))

        override.enable()
        self.addCleanup(override.disable)

        self.user = get_user_model().objects.create_user("org-user", password="x")
        self.client.force_login(self.user)

    def payload(self, rows, sample_id="ORG-1", sample_type="Other", **extra):
        return {
            "action": "add_sample", "sample_id": sample_id, "sample_type": sample_type, "custom_organism_name": "",
            "owner": str(self.user.pk), "aliquot_count": "1", "organisms_json": json.dumps(rows), **extra,
        }


class ServiceTests(OrganismBase):
    def test_search_without_index_is_unavailable(self):
        self.assertFalse(sample_organisms.search("staph")["available"])

    def test_search_is_limited_to_the_type_branch(self):
        taxonomy_local.build_index()

        self.assertEqual([r["name"] for r in sample_organisms.search("staphylococcus a", "Bacterium (Host)")["results"]], ["Staphylococcus aureus"])
        self.assertEqual(sample_organisms.search("staphylococcus a", "Phage (Virus)")["results"], [])
        self.assertEqual(sample_organisms.search("escherichia", "Phage (Virus)")["results"][0]["taxid"], 12333)
        self.assertEqual(sample_organisms.search("staphylococcus a", "Other")["results"][0]["genus"], "Staphylococcus")

    def test_clean_takes_names_from_the_index_and_enforces_scope(self):
        taxonomy_local.build_index()

        rows = sample_organisms.clean([{"name": "forged", "taxid": "1280", "role": "member"}, {"name": "Hand made", "strain": "X1"}], "Bacterium (Host)")

        self.assertEqual([r["name"] for r in rows], ["Staphylococcus aureus", "Hand made"])
        self.assertEqual(rows[0]["role"], "primary")
        self.assertEqual(rows[1]["source"], "manual")
        self.assertTrue(rows[0]["lineage"])

        with self.assertRaises(ValidationError):
            sample_organisms.clean([{"taxid": "12333", "role": "primary"}], "Bacterium (Host)")

        # a phage may list its bacterial host
        sample_organisms.clean([{"taxid": "12333", "role": "primary"}, {"taxid": "1280", "role": "host"}], "Phage (Virus)")

    def test_clean_rejects_bad_input(self):
        taxonomy_local.build_index()

        for rows in ([{"taxid": "abc"}], [{"taxid": "999999"}], [{"name": "A"}, {"name": "a"}], [{"name": "x" * 300}], [{"name": "a", "role": "boss"}]):
            with self.assertRaises(ValidationError):
                sample_organisms.clean(rows, "Other")

        with self.assertRaises(ValidationError):
            sample_organisms.parse("{not json")

        self.assertEqual(sample_organisms.parse(""), [])

    def test_summary_leaves_hosts_out_and_shortens(self):
        rows = [{"name": f"Org {i}", "strain": "", "role": "primary" if i == 0 else "member"} for i in range(5)] + [{"name": "Host", "strain": "", "role": "host"}]

        self.assertEqual(sample_organisms.summary(rows), "Org 0 + Org 1 + Org 2 + 2 more")


class ViewTests(OrganismBase):
    def test_search_api_needs_login_and_two_characters(self):
        taxonomy_local.build_index()

        url = reverse("sample_organism_search")

        self.assertEqual(self.client.get(url, {"q": "s"}).json()["results"], [])
        self.assertEqual(self.client.get(url, {"q": "staph", "type": "Bacterium (Host)"}).json()["results"][0]["taxid"], 1280)

        self.client.logout()

        self.assertEqual(self.client.get(url, {"q": "staph"}).status_code, 302)

    def test_create_with_a_mixed_culture_and_a_manual_organism(self):
        taxonomy_local.build_index()

        response = self.client.post(reverse("sample_add"), self.payload([{"taxid": "1280", "role": "primary"}, {"name": "Unnamed isolate", "role": "member"}]))

        self.assertEqual(response.status_code, 302)

        sample = Sample.objects.get(sample_id="ORG-1")

        self.assertEqual(sample.organism_name, "Staphylococcus aureus + Unnamed isolate")
        self.assertEqual(list(sample.organisms.values_list("name", "source")), [("Staphylococcus aureus", "ncbi"), ("Unnamed isolate", "manual")])

        page = self.client.get(reverse("sample_detail", args=[sample.pk]))

        self.assertContains(page, "typed by hand")
        self.assertContains(page, "taxid 1280")

    def test_invalid_organisms_create_nothing(self):
        taxonomy_local.build_index()

        self.client.post(reverse("sample_add"), self.payload([{"taxid": "999999"}], sample_id="ORG-BAD"))

        self.assertFalse(Sample.objects.filter(sample_id="ORG-BAD").exists())

    def test_create_without_organisms_still_works(self):
        self.assertEqual(self.client.post(reverse("sample_add"), self.payload([], sample_id="ORG-NONE", custom_organism_name="Soil")).status_code, 302)
        self.assertEqual(Sample.objects.get(sample_id="ORG-NONE").organisms.count(), 0)

    def test_edit_shows_and_replaces_organisms(self):
        taxonomy_local.build_index()

        self.client.post(reverse("sample_add"), self.payload([{"taxid": "1280"}], sample_id="ORG-EDIT", custom_organism_name="Soil"))

        sample = Sample.objects.get(sample_id="ORG-EDIT")
        page = self.client.get(reverse("sample_edit", args=[sample.pk]))

        self.assertContains(page, "organisms-initial")
        self.assertContains(page, "Staphylococcus aureus")

        SampleOrganism.objects.filter(sample=sample).delete()
        sample_organisms.replace(sample, sample_organisms.clean([{"name": "Old"}], "Other"))

        self.assertEqual(sample.organisms.get().name, "Old")


class SubmissionSuggestionTests(OrganismBase):
    def test_main_taxid_is_used_for_the_package_taxon(self):
        from core.models import SubmissionPackage
        from core.services import submissions

        taxonomy_local.build_index()

        sample = Sample.objects.create(sample_id="ORG-SUB", organism_name="Weird label", sample_type="Other", owner=self.user)

        sample_organisms.replace(sample, sample_organisms.clean([{"taxid": "1280"}], "Other"))

        package = SubmissionPackage.objects.create(title="p", owner=self.user)

        package.items.create(kind="sample", sample=sample)
        submissions.suggest_taxon(package)
        package.refresh_from_db()

        self.assertEqual(package.taxon_id, "1280")
