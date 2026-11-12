from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


class InstallationContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ana", password="pw-12345678")
        self.client.force_login(self.user)

    @override_settings(BIOBANK_ORG_NAME="Lab Fictício", BIOBANK_JUPYTER_ENABLED=False)
    def test_footer_shows_the_configured_name_and_jupyter_explains_itself(self):
        page = self.client.get("/samples/")
        self.assertContains(page, "© Lab Fictício")
        self.assertNotContains(page, "CEPID")

        connect = self.client.get("/internal/lab-tools/jupyter/", follow=True)
        self.assertEqual(connect.redirect_chain[-1][0], "/internal/lab-tools/jupyter/connect/")
        self.assertContains(connect, "Use B3 LIMS data in Jupyter")
        self.assertNotContains(connect, "DaVinci")

        launch = self.client.get("/internal/lab-tools/jupyter/launch/")
        self.assertEqual(launch.status_code, 302)

    @override_settings(BIOBANK_JUPYTER_ENABLED=True)
    def test_hpc_installations_keep_the_launcher(self):
        page = self.client.get("/internal/lab-tools/jupyter/")
        self.assertEqual(page.status_code, 200)
