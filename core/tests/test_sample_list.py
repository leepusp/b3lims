from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


class SampleListViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.owner = user_model.objects.create_user(
            username="listowner",
            password="test-password",
        )

        self.other = user_model.objects.create_user(
            username="listother",
            password="test-password",
        )

        self.alpha = Sample.objects.create(
            sample_id="LIST-ALPHA-001",
            sample_type="Plasmid",
            organism_name="Alpha construct",
            biosafety_level="NB-2",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
            storage_location=(
                "Room 1 > Freezer A > Box 1"
            ),
        )

        self.beta = Sample.objects.create(
            sample_id="LIST-BETA-002",
            sample_type="Bacterium (Host)",
            organism_name="Beta bacterium",
            owner=self.owner,
            status="pending",
            is_public=False,
            is_active=True,
        )

        self.public_other = Sample.objects.create(
            sample_id="LIST-PUBLIC-003",
            sample_type="Phage (Virus)",
            organism_name="Public phage",
            owner=self.other,
            status="qc",
            is_public=True,
            is_active=True,
        )

        self.private_other = Sample.objects.create(
            sample_id="LIST-HIDDEN-004",
            sample_type="Plasmid",
            organism_name="Hidden construct",
            owner=self.other,
            status="available",
            is_public=False,
            is_active=True,
        )

        logical_name = (
            "users/listowner/"
            "samples/"
            f"sample_{self.alpha.pk}_"
            "LIST-ALPHA-001/"
            "files/result.pdf"
        )

        SampleFile.objects.bulk_create(
            [
                SampleFile(
                    sample=self.alpha,
                    file=logical_name,
                    description="Result",
                    mime_type="application/pdf",
                    file_size=1024,
                    category="pdf",
                )
            ]
        )

        self.url = reverse(
            "samples_list"
        )

        self.client_path = self._client_path(
            self.url
        )

    @staticmethod
    def _client_path(url):
        script_name = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        ).rstrip("/")

        if not script_name:
            return url

        if url == script_name:
            return "/"

        if url.startswith(
            script_name + "/"
        ):
            return url[
                len(script_name):
            ]

        return url

    def get_list(self, params=None):
        self.client.force_login(
            self.owner
        )

        return self.client.get(
            self.client_path,
            data=params or {},
        )

    def test_list_respects_sample_visibility(
        self,
    ):
        response = self.get_list()

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertContains(
            response,
            self.beta.sample_id,
        )

        self.assertContains(
            response,
            self.public_other.sample_id,
        )

        self.assertNotContains(
            response,
            self.private_other.sample_id,
        )

    def test_search_matches_sample_id_organism_and_type(
        self,
    ):
        response = self.get_list(
            {
                "q": "Alpha",
            }
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertNotContains(
            response,
            self.beta.sample_id,
        )

        response = self.get_list(
            {
                "q": "Bacterium",
            }
        )

        self.assertContains(
            response,
            self.beta.sample_id,
        )

    def test_status_type_owner_and_biosafety_filters(
        self,
    ):
        response = self.get_list(
            {
                "status": "available",
                "sample_type": "Plasmid",
                "owner": str(
                    self.owner.pk
                ),
                "biosafety": "NB-2",
            }
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertNotContains(
            response,
            self.beta.sample_id,
        )

        self.assertNotContains(
            response,
            self.public_other.sample_id,
        )

    def test_storage_filter(
        self,
    ):
        response = self.get_list(
            {
                "storage": "assigned",
            }
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertNotContains(
            response,
            self.beta.sample_id,
        )

        response = self.get_list(
            {
                "storage": "unassigned",
            }
        )

        self.assertNotContains(
            response,
            self.alpha.sample_id,
        )

        self.assertContains(
            response,
            self.beta.sample_id,
        )

    def test_file_filter_and_file_count(
        self,
    ):
        response = self.get_list(
            {
                "files": "with",
            }
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertContains(
            response,
            ">1<",
            html=False,
        )

        self.assertNotContains(
            response,
            self.beta.sample_id,
        )

        response = self.get_list(
            {
                "files": "without",
            }
        )

        self.assertNotContains(
            response,
            self.alpha.sample_id,
        )

        self.assertContains(
            response,
            self.beta.sample_id,
        )

    def test_visibility_filter(
        self,
    ):
        response = self.get_list(
            {
                "visibility": "public",
            }
        )

        self.assertContains(
            response,
            self.public_other.sample_id,
        )

        self.assertNotContains(
            response,
            self.alpha.sample_id,
        )

        response = self.get_list(
            {
                "visibility": "private",
            }
        )

        self.assertContains(
            response,
            self.alpha.sample_id,
        )

        self.assertContains(
            response,
            self.beta.sample_id,
        )

        self.assertNotContains(
            response,
            self.public_other.sample_id,
        )

    def test_actions_are_permission_sensitive(
        self,
    ):
        response = self.get_list()

        own_edit = reverse(
            "sample_edit",
            args=[
                self.alpha.pk
            ],
        )

        other_edit = reverse(
            "sample_edit",
            args=[
                self.public_other.pk
            ],
        )

        self.assertContains(
            response,
            own_edit,
        )

        self.assertNotContains(
            response,
            other_edit,
        )

    def test_list_uses_secure_storage_display(
        self,
    ):
        response = self.get_list()

        self.assertContains(
            response,
            "Room 1 &gt; Freezer A &gt; Box 1",
        )

        self.assertNotContains(
            response,
            "users/listowner/",
        )

        self.assertNotContains(
            response,
            "/home/listowner/",
        )

    def test_filter_controls_are_present(
        self,
    ):
        response = self.get_list()

        for field_name in (
            "q",
            "status",
            "sample_type",
            "owner",
            "research_group",
            "biobank",
            "biosafety",
            "collection",
            "storage",
            "files",
            "visibility",
        ):
            self.assertContains(
                response,
                f'name="{field_name}"',
            )

        self.assertContains(
            response,
            "Rejected / Nonviable",
        )

        self.assertContains(
            response,
            "Depleted",
        )

    def test_list_is_paginated_at_25_rows(
        self,
    ):
        for index in range(30):
            Sample.objects.create(
                sample_id=(
                    f"LIST-PAGE-{index:03d}"
                ),
                sample_type="Plasmid",
                organism_name=(
                    f"Pagination construct {index}"
                ),
                owner=self.owner,
                status="pending",
                is_public=False,
                is_active=True,
            )

        response = self.get_list()

        page_obj = response.context[
            "page_obj"
        ]

        self.assertEqual(
            len(
                response.context[
                    "samples"
                ]
            ),
            25,
        )

        self.assertEqual(
            page_obj.paginator.per_page,
            25,
        )

        self.assertGreater(
            page_obj.paginator.count,
            25,
        )

        self.assertTrue(
            page_obj.has_next()
        )

        self.assertContains(
            response,
            "Next",
        )

    def test_filter_query_is_preserved_for_pagination(
        self,
    ):
        for index in range(30):
            Sample.objects.create(
                sample_id=(
                    f"LIST-AVAILABLE-{index:03d}"
                ),
                sample_type="Plasmid",
                organism_name=(
                    f"Available construct {index}"
                ),
                owner=self.owner,
                status="available",
                is_public=False,
                is_active=True,
            )

        response = self.get_list(
            {
                "status": "available",
            }
        )

        self.assertTrue(
            response.context[
                "page_obj"
            ].has_next()
        )

        self.assertContains(
            response,
            "status=available",
        )

        self.assertContains(
            response,
            "page=2",
        )

    def test_unauthenticated_user_is_redirected(
        self,
    ):
        response = self.client.get(
            self.client_path
        )

        self.assertEqual(
            response.status_code,
            302,
        )
