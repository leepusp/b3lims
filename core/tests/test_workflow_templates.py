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

    def test_analysis_steps_carry_starter_parameters_and_instructions(self):
        self.post({"action": "apply_template", "template": "blast_search"})

        blast = self.workflow.steps.get(title="Run BLAST")

        self.assertEqual(blast.kind, "jupyter")
        self.assertEqual(blast.config["parameters"], {"db": "nt", "evalue": "1e-5"})
        self.assertIn("database", blast.notes)

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
        catalog = templates.catalog()

        self.assertEqual(len(catalog), len(templates.TEMPLATES))
        self.assertTrue(all(c["inputs"] and c["steps"] for c in catalog))

        page = self.client.get(reverse("workflow_detail", args=[self.workflow.pk]))

        self.assertContains(page, "wf-templates-data")
        self.assertContains(page, "Assembled sequence to GenBank")


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
