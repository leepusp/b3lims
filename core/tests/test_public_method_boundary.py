from django.test import TestCase
from django.urls import reverse


class PublicMethodBoundaryTests(
    TestCase
):
    """
    Public informational/catalog views are explicitly read-only.

    Apache decides which URLs may be reached anonymously. Django
    independently constrains the corresponding views to HTTP safe
    methods so a future proxy configuration change cannot silently
    turn these catalog endpoints into generic write surfaces.
    """

    SAFE_LIST_ROUTES = (
        "public_home",
        "public_about",
        "public_governance",
        "public_samples",
        "public_collections",
        "public_biobanks",
    )

    UNSAFE_METHODS = (
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "TRACE",
    )

    def _all_public_urls(
        self,
    ):
        return (
            reverse(
                "public_home"
            ),
            reverse(
                "public_about"
            ),
            reverse(
                "public_governance"
            ),
            reverse(
                "public_samples"
            ),
            reverse(
                "public_sample_detail",
                args=[
                    "PUBLIC-METHOD-BOUNDARY-NOT-FOUND",
                ],
            ),
            reverse(
                "public_collections"
            ),
            reverse(
                "public_collection_detail",
                args=[
                    2147483647,
                ],
            ),
            reverse(
                "public_biobanks"
            ),
            reverse(
                "public_biobank_detail",
                args=[
                    2147483647,
                ],
            ),
        )

    def _request(
        self,
        method,
        url,
    ):
        if method == "TRACE":
            return self.client.generic(
                "TRACE",
                url,
            )

        return getattr(
            self.client,
            method.lower(),
        )(
            url,
        )

    def test_public_list_and_information_routes_allow_get_and_head(
        self,
    ):
        for route_name in self.SAFE_LIST_ROUTES:
            with self.subTest(
                route=route_name,
                method="GET",
            ):
                response = self.client.get(
                    reverse(
                        route_name
                    )
                )

                self.assertEqual(
                    response.status_code,
                    200,
                )

            with self.subTest(
                route=route_name,
                method="HEAD",
            ):
                response = self.client.head(
                    reverse(
                        route_name
                    )
                )

                self.assertEqual(
                    response.status_code,
                    200,
                )

    def test_every_public_catalog_view_rejects_unsafe_methods(
        self,
    ):
        for url in self._all_public_urls():
            for method in self.UNSAFE_METHODS:
                with self.subTest(
                    url=url,
                    method=method,
                ):
                    response = self._request(
                        method,
                        url,
                    )

                    self.assertEqual(
                        response.status_code,
                        405,
                    )

                    self.assertEqual(
                        response.headers.get(
                            "Allow"
                        ),
                        "GET, HEAD",
                    )

    def test_method_boundary_does_not_depend_on_object_existence(
        self,
    ):
        """
        Detail views reject unsafe methods before attempting object
        lookup, even for identifiers that do not exist.
        """

        detail_urls = (
            reverse(
                "public_sample_detail",
                args=[
                    "PUBLIC-METHOD-BOUNDARY-NOT-FOUND",
                ],
            ),
            reverse(
                "public_collection_detail",
                args=[
                    2147483647,
                ],
            ),
            reverse(
                "public_biobank_detail",
                args=[
                    2147483647,
                ],
            ),
        )

        for url in detail_urls:
            with self.subTest(
                url=url,
            ):
                response = self.client.post(
                    url,
                )

                self.assertEqual(
                    response.status_code,
                    405,
                )
