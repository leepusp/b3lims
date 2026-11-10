"""Ready-made workflows, destination guides and the locked kind of submission steps."""

import json

from django.urls import reverse

from core.models.lab_tools.submission import SubmissionPackage
from core.models.lab_tools.workflow import Workflow
from core.services import submission_guides as guides
from core.services import workflow_templates as templates
from core.tests.test_submission_gaps import SRA
from core.tests.test_submissions import SubmissionBase


class TemplateTests(SubmissionBase):
    def setUp(self):
        super().setUp()
        self.workflow = Workflow.objects.create(name="From template", owner=self.ana)

    def post(self, payload, workflow=None):
        return self.client.post(
            reverse("workflow_api", args=[(workflow or self.workflow).pk]), json.dumps(payload), content_type="application/json"
        )

    def test_every_template_builds_a_connected_acyclic_flow(self):
        for template in templates.TEMPLATES:
            with self.subTest(template["key"]):
                wf = Workflow.objects.create(name=template["key"], owner=self.ana)
                response = self.post({"action": "apply_template", "template": template["key"]}, wf)

                self.assertEqual(response.status_code, 200, response.content)

                expected = len(template["steps"]) + (1 if template.get("submission") else 0)

                self.assertEqual(wf.steps.count(), expected)
                self.assertEqual(wf.edges.count(), sum(len(s["after"]) for s in template["steps"]) + (1 if template.get("submission") else 0))
                self.assertEqual(len({(s.x, s.y) for s in wf.steps.all()}), expected, "steps must not overlap")

    def test_analysis_steps_get_their_own_ready_notebook_and_parameters(self):
        from core.models.lab_tools.notebook import JupyterNotebook

        self.post({"action": "apply_template", "template": "blast_search"})

        step = self.workflow.steps.get(title="Filter and summarise hits")
        notebook = JupyterNotebook.objects.get(pk=step.config["notebook_id"])

        self.assertEqual(step.kind, "jupyter")
        self.assertEqual(notebook.owner, self.ana)
        self.assertEqual(notebook.notebook_json["metadata"]["biobank"]["template"], "blast_hits")
        self.assertEqual(step.config["parameters"]["min_identity"], "90")
        self.assertIn("hits_path", step.config["parameters"])
        self.assertEqual(self.workflow.steps.get(title="Run BLAST").kind, "manual")

    def test_failed_template_leaves_no_orphan_notebooks(self):
        from core.models.lab_tools.notebook import JupyterNotebook
        from core.services import workflow as service

        before = JupyterNotebook.objects.count()
        old = service.MAX_STEPS
        service.MAX_STEPS = 3

        try:
            self.assertEqual(self.post({"action": "apply_template", "template": "genome_genbank"}).status_code, 400)
        finally:
            service.MAX_STEPS = old

        self.assertEqual(JupyterNotebook.objects.count(), before)

    def test_submission_templates_create_the_package_and_link_it_to_the_flow(self):
        self.post({"action": "apply_template", "template": "reads_sra"})

        package = SubmissionPackage.objects.get(workflow=self.workflow)
        step = self.workflow.steps.get(kind="submission")

        self.assertEqual(package.destination, "genbank")
        self.assertEqual(step.config["package_id"], package.pk)
        self.assertTrue(self.workflow.edges.filter(target=step).exists())

    def test_unknown_template_and_step_limit_are_refused(self):
        self.assertEqual(self.post({"action": "apply_template", "template": "nope"}).status_code, 400)

        from core.services import workflow as service

        old = service.MAX_STEPS
        service.MAX_STEPS = 2

        try:
            self.assertEqual(self.post({"action": "apply_template", "template": "table_pca"}).status_code, 400)
        finally:
            service.MAX_STEPS = old

        self.assertEqual(self.workflow.steps.count(), 0)

    def test_someone_who_cannot_edit_cannot_apply_a_template(self):
        self.client.force_login(self.bia)

        self.assertIn(self.post({"action": "apply_template", "template": "table_pca"}).status_code, (400, 403, 404))
        self.assertEqual(self.workflow.steps.count(), 0)

    def test_the_picker_lists_every_template_with_inputs(self):
        catalog = templates.catalog()["workflows"]

        self.assertEqual(len(catalog), len(templates.TEMPLATES))
        self.assertTrue(all(c["inputs"] and c["steps"] for c in catalog))

        page = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertContains(page, "wf-templates-data")
        self.assertContains(page, "Assembled sequence to GenBank")
        self.assertContains(page, 'id="wf-tpl-q"')  # the search box

    def test_blocks_catalog_lists_tasks_notes_notebooks_and_every_destination(self):
        blocks = {b["key"] for b in templates.catalog()["blocks"]}

        self.assertTrue({"manual", "note", "notebook:read_qc", "notebook:pca_table", "submission:genbank", "submission:zenodo"} <= blocks)
        self.assertEqual(len(blocks), len(templates.catalog()["blocks"]), "keys are unique")

    def test_single_blocks_add_one_ready_step(self):
        from core.models.lab_tools.notebook import JupyterNotebook

        for key, kind in (("manual", "manual"), ("note", "note"), ("notebook:read_qc", "jupyter"), ("submission:pdb", "submission")):
            with self.subTest(key):
                r = self.post({"action": "add_block", "block": key, "x": 10, "y": 20})

                self.assertEqual(r.status_code, 200, r.content)
                step = self.workflow.steps.get(pk=r.json()["step_id"])

                self.assertEqual((step.kind, step.x, step.y), (kind, 10, 20))

        notebook = JupyterNotebook.objects.get(pk=self.workflow.steps.get(kind="jupyter").config["notebook_id"])

        self.assertEqual((notebook.owner, notebook.notebook_json["metadata"]["biobank"]["template"]), (self.ana, "read_qc"))
        self.assertEqual(self.workflow.steps.get(kind="jupyter").config["parameters"]["min_quality"], "20")
        self.assertEqual(SubmissionPackage.objects.get(workflow=self.workflow).destination, "pdb")

    def test_unknown_block_and_missing_edit_rights_are_refused(self):
        self.assertEqual(self.post({"action": "add_block", "block": "notebook:nope"}).status_code, 400)
        self.assertEqual(self.post({"action": "add_block", "block": "submission:ftp"}).status_code, 400)

        self.client.force_login(self.bia)

        self.assertIn(self.post({"action": "add_block", "block": "manual"}).status_code, (400, 403, 404))
        self.assertEqual(self.workflow.steps.count(), 0)


class SubmissionStepKindTests(SubmissionBase):
    def test_a_submission_step_cannot_be_turned_into_something_else(self):
        workflow = Workflow.objects.create(name="W", owner=self.ana)
        response = self.client.post(
            reverse("workflow_api", args=[workflow.pk]), json.dumps({"action": "create_submission", "destination": "zenodo"}),
            content_type="application/json",
        )
        step = workflow.steps.get(pk=response.json()["step_id"])

        self.client.post(
            reverse("workflow_api", args=[workflow.pk]),
            json.dumps({"action": "update_step", "step_id": step.pk, "step": {"kind": "jupyter", "title": "Renamed"}}),
            content_type="application/json",
        )
        step.refresh_from_db()

        self.assertEqual(step.kind, "submission")
        self.assertEqual(step.title, "Renamed")
        self.assertTrue(step.config["package_id"])

    def test_the_type_selector_offers_the_kind_so_it_is_not_lost_on_save(self):
        workflow = Workflow.objects.create(name="W", owner=self.ana)
        page = self.client.get(reverse("workflow_detail", args=[workflow.pk])).content.decode()
        option = page.split('value="submission"')[1].split(">")[0]

        self.assertNotIn("disabled", option)


class GuideTests(SubmissionBase):
    def test_genbank_guide_tracks_what_is_missing(self):
        self.package.destination = "genbank"
        self.package.save()

        g = guides.guide(self.package)
        met = {r["key"]: r["met"] for r in g["requirements"]}

        self.assertFalse(met["sequences"])
        self.assertFalse(met["organism"])
        self.assertIsNone(met["library"])
        self.assertEqual(g["flow"][0]["state"], "current")
        self.assertEqual(g["portal"], "https://submit.ncbi.nlm.nih.gov/")

    def test_guide_goes_green_as_the_package_is_filled(self):
        self.seq.sequence = "ATGC" * 100
        self.seq.save()
        self.build_index()
        self.api({"action": "add_item", "kind": "sequence", "ref": self.seq.pk})
        self.package.destination = "genbank"
        self.package.save()
        self.assertEqual(self.api({"action": "update", "taxon_id": "1280", "metadata": {"authors": "Ana Silva"}}).status_code, 200)
        self.package.refresh_from_db()

        g = guides.guide(self.package)

        self.assertTrue(all(r["met"] for r in g["requirements"] if r["required"] and r["met"] is not None))
        self.assertIn("genbank/sequences.fsa", g["outputs"])
        self.assertEqual([n["state"] for n in g["flow"]][:2], ["done", "done"])

    def test_library_fields_become_required_when_reads_are_listed(self):
        self.package.destination = "genbank"
        self.package.metadata = {"sra_reads": SRA["sra_reads"]}
        self.package.save()

        library = next(r for r in guides.guide(self.package)["requirements"] if r["key"] == "library")

        self.assertTrue(library["required"])
        self.assertFalse(library["met"])

        self.package.metadata = SRA
        self.package.save()

        library = next(r for r in guides.guide(self.package)["requirements"] if r["key"] == "library")

        self.assertTrue(library["met"])

    def test_every_destination_has_a_guide_and_the_api_returns_it(self):
        for destination in ("internal", "genbank", "pdb", "zenodo"):
            self.package.destination = destination
            self.package.save()

            data = guides.guide(self.package)

            self.assertTrue(data["requirements"] and data["flow"] and data["summary"], destination)

        from core.services import submissions

        self.assertIn("guide", submissions.serialize(self.package, self.ana))

    def test_external_destinations_end_with_the_portal_and_the_reference(self):
        self.package.destination = "pdb"
        self.package.save()

        titles = [n["title"] for n in guides.guide(self.package)["flow"]]

        self.assertEqual(titles[-2:], ["Submit in the portal", "Record the reference"])

    def test_workflow_card_shows_flow_and_what_is_missing(self):
        workflow = Workflow.objects.create(name="W", owner=self.ana)
        response = self.client.post(
            reverse("workflow_api", args=[workflow.pk]), json.dumps({"action": "create_submission", "destination": "genbank"}),
            content_type="application/json",
        )
        info = next(s for s in response.json()["workflow"]["steps"] if s["kind"] == "submission")["submission"]

        self.assertIn("Submit in the portal", [n["title"] for n in info["flow"]])
        self.assertIn("Nucleotide sequence records", info["missing"])


class ReferenceTests(SubmissionBase):
    def refs(self, destination, text):
        self.package.destination = destination
        self.package.external_reference = text

        return guides.references(self.package)

    def test_genbank_accessions_runs_and_projects_are_recognised_and_linked(self):
        found = {r["text"]: r for r in self.refs("genbank", "MN908947.3, SRR1234567 PRJNA123456\nSAMN0001234 bogus")}

        self.assertEqual(found["MN908947.3"]["url"], "https://www.ncbi.nlm.nih.gov/nuccore/MN908947.3")
        self.assertEqual(found["SRR1234567"]["kind"], "SRA run")
        self.assertEqual(found["PRJNA123456"]["url"], "https://www.ncbi.nlm.nih.gov/bioproject/PRJNA123456")
        self.assertEqual(found["SAMN0001234"]["kind"], "BioSample")
        self.assertFalse(found["bogus"]["valid"])

    def test_pdb_ids_and_zenodo_dois(self):
        pdb = {r["text"]: r for r in self.refs("pdb", "1ABC 2023 pdb_00001abc")}

        self.assertEqual(pdb["1ABC"]["url"], "https://www.rcsb.org/structure/1ABC")
        self.assertFalse(pdb["2023"]["valid"], "a bare number is not a PDB id")
        self.assertTrue(pdb["pdb_00001abc"]["valid"])

        doi = self.refs("zenodo", "10.5281/zenodo.123456")[0]

        self.assertEqual(doi["url"], "https://doi.org/10.5281/zenodo.123456")

    def test_links_are_accepted_for_external_destinations_only_and_no_script_urls(self):
        self.assertTrue(self.refs("zenodo", "https://zenodo.org/deposit/1")[0]["valid"])
        self.assertFalse(self.refs("internal", "https://example.org/x")[0]["valid"])
        self.assertFalse(self.refs("zenodo", "javascript:alert(1)")[0]["valid"])

    def test_recording_a_valid_reference_completes_the_flow(self):
        self.package.destination = "genbank"
        self.package.status = "published"
        self.package.external_reference = "nonsense"
        self.package.save()

        self.assertNotEqual(guides.guide(self.package)["flow"][-1]["state"], "done")

        self.package.external_reference = "MN908947.3"
        self.package.save()

        self.assertEqual(guides.guide(self.package)["flow"][-1]["state"], "done")
        self.assertEqual(guides.guide(self.package)["references"][0]["kind"], "GenBank accession")
