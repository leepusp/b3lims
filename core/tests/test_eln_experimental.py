"""Tests for the disabled-by-default ELN interface."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse

from core.permissions.eln_experimental import (
    can_access_eln_experimental,
)
from core.views.internal.lab_tools.eln_experimental import (
    eln_experimental_index,
)


class FakeGroups:
    def __init__(self, allowed=False):
        self.allowed = allowed

    def filter(self, **kwargs):
        return SimpleNamespace(
            exists=lambda: (
                self.allowed
                and kwargs.get("name") == "b3_eln_evaluators"
            )
        )


def make_user(*, evaluator=False, superuser=False):
    return SimpleNamespace(
        is_authenticated=True,
        is_superuser=superuser,
        groups=FakeGroups(evaluator),
    )


class ElnExperimentalTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=False)
    def test_disabled_for_evaluator(self):
        user = make_user(evaluator=True)
        self.assertFalse(can_access_eln_experimental(user))

        request = self.factory.get("/")
        request.user = user

        with self.assertRaises(Http404):
            eln_experimental_index(request)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_anonymous_user_has_no_access(self):
        self.assertFalse(
            can_access_eln_experimental(AnonymousUser())
        )

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_unauthorized_user_is_forbidden(self):
        request = self.factory.get("/")
        request.user = make_user()

        response = eln_experimental_index(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_evaluator_can_access(self):
        request = self.factory.get("/")
        request.user = make_user(evaluator=True)

        with patch(
            "core.views.internal.lab_tools."
            "eln_experimental.render",
            return_value=HttpResponse("ELN"),
        ) as render_mock:
            response = eln_experimental_index(request)

        self.assertEqual(response.status_code, 200)
        render_mock.assert_called_once()

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_superuser_can_access(self):
        self.assertTrue(
            can_access_eln_experimental(
                make_user(superuser=True)
            )
        )

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
    def test_non_evaluator_has_no_access(self):
        self.assertFalse(
            can_access_eln_experimental(make_user())
        )

    def test_registered_url(self):
        self.assertTrue(
            reverse("eln_experimental_index").endswith(
                "/internal/lab-tools/eln-experimental/"
            )
        )
