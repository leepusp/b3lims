from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from core.permissions.storage_workspaces_v8 import is_storage_global_admin
from core.services.geocoding import default_user_agent


class GlobalStorageAdminSettingTests(TestCase):
    def make(self, username, **flags):
        return get_user_model().objects.create_user(username=username, password="x-password-123", **flags)

    @override_settings(BIOBANK_STORAGE_GLOBAL_ADMINS=["boss"], BIOBANK_STORAGE_SUPERUSER_IS_GLOBAL_ADMIN=False)
    def test_only_named_staff_user_is_global_admin(self):
        self.assertTrue(is_storage_global_admin(self.make("Boss", is_staff=True)))
        self.assertFalse(is_storage_global_admin(self.make("boss2", is_staff=True)))
        self.assertFalse(is_storage_global_admin(self.make("outsider", is_superuser=True)))

    @override_settings(BIOBANK_STORAGE_GLOBAL_ADMINS=["boss"], BIOBANK_STORAGE_SUPERUSER_IS_GLOBAL_ADMIN=False)
    def test_named_user_without_staff_is_not_global_admin(self):
        self.assertFalse(is_storage_global_admin(self.make("boss")))

    @override_settings(BIOBANK_STORAGE_GLOBAL_ADMINS=[], BIOBANK_STORAGE_SUPERUSER_IS_GLOBAL_ADMIN=True)
    def test_single_lab_superuser_is_global_admin(self):
        self.assertTrue(is_storage_global_admin(self.make("first-admin", is_superuser=True, is_staff=True)))
        self.assertFalse(is_storage_global_admin(self.make("member", is_staff=True)))


class GeocodingUserAgentTests(SimpleTestCase):
    @override_settings(BIOBANK_PUBLIC_URL="")
    def test_without_public_url_no_contact_is_sent(self):
        self.assertEqual(default_user_agent(), "B3-LIMS/1.0")

    @override_settings(BIOBANK_PUBLIC_URL="https://lims.example.org/")
    def test_public_url_is_used_as_contact(self):
        self.assertEqual(default_user_agent(), "B3-LIMS/1.0 (+https://lims.example.org/)")
