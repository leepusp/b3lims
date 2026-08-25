from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import ResearchGroup, UserProfile


User = get_user_model()


def request_path(name, args=None):
    external_path = reverse(
        name,
        args=args,
    )

    prefix = (
        settings.FORCE_SCRIPT_NAME or ""
    ).rstrip("/")

    if prefix and external_path.startswith(prefix + "/"):
        return external_path[len(prefix):]

    return external_path


class UserProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile-user",
            email="before@example.org",
        )
        self.client.force_login(self.user)
        self.external_url = reverse("user_profile")
        self.url = request_path("user_profile")

    def profile_payload(self, **overrides):
        payload = {
            "action": "update_profile",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.org",
            "preferred_name": "Ada",
            "institution": "B3 Research Institute",
            "department": "Genome Laboratory",
            "orcid": "0000-0002-1825-0097",
            "phone": "+55 11 5555-0100",
            "expertise": "Genome analysis",
            "biography": "Researcher profile biography.",
            "profile_visibility": UserProfile.Visibility.MEMBERS,
        }
        payload.update(overrides)
        return payload

    def test_profile_page_does_not_create_a_row_on_get(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scientific Identity")
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_update_persists_user_and_scientific_identity(self):
        response = self.client.post(self.url, self.profile_payload())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self.external_url,
        )
        self.user.refresh_from_db()
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.last_name, "Lovelace")
        self.assertEqual(self.user.email, "ada@example.org")
        self.assertEqual(profile.preferred_name, "Ada")
        self.assertEqual(profile.orcid, "0000-0002-1825-0097")
        self.assertEqual(profile.institution, "B3 Research Institute")

    def test_invalid_orcid_is_rejected_without_writes(self):
        response = self.client.post(
            self.url,
            self.profile_payload(orcid="0000-0002-1825-0098"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid ORCID checksum.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "before@example.org")
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())

    def test_username_is_not_editable_through_profile_form(self):
        payload = self.profile_payload()
        payload["username"] = "changed-username"

        self.client.post(self.url, payload)

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile-user")

    def test_coordinator_can_add_a_research_group_member(self):
        member = User.objects.create_user(
            username="new-member",
            email="member@example.org",
        )
        group = ResearchGroup.objects.create(
            name="Genome Group",
            coordinator=self.user,
        )

        response = self.client.post(
            self.url,
            {
                "action": "add_member",
                "group_id": group.id,
                "member_identifier": "member@example.org",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self.external_url,
        )
        self.assertTrue(group.members.filter(id=member.id).exists())

    def test_non_coordinator_cannot_add_a_group_member(self):
        coordinator = User.objects.create_user(username="coordinator")
        member = User.objects.create_user(username="blocked-member")
        group = ResearchGroup.objects.create(
            name="Protected Group",
            coordinator=coordinator,
        )

        response = self.client.post(
            self.url,
            {
                "action": "add_member",
                "group_id": group.id,
                "member_identifier": member.username,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self.external_url,
        )
        self.assertFalse(group.members.filter(id=member.id).exists())

    def test_profile_does_not_duplicate_scoped_roles_or_groups(self):
        field_names = {field.name for field in UserProfile._meta.get_fields()}

        self.assertNotIn("role", field_names)
        self.assertNotIn("research_group", field_names)
        self.assertNotIn("research_groups", field_names)
