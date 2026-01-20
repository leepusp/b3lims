from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

# IMPORTANTE: Importação necessária para servir estáticos de pastas customizadas (como 'interfaces')
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

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

# BIOBANKS: Separado em views (geral) e members (membros)
from core.views.internal.biobanks.members import biobank_members_view

# COLLECTIONS: Separado em views e members
from core.views.internal.collections.views import collections_view
from core.views.internal.collections.members import manage_collection_members

# SAMPLES: Onde incluímos a lógica de impressão do CEBID
from core.views.internal.samples.views import samples_view, print_sample_label

# TAGS & KEYWORDS
from core.views.internal.tags.views import tags_view, create_tag_ajax_view
from core.views.internal.keywords.views import keywords_view

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
    path("biobanks/<int:biobank_id>/members/", biobank_members_view, name="biobank_members"),

    # ================= INTERNAL COLLECTION ======
    path("collections/<int:collection_id>/members/", manage_collection_members, name="collection_members"),

    # ================= INTERNAL SAMPLES =========
    path("samples/<int:sample_id>/print/", print_sample_label, name="print_sample_label"),

    # ================= TAGS & KEYWORDS ==========
    path("tags/", tags_view, name="tags_view"),
    path("keywords/", keywords_view, name="keywords_view"),

    # ================= AJAX =====================
    path("ajax/add_tag/", create_tag_ajax_view, name="ajax_add_tag"),

    # ================= INTERNAL HOME (WORKSPACE)
    path("", home, name="home"),
]

# ================= DEBUG CONFIG =================
if settings.DEBUG:
    # 1. Serve arquivos de MEDIA (Uploads de usuários, arquivos de samples)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # 2. Serve arquivos STATIC que estão na pasta 'core/interfaces'
    # Esta função lê o seu STATICFILES_DIRS do settings.py e cria as rotas automaticamente
    urlpatterns += staticfiles_urlpatterns()