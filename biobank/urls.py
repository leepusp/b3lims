from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

# ========================================================
# IMPORTS: PUBLIC VIEWS
# ========================================================
from core.views.public.home import public_home
from core.views.public.about import public_about
from core.views.public.governance import public_governance
from core.views.public.collections import (
    public_collection_list,
    public_collection_detail,
)

# ========================================================
# IMPORTS: AUTHENTICATION
# ========================================================
from core.views.auth import CoreLoginView, logout_user

# ========================================================
# IMPORTS: INTERNAL LIMS (CORE)
# ========================================================
from core.views.internal.workspace import home

# Biobanks, Collections & Samples
from core.views.internal.biobanks.members import biobank_members_view
from core.views.internal.collections.members import manage_collection_members
from core.views.internal.samples.views import print_sample_label

# Tags & Keywords
from core.views.internal.tags.views import tags_view, create_tag_ajax_view
from core.views.internal.keywords.views import keywords_view

# ========================================================
# IMPORTS: LAB TOOLS (SEPARADOS)
# ========================================================
from core.views.internal.lab_tools import notebook as notebook_views
from core.views.internal.lab_tools import molecular as molecular_views

urlpatterns = [
    # ================= PUBLIC PAGES ==================
    path("public/", public_home, name="public_home"),
    path("public/about/", public_about, name="public_about"),
    path("public/governance/", public_governance, name="public_governance"),
    path("public/collections/", public_collection_list, name="public_collections"),
    path("public/collections/<int:collection_id>/", public_collection_detail, name="public_collection_detail"),

    # ================= ADMIN & AUTH ==================
    path("admin/", admin.site.urls),
    path("login/", CoreLoginView.as_view(), name="login"),
    path("logout/", logout_user, name="logout"),

    # ================= INTERNAL: MANAGEMENT ==========
    path("biobanks/<int:biobank_id>/members/", biobank_members_view, name="biobank_members"),
    path("collections/<int:collection_id>/members/", manage_collection_members, name="collection_members"),
    path("samples/<int:sample_id>/print/", print_sample_label, name="print_sample_label"),

    # Tags & Keywords
    path("tags/", tags_view, name="tags_view"),
    path("keywords/", keywords_view, name="keywords_view"),
    path("ajax/add_tag/", create_tag_ajax_view, name="ajax_add_tag"),

    # ================= INTERNAL: LAB TOOLS ===========

    # --- NOTEBOOK (ELN) ---
    path('internal/lab-tools/notebook/', notebook_views.notebook_index, name='notebook_index'),
    path('internal/lab-tools/notebook/create/', notebook_views.notebook_create, name='notebook_create'),
    path('internal/lab-tools/notebook/api/save/<int:entry_id>/', notebook_views.notebook_save_api, name='notebook_save_api'),
    path('internal/api/search-samples/', notebook_views.search_samples_api, name='search_samples_api'),

    # --- MOLECULAR VIEWER ---
    path('internal/lab-tools/molecular/', molecular_views.molecular_index, name='molecular_index'),
    path('internal/lab-tools/molecular/<int:seq_id>/', molecular_views.molecular_viewer, name='molecular_viewer'),
    # NOVA ROTA: Necessária para o formulário de upload no modal
    path('internal/lab-tools/molecular/upload/', molecular_views.molecular_upload, name='molecular_upload'),

    # ================= WORKSPACE (HOME) ==============
    path("", home, name="home"),
]

# ================= DEBUG & STATIC FILES =============
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()