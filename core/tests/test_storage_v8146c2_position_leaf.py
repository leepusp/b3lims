"""Position-as-final-level semantics for B3 LIMS V8.14.6C2."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_anchor_v8 import (
    validate_storage_anchor_plan,
)
from core.services.storage_sample_intake_v8 import (
    prepare_storage_sample_intake_v8,
)
from core.services.storage_position_names_v8146c2 import (
    normalize_physical_position_v8146c2,
)


class StoragePositionLeafC2Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="c2-storage-owner",
            is_staff=True,
        )

        cls.workspace = StorageWorkspace.objects.create(
            name="C2 physical hierarchy",
            scope="personal",
            owner=cls.owner,
        )

        cls.root = StorageLocation.objects.create(
            name="Freezer 1",
            location_type="other",
            workspace=cls.workspace,
        )

        cls.box = StorageLocation.objects.create(
            name="Caixa A",
            location_type="other",
            parent=cls.root,
            workspace=cls.workspace,
        )

    def make_plan(self, position, *, leaf=True):
        text = self.box.full_path

        if leaf:
            text += " > " + position

        return prepare_storage_sample_intake_v8(
            mode="physical",
            storage_text=text,
            anchor_id=str(self.box.pk),
            positions=[position],
            expected_samples=1,
            actor=self.owner,
            position_leaf_mode=leaf,
        )

    def test_arbitrary_position_preserves_user_spelling(self):
        self.assertEqual(
            normalize_physical_position_v8146c2(" posição azul "),
            "posição azul",
        )

    def test_legacy_codes_are_uppercase(self):
        self.assertEqual(
            normalize_physical_position_v8146c2("a1"),
            "A1",
        )
        self.assertEqual(
            normalize_physical_position_v8146c2("p03"),
            "P03",
        )

    def test_custom_names_keep_their_spelling(self):
        self.assertEqual(
            normalize_physical_position_v8146c2("posição azul"),
            "posição azul",
        )
        self.assertEqual(
            normalize_physical_position_v8146c2("Tubo 01"),
            "Tubo 01",
        )

    def test_position_leaf_uses_parent_as_physical_anchor(self):
        plan = self.make_plan("posição azul")

        self.assertEqual(plan.target_id, self.box.pk)
        self.assertEqual(plan.positions, ("posição azul",))
        self.assertEqual(plan.mode, "physical")

    def test_lowercase_legacy_leaf_matches_canonical_position(self):
        plan = self.make_plan("a1")

        self.assertEqual(plan.target_id, self.box.pk)
        self.assertEqual(plan.positions, ("A1",))
        self.assertEqual(plan.mode, "physical")

    def test_original_anchor_only_contract_is_preserved(self):
        plan = self.make_plan("A4", leaf=False)

        self.assertEqual(plan.target_id, self.box.pk)
        self.assertEqual(plan.positions, ("A4",))

    def test_leaf_mode_rejects_different_visual_path(self):
        with self.assertRaises(ValidationError):
            prepare_storage_sample_intake_v8(
                mode="physical",
                storage_text="Freezer 1 > Outra Caixa > A4",
                anchor_id=str(self.box.pk),
                positions=["A4"],
                expected_samples=1,
                actor=self.owner,
                position_leaf_mode=True,
            )

    def test_position_names_support_spaces_and_accents(self):
        plan = validate_storage_anchor_plan(
            mode="physical",
            box_id=self.box.pk,
            positions=["Posição Azul", "Tubo 01"],
            expected_samples=2,
            actor=self.owner,
        )

        self.assertEqual(
            plan.positions,
            ("Posição Azul", "Tubo 01"),
        )

    def test_position_duplicates_are_case_insensitive(self):
        with self.assertRaises(ValidationError):
            validate_storage_anchor_plan(
                mode="physical",
                box_id=self.box.pk,
                positions=["Tubo Azul", "tubo azul"],
                expected_samples=2,
                actor=self.owner,
            )

    def test_position_rejects_hierarchy_separator(self):
        for name in ("A > B", "A;B", "A,B", "A\nB", ""):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    normalize_physical_position_v8146c2(name)

    def test_long_position_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_physical_position_v8146c2("X" * 101)

    def test_layout_uses_side_by_side_columns(self):
        template = (
            Path(settings.BASE_DIR) /
            "core/interfaces/internal/samples/samples.html"
        ).read_text()

        self.assertIn('class="b3s-one-path"', template)
        self.assertIn('class="b3s-one-ws"', template)
        self.assertIn(
            'id="storage_position_leaf_v8146c2"',
            template,
        )

    def test_new_sample_uses_parent_and_position_separately(self):
        js = (
            Path(settings.BASE_DIR) /
            "core/static/internal/samples/storage_child_v8146.js"
        ).read_text()

        self.assertIn("samplePosition = parts.pop()", js)
        self.assertIn('hierarchyPath = parts.join(" > ")', js)
        self.assertIn("samplePosition: sampleIntake", js)
