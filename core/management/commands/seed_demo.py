"""Load a small, clearly fictional demonstration lab (used for screenshots and first-run exploration).

    python manage.py seed_demo            # or: biobank-local setup --demo

Everything is created under the user "demo" and the research group "Demo Lab"; running it again
does nothing. Sequences are synthetic and are not real constructs.
"""

import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client

from core.models import Biobank, Collection, ResearchGroup, Sample
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.lab_tools.notebook import MolecularFeature, MolecularSequence, NotebookEntry, NotebookSampleLink
from core.models.samples.storage import StorageLocation
from core.services.storage_registration_v8 import register_initial_physical_storage

DEMO_USER = "demo"
DEMO_GROUP = "Demo Lab"

BACTERIA = [
    ("Escherichia coli K-12 MG1655", "NB-1"),
    ("Escherichia coli BL21(DE3)", "NB-1"),
    ("Pseudomonas aeruginosa PAO1", "NB-2"),
    ("Klebsiella pneumoniae ATCC 13883", "NB-2"),
    ("Bacillus subtilis 168", "NB-1"),
    ("Salmonella enterica Typhimurium LT2", "NB-2"),
    ("Staphylococcus aureus RN4220", "NB-2"),
    ("Acinetobacter baumannii ATCC 19606", "NB-2"),
]
PHAGES = [
    ("Escherichia phage T4", "NB-1"),
    ("Escherichia phage lambda", "NB-1"),
    ("Pseudomonas phage PhiKZ", "NB-2"),
    ("Klebsiella phage KP32", "NB-2"),
    ("Staphylococcus phage K", "NB-2"),
]
PLASMIDS = ["pDEMO-GFP", "pDEMO-KanR", "pDEMO-Express", "pDEMO-Reporter"]
BOXES = ["Box 1", "Box 2", "Box 3"]


def synthetic_dna(length, seed):
    rng = random.Random(seed)

    return "".join(rng.choice("ACGT") for _ in range(length))


class Command(BaseCommand):
    help = "Load a small fictional demonstration lab (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        if User.objects.filter(username=DEMO_USER).exists():
            self.stdout.write("Demo data already present; nothing to do.")

            return

        user = User.objects.create_user(
            DEMO_USER, "demo@example.org", "demo-password-123",
            first_name="Dana", last_name="Demo", is_staff=False,
        )
        group = ResearchGroup.objects.create(name=DEMO_GROUP, description="Fictional lab used for demonstrations.", coordinator=user)
        group.members.add(user)
        biobank = Biobank.objects.create(
            name="Demo Biobank", description="Example collection of bacteria, phages and plasmids.",
            location_label="Building A, room 12", owner=user, research_group=group, is_public=False,
        )
        BiobankUserRole.objects.get_or_create(user=user, biobank=biobank, defaults={"role": "owner"})
        collection = Collection.objects.create(
            name="Reference strains", description="Reference strains and their phages.",
            owner=user, research_group=group, is_public=False,
        )

        self.make_storage(user)
        samples = self.make_samples(user, group, biobank, collection)
        self.make_molecules(user)
        self.make_notebook(user, group, samples)

        self.stdout.write(self.style.SUCCESS(
            f"Demo lab loaded. Sign in as '{DEMO_USER}' with password 'demo-password-123' (change it after exploring)."
        ))

    # ------------------------------------------------------------------ storage

    def make_storage(self, user):
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)

        self.boxes = {}

        for box in BOXES:
            response = client.post(
                self.register_url(),
                {"workspace_id": "", "path": f"Demo Lab > Freezer -80 A > Rack 1 > {box}",
                 "organization": "grid", "rows": "9", "columns": "9"},
            )

            if response.status_code >= 300:
                self.stderr.write(f"Could not register {box}: {response.content[:200]!r}")
            else:
                self.boxes[box] = StorageLocation.objects.get(pk=response.json()["anchor"]["id"])

        client.post(
            self.register_url(),
            {"workspace_id": "", "path": "Demo Lab > Cabinet 2 > Shelves", "organization": "slots",
             "slot_label": ["Top shelf", "Middle shelf", "Bottom shelf"], "slot_direction": "column"},
        )

    @staticmethod
    def register_url():
        from django.urls import reverse

        return reverse("storage_path_register_v8146")

    # ------------------------------------------------------------------ samples

    def make_samples(self, user, group, biobank, collection):
        rows, cols = "ABCDEFGHI", range(1, 10)
        positions = [f"{r}{c}" for r in rows for c in cols]
        samples = []
        index = 0

        def add(prefix, number, kind, organism, level, notes, position, box):
            nonlocal index
            sample = Sample.objects.create(
                sample_id=f"{prefix}-{number:03d}", sample_type=kind, organism_name=organism,
                biosafety_level=level, biobank=biobank, owner=user, research_group=group,
                status="available", scientific_notes=notes,
            )
            sample.collections.add(collection)
            register_initial_physical_storage(
                sample=sample, box=self.boxes[box], position=position, actor=user, mode="new", expected_legacy_path="",
            )
            samples.append(sample)
            index += 1

            return sample

        for number, (name, level) in enumerate(BACTERIA, start=1):
            add("BAC", number, "Bacterium", name, level, f"Glycerol stock of {name}.", positions[index], BOXES[0])

        for number, (name, level) in enumerate(PHAGES, start=1):
            add("PHA", number, "Phage", name, level, f"High-titre lysate of {name}.", positions[index], BOXES[1])

        for number, name in enumerate(PLASMIDS, start=1):
            add("PLA", number, "Plasmid", name, "NB-1", f"Miniprep of {name}.", positions[index], BOXES[2])

        return samples

    # ------------------------------------------------------------------ molecular records

    def make_molecules(self, user):
        plasmid = MolecularSequence.objects.create(
            name="pDEMO-GFP (synthetic)", sequence_type="plasmid", topology="circular",
            sequence=synthetic_dna(3200, 1), description="Synthetic example; not a real construct.", owner=user,
        )

        for order, (name, kind, start, end, strand, color) in enumerate([
            ("Promoter", "promoter", 120, 220, "+", "#2b8a3e"),
            ("RBS", "rbs", 221, 240, "+", "#e67700"),
            ("GFP (example)", "cds", 241, 960, "+", "#1c7ed6"),
            ("Terminator", "terminator", 961, 1050, "+", "#c92a2a"),
            ("KanR", "antibiotic", 1500, 2300, "-", "#7048e8"),
            ("ori", "ori", 2400, 3000, "+", "#868e96"),
        ]):
            MolecularFeature.objects.create(
                molecule=plasmid, name=name, feature_type=kind, start=start, end=end, strand=strand, color=color, order=order,
            )

        MolecularSequence.objects.create(
            name="Insert-1 (synthetic)", sequence_type="dna", topology="linear",
            sequence=synthetic_dna(900, 2), owner=user,
        )
        MolecularSequence.objects.create(
            name="DEMO-Fwd", sequence_type="primer", topology="linear",
            sequence="ATGGCTAGCAAAGGAGAAGAACTTTTC", description="Forward primer, example.", owner=user,
        )
        MolecularSequence.objects.create(
            name="DEMO-Rev", sequence_type="primer", topology="linear",
            sequence="TTATTTGTAGAGCTCATCCATGCC", description="Reverse primer, example.", owner=user,
        )
        MolecularSequence.objects.create(
            name="Demo fluorescent protein (example)", sequence_type="protein", topology="linear",
            sequence="MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTFGYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK",
            owner=user,
        )

    # ------------------------------------------------------------------ notebook

    def make_notebook(self, user, group, samples):
        today = date.today()
        entries = [
            ("Phage host range on reference strains", "experiment", "completed", today - timedelta(days=6),
             "<h2>Aim</h2><p>Test whether the phages in the collection lyse the reference bacteria.</p>"
             "<h2>Method</h2><p>Spot assay, 10 &micro;L of each lysate on a lawn, 37 &deg;C overnight.</p>"
             "<h2>Result</h2><p>Clear zones for T4 and lambda on <em>E. coli</em>; none on <em>P. aeruginosa</em>.</p>"),
            ("Transformation of pDEMO-GFP into BL21(DE3)", "experiment", "in_progress", today - timedelta(days=2),
             "<h2>Aim</h2><p>Express the example reporter in BL21(DE3).</p>"
             "<ol><li>Thaw competent cells on ice.</li><li>Add 50 ng plasmid, heat shock 42 &deg;C, 45 s.</li>"
             "<li>Recover 1 h in SOC, plate on kanamycin.</li></ol>"),
            ("Glycerol stock preparation", "protocol", "reviewed", today - timedelta(days=20),
             "<p>Mix 500 &micro;L overnight culture with 500 &micro;L 50 % glycerol, freeze at &minus;80 &deg;C.</p>"),
        ]

        for position, (title, kind, status, when, html) in enumerate(entries):
            entry = NotebookEntry.objects.create(
                title=title, entry_type=kind, status=status, experiment_date=when, content=html,
                research_group=group, author=user, visibility="lab",
            )

            for sample in samples[position * 3: position * 3 + 3]:
                NotebookSampleLink.objects.create(entry=entry, sample=sample, linked_by=user)
