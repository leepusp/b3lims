from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import Sample
from core.models.lab_tools.notebook import MolecularSequence, NotebookEntry
from core.models.samples.storage import SampleStorageAssignment


class SeedDemoTests(TestCase):
    def test_seed_demo_creates_lab_and_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        self.assertTrue(get_user_model().objects.filter(username="demo").exists())
        samples = Sample.objects.count()
        self.assertEqual(samples, 17)
        self.assertEqual(SampleStorageAssignment.objects.count(), 17)
        self.assertGreaterEqual(MolecularSequence.objects.count(), 4)
        self.assertEqual(NotebookEntry.objects.count(), 3)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Sample.objects.count(), samples)
