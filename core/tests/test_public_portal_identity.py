from pathlib import Path

from django.test import (
    TestCase,
)
from django.urls import reverse


PUBLIC_TEMPLATE_ROOT = Path(
    "core/interfaces/public"
)


class PublicPortalIdentityTests(
    TestCase
):
    def test_public_base_uses_b3_lims_identity(
        self,
    ):
        template = (
            PUBLIC_TEMPLATE_ROOT
            / "base.html"
        ).read_text()

        self.assertIn(
            '<html lang="en">',
            template,
        )

        self.assertIn(
            "B3 LIMS",
            template,
        )

        self.assertNotIn(
            "Biobank CEPID B3",
            template,
        )

        self.assertNotIn(
            '<nav class="navbar',
            template,
        )

    def test_public_base_uses_pale_blue_background(
        self,
    ):
        template = (
            PUBLIC_TEMPLATE_ROOT
            / "base.html"
        ).read_text()

        self.assertIn(
            "--b3-page-bg: #f2f8fc",
            template,
        )

        self.assertIn(
            "#f3f9fd",
            template,
        )

        self.assertIn(
            "#eef6fb",
            template,
        )

    def test_home_uses_canonical_b3_lims_brand(
        self,
    ):
        template = (
            PUBLIC_TEMPLATE_ROOT
            / "index.html"
        ).read_text()

        self.assertIn(
            (
                "Welcome to the "
                "B3 LIMS public catalog"
            ),
            template,
        )

        self.assertIn(
            "CEPID B3 RESEARCH NETWORK",
            template,
        )

        self.assertNotIn(
            (
                "Welcome to the "
                "B3 Biobank public catalog"
            ),
            template,
        )

    def test_home_contains_five_quick_access_destinations(
        self,
    ):
        template = (
            PUBLIC_TEMPLATE_ROOT
            / "index.html"
        ).read_text()

        for route_name in (
            "public_collections",
            "public_about",
            "public_governance",
            "public_shipments_portal",
            "login",
        ):
            self.assertIn(
                (
                    "{% url '"
                    + route_name
                    + "' %}"
                ),
                template,
            )

        for label in (
            "Browse Collections",
            "About B3 LIMS",
            "Governance",
            "Shipments",
            "Internal Area",
        ):
            self.assertIn(
                label,
                template,
            )

    def test_public_template_owned_ui_is_english(
        self,
    ):
        targets = (
            "base.html",
            "about.html",
            "governance.html",
            "collections/list.html",
            "collections/detail.html",
            "shipments/portal.html",
            "shipments/documents.html",
            "shipments/new.html",
            "shipments/submitted.html",
            "shipments/track.html",
            "shipments/upload_document.html",
        )

        forbidden = (
            "Início",
            "Coleções",
            "Sobre o ",
            "Governança,",
            "Governança e ",
            "Remessas",
            "Área interna",
            "Buscar",
            "Catálogo de Coleções",
            "Coleção pública",
            "Descrição",
            "Informações públicas",
            "Tags públicas",
            "Voltar ao catálogo",
            "Remessa de Material Biológico",
            "Documentos da Remessa",
            "Rastreio da Remessa",
            "Enviar Documento Assinado",
            "Baixar",
            "Acompanhar",
            "Nenhum item registrado",
            "Enviar arquivo assinado",
            "Cancelar",
            "Biobank CEPID B3",
        )

        for relative_path in targets:
            text = (
                PUBLIC_TEMPLATE_ROOT
                / relative_path
            ).read_text()

            for token in forbidden:
                with self.subTest(
                    template=relative_path,
                    token=token,
                ):
                    self.assertNotIn(
                        token,
                        text,
                    )

    def test_public_collection_templates_keep_sensitive_relations_absent(
        self,
    ):
        combined = (
            (
                PUBLIC_TEMPLATE_ROOT
                / "collections/list.html"
            ).read_text()
            + "\n"
            + (
                PUBLIC_TEMPLATE_ROOT
                / "collections/detail.html"
            ).read_text()
        )

        for forbidden in (
            "collection.owner",
            "collection.research_group",
            "collection.biobank",
            "collection.tags.all",
            "collection.samples.",
        ):
            self.assertNotIn(
                forbidden,
                combined,
            )

    def test_public_home_response_has_no_top_navbar(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertNotContains(
            response,
            '<nav class="navbar',
        )

        self.assertContains(
            response,
            (
                "Welcome to the "
                "B3 LIMS public catalog"
            ),
        )

        self.assertContains(
            response,
            "Internal Area",
        )
