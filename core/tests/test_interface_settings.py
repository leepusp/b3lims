from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.interface_settings import InterfaceSettings
from core.services import interface_settings


class InterfaceSettingsTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        model = get_user_model()
        self.admin = model.objects.create_user("boss", password="pw-12345678", is_staff=True)
        self.member = model.objects.create_user("ana", password="pw-12345678")

    def test_everything_is_visible_by_default(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse("samples_list"))

        self.assertContains(page, "ELN Notebook")
        self.assertContains(page, "Chemicals")
        self.assertNotContains(page, "Interface</span>")

    def test_only_administrators_open_the_panel(self):
        self.client.force_login(self.member)

        self.assertEqual(self.client.get(reverse("interface_settings")).status_code, 403)
        self.assertEqual(self.client.post(reverse("interface_settings"), {}).status_code, 403)
        self.assertFalse(InterfaceSettings.objects.exists())

    def test_hidden_items_leave_the_menu_and_the_new_sample_form(self):
        self.client.force_login(self.admin)
        every = [key for key, _ in interface_settings.FEATURES]
        keep = [k for k in every if k not in {"eln", "chemicals"}]
        saved = self.client.post(reverse("interface_settings"), {
            "show_feature": keep, "show_type": ["Other"],
        })

        self.assertEqual(saved.status_code, 302)
        row = InterfaceSettings.objects.get()
        self.assertEqual(set(row.hidden_features), {"eln", "chemicals"})
        self.assertEqual(set(row.hidden_sample_types), {"Bacterium (Host)", "Phage (Virus)", "Plasmid"})

        menu = self.client.get(reverse("samples_list"))
        self.assertNotContains(menu, "ELN Notebook")
        self.assertNotContains(menu, "Chemicals")
        self.assertContains(menu, "Molecular Registry")
        self.assertContains(menu, "Interface</span>")

        form = self.client.get(reverse("sample_add"))
        self.assertNotContains(form, '<option value="Plasmid"')
        self.assertContains(form, '<option value="Other"')
