import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import MolecularSequence, NotebookEntry
from core.models.lab_tools.submission import SubmissionPackage
from core.services import repository, taxonomy_local


def write_taxdump(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    nodes = [(1, 1, "no rank"), (131567, 1, "cellular root"), (2, 131567, "domain"), (1239, 2, "phylum"), (1279, 1239, "genus"), (1280, 1279, "species")]
    names = {1: "root", 131567: "cellular organisms", 2: "Bacteria", 1239: "Bacillota", 1279: "Staphylococcus", 1280: "Staphylococcus aureus"}

    (directory / "nodes.dmp").write_text("".join(f"{t}\t|\t{p}\t|\t{r}\t|\t\t|\n" for t, p, r in nodes))

    lines = [f"{t}\t|\t{n}\t|\t\t|\tscientific name\t|\n" for t, n in names.items()]

    lines.append("1280\t|\tStaph aureus\t|\t\t|\tsynonym\t|\n")
    (directory / "names.dmp").write_text("".join(lines))


class SubmissionBase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "biobank"
        self.root.mkdir()
        self.dump = self.tmp / "taxonomy"
        write_taxdump(self.dump)

        override = override_settings(BIOBANK_REPOSITORY_ROOT=str(self.root), BIOBANK_TAXONOMY_DIR=str(self.dump))

        override.enable()
        self.addCleanup(override.disable)

        User = get_user_model()

        self.ana = User.objects.create_user("ana", password="x")
        self.bia = User.objects.create_user("bia", password="x")
        self.boss = User.objects.create_user("boss", password="x")
        self.boss.user_permissions.add(Permission.objects.get(codename="approve_submission"))
        self.client.force_login(self.ana)

        self.seq = MolecularSequence.objects.create(name="gfp 1", sequence_type="dna", topology="linear", sequence="ATGC" * 40, owner=self.ana)
        self.entry = NotebookEntry.objects.create(title="Cloning <gfp>", author=self.ana, content="<p>Done</p>")
        self.package = SubmissionPackage.objects.create(title="GFP data set", owner=self.ana)

    def api(self, payload, user=None, package=None):
        if user:
            self.client.force_login(user)

        return self.client.post(
            reverse("submission_api", args=[(package or self.package).pk]), json.dumps(payload), content_type="application/json"
        )

    def build_index(self):
        taxonomy_local.build_index()


class TaxonomyLocalTests(SubmissionBase):
    def test_index_lookup_lineage_and_search(self):
        self.assertFalse(taxonomy_local.available())
        self.assertEqual(taxonomy_local.lineage(1280), [])

        summary = taxonomy_local.build_index()

        self.assertEqual(summary["nodes"], 6)
        self.assertTrue(taxonomy_local.available())
        self.assertEqual(taxonomy_local.get(1280)["name"], "Staphylococcus aureus")
        self.assertEqual([t["name"] for t in taxonomy_local.lineage(1280)], ["root", "cellular organisms", "Bacteria", "Bacillota", "Staphylococcus", "Staphylococcus aureus"])
        self.assertEqual([t["taxid"] for t in taxonomy_local.search("staphylococcus a")], [1280])
        self.assertEqual(taxonomy_local.search("1279")[0]["name"], "Staphylococcus")
        self.assertEqual(taxonomy_local.search("100%"), [])
        self.assertIsNone(taxonomy_local.get("abc"))
        self.assertTrue(taxonomy_local.version())

    def test_management_command_and_missing_dump(self):
        call_command("build_taxonomy_index", stdout=open("/dev/null", "w"))

        self.assertTrue(taxonomy_local.available())

        with self.assertRaises(Exception):
            call_command("build_taxonomy_index", taxdump=str(self.tmp / "nope"))


class SubmissionFlowTests(SubmissionBase):
    def test_edit_details_taxon_and_items(self):
        self.build_index()

        ok = self.api({"action": "update", "title": "GFP set", "taxon_id": "1280", "metadata": {"license": "https://x/y", "authors": "Ana", "junk": "no"}})

        self.assertEqual(ok.status_code, 200, ok.content)

        self.package.refresh_from_db()

        self.assertEqual(self.package.taxon_name, "Staphylococcus aureus")
        self.assertEqual(self.package.lineage[-1]["taxid"], 1280)
        self.assertEqual(self.package.metadata, {"license": "https://x/y", "authors": "Ana"})
        self.assertEqual(self.api({"action": "update", "taxon_id": "999999"}).status_code, 400)
        self.assertEqual(self.api({"action": "update", "taxon_id": "abc"}).status_code, 400)
        self.assertEqual(self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk}).status_code, 200)
        self.assertEqual(self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk}).status_code, 400)
        self.assertEqual(self.api({"action": "add_item", "kind": "entry", "ref": self.entry.pk}).status_code, 200)

        theirs = MolecularSequence.objects.create(name="secret", sequence_type="dna", sequence="AAAA", owner=self.bia)

        self.assertEqual(self.api({"action": "add_item", "kind": "sequence", "ref": theirs.pk}).status_code, 400)
        self.assertEqual(self.api({"action": "update", "taxon_id": ""}).status_code, 200)

    def test_taxon_needs_the_index(self):
        response = self.api({"action": "update", "taxon_id": "1280"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("build_taxonomy_index", response.json()["message"])

    def test_review_rules(self):
        self.assertEqual(self.api({"action": "propose"}).status_code, 400)

        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})

        self.assertEqual(self.api({"action": "propose"}).status_code, 200)
        self.assertEqual(self.api({"action": "update", "title": "late"}).status_code, 400)
        # the owner cannot approve, nor can a user without the permission
        self.assertEqual(self.api({"action": "approve"}).status_code, 400)
        self.assertEqual(self.api({"action": "approve"}, user=self.bia).status_code, 404)

        self.assertEqual(self.api({"action": "reject", "note": ""}, user=self.boss).status_code, 400)
        self.assertEqual(self.api({"action": "reject", "note": "Add the taxon"}, user=self.boss).status_code, 200)

        self.package.refresh_from_db()

        self.assertEqual(self.package.status, "rejected")
        self.assertEqual(self.api({"action": "propose"}, user=self.ana).status_code, 200)
        self.assertEqual(self.api({"action": "approve", "note": "Looks good"}, user=self.boss).status_code, 200)

        self.package.refresh_from_db()

        self.assertEqual((self.package.status, self.package.approved_by), ("approved", self.boss))

    def test_superuser_may_approve_own_package(self):
        self.ana.is_superuser = True
        self.ana.save()
        self.api({"action": "add_item", "kind": "entry", "ref": self.entry.pk})
        self.api({"action": "propose"})

        self.assertEqual(self.api({"action": "approve"}).status_code, 200)

    def test_visibility_of_drafts_and_published(self):
        self.assertContains(self.client.get(reverse("submission_list")), "GFP data set")

        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(reverse("submission_detail", args=[self.package.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("submission_list")), "GFP data set")

        self.package.status = "published"
        self.package.save()

        self.assertEqual(self.client.get(reverse("submission_detail", args=[self.package.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("submission_list"), {"tab": "repository"}), "GFP data set")

    def test_delete_only_drafts_by_owner(self):
        self.assertEqual(self.api({"action": "delete"}, user=self.bia).status_code, 404)
        self.assertTrue(self.api({"action": "delete"}, user=self.ana).json()["deleted"])


class PublishToRepositoryTests(SubmissionBase):
    def approve_package(self):
        self.build_index()
        self.api({"action": "update", "taxon_id": "1280", "description": "Reporter", "metadata": {"license": "https://creativecommons.org/licenses/by/4.0/"}})
        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})
        self.api({"action": "add_item", "kind": "entry", "ref": self.entry.pk})
        self.api({"action": "propose"})
        self.api({"action": "approve", "note": "ok"}, user=self.boss)
        self.package.refresh_from_db()

    def test_publish_writes_manifest_rocrate_and_files(self):
        self.approve_package()

        response = self.api({"action": "publish"}, user=self.ana)

        self.assertEqual(response.status_code, 200, response.content)

        self.package.refresh_from_db()

        self.assertEqual(self.package.status, "published")

        base = self.root / self.package.repository_path
        manifest = json.loads((base / "manifest.json").read_text())
        crate = json.loads((base / "ro-crate-metadata.json").read_text())

        self.assertEqual(manifest["schema"], "b3-lims-package/1")
        self.assertEqual(manifest["approval"]["approved_by"], "boss")
        self.assertEqual(manifest["taxon"]["ncbi_taxid"], "1280")
        self.assertIn("1239", manifest["taxon"]["lineage_ids"])
        self.assertEqual(sorted(f["path"] for f in manifest["files"]), ["entries/%d-Cloning_gfp.html" % self.entry.pk, "sequences/gfp_1.fasta"])
        self.assertTrue((base / "sequences" / "gfp_1.fasta").read_text().startswith(">gfp_1 type=dna"))
        self.assertIn("&lt;gfp&gt;", (base / "entries" / f"{self.entry.pk}-Cloning_gfp.html").read_text())
        self.assertEqual(crate["@context"], "https://w3id.org/ro/crate/1.1/context")
        self.assertTrue(any(n["@id"] == "sequences/gfp_1.fasta" for n in crate["@graph"]))
        self.assertTrue(any(n.get("@type") == "Taxon" and n["name"] == "Staphylococcus aureus" for n in crate["@graph"]))

        line = json.loads((self.root / "index" / "packages.jsonl").read_text().splitlines()[-1])

        self.assertEqual(line["id"], self.package.pk)
        self.assertIn("1239", line["lineage_ids"])
        self.assertEqual(self.package.manifest_sha256, repository._sha256((base / "manifest.json").read_bytes()))

    def test_repository_filter_by_taxon_includes_descendants(self):
        self.approve_package()
        self.api({"action": "publish"}, user=self.ana)
        self.client.force_login(self.bia)

        hit = self.client.get(reverse("submission_list"), {"tab": "repository", "taxon": "1239"})
        miss = self.client.get(reverse("submission_list"), {"tab": "repository", "taxon": "9999"})

        self.assertContains(hit, "GFP data set")
        self.assertNotContains(miss, "GFP data set")

    def test_cannot_publish_twice_unapproved_or_to_other_destinations(self):
        self.assertEqual(self.api({"action": "publish"}).status_code, 400)

        self.approve_package()

        self.package.destination = "zenodo"
        self.package.save()

        self.assertEqual(self.api({"action": "publish"}, user=self.ana).status_code, 400)

        self.package.destination = "internal"
        self.package.save()

        self.assertEqual(self.api({"action": "publish"}, user=self.bia).status_code, 404)
        self.assertEqual(self.api({"action": "publish"}, user=self.ana).status_code, 200)
        self.assertEqual(self.api({"action": "publish"}, user=self.ana).status_code, 400)

    def test_missing_repository_directory_is_reported(self):
        self.approve_package()
        shutil.rmtree(self.root)

        response = self.api({"action": "publish"}, user=self.ana)

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not exist", response.json()["message"])
        self.package.refresh_from_db()
        self.assertEqual(self.package.status, "approved")

    def test_helpers_are_path_safe(self):
        self.assertEqual(repository.safe_name("../../etc/passwd"), "etc_passwd")
        self.assertEqual(repository.safe_name("..."), "file")
        self.assertEqual(repository.slugify("Ação GFP / 2026"), "a-o-gfp-2026")


class SubmissionWiringTests(SubmissionBase):
    def test_lookup_and_pages(self):
        self.build_index()

        taxa = self.client.get(reverse("submission_lookup_api"), {"kind": "taxon", "q": "staph"}).json()["results"]

        self.assertEqual({t["id"] for t in taxa}, {1279, 1280})
        self.assertEqual(len(self.client.get(reverse("submission_lookup_api"), {"kind": "sequence", "q": "gfp"}).json()["results"]), 1)
        self.assertEqual(self.client.get(reverse("submission_lookup_api"), {"kind": "zzz"}).status_code, 404)

        page = self.client.get(reverse("submission_detail", args=[self.package.pk]))

        self.assertContains(page, "submission_editor.js")
        self.assertContains(page, 'id="sp-data"')
        self.assertContains(self.client.get(reverse("submission_list")), "Data submissions")
        self.assertContains(self.client.get(reverse("bench:home")), reverse("submission_list"))

    def test_create_redirects_to_the_new_package(self):
        response = self.client.post(reverse("submission_create"), {"title": "New", "destination": "zenodo"})
        package = SubmissionPackage.objects.get(title="New")

        self.assertRedirects(response, reverse("submission_detail", args=[package.pk]))
        self.assertEqual(package.destination, "zenodo")
        self.assertTrue(package.owner == self.ana)
