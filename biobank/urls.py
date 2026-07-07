from core.views.internal.shipments.views import shipment_generated_document_view
from core.views.internal.shipments.views import shipment_document_workspace_view
from core.views.internal.shipments.views import shipment_edit_view
from core.views.public.shipments.views import public_shipments_portal_view, public_shipment_new_view, public_shipment_submitted_view, public_shipment_track_view, public_shipment_documents_view, public_shipment_document_upload_view
from core.views.internal.shipments.views import shipments_list_view, shipments_dashboard_view, shipment_detail_view, shipment_scan_view, shipment_approve_documents_view, shipment_package_labels_view, shipment_documents_review_view, shipment_request_document_correction_view
# core/urls.py
from django.contrib import admin
from django.urls import include, path
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
from core.views.internal.health import healthz_view
from core.views.internal.workspace.views import home

# --- NOVAS VIEWS: PROFILE & CALENDAR ---
from core.views.internal.profile.views import profile_view
from core.views.internal.calendar.views import calendar_view

# 4. BIOBANKS & COLLECTIONS (Gestão Interna)
from core.views.internal.biobanks.views import (
    biobanks_list_view,
    biobank_create_view,
    biobanks_dashboard_view,
)
from core.views.internal.biobanks.members import biobank_members_view
from core.views.internal.collections.views import collections_list_view, collection_create_view, collections_dashboard_view

# 5. SAMPLES (AMOSTRAS)
from core.views.internal.samples.views import (
    sample_create_shipment_view,
    print_sample_label,
    samples_list_view,
    samples_dashboard_view,
    sample_create_view,
    export_samples_csv,
    sample_edit_view,
    sample_detail_view,
    sample_relate_view,
    samples_network_view,  # <-- FUNÇÃO DO GRAFO IMPORTADA AQUI
    sample_import_view,
    sample_import_batch_detail_view,
)

# 6. CHEMICALS (REAGENTES)
from core.views.internal.chemicals.views import chemicals_list_view, chemical_create_view, chemicals_dashboard_view, chemical_detail_view, chemical_edit_view, chemical_delete_view, chemical_movement_create_view

# 7. TAGS & KEYWORDS
from core.views.internal.tags.views import tags_view, create_tag_ajax_view
from core.views.internal.keywords.views import keywords_view

# 8. LAB TOOLS (NOTEBOOK, MOLECULAR, PLASMID)
from core.views.internal.lab_tools import notebook as notebook_views

# 9. QR CODE (PAGE)
from core.views.internal.samples.views import sample_qr_scan_view

# ================= ROTAS (URLPATTERNS) =================

urlpatterns = [
    path("public/shipments/", public_shipments_portal_view, name="public_shipments_portal"),
    path("public/shipments/new/", public_shipment_new_view, name="public_shipment_new"),
    path("public/shipments/submitted/<uuid:token>/", public_shipment_submitted_view, name="public_shipment_submitted"),
    path("public/shipments/track/<uuid:token>/", public_shipment_track_view, name="public_shipment_track"),
    path("public/shipments/documents/<uuid:token>/", public_shipment_documents_view, name="public_shipment_documents"),
    path("public/shipments/documents/<uuid:token>/upload/<int:document_id>/", public_shipment_document_upload_view, name="public_shipment_document_upload"),

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
    path("healthz/", healthz_view, name="healthz"),
    path("", home, name="workspace"),

    # USER TOOLS
    path("profile/", profile_view, name="user_profile"),
    path("calendar/", calendar_view, name="lab_calendar"),

    # ---------------- BIOBANKS & COLLECTIONS (GESTÃO) ----------------
    path("biobanks/", biobanks_list_view, name="biobanks_list"),
    path("biobanks/add/", biobank_create_view, name="biobank_create"),
    path("biobanks/dashboard/", biobanks_dashboard_view, name="biobanks_dashboard"),
    path("biobanks/<int:biobank_id>/members/", biobank_members_view, name="biobank_members"),
    path("collections/", collections_list_view, name="collections_list"),
    path("collections/add/", collection_create_view, name="collection_create"),
    path("collections/dashboard/", collections_dashboard_view, name="collections_dashboard"),

    # ---------------- SAMPLES (AMOSTRAS) ----------------
    path("shipments/", shipments_list_view, name="shipments"),
    path("shipments/dashboard/", shipments_dashboard_view, name="shipments_dashboard"),
    path("shipments/scan/<uuid:shipment_uuid>/", shipment_scan_view, name="shipment_scan"),
    path("shipments/<int:shipment_id>/approve-documents/", shipment_approve_documents_view, name="shipment_approve_documents"),
    path("shipments/<int:shipment_id>/package-labels/", shipment_package_labels_view, name="shipment_package_labels"),
    path("shipments/<int:shipment_id>/documents/<int:document_id>/generated/", shipment_generated_document_view, name="shipment_generated_document"),
    path("shipments/<int:shipment_id>/documents/<int:document_id>/", shipment_document_workspace_view, name="shipment_document_workspace"),
    path("shipments/<int:shipment_id>/documents-review/", shipment_documents_review_view, name="shipment_documents_review"),
    path("shipments/<int:shipment_id>/documents-review/<int:document_id>/request-correction/", shipment_request_document_correction_view, name="shipment_request_document_correction"),
    path("shipments/<int:shipment_id>/edit/", shipment_edit_view, name="shipment_edit"),
    path("shipments/<int:shipment_id>/", shipment_detail_view, name="shipment_detail"),
    path("samples/", samples_list_view, name="samples_list"),
    path("samples/dashboard/", samples_dashboard_view, name="samples_dashboard"),
    path("samples/import/", sample_import_view, name="samples_import"),
    path("samples/import/<int:batch_id>/", sample_import_batch_detail_view, name="samples_import_batch"),
    path("samples/add/", sample_create_view, name="sample_add"),
    path("samples/network/", samples_network_view, name="samples_network"), # <-- ROTA DO GRAFO AQUI
    path("samples/<int:sample_id>/print/", print_sample_label, name="print_sample_label"),
    path("samples/<int:sample_id>/create-shipment/", sample_create_shipment_view, name="sample_create_shipment"),
    path("samples/<int:sample_id>/edit/", sample_edit_view, name="sample_edit"),
    path("samples/<int:sample_id>/", sample_detail_view, name="sample_detail"),
    path("samples/<int:sample_id>/notebook/create/", notebook_views.notebook_create_from_sample, name="notebook_create_from_sample"),
    path("samples/<int:sample_id>/relate/", sample_relate_view, name="sample_relate"),
    path("samples/export/", export_samples_csv, name="export_samples_csv"),

    # ---------------- CHEMICALS (REAGENTES) ----------------
    path("chemicals/", chemicals_list_view, name="chemicals_list"),
    path("chemicals/dashboard/", chemicals_dashboard_view, name="chemicals_dashboard"),
    path("chemicals/<int:chemical_id>/movements/add/", chemical_movement_create_view, name="chemical_movement_add"),
    path("chemicals/<int:chemical_id>/edit/", chemical_edit_view, name="chemical_edit"),
    path("chemicals/<int:chemical_id>/delete/", chemical_delete_view, name="chemical_delete"),
    path("chemicals/<int:chemical_id>/", chemical_detail_view, name="chemical_detail"),
    path("chemicals/add/", chemical_create_view, name="chemical_add"),

    # ---------------- INTERNAL: MANAGEMENT (TAGS) ----------------
    path("tags/", tags_view, name="tags_view"),
    path("keywords/", keywords_view, name="keywords_view"),
    path("ajax/add_tag/", create_tag_ajax_view, name="ajax_add_tag"),

    # ---------------- INTERNAL: LAB TOOLS ----------------
    path('internal/lab-tools/notebook/', notebook_views.notebook_index, name='notebook_index'),
    path('internal/lab-tools/notebook/create/', notebook_views.notebook_create, name='notebook_create'),
    path('internal/lab-tools/notebook/api/save/<int:entry_id>/', notebook_views.notebook_save_api, name='notebook_save_api'),
    path('internal/lab-tools/notebook/api/delete/<int:entry_id>/', notebook_views.notebook_delete_entry_api, name='notebook_delete_entry_api'),
    path('internal/api/search-samples/', notebook_views.search_samples_api, name='search_samples_api'),
    path('internal/api/search-chemicals/', notebook_views.search_chemicals_api, name='search_chemicals_api'),
    path('internal/lab-tools/notebook/api/link-sample/<int:entry_id>/', notebook_views.notebook_link_sample_api, name='notebook_link_sample_api'),
    path('internal/lab-tools/notebook/api/unlink-sample/<int:entry_id>/<int:link_id>/', notebook_views.notebook_unlink_sample_api, name='notebook_unlink_sample_api'),
    path('internal/lab-tools/notebook/api/link-chemical/<int:entry_id>/', notebook_views.notebook_link_chemical_api, name='notebook_link_chemical_api'),
    path('internal/lab-tools/notebook/api/unlink-chemical/<int:entry_id>/<int:link_id>/', notebook_views.notebook_unlink_chemical_api, name='notebook_unlink_chemical_api'),
    path('internal/lab-tools/notebook/molecular-sequence/<int:sequence_id>/', notebook_views.molecular_sequence_detail, name='molecular_sequence_detail'),
    path('internal/lab-tools/notebook/api/molecular-sequence/update/<int:sequence_id>/', notebook_views.molecular_sequence_update_api, name='molecular_sequence_update_api'),
    path('internal/lab-tools/notebook/api/molecular-sequence/features/<int:molecule_id>/', notebook_views.molecular_sequence_features_api, name='molecular_sequence_features_api'),
    path('internal/lab-tools/notebook/api/molecular-sequence/delete/<int:sequence_id>/', notebook_views.molecular_sequence_delete_api, name='molecular_sequence_delete_api'),
    path('internal/lab-tools/notebook/api/molecular-sequence/create/<int:entry_id>/', notebook_views.notebook_create_molecular_sequence_api, name='notebook_create_molecular_sequence_api'),
    path('internal/lab-tools/notebook/api/block/create/<int:entry_id>/', notebook_views.notebook_create_block_api, name='notebook_create_block_api'),
    path('internal/lab-tools/notebook/api/block/update/<int:block_id>/', notebook_views.notebook_update_block_api, name='notebook_update_block_api'),
    path('internal/lab-tools/notebook/api/block/delete/<int:block_id>/', notebook_views.notebook_delete_block_api, name='notebook_delete_block_api'),
    path('internal/lab-tools/notebook/api/upload/<int:entry_id>/', notebook_views.notebook_upload_attachment_api, name='notebook_upload_attachment_api'),
    path('internal/lab-tools/notebook/attachments/<int:attachment_id>/download/', notebook_views.notebook_attachment_download, name='notebook_attachment_download'),


    # ---------------- QR CODE (PAGE) --------------------------------
    path('samples/scan/<uuid:uuid>/', sample_qr_scan_view, name='sample_qr_scan'),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
