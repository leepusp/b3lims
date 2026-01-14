from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

# ================= PUBLIC ======================
from core.views.public.home import public_home
from core.views.public.collections import (
    public_collection_list,
    public_collection_detail,
)
from core.views.public.about import public_about
from core.views.public.governance import public_governance

# ================= AUTH ========================
from core.views.auth import CoreLoginView, logout_user

# ================= INTERNAL (LIMS) =============
from core.views.internal.workspace import home

# IMPORTANTE: Caminhos padronizados para a nova estrutura de subpastas
# Biobanks
from core.views.internal.biobanks.views import biobanks_view
from core.views.internal.biobanks.members import biobank_members_view

# Collections
from core.views.internal.collections.views import collections_view
from core.views.internal.collections.members import manage_collection_members

# Tags & Keywords
from core.views.internal.tags import (
    tags_view, 
    create_tag_ajax_view
)
from core.views.internal.keywords import keywords_view

urlpatterns = [
    # ================= PUBLIC ==================
    path("public/", public_home, name="public_home"),
    path("public/about/", public_about, name="public_about"),
    path("public/governance/", public_governance, name="public_governance"),
    path("public/collections/", public_collection_list, name="public_collections"),
    path("public/collections/<int:collection_id>/", public_collection_detail, name="public_collection_detail"),

    # ================= ADMIN ===================
    path("admin/", admin.site.urls),

    # ================= AUTH ====================
    path("login/", CoreLoginView.as_view(), name="login"),
    path("logout/", logout_user, name="logout"),

    # ================= INTERNAL BIOBANK =========
    # Listagem de Biobanks (via workspace/page=biobanks)
    # Gestão de Membros específica:
    path(
        "biobanks/<int:biobank_id>/members/",
        biobank_members_view,
        name="biobank_members",
    ),

    # ================= INTERNAL COLLECTION ======
    # Gestão de Membros específica:
    path(
        "collections/<int:collection_id>/members/",
        manage_collection_members,
        name="collection_members",
    ),

    # ================= TAGS & KEYWORDS ==========
    path("tags/", tags_view, name="tags_view"),
    path("keywords/", keywords_view, name="keywords_view"),

    # ================= AJAX =====================
    path(
        "ajax/add_tag/",
        create_tag_ajax_view,
        name="ajax_add_tag",
    ),

    # ================= INTERNAL HOME (WORKSPACE)
    # O entrypoint do LIMS que gerencia as abas via ?page=
    path("", home, name="home"),
]

# Servir arquivos de mídia (Fotos de amostras, PDFs, etc) em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)