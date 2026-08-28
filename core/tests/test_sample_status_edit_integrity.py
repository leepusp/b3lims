from django.conf import settings
from django.contrib.auth import get_user_model
from django.forms import CheckboxInput
from django.test import (
    RequestFactory,
    TestCase,
)
from django.urls import reverse

from core.forms import SampleForm
from core.models import Sample
from core.views.internal.samples.views import (
    _sync_sample_after_successful_edit,
)


User = get_user_model()


class SampleStatusEditIntegrityTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="sample-status-owner",
        )

    @staticmethod
    def client_path(
        url,
    ):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if (
            prefix
            and url.startswith(
                prefix
            )
        ):
            return (
                url[
                    len(prefix):
                ]
                or "/"
            )

        return url

    def sample(
        self,
        sample_id,
        *,
        status="pending",
    ):
        return Sample.objects.create(
            sample_id=sample_id,
            sample_type="Other",
            organism_name=sample_id,
            owner=self.owner,
            status=status,
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

    def edit_url(
        self,
        sample,
    ):
        return self.client_path(
            reverse(
                "sample_edit",
                args=[
                    sample.pk,
                ],
            )
        )

    def form_data(
        self,
        sample,
    ):
        form = SampleForm(
            instance=sample,
            user=self.owner,
        )

        data = {}

        for name, field in form.fields.items():
            if field.disabled:
                continue

            value = form[
                name
            ].value()

            if isinstance(
                field.widget,
                CheckboxInput,
            ):
                if value:
                    data[
                        name
                    ] = "on"

                continue

            if isinstance(
                value,
                (
                    list,
                    tuple,
                ),
            ):
                data[
                    name
                ] = [
                    str(
                        item
                    )
                    for item in value
                    if item not in (
                        None,
                        "",
                    )
                ]

            elif value is None:
                data[
                    name
                ] = ""

            else:
                data[
                    name
                ] = str(
                    value
                )

        return data

    def test_existing_sample_status_is_server_side_disabled(
        self,
    ):
        sample = self.sample(
            "STATUS-LOCK-001",
            status="qc",
        )

        form = SampleForm(
            instance=sample,
            user=self.owner,
        )

        self.assertTrue(
            form.fields[
                "status"
            ].disabled
        )

        self.assertIn(
            "preserved",
            form.fields[
                "status"
            ].help_text.lower(),
        )

    def test_existing_status_is_locked_without_explicit_user_context(
        self,
    ):
        sample = self.sample(
            "STATUS-LOCK-002",
            status="rejected",
        )

        form = SampleForm(
            instance=sample,
        )

        self.assertTrue(
            form.fields[
                "status"
            ].disabled
        )

    def test_new_sample_registration_keeps_status_editable(
        self,
    ):
        form = SampleForm(
            user=self.owner,
        )

        self.assertFalse(
            form.fields[
                "status"
            ].disabled
        )

    def test_crafted_post_cannot_change_existing_status(
        self,
    ):
        sample = self.sample(
            "STATUS-TAMPER-001",
            status="qc",
        )

        data = self.form_data(
            sample
        )

        data[
            "status"
        ] = "available"

        form = SampleForm(
            data=data,
            instance=sample,
            user=self.owner,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        form.save()

        sample.refresh_from_db()

        self.assertEqual(
            sample.status,
            "qc",
        )

    def test_post_edit_sync_preserves_status(
        self,
    ):
        sample = self.sample(
            "STATUS-SYNC-001",
            status="pending",
        )

        request = RequestFactory().post(
            "/",
            {
                "organism_name": (
                    "Updated display identity"
                ),
            },
        )

        _sync_sample_after_successful_edit(
            base_sample=sample,
            real_sample=sample,
            request=request,
            identity_before=(
                sample.organism_name
            ),
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.status,
            "pending",
        )

    def test_standard_edit_view_preserves_every_sample_status(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        statuses = [
            value
            for value, _label
            in Sample.STATUS_CHOICES
        ]

        self.assertEqual(
            statuses,
            [
                "pending",
                "qc",
                "available",
                "rejected",
                "depleted",
            ],
        )

        for index, status in enumerate(
            statuses,
            start=1,
        ):
            with self.subTest(
                status=status
            ):
                sample = self.sample(
                    (
                        "STATUS-VIEW-"
                        f"{index:03d}"
                    ),
                    status=status,
                )

                data = self.form_data(
                    sample
                )

                data[
                    "notes"
                ] = (
                    "Metadata changed without "
                    "status transition."
                )

                # Crafted status POST must not override the
                # existing workflow state either.
                data[
                    "status"
                ] = (
                    "available"
                    if status != "available"
                    else "rejected"
                )

                response = self.client.post(
                    self.edit_url(
                        sample
                    ),
                    data=data,
                )

                self.assertEqual(
                    response.status_code,
                    302,
                )

                sample.refresh_from_db()

                self.assertEqual(
                    sample.status,
                    status,
                )

                self.assertEqual(
                    sample.notes,
                    (
                        "Metadata changed without "
                        "status transition."
                    ),
                )
