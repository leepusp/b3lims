from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Sample


class SampleAliquotBatchLabelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="aliquot-label-owner",
            password="test-password",
        )

        cls.outsider = User.objects.create_user(
            username="aliquot-label-outsider",
            password="test-password",
        )

        cls.aliquot_1 = Sample.objects.create(
            sample_id="BATCH-LABEL_1.1",
            sample_type="Other",
            organism_name="Batch label sample",
            owner=cls.owner,
            aliquot_count=1,
        )

        cls.aliquot_2 = Sample.objects.create(
            sample_id="BATCH-LABEL_1.2",
            sample_type="Other",
            organism_name="Batch label sample",
            owner=cls.owner,
            aliquot_count=1,
        )

        cls.hidden = Sample.objects.create(
            sample_id="BATCH-HIDDEN_1.1",
            sample_type="Other",
            organism_name="Hidden batch sample",
            owner=cls.outsider,
            aliquot_count=1,
            is_public=False,
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        ).rstrip("/")

        if prefix and url.startswith(
            prefix + "/"
        ):
            return url[
                len(prefix):
            ]

        return url

    def batch_url(self, *samples):
        base = reverse(
            "print_sample_labels"
        )

        query = "&".join(
            f"sample={sample.pk}"
            for sample in samples
        )

        return self.client_path(
            f"{base}?{query}"
        )

    def test_batch_print_renders_one_label_per_aliquot(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.batch_url(
                self.aliquot_1,
                self.aliquot_2,
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "internal/samples/print_labels.html",
        )

        self.assertContains(
            response,
            'data-sample-label="physical-aliquot"',
            count=2,
        )

        self.assertContains(
            response,
            self.aliquot_1.sample_id,
        )

        self.assertContains(
            response,
            self.aliquot_2.sample_id,
        )

        self.assertContains(
            response,
            self.aliquot_1.micro_qr_token,
        )

        self.assertContains(
            response,
            self.aliquot_2.micro_qr_token,
        )

        self.assertNotEqual(
            self.aliquot_1.micro_qr_token,
            self.aliquot_2.micro_qr_token,
        )

    def test_batch_print_rejects_sample_not_visible_to_user(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.batch_url(
                self.aliquot_1,
                self.hidden,
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_batch_print_requires_at_least_one_sample(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "print_sample_labels"
                )
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )
