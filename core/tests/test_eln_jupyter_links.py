from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    JupyterNotebook,
    NotebookEntry,
    NotebookJupyterLink,
)


def request_path(name, args=None):
    path = reverse(name, args=args)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNJupyterLinkTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="jupyter-link-owner",
        )
        self.other_user = (
            get_user_model().objects.create_user(
                username="jupyter-link-other",
            )
        )
        self.client.force_login(self.user)

        self.entry = NotebookEntry.objects.create(
            title="Notebook attachment experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )
        self.notebook = JupyterNotebook.objects.create(
            title="Reusable analysis",
            owner=self.user,
            updated_by=self.user,
            notebook_json={
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
        )

    def test_existing_notebook_can_be_attached(self):
        response = self.client.post(
            request_path(
                "notebook_link_jupyter",
                [self.entry.id],
            ),
            {
                "notebook_id": self.notebook.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            NotebookJupyterLink.objects.filter(
                entry=self.entry,
                notebook=self.notebook,
            ).exists()
        )

    def test_detach_preserves_notebook(self):
        link = NotebookJupyterLink.objects.create(
            entry=self.entry,
            notebook=self.notebook,
            linked_by=self.user,
        )

        response = self.client.post(
            request_path(
                "notebook_unlink_jupyter",
                [
                    self.entry.id,
                    link.id,
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            NotebookJupyterLink.objects.filter(
                id=link.id
            ).exists()
        )
        self.assertTrue(
            JupyterNotebook.objects.filter(
                id=self.notebook.id
            ).exists()
        )

    def test_other_users_notebook_cannot_be_attached(self):
        other_notebook = JupyterNotebook.objects.create(
            title="Other private notebook",
            owner=self.other_user,
            updated_by=self.other_user,
            notebook_json={
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
        )

        response = self.client.post(
            request_path(
                "notebook_link_jupyter",
                [self.entry.id],
            ),
            {
                "notebook_id": other_notebook.id,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            NotebookJupyterLink.objects.filter(
                notebook=other_notebook
            ).exists()
        )

    def test_eln_displays_attachment_interface(self):
        response = self.client.get(
            request_path("notebook_index"),
            {
                "entry_id": self.entry.id,
                "tab": "items",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Attach notebook",
        )

        NotebookJupyterLink.objects.create(
            entry=self.entry,
            notebook=self.notebook,
            linked_by=self.user,
        )

        response = self.client.get(
            request_path("notebook_index"),
            {
                "entry_id": self.entry.id,
                "tab": "items",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.notebook.title,
        )
        self.assertContains(
            response,
            "The notebook will not be deleted",
        )
        self.assertContains(
            response,
            "Attach notebook",
        )
        self.assertNotContains(
            response,
            "Create analysis",
        )
        self.assertNotContains(
            response,
            "Continue analysis",
        )

    def test_attached_notebook_is_excluded_from_options(self):
        NotebookJupyterLink.objects.create(
            entry=self.entry,
            notebook=self.notebook,
            linked_by=self.user,
        )

        self.assertFalse(
            self.entry.available_jupyter_notebooks()
            .filter(id=self.notebook.id)
            .exists()
        )

    def test_jupyter_empty_state_has_one_creation_action(self):
        response = self.client.get(
            request_path("jupyter_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "New Jupyter notebook",
            count=1,
        )
        self.assertNotContains(
            response,
            "Launch Notebook",
        )
