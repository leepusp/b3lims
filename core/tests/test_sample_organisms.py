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
        found = sample_organisms.search("staphylococcus a", "Other")["results"][0]

        self.assertEqual(found["genus"], "Staphylococcus")
        self.assertEqual(found["ranks"]["species"], "Staphylococcus aureus")

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

    def test_taxonomy_fill_box_is_on_new_and_edit_pages(self):
        self.assertContains(self.client.get(reverse("sample_add")), 'id="taxFill"')

        sample = Sample.objects.create(sample_id="ORG-FILL", organism_name="x", sample_type="Other", owner=self.user)

        self.assertContains(self.client.get(reverse("sample_edit", args=[sample.pk])), "organismsSection")

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


class RichTaxonomyTests(OrganismBase):
    def setUp(self):
        super().setUp()

        # a richer dump: division, genetic code, synonyms, authority and a merged taxon
        nodes = [(1, 1, "no rank", 8, 11), (2, 1, "domain", 0, 11), (1280, 2, "species", 0, 11), (10239, 1, "domain", 9, 1), (77920, 10239, "species", 9, 1)]
        (self.dump / "nodes.dmp").write_text("".join(f"{t}\t|\t{p}\t|\t{r}\t|\t\t|\t{d}\t|\t1\t|\t{g}\t|\n" for t, p, r, d, g in nodes))
        (self.dump / "names.dmp").write_text(
            "1\t|\troot\t|\t\t|\tscientific name\t|\n2\t|\tBacteria\t|\t\t|\tscientific name\t|\n"
            "1280\t|\tStaphylococcus aureus\t|\t\t|\tscientific name\t|\n1280\t|\tStaph aureus\t|\t\t|\tsynonym\t|\n"
            "1280\t|\tStaphylococcus aureus Rosenbach 1884\t|\t\t|\tauthority\t|\n1280\t|\tgolden staph\t|\t\t|\tcommon name\t|\n"
            "10239\t|\tViruses\t|\t\t|\tscientific name\t|\n77920\t|\tPhage #D\t|\t\t|\tscientific name\t|\n"
        )
        (self.dump / "division.dmp").write_text("0\t|\tBCT\t|\tBacteria\t|\t\t|\n9\t|\tPHG\t|\tPhages\t|\t\t|\n")
        (self.dump / "gencode.dmp").write_text("1\t|\tSGC0\t|\tStandard\t|\t\t|\t\t|\n11\t|\tSGC3\t|\tBacterial, Archaeal and Plant Plastid\t|\t\t|\t\t|\n")
        (self.dump / "merged.dmp").write_text("123\t|\t1280\t|\n")
        taxonomy_local.build_index()

    def test_details_carry_names_division_and_code(self):
        d = taxonomy_local.details(1280)

        self.assertEqual(d["synonyms"], ["Staph aureus"])
        self.assertEqual(d["common_names"], ["golden staph"])
        self.assertEqual(d["authority"], ["Staphylococcus aureus Rosenbach 1884"])
        self.assertEqual((d["division"], d["genetic_code"]), ("Bacteria", "Bacterial, Archaeal and Plant Plastid"))

    def test_merged_taxon_resolves_to_the_current_one(self):
        self.assertEqual(taxonomy_local.get(123)["taxid"], 1280)
        self.assertEqual(sample_organisms.clean([{"taxid": "123"}], "Other")[0]["taxon_id"], "1280")

    def test_unclassified_virus_gets_a_warning_and_nothing_inferred(self):
        d = sample_organisms.details(77920, "Phage (Virus)")

        self.assertTrue(d["warnings"])
        self.assertEqual(d["inferred"], {})

    def test_virus_traits_are_inferred_from_the_lineage(self):
        chain = [{"name": "Viruses"}, {"name": "Duplodnaviria"}, {"name": "Caudoviricetes"}, {"name": "Myoviridae"}]

        self.assertEqual(sample_organisms.infer_virus(chain)["genome_type"]["value"], "dsDNA")
        self.assertEqual(sample_organisms.infer_virus(chain)["morphotype"]["value"], "myovirus")

    def test_details_api(self):
        url = reverse("sample_organism_details")

        self.assertEqual(self.client.get(url, {"taxid": "x"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"taxid": "999"}).status_code, 404)
        self.assertEqual(self.client.get(url, {"taxid": "1280", "type": "Bacterium (Host)"}).json()["name"], "Staphylococcus aureus")


class GtdbTests(OrganismBase):
    def test_species_summary_from_metadata(self):
        import gzip

        from core.services import gtdb_local

        head = "accession\tgtdb_taxonomy\tgtdb_representative\tgenome_size\tgc_percentage\tcheckm2_completeness\tcheckm2_contamination\tncbi_isolation_source\tncbi_country\tncbi_species_taxid\tgtdb_type_designation_ncbi_taxa\tncbi_assembly_level\n"
        tax = "d__Bacteria;p__Bacillota;c__Bacilli;o__Staph;f__Staphylococcaceae;g__Staphylococcus;s__Staphylococcus aureus"
        rows = [
            f"RS_1\t{tax}\tt\t2800000\t32.8\t99\t0.5\tblood\tBrazil: SP\t1280\tnot type material\tComplete\n",
            f"RS_2\t{tax}\tf\t2900000\t32.9\t98\t1.0\tblood\tBrazil\t1280\ttype strain of species\tContig\n",
            f"RS_3\t{tax}\tf\t2700000\t32.7\t97\t0.2\tna\tChina\t1280\tnot type material\tContig\n",
        ]
        path = self.tmp / "gtdb" / "2026-r232"

        path.mkdir(parents=True)

        with gzip.open(path / "bac120_metadata_r232.tsv.gz", "wt") as out:
            out.write(head + "".join(rows))

        self.assertFalse(gtdb_local.available())
        self.assertEqual(gtdb_local.build_index(path / "bac120_metadata_r232.tsv.gz")["species"], 1)

        d = gtdb_local.for_species(taxid=1280)

        self.assertEqual((d["genomes"], d["genome_size_median"], d["type_material_genomes"], d["representative"]), (3, 2800000, 1, "RS_1"))
        self.assertEqual(d["isolation_sources"], [["blood", 2]])
        self.assertEqual(d["countries"][0], ["Brazil", 2])
        self.assertEqual(gtdb_local.for_species(name="staphylococcus aureus")["release"], "r232")
        self.assertIsNone(gtdb_local.for_species(name="Nothing here"))
