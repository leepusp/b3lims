from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import NotebookEntry


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(
    FORCE_SCRIPT_NAME=None,
    BIOBANK_JUPYTER_PARTITION="max50",
    BIOBANK_JUPYTER_PARTITIONS=("basic", "max50"),
)
class ElnJupyterPartitionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="jupyter-partition-admin",
            password="test-password",
            email="jupyter@example.org",
        )
        self.client.force_login(self.user)

    def test_launch_form_offers_approved_partitions(self):
        response = self.client.get(
            request_path("notebook_jupyter_launch")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'value="basic"',
            html=False,
        )
        self.assertContains(
            response,
            'value="max50"',
            html=False,
        )

    @patch(
        "core.views.internal.lab_tools.notebook."
        "persist_document"
    )
    @patch(
        "core.views.internal.lab_tools.notebook."
        "submit_document"
    )
    def test_basic_partition_reaches_submission(
        self,
        submit_document_mock,
        persist_document_mock,
    ):
        response = self.client.post(
            request_path("notebook_jupyter_launch"),
            {
                "title": "Basic partition analysis",
                "partition": "basic",
                "cpus": "2",
                "memory_mb": "4096",
                "hours": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            NotebookEntry.objects.filter(
                title="Basic partition analysis"
            ).exists()
        )

        submit_document_mock.assert_called_once()
        self.assertEqual(
            submit_document_mock.call_args.kwargs[
                "partition"
            ],
            "basic",
        )
        self.assertEqual(
            submit_document_mock.call_args.kwargs["cpus"],
            2,
        )
        self.assertEqual(
            submit_document_mock.call_args.kwargs[
                "memory_mb"
            ],
            4096,
        )

    def test_regular_eln_has_no_embedded_jupyter_tab(self):
        entry = NotebookEntry.objects.create(
            title="Regular ELN note",
            author=self.user,
            visibility="private",
        )

        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={entry.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            'id="jupyter-tab"',
        )
        self.assertNotContains(
            response,
            'id="jupyter-pane"',
        )
        self.assertNotContains(
            response,
            "notebook_jupyter.js",
        )
