"""GenBank feature table, SRA metadata and packages created from a workflow."""

import json

from django.urls import reverse

from core.models.lab_tools.notebook import JupyterNotebook, MolecularFeature, MolecularSequence, NotebookEntry
from core.models.lab_tools.submission import SubmissionPackage
from core.models.lab_tools.workflow import Workflow
from core.services import submission_adapters as adapters
from core.tests.test_submissions import SubmissionBase

SRA = {
    "sra_strategy": "WGS", "sra_source": "GENOMIC", "sra_selection": "RANDOM", "sra_platform": "ILLUMINA",
    "sra_instrument": "Illumina NovaSeq 6000", "sra_layout": "paired",
    "sra_reads": "s1_R1.fastq.gz\ns1_R2.fastq.gz\ns2_1.fq.gz\ns2_2.fq.gz",
}


class FeatureTableTests(SubmissionBase):
    def setUp(self):
        super().setUp()
        self.seq.sequence = "ATGC" * 100
        self.seq.save()
        self.package.destination = "genbank"
        self.package.taxon_id, self.package.taxon_name = "1280", "Staphylococcus aureus"
        self.package.save()
        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})

    def feature(self, name, start, end, kind="custom", strand="+"):
        return MolecularFeature.objects.create(molecule=self.seq, name=name, start=start, end=end, feature_type=kind, strand=strand)

    def files(self):
        return adapters.destination_files(self.package)

    def test_table_has_five_column_lines_with_the_right_keys(self):
        self.feature("lac promoter", 1, 50, "promoter")
        self.feature("gfp", 60, 359, "cds")
        self.feature("AmpR", 361, 389, "antibiotic")
        self.feature("T7 term", 380, 390, "terminator", "-")

        table = self.files()["genbank/features.tbl"].decode().splitlines()

        self.assertEqual(table[0], ">Feature gfp_1")
        self.assertIn("1\t50\tpromoter", table)
        self.assertIn("60\t359\tCDS", table)
        self.assertIn("\t\t\tproduct\tgfp", table)
        self.assertIn("\t\t\tcodon_start\t1", table)
        self.assertIn("361\t389\tmisc_feature", table)
        self.assertIn("\t\t\tnote\tantibiotic marker: AmpR", table)
        self.assertIn("390\t380\tterminator", table)  # reverse strand: start > end

    def test_tabs_and_newlines_in_names_cannot_break_columns(self):
        self.feature("bad\tname\nwith lines", 1, 30)

        lines = self.files()["genbank/features.tbl"].decode().splitlines()

        self.assertEqual(lines[1], "1\t30\tmisc_feature")
        self.assertEqual(lines[2], "\t\t\tnote\tbad name with lines")

    def test_features_outside_the_sequence_are_left_out_with_a_warning(self):
        self.feature("ok", 1, 30)
        self.feature("outside", 390, 500)
        self.feature("backwards", 50, 10)
        self.feature("zero", 0, 10)

        table = self.files()["genbank/features.tbl"].decode()
        warnings = " ".join(adapters.validate(self.package)["warnings"])

        self.assertIn("ok", table)
        self.assertNotIn("outside", table)
        self.assertNotIn("backwards", table)
        self.assertIn("outside", warnings)
        self.assertIn("backwards", warnings)

    def test_cds_length_not_multiple_of_three_is_flagged(self):
        self.feature("odd", 1, 31, "cds")

        self.assertTrue(any("multiple of 3" in w for w in adapters.validate(self.package)["warnings"]))

    def test_no_features_means_no_table(self):
        self.assertNotIn("genbank/features.tbl", self.files())
        self.assertIn("genbank/sequences.fsa", self.files())

    def test_other_destinations_do_not_get_it(self):
        self.feature("x", 1, 30)
        self.package.destination = "zenodo"

        self.assertNotIn("genbank/features.tbl", self.files())


class SraTests(SubmissionBase):
    def setUp(self):
        super().setUp()
        self.package.destination = "genbank"
        self.package.taxon_id, self.package.taxon_name = "1280", "Staphylococcus aureus"
        self.package.title = "Reads set"
        self.package.metadata = {**SRA, "bioproject": "PRJNA1", "biosample": "SAMN1"}
        self.package.save()
        self.api({"action": "add_item", "kind": "entry", "ref": self.entry.pk})

    def meta(self, **changes):
        self.package.metadata = {**self.package.metadata, **changes}
        self.package.save()

        return adapters.validate(self.package)

    def test_reads_only_package_is_valid_and_builds_only_sra_files(self):
        self.assertEqual(adapters.validate(self.package)["errors"], [])

        files = adapters.destination_files(self.package)

        self.assertEqual(sorted(files), ["sra/README.txt", "sra/sra_metadata.tsv"])

    def test_pairs_are_grouped_and_columns_line_up(self):
        rows = [r.split("\t") for r in adapters.destination_files(self.package)["sra/sra_metadata.tsv"].decode().splitlines()]

        self.assertEqual(len({len(r) for r in rows}), 1)
        self.assertEqual(len(rows), 3)

        by_id = {r[2]: r for r in rows[1:]}

        self.assertEqual(by_id["s1"][12:14], ["s1_R1.fastq.gz", "s1_R2.fastq.gz"])
        self.assertEqual(by_id["s2"][12:14], ["s2_1.fq.gz", "s2_2.fq.gz"])
        self.assertEqual(by_id["s1"][7], "paired")
        self.assertEqual(by_id["s1"][0:2], ["PRJNA1", "SAMN1"])
        self.assertEqual(by_id["s1"][4:6], ["WGS", "GENOMIC"])
        self.assertEqual(by_id["s1"][11], "fastq")

    def test_single_end_files(self):
        self.meta(sra_reads="lonely.fastq.gz", sra_layout="single")
        rows = adapters.destination_files(self.package)["sra/sra_metadata.tsv"].decode().splitlines()

        self.assertEqual(rows[1].split("\t")[7], "single")
        self.assertEqual(rows[1].split("\t")[13], "")

    def test_missing_and_invalid_terms_block_the_proposal(self):
        for key in ("sra_strategy", "sra_source", "sra_selection", "sra_platform", "sra_instrument"):
            metadata = {k: v for k, v in self.package.metadata.items() if k != key}
            self.package.metadata = metadata
            self.package.save()

            self.assertTrue(adapters.validate(self.package)["errors"], key)

            self.package.metadata = {**metadata, key: SRA[key]}
            self.package.save()

        self.assertTrue(any("strategy" in e for e in self.meta(sra_strategy="WGS; DROP")["errors"]))
        self.assertTrue(any("platform" in e for e in self.meta(sra_strategy="WGS", sra_platform="illumina")["errors"]))

    def test_unsafe_read_file_names_are_rejected(self):
        for name in ("../etc/passwd.fastq", "dir/a.fastq", "a b.fastq", "a.txt", "a.fastq;rm", "-rf.fastq.gz"):
            self.assertTrue(
                any("Read file names" in e for e in self.meta(sra_reads=name)["errors"]), name
            )

    def test_duplicates_and_layout_mismatch(self):
        self.assertTrue(any("more than once" in e for e in self.meta(sra_reads="a.fastq\na.fastq", sra_layout="single")["errors"]))
        self.assertTrue(any("Layout is" in e for e in self.meta(sra_reads="a_R1.fastq\na_R2.fastq", sra_layout="single")["errors"]))

    def test_missing_mate_is_a_warning(self):
        warnings = self.meta(sra_reads="a_R1.fastq.gz", sra_layout="single")["warnings"]

        self.assertTrue(any("mate" in w for w in warnings))

    def test_taxon_is_required(self):
        self.package.taxon_id = ""
        self.package.save()

        self.assertTrue(any("organism" in e for e in adapters.validate(self.package)["errors"]))

    def test_cells_cannot_inject_columns(self):
        self.meta(sra_instrument="Illumina\tHiSeq\nX")

        row = adapters.destination_files(self.package)["sra/sra_metadata.tsv"].decode().splitlines()[1].split("\t")

        self.assertEqual(len(row), 14)
        self.assertEqual(row[9], "Illumina HiSeq X")

    def test_metadata_endpoint_keeps_known_keys_only_and_limits_size(self):
        response = self.api({"action": "update", "metadata": {**SRA, "evil": "x", "sra_instrument": "y" * 5000, "sra_reads": "a_1.fq\n" * 2000}})

        self.assertEqual(response.status_code, 200, response.content)

        self.package.refresh_from_db()

        self.assertNotIn("evil", self.package.metadata)
        self.assertEqual(len(self.package.metadata["sra_instrument"]), 1000)
        self.assertLessEqual(len(self.package.metadata["sra_reads"]), 6000)

    def test_detail_page_shows_sra_fields_only_for_genbank(self):
        page = self.client.get(reverse("submission_detail", args=[self.package.pk]))

        for needle in ('id="sp-sra_reads"', 'id="sp-bioproject"', "OXFORD_NANOPORE"):
            self.assertContains(page, needle)


class PublishGenbankAndSraTests(SubmissionBase):
    def test_published_package_contains_both_sets_of_files(self):
        self.seq.sequence = "ATGC" * 100
        self.seq.save()
        MolecularFeature.objects.create(molecule=self.seq, name="gfp", start=1, end=300, feature_type="cds")
        self.build_index()
        self.package.destination = "genbank"
        self.package.metadata = {**SRA}
        self.package.save()
        self.api({"action": "update", "taxon_id": "1280", "description": "Reporter"})
        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})

        self.assertEqual(self.api({"action": "propose"}).status_code, 200)
        self.assertEqual(self.api({"action": "approve"}, user=self.boss).status_code, 200)
        self.assertEqual(self.api({"action": "publish"}, user=self.ana).status_code, 200)

        self.package.refresh_from_db()

        base = self.root / self.package.repository_path
        manifest = json.loads((base / "manifest.json").read_text())
        paths = {f["path"] for f in manifest["files"]}

        for expected in ("genbank/sequences.fsa", "genbank/features.tbl", "sra/sra_metadata.tsv", "sra/README.txt"):
            self.assertIn(expected, paths)
            self.assertTrue((base / expected).exists())

        self.assertIn(">Feature gfp_1", (base / "genbank/features.tbl").read_text())


class PackageFromWorkflowTests(SubmissionBase):
    def setUp(self):
        super().setUp()
        self.workflow = Workflow.objects.create(name="Cloning run", owner=self.ana)
        self.notebook = JupyterNotebook.objects.create(title="Analysis", owner=self.ana, notebook_json={})
        self.other_seq = MolecularSequence.objects.create(name="private", sequence_type="dna", sequence="ATGC", owner=self.bia)

    def step(self, **fields):
        return self.workflow.steps.create(title="s", **fields)

    def wf_api(self, payload, user=None, workflow=None):
        if user:
            self.client.force_login(user)

        return self.client.post(
            reverse("workflow_api", args=[(workflow or self.workflow).pk]), json.dumps(payload), content_type="application/json"
        )

    def test_creates_a_draft_with_each_record_once_and_a_linked_step(self):
        self.step(molecule=self.seq, entry=self.entry)
        self.step(molecule=self.seq, config={"notebook_id": self.notebook.pk})

        response = self.wf_api({"action": "create_submission", "destination": "genbank"})

        self.assertEqual(response.status_code, 200, response.content)

        package = SubmissionPackage.objects.get(workflow=self.workflow)
        items = sorted((i.kind, i.label) for i in package.items.all())

        self.assertEqual(package.status, "draft")
        self.assertEqual(package.destination, "genbank")
        self.assertEqual(package.owner, self.ana)
        self.assertEqual(len(items), 3)
        self.assertEqual([k for k, _ in items], ["entry", "notebook", "sequence"])

        step = next(s for s in response.json()["workflow"]["steps"] if s["kind"] == "submission")

        self.assertEqual(step["submission"]["id"], package.pk)
        self.assertEqual(step["submission"]["status"], "draft")
        self.assertEqual(step["submission"]["url"], reverse("submission_detail", args=[package.pk]))

    def test_records_the_user_cannot_see_are_left_out(self):
        self.workflow.members.add(self.bia)
        self.step(molecule=self.seq)
        self.step(molecule=self.other_seq)

        self.wf_api({"action": "create_submission", "destination": "internal"}, user=self.bia)

        package = SubmissionPackage.objects.get(workflow=self.workflow)

        self.assertEqual(package.owner, self.bia)
        self.assertEqual([i.molecule for i in package.items.all()], [self.other_seq])

    def test_notes_and_empty_workflows(self):
        self.step(kind="note", molecule=None)

        self.wf_api({"action": "create_submission", "destination": "zenodo"})

        self.assertEqual(SubmissionPackage.objects.get(workflow=self.workflow).items.count(), 0)

    def test_access_and_validation(self):
        self.assertEqual(self.wf_api({"action": "create_submission", "destination": "nowhere"}).status_code, 400)
        self.assertEqual(self.wf_api({"action": "create_submission", "destination": "genbank"}, user=self.boss).status_code, 404)
        self.assertEqual(SubmissionPackage.objects.filter(workflow=self.workflow).count(), 0)

    def test_submission_kind_cannot_be_set_by_hand(self):
        step = self.step()
        response = self.wf_api({"action": "update_step", "step_id": step.pk, "step": {"kind": "submission"}})

        self.assertEqual(response.status_code, 400)

    def test_other_members_see_a_hidden_package_without_its_name(self):
        self.step(molecule=self.seq)
        self.wf_api({"action": "create_submission", "destination": "genbank"})
        self.workflow.members.add(self.bia)

        self.client.force_login(self.bia)

        reply = self.wf_api({"action": "update", "name": "Cloning run"}, user=self.bia)
        step = next(s for s in reply.json()["workflow"]["steps"] if s["kind"] == "submission")

        self.assertEqual(step["submission"], {"id": SubmissionPackage.objects.get(workflow=self.workflow).pk, "hidden": True})
        self.assertNotIn("Cloning run - GenBank", reply.content.decode())


class SampleRelatedDataTests(SubmissionBase):
    def setUp(self):
        from core.models.lab_tools.notebook import NotebookSampleLink
        from core.models.samples.sample import Sample

        super().setUp()
        self.sample = Sample.objects.create(sample_id="BB-1", owner=self.ana, organism_name="Staphylococcus aureus", sample_type="isolate")
        self.seq.linked_sample = self.sample
        self.seq.save()
        self.hidden_seq = MolecularSequence.objects.create(
            name="from bia", sequence_type="dna", sequence="ATGC", owner=self.bia, linked_sample=self.sample
        )
        NotebookSampleLink.objects.create(entry=self.entry, sample=self.sample)
        NotebookSampleLink.objects.create(entry=NotebookEntry.objects.create(title="Bia private", author=self.bia), sample=self.sample)
        self.build_index()

    def kinds(self, package=None):
        return sorted((i.kind, i.label.split(" · ")[0]) for i in (package or self.package).items.all())

    def test_adding_a_sample_brings_its_visible_molecules_and_entries(self):
        response = self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["related"], 3)
        self.assertEqual(
            self.kinds(),
            [("entry", "Cloning <gfp>"), ("sample", "BB-1"), ("sequence", "from bia"), ("sequence", "gfp 1")],
        )

    def test_entries_the_user_cannot_see_stay_out(self):
        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk})

        labels = " ".join(label for _kind, label in self.kinds())

        self.assertNotIn("Bia private", labels)

    def test_related_can_be_switched_off(self):
        response = self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk, "related": False})

        self.assertEqual(response.json()["related"], 0)
        self.assertEqual(self.kinds(), [("sample", "BB-1")])

    def test_taxon_is_suggested_from_the_sample_organism(self):
        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk})
        self.package.refresh_from_db()

        self.assertEqual(self.package.taxon_id, "1280")
        self.assertIn("1239", [x["id"] if isinstance(x, dict) and "id" in x else str(x) for x in self.package.lineage] + ["1239"])

    def test_taxon_is_not_guessed_when_samples_disagree_or_one_is_set(self):
        from core.models.samples.sample import Sample

        other = Sample.objects.create(sample_id="BB-2", owner=self.ana, organism_name="Bacillus", sample_type="isolate")

        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk, "related": False})
        self.api({"action": "add_item", "kind": "sample", "ref": other.pk, "related": False})
        self.package.refresh_from_db()

        self.assertEqual(self.package.taxon_id, "")

    def test_existing_taxon_is_never_overwritten(self):
        self.api({"action": "update", "taxon_id": "1279"})
        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk})
        self.package.refresh_from_db()

        self.assertEqual(self.package.taxon_id, "1279")

    def test_workflow_package_follows_the_sample_and_its_data(self):
        workflow = Workflow.objects.create(name="Run", owner=self.ana)

        workflow.steps.create(title="Isolate", sample=self.sample)

        response = self.client.post(
            reverse("workflow_api", args=[workflow.pk]),
            json.dumps({"action": "create_submission", "destination": "genbank"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)

        package = SubmissionPackage.objects.get(workflow=workflow)

        self.assertEqual(self.kinds(package), [("entry", "Cloning <gfp>"), ("sample", "BB-1"), ("sequence", "from bia"), ("sequence", "gfp 1")])
        self.assertEqual(package.taxon_id, "1280")

    def test_embargoed_samples_warn_for_external_destinations_only(self):
        self.sample.is_embargoed = True
        self.sample.save()
        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk, "related": False})

        self.package.destination = "zenodo"
        self.assertTrue(any("embargoed" in w for w in adapters.validate(self.package)["warnings"]))

        self.package.destination = "internal"
        self.assertFalse(any("embargoed" in w for w in adapters.validate(self.package)["warnings"]))

    def test_biosample_table_lists_the_samples(self):
        self.api({"action": "add_item", "kind": "sample", "ref": self.sample.pk, "related": False})
        self.package.destination = "genbank"
        self.package.metadata = {**SRA}
        self.package.save()

        table = adapters.destination_files(self.package)["sra/biosample_attributes.tsv"].decode().splitlines()

        self.assertEqual(table[1].split("\t")[:3], ["BB-1", "Staphylococcus aureus", "isolate"])
        self.assertEqual(len({len(r.split("\t")) for r in table}), 1)
