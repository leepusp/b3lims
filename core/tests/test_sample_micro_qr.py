import re

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Sample
from core.models.samples.sample import (
    SAMPLE_MICRO_QR_ALPHABET,
    SAMPLE_MICRO_QR_TOKEN_LENGTH,
    generate_sample_micro_qr_token,
)


TOKEN_PATTERN = re.compile(
    r"^[2-9A-HJ-NP-Z]{10}$"
)


class SampleMicroQrTokenTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="sample-micro-qr-owner",
            password="test-password",
        )

    def test_alphabet_contract(self):
        self.assertEqual(
            len(SAMPLE_MICRO_QR_ALPHABET),
            32,
        )

        self.assertEqual(
            len(set(SAMPLE_MICRO_QR_ALPHABET)),
            32,
        )

        for ambiguous in (
            "0",
            "1",
            "I",
            "O",
        ):
            self.assertNotIn(
                ambiguous,
                SAMPLE_MICRO_QR_ALPHABET,
            )

    def test_generator_contract(self):
        token = generate_sample_micro_qr_token()

        self.assertEqual(
            len(token),
            SAMPLE_MICRO_QR_TOKEN_LENGTH,
        )

        self.assertRegex(
            token,
            TOKEN_PATTERN,
        )

    def test_new_sample_receives_micro_qr_token(self):
        sample = Sample.objects.create(
            sample_id="MICRO-QR-TEST-0001",
            owner=self.owner,
        )

        self.assertEqual(
            len(sample.micro_qr_token),
            10,
        )

        self.assertRegex(
            sample.micro_qr_token,
            TOKEN_PATTERN,
        )

    def test_tokens_are_unique_across_new_samples(self):
        tokens = set()

        for index in range(25):
            sample = Sample.objects.create(
                sample_id=(
                    f"MICRO-QR-TEST-{index + 100:04d}"
                ),
                owner=self.owner,
            )

            tokens.add(
                sample.micro_qr_token
            )

        self.assertEqual(
            len(tokens),
            25,
        )

    def test_model_field_contract(self):
        field = Sample._meta.get_field(
            "micro_qr_token"
        )

        self.assertEqual(
            field.max_length,
            10,
        )

        self.assertTrue(
            field.unique,
        )

        self.assertFalse(
            field.editable,
        )

        self.assertFalse(
            field.null,
        )

        self.assertIs(
            field.default,
            generate_sample_micro_qr_token,
        )
