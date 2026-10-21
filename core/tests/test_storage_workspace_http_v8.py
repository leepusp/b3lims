from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.research_groups.model import ResearchGroup
from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)


class _StorageActionRowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current = {"text": [], "actions": []}
        elif self.current is not None and tag == "input":
            values = dict(attrs)
            if values.get("name") == "action":
                self.current["actions"].append(
                    values.get("value")
                )

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "tr" and self.current is not None:
            self.rows.append((
                " ".join(self.current["text"]),
                self.current["actions"],
            ))
            self.current = None


class StorageWorkspaceHTTPV8Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner = User.objects.create_user(
            username="storage-http-owner",
        )
        cls.coordinator = User.objects.create_user(
            username="storage-http-coordinator",
        )
        cls.member = User.objects.create_user(
            username="storage-http-member",
        )
        cls.outsider = User.objects.create_user(
            username="storage-http-outsider",
        )

        cls.group = ResearchGroup.objects.create(
            name="Storage HTTP Group",
            coordinator=cls.coordinator,
        )
        cls.group.members.add(cls.member)

        cls.personal = StorageWorkspace.objects.create(
            name="HTTP Personal Storage",
            scope="personal",
            owner=cls.owner,
        )
        cls.shared = StorageWorkspace.objects.create(
            name="HTTP Group Storage",
            scope="group",
            owner=cls.coordinator,
            research_group=cls.group,
        )

        cls.freezer = StorageLocation.objects.create(
            name="HTTP Freezer",
            location_type="freezer",
            workspace=cls.personal,
        )

    def location_actions(self, response, location_name):
        parser = _StorageActionRowParser()
        parser.feed(response.content.decode("utf-8"))

        matches = [
            actions
            for text, actions in parser.rows
            if location_name in text
        ]

        self.assertEqual(
            len(matches),
            1,
            f"Expected one table row for {location_name}",
        )

        return matches[0]

    def test_personal_owner_sees_infrastructure_controls_v8(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'value="create_location"'
        )
        self.assertIn(
            "update_location",
            self.location_actions(response, "HTTP Freezer"),
        )

    def test_group_coordinator_manages_member_reads_only_v8(self):
        group_location = StorageLocation.objects.create(
            name="HTTP Coordinator Group Box",
            location_type="box",
            workspace=self.shared,
        )

        self.client.force_login(self.coordinator)
        coordinator_response = self.client.get(self.url)

        self.assertIn(
            "update_location",
            self.location_actions(
                coordinator_response,
                group_location.name,
            ),
        )

        self.client.force_login(self.member)
        member_response = self.client.get(self.url)

        self.assertEqual(member_response.status_code, 200)
        self.assertContains(member_response, group_location.name)
        self.assertEqual(
            self.location_actions(
                member_response,
                group_location.name,
            ),
            [],
        )
        self.assertNotContains(
            member_response,
            'value="create_location"',
        )

    def test_mixed_access_has_per_location_controls_v8(self):
        User = get_user_model()

        mixed = User.objects.create_user(
            username="storage-http-mixed-owner",
        )
        self.group.members.add(mixed)

        personal = StorageWorkspace.objects.create(
            name="Mixed Owner Personal Workspace",
            scope="personal",
            owner=mixed,
        )

        owned_location = StorageLocation.objects.create(
            name="Mixed Owned Freezer",
            location_type="freezer",
            workspace=personal,
        )

        group_location = StorageLocation.objects.create(
            name="Mixed Readonly Group Freezer",
            location_type="freezer",
            workspace=self.shared,
        )

        self.client.force_login(mixed)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            "update_location",
            self.location_actions(
                response, owned_location.name
            ),
        )

        self.assertEqual(
            self.location_actions(
                response, group_location.name
            ),
            [],
        )

        html = response.content.decode("utf-8")
        select_start = html.index('name="parent_id"')
        select_end = html.index("</select>", select_start)
        parent_select = html[select_start:select_end]

        self.assertIn(
            f'value="{owned_location.pk}"',
            parent_select,
        )
        self.assertNotIn(
            f'value="{group_location.pk}"',
            parent_select,
        )

    def test_global_admin_manages_unscoped_legacy_node_v8(self):
        User = get_user_model()

        admin = User.objects.create_superuser(
            username="ccalomeno",
            email="storage-admin@example.invalid",
            password="test-only-password",
        )

        legacy = StorageLocation.objects.create(
            name="Legacy Global Freezer",
            location_type="freezer",
        )

        self.client.force_login(admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "update_location",
            self.location_actions(response, legacy.name),
        )

    def setUp(self):
        # Django is mounted externally at /b3lims.
        # The test client must use URLconf-relative paths.
        from django.conf import settings
        from django.urls import resolve

        public_url = reverse("storage_workspace")

        prefix = (
            settings.FORCE_SCRIPT_NAME or ""
        ).rstrip("/")

        if prefix and public_url.startswith(prefix + "/"):
            internal_url = public_url[len(prefix):]
        else:
            internal_url = public_url

        assert resolve(internal_url).url_name == (
            "storage_workspace"
        )

        self.canonical_url = internal_url

        # V8 HTTP tests verify the original management UI.
        # That UI is now an explicit compatibility route.
        self.url = internal_url + "?legacy=1"

    def test_v814_storage_is_canonical(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            self.canonical_url
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'id="b3-storage-v814"',
        )

        self.assertNotContains(
            response,
            "storage_isometric_v813.js",
        )

    def test_legacy_route_remains_explicit(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            'id="b3-storage-v814"',
        )

    def submit(self, user, data):
        self.client.force_login(user)
        return self.client.post(self.url, data)

    def test_user_creates_personal_workspace(self):
        response = self.submit(self.outsider, {
            "action": "create_storage_workspace_v8",
            "workspace_name": "First Workspace",
            "workspace_scope": "personal",
            "research_group_id": "",
        })

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StorageWorkspace.objects.filter(
                owner=self.outsider,
                name="First Workspace",
            ).exists()
        )

    def test_member_cannot_create_group_workspace(self):
        response = self.submit(self.member, {
            "action": "create_storage_workspace_v8",
            "workspace_name": "Unauthorized",
            "workspace_scope": "group",
            "research_group_id": self.group.pk,
        })

        self.assertEqual(response.status_code, 403)

    def test_owner_creates_box_under_freezer(self):
        response = self.submit(self.owner, {
            "action": "create_location",
            "workspace_id": self.personal.pk,
            "parent_id": self.freezer.pk,
            "name": "HTTP Box",
            "location_type": "box",
            "rank": "1",
        })

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StorageLocation.objects.filter(
                name="HTTP Box",
                workspace=self.personal,
                parent=self.freezer,
            ).exists()
        )

    def test_member_cannot_manage_group_infrastructure(self):
        response = self.submit(self.member, {
            "action": "create_location",
            "workspace_id": self.shared.pk,
            "parent_id": "",
            "name": "Unauthorized Freezer",
            "location_type": "freezer",
        })

        self.assertEqual(response.status_code, 403)

    def test_cross_workspace_parent_is_denied(self):
        response = self.submit(self.coordinator, {
            "action": "create_location",
            "workspace_id": self.shared.pk,
            "parent_id": self.freezer.pk,
            "name": "Foreign Box",
            "location_type": "box",
        })

        self.assertEqual(response.status_code, 403)

    def test_foreign_update_is_denied(self):
        response = self.submit(self.outsider, {
            "action": "update_location",
            "location_id": self.freezer.pk,
            "name": "Unauthorized Name",
            "location_type": "freezer",
        })

        self.assertEqual(response.status_code, 403)

        self.freezer.refresh_from_db()
        self.assertEqual(self.freezer.name, "HTTP Freezer")

    def test_owner_updates_location(self):
        response = self.submit(self.owner, {
            "action": "update_location",
            "location_id": self.freezer.pk,
            "name": "Updated HTTP Freezer",
            "location_type": "freezer",
        })

        self.assertEqual(response.status_code, 302)

        self.freezer.refresh_from_db()
        self.assertEqual(
            self.freezer.name,
            "Updated HTTP Freezer",
        )

    def test_foreign_deactivation_is_denied(self):
        response = self.submit(self.outsider, {
            "action": "deactivate_location",
            "location_id": self.freezer.pk,
        })

        self.assertEqual(response.status_code, 403)

        self.freezer.refresh_from_db()
        self.assertTrue(self.freezer.is_active)

    def test_workspace_panel_is_rendered(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="storage-workspaces-v8"',
        )
        self.assertContains(
            response,
            "HTTP Personal Storage",
        )

    def test_private_workspace_is_hidden(self):
        self.client.force_login(self.outsider)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            "HTTP Personal Storage",
        )
