"""The retired ELN Experimental URL redirects to the canonical Notebook."""

from django.urls import reverse
from django.test import SimpleTestCase


class ElnExperimentalRouteTests(SimpleTestCase):
    def test_registered_url(self):
        self.assertTrue(
            reverse("eln_experimental_index").endswith(
                "/internal/lab-tools/eln-experimental/"
            )
        )
