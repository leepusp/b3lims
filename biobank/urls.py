# core/urls.py
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

# ================= IMPORTAÇÕES =================

# 1. PUBLIC VIEWS
from core.views.public.home import public_home
from core.views.public.about import public_about
from core.views.public.governance import public_governance
from core.views.public.collections import (
    public_collection_list,
    public_collection_detail,
)

# 2. AUTHENTICATION
from core.views.auth import CoreLoginView, logout_user

# 3. INTERNAL LIMS (CORE / WORKSPACE)
from core.views.internal.workspace.views import home
from core.views.internal.backup import workspace_backup_view

# --- NOVAS VIEWS: PROFILE & CALENDAR ---
from core.views.internal.profile.views import profile_view
from core.views.internal.calendar.views import calendar_view

# 4. BIOBANKS & COLLECTIONS (Gestão Interna)
from core.views.internal.biobanks.views import biobanks_list_view
from core.views.internal.collections.views import collections_list_view

# 5. SAMPLES (AMOSTRAS)
from core.views.internal.samples.views import (
    print_sample_label,
    samples_list_view,
    sample_create_view,
    export_samples_csv,
    sample_edit_view,
    sample_relate_view,
    samples_network_view,  # <-- FUNÇÃO DO GRAFO IMPORTADA AQUI
    sample_import_view,
    sample_import_batch_detail_view,
)

# 6. CHEMICALS (REAGENTES)
from core.views.internal.chemicals.views import chemicals_list_view, chemical_create_view

# 7. TAGS & KEYWORDS
from core.views.internal.tags.views import tags_view, create_tag_ajax_view
from core.views.internal.keywords.views import keywords_view

# 8. LAB TOOLS (NOTEBOOK, MOLECULAR, PLASMID)
from core.views.internal.lab_tools import notebook as notebook_views
from core.views.internal.lab_tools import molecular as molecular_views
from core.views.internal.lab_tools import plasmid as plasmid_views

# 9. QR CODE (PAGE)
from core.views.internal.samples.views import sample_qr_scan_view

# ================= ROTAS (URLPATTERNS) =================

urlpatterns = [
    # ---------------- PUBLIC PAGES ----------------
    path("public/", public_home, name="public_home"),
    path("public/about/", public_about, name="public_about"),
    path("public/governance/", public_governance, name="public_governance"),
    path("public/collections/", public_collection_list, name="public_collections"),
    path("public/collections/<int:collection_id>/", public_collection_detail, name="public_collection_detail"),

    # ---------------- ADMIN & AUTH ----------------
    path("admin/", admin.site.urls),
    path("login/", CoreLoginView.as_view(), name="login"),
    path("logout/", logout_user, name="logout"),

    # ---------------- INTERNAL: DASHBOARD & SYSTEM ----------------
    path("", home, name="workspace"),
    path("backup/", workspace_backup_view, name="workspace_backup"),

    # USER TOOLS
    path("profile/", profile_view, name="user_profile"),
    path("calendar/", calendar_view, name="lab_calendar"),

    # ---------------- BIOBANKS & COLLECTIONS (GESTÃO) ----------------
    path("biobanks/", biobanks_list_view, name="biobanks_list"),
    path("collections/", collections_list_view, name="collections_list"),

    # ---------------- SAMPLES (AMOSTRAS) ----------------
    path("samples/", samples_list_view, name="samples_list"),
    path("samples/import/", sample_import_view, name="samples_import"),
    path("samples/import/<int:batch_id>/", sample_import_batch_detail_view, name="samples_import_batch"),
    path("samples/add/", sample_create_view, name="sample_add"),
    path("samples/network/", samples_network_view, name="samples_network"), # <-- ROTA DO GRAFO AQUI
    path("samples/<int:sample_id>/print/", print_sample_label, name="print_sample_label"),
    path("samples/<int:sample_id>/edit/", sample_edit_view, name="sample_edit"),
    path("samples/<int:sample_id>/relate/", sample_relate_view, name="sample_relate"),
    path("samples/export/", export_samples_csv, name="export_samples_csv"),

    # ---------------- CHEMICALS (REAGENTES) ----------------
    path("chemicals/", chemicals_list_view, name="chemicals_list"),
    path("chemicals/add/", chemical_create_view, name="chemical_add"),

    # ---------------- INTERNAL: MANAGEMENT (TAGS) ----------------
    path("tags/", tags_view, name="tags_view"),
    path("keywords/", keywords_view, name="keywords_view"),
    path("ajax/add_tag/", create_tag_ajax_view, name="ajax_add_tag"),

    # ---------------- INTERNAL: LAB TOOLS ----------------
    path('internal/lab-tools/notebook/', notebook_views.notebook_index, name='notebook_index'),
    path('internal/lab-tools/notebook/create/', notebook_views.notebook_create, name='notebook_create'),
    path('internal/lab-tools/notebook/api/save/<int:entry_id>/', notebook_views.notebook_save_api, name='notebook_save_api'),
    path('internal/api/search-samples/', notebook_views.search_samples_api, name='search_samples_api'),
    path('internal/lab-tools/molecular/', molecular_views.molecular_viewer, name='molecular_index'),
    path('internal/lab-tools/plasmid/', plasmid_views.plasmid_editor, name='plasmid_editor'),


    # ---------------- QR CODE (PAGE) --------------------------------
    path('samples/scan/<uuid:uuid>/', sample_qr_scan_view, name='sample_qr_scan'),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
