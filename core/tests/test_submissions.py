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

    def test_cannot_publish_twice_unapproved_or_by_others(self):
        self.assertEqual(self.api({"action": "publish"}).status_code, 400)

        self.approve_package()

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


class DestinationAdapterTests(SubmissionBase):
    def make(self, destination, **fields):
        package = SubmissionPackage.objects.create(title="Export set", owner=self.ana, destination=destination, **fields)

        return package

    def add(self, package, kind, ref):
        return self.api({"action": "add_item", "kind": kind, "ref": ref}, package=package)

    def approve_and_publish(self, package):
        self.assertEqual(self.api({"action": "propose"}, user=self.ana, package=package).status_code, 200)
        self.assertEqual(self.api({"action": "approve"}, user=self.boss, package=package).status_code, 200)

        return self.api({"action": "publish"}, user=self.ana, package=package)

    def test_genbank_needs_nucleotides_and_a_taxon(self):
        self.build_index()

        package = self.make("genbank")

        self.assertEqual(self.api({"action": "propose"}, package=package).status_code, 400)

        protein = MolecularSequence.objects.create(name="GFP protein", sequence_type="protein", sequence="MSKGEEL" * 40, owner=self.ana)

        self.add(package, "sequence", protein.pk)

        message = self.api({"action": "propose"}, package=package).json()["message"]

        self.assertIn("only has proteins", message)

        self.add(package, "sequence", self.seq.pk)
        self.assertIn("choose a taxon", self.api({"action": "propose"}, package=package).json()["message"])

        bad = MolecularSequence.objects.create(name="bad", sequence_type="dna", sequence="ATGXZ" * 50, owner=self.ana)

        self.add(package, "sequence", bad.pk)
        self.assertIn("not nucleotide codes", self.api({"action": "propose"}, package=package).json()["message"])

    def test_genbank_export_files(self):
        self.build_index()

        plasmid = MolecularSequence.objects.create(name="pGFP 1", sequence_type="plasmid", topology="circular", sequence="ATGC" * 80, owner=self.ana)
        package = self.make("genbank")

        self.api({"action": "update", "taxon_id": "1280"}, package=package)
        self.add(package, "sequence", self.seq.pk)
        self.add(package, "sequence", plasmid.pk)

        self.assertEqual(self.approve_and_publish(package).status_code, 200)

        package.refresh_from_db()

        base = self.root / package.repository_path
        fasta = (base / "genbank" / "sequences.fsa").read_text()
        table = (base / "genbank" / "source_modifiers.tsv").read_text().splitlines()

        self.assertTrue(package.repository_path.startswith("exports/genbank/"))
        self.assertIn(">gfp_1 [organism=Staphylococcus aureus] [moltype=genomic]", fasta)
        self.assertIn(">pGFP_1 [organism=Staphylococcus aureus] [topology=circular] [moltype=genomic]", fasta)
        self.assertEqual(table[0], "Sequence_ID\tOrganism\tdb_xref")
        self.assertEqual(table[1], "gfp_1\tStaphylococcus aureus\ttaxon:1280")
        self.assertTrue((base / "genbank" / "README.txt").is_file())
        self.assertTrue((base / "manifest.json").is_file())

        # exports are private to the owner, not part of the shared repository
        self.client.force_login(self.bia)

        self.assertEqual(self.client.get(reverse("submission_detail", args=[package.pk])).status_code, 404)

    def test_pdb_needs_a_structure_and_exports_entities(self):
        from core.models.lab_tools.notebook import MolecularStructure

        self.build_index()

        protein = MolecularSequence.objects.create(name="GFP protein", sequence_type="protein", sequence="MSKGEEL" * 10, owner=self.ana)
        package = self.make("pdb")

        self.add(package, "sequence", protein.pk)

        self.assertIn("at least one 3D structure", self.api({"action": "propose"}, package=package).json()["message"])

        structure = MolecularStructure.objects.create(
            molecule=protein, file="s/model.pdb", original_filename="model.pdb", source_format="pdb", uploaded_by=self.ana
        )

        self.add(package, "structure", structure.pk)
        self.api({"action": "update", "taxon_id": "1280", "metadata": {"authors": "Ana; Bia", "keywords": "gfp, fold"}}, package=package)

        from unittest import mock

        with mock.patch.object(repository, "_read_structure", return_value=b"data_model\n"):
            response = self.approve_and_publish(package)

        self.assertEqual(response.status_code, 200, response.content)

        package.refresh_from_db()

        base = self.root / package.repository_path
        meta = json.loads((base / "wwpdb" / "deposition_metadata.json").read_text())

        self.assertEqual(meta["authors"], ["Ana", "Bia"])
        self.assertEqual(meta["keywords"], ["gfp", "fold"])
        self.assertEqual(meta["source_organism"]["ncbi_taxid"], "1280")
        self.assertIn(">entity_1|GFP_protein|protein Staphylococcus aureus (taxid 1280)", (base / "wwpdb" / "entity_sequences.fasta").read_text())
        self.assertTrue((base / "structures" / "model.pdb").is_file())

        warnings = self.api({"action": "update", "title": "x"}, package=package).status_code

        self.assertEqual(warnings, 400)  # published packages are read-only

    def test_zenodo_metadata_and_validation(self):
        from core.services import submission_adapters as adapters

        package = self.make("zenodo", metadata={"license": "https://creativecommons.org/publicdomain/zero/1.0/", "authors": "Silva, Ana;Souza, Bia", "keywords": "a; b"})

        self.add(package, "entry", self.entry.pk)

        self.assertIn("needs a description", self.api({"action": "propose"}, package=package).json()["message"])

        package.description = "Reporter constructs"
        package.save()

        data = adapters.zenodo_metadata(package)

        self.assertEqual(data["license"], "cc0-1.0")
        self.assertEqual([c["name"] for c in data["creators"]], ["Silva, Ana", "Souza, Bia"])
        self.assertEqual(data["keywords"], ["a", "b"])
        self.assertEqual(data["upload_type"], "dataset")

        package.metadata = {"license": "https://example.org/own"}

        self.assertEqual(adapters.zenodo_metadata(package)["license"], "cc-by-4.0")
        self.assertTrue(any("license" in w for w in adapters.validate(package)["warnings"]))

    def test_zenodo_draft_upload_never_publishes_and_references_are_saved(self):
        from unittest import mock

        from core.services import submission_adapters as adapters

        package = self.make("zenodo", description="Reporter constructs")

        self.add(package, "entry", self.entry.pk)
        self.assertEqual(self.approve_and_publish(package).status_code, 200)
        self.assertEqual(self.api({"action": "upload_zenodo"}, package=package).status_code, 400)  # not configured

        calls = []

        def fake(method, url, token, body=None, content_type="application/json", timeout=60):
            calls.append((method, url))

            if method == "POST":
                return {"id": 77, "links": {"bucket": "https://z.test/api/files/b1", "html": "https://z.test/deposit/77"}}

            return {}

        with override_settings(BIOBANK_ZENODO_TOKEN="t0k", BIOBANK_ZENODO_API="https://z.test/api"), \
                mock.patch.object(adapters, "_zenodo_request", side_effect=fake):
            response = self.api({"action": "upload_zenodo"}, package=package)

            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(self.api({"action": "upload_zenodo"}, package=package).status_code, 400)

        package.refresh_from_db()

        self.assertEqual(package.external_reference, "https://z.test/deposit/77")
        self.assertEqual(calls[0], ("POST", "https://z.test/api/deposit/depositions"))
        self.assertTrue(any(m == "PUT" and "/files/b1/" in u for m, u in calls))
        self.assertTrue(any(u.endswith("/deposit/depositions/77") for _, u in calls))
        self.assertFalse(any("publish" in u for _, u in calls))

        self.assertEqual(self.api({"action": "set_reference", "value": "10.5281/zenodo.77"}, package=package).status_code, 200)
        self.assertEqual(self.api({"action": "set_reference", "value": "x"}, user=self.bia, package=package).status_code, 404)

        draft = self.make("zenodo")

        self.assertEqual(self.api({"action": "set_reference", "value": "x"}, user=self.ana, package=draft).status_code, 400)

    def test_zenodo_errors_become_validation_errors(self):
        import urllib.error
        from unittest import mock

        from django.core.exceptions import ValidationError

        from core.services import submission_adapters as adapters

        with override_settings(BIOBANK_ZENODO_TOKEN="t"), mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(ValidationError):
                adapters.upload_zenodo_draft(self.package, {"a.txt": b"x"})


class NotebookItemAndClientTests(SubmissionBase):
    def test_a_jupyter_notebook_is_exported_and_the_client_is_installed(self):
        from core.models.lab_tools.notebook import JupyterNotebook

        nb = JupyterNotebook.objects.create(title="Align reads", owner=self.ana, notebook_json={"cells": [], "nbformat": 4})
        other = JupyterNotebook.objects.create(title="Private", owner=self.bia, notebook_json={})

        self.assertEqual(self.api({"action": "add_item", "kind": "notebook", "ref": other.pk}).status_code, 400)
        self.assertEqual(self.api({"action": "add_item", "kind": "notebook", "ref": nb.pk}).status_code, 200)
        self.assertEqual(self.api({"action": "add_item", "kind": "notebook", "ref": nb.pk}).status_code, 400)
        self.assertEqual(len(self.client.get(reverse("submission_lookup_api"), {"kind": "notebook"}).json()["results"]), 1)

        self.build_index()
        self.api({"action": "update", "taxon_id": "1280"})
        self.api({"action": "propose"})
        self.api({"action": "approve"}, user=self.boss)

        self.assertEqual(self.api({"action": "publish"}, user=self.ana).status_code, 200)

        self.package.refresh_from_db()

        base = self.root / self.package.repository_path

        self.assertEqual(json.loads((base / "notebooks" / f"{nb.pk}-Align_reads.ipynb").read_text())["nbformat"], 4)
        self.assertTrue((self.root / "lib" / "b3repo.py").is_file())

    def test_b3repo_reads_the_repository_without_django(self):
        from core.services import b3repo

        self.build_index()
        self.api({"action": "update", "taxon_id": "1280"})
        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})
        self.api({"action": "propose"})
        self.api({"action": "approve"}, user=self.boss)
        self.api({"action": "publish"}, user=self.ana)

        found = b3repo.find(q="gfp", repository=self.root)

        self.assertEqual([p["id"] for p in found], [self.package.pk])
        self.assertEqual(len(b3repo.find(taxid=1239, repository=self.root)), 1)
        self.assertEqual(b3repo.find(taxid=9999, repository=self.root), [])
        self.assertEqual(b3repo.find(destination="genbank", repository=self.root), [])
        self.assertEqual(b3repo.manifest(found[0], self.root)["taxon"]["ncbi_taxid"], "1280")
        self.assertTrue(all(path.is_file() for path in b3repo.files(found[0], self.root)))
        self.assertEqual([t["name"] for t in b3repo.lineage(1280, self.root)][-2:], ["Staphylococcus", "Staphylococcus aureus"])
        self.assertEqual(b3repo.taxon(1279, self.root)["rank"], "genus")
        self.assertEqual([t["taxid"] for t in b3repo.search_taxa("staph", repository=self.root)], [1279, 1280])
        self.assertEqual(b3repo.packages(self.tmp / "empty"), [])

        with self.assertRaises(FileNotFoundError):
            b3repo.taxon(1, self.tmp / "empty")

    def test_the_client_module_has_no_django_dependency_and_command_installs_it(self):
        import ast

        from core.services import b3repo

        imported = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(open(b3repo.__file__).read())) if isinstance(n, ast.Import)}
        imported |= {n.module.split(".")[0] for n in ast.walk(ast.parse(open(b3repo.__file__).read())) if isinstance(n, ast.ImportFrom) and n.module}

        self.assertFalse({"django", "core"} & imported)

        call_command("install_repository_client", stdout=open("/dev/null", "w"))

        self.assertTrue((self.root / "lib" / "b3repo.py").is_file())
