from core.views.internal.shipments.views import shipment_generated_document_view
from core.views.internal.shipments.views import (
    shipment_cibio_template_download_view,
    shipment_document_workspace_view,
)
from core.views.internal.shipments.views import shipment_edit_view
from core.views.internal.shipments.views import shipment_document_file_download_view
from core.views.internal.shipments.views import shipments_list_view, shipments_dashboard_view, shipment_detail_view, shipment_scan_view, shipment_approve_documents_view, shipment_package_labels_view, shipment_documents_review_view, shipment_request_document_correction_view
# core/urls.py
from django.contrib import admin
from django.urls import include, path, re_path
from core.views.internal.storage.location_layout_v8146c3 import storage_location_create_with_layout_v8146c3
from core.views.internal.storage.location_child_v8146 import storage_location_child_create_v8146, storage_path_register_v8146
from core.views.internal.samples.storage_move_v8146 import sample_storage_move_v8146
from django.views.generic.base import RedirectView
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
from core.views.public.samples import (
    public_sample_list,
    public_sample_detail,
)
from core.views.public.biobank_directory import (
    public_biobank_list,
    public_biobank_detail,
)

# 2. AUTHENTICATION
from core.views.auth import CoreLoginView, logout_user

# 3. INTERNAL LIMS (CORE / WORKSPACE)
from core.views.internal.health import healthz_view
from core.views.internal.workspace.views import home

# --- NOVAS VIEWS: PROFILE & CALENDAR ---
from core.views.internal.profile.views import profile_view
from core.views.internal.calendar.views import calendar_view
from core.views.internal.calendar.history import activity_history
from core.views.internal.storage.views import storage_workspace_view
from core.views.internal.storage.sample_search import storage_sample_search
from core.views.internal.storage.location_layout_update import (
    storage_location_layout_update,
)
from core.views.internal.storage.anchor_catalog_v8 import (
    storage_anchor_catalog_v8,
)

# 4. BIOBANKS & COLLECTIONS (Gestão Interna)
from core.views.internal.biobanks.views import (
    biobanks_list_view,
    biobank_create_view,
    biobanks_dashboard_view,
)
from core.views.internal.biobanks.geocoding import (
    biobank_geocode_reverse_view,
    biobank_geocode_search_view,
)
from core.views.internal.biobanks.members import biobank_members_view
from core.views.internal.biobanks.profile import biobank_profile_view
from core.views.internal.collections.views import (
    collections_list_view,
    collection_create_view,
    collections_dashboard_view,
    collection_detail_view,
    collection_edit_view,
    collection_share_view,
    collection_share_revoke_view,
    collection_archive_view,
    collection_reactivate_view,
)

# 5. SAMPLES (AMOSTRAS)
from core.views.internal.samples.views import (
    sample_create_shipment_view,
    print_sample_label,
    print_sample_labels,
    samples_list_view,
    samples_dashboard_view,
    samples_origin_map_view,
    sample_create_view,
    export_samples_csv,
    sample_edit_view,
    sample_detail_view,
    sample_ncbi_genome_resolve_view,
    sample_genome_assembly_review_view,
    sample_ncbi_taxonomy_resolve_view,
    sample_taxonomy_review_view,
    sample_relate_view,
    samples_network_view,  # <-- FUNÇÃO DO GRAFO IMPORTADA AQUI
    sample_import_view,
    sample_import_batch_detail_view,
)

# 6. CHEMICALS (REAGENTES)
from core.views.internal.chemicals.views import (
    chemical_create_view,
    chemical_delete_view,
    chemical_detail_view,
    chemical_edit_view,
    chemical_file_deactivate_view,
    chemical_file_download_view,
    chemical_file_upload_view,
    chemical_movement_create_view,
    chemical_qr_scan_view,
    chemicals_dashboard_view,
    chemicals_list_view,
    print_chemical_label,
)

# 7. TAGS & KEYWORDS
from core.views.internal.tags.views import (
    create_tag_ajax_view,
    create_tag_view,
    delete_tag_view,
    edit_tag_view,
    tags_view,
)
from core.views.internal.keywords.views import (
    create_keyword_view,
    delete_keyword_value_view,
    delete_keyword_view,
    edit_keyword_view,
    keywords_view,
)

# 8. LAB TOOLS (NOTEBOOK, MOLECULAR, PLASMID)
from core.views.internal.lab_tools import notebook as notebook_views
from core.views.internal.lab_tools import tool_records as tool_record_views
from core.views.internal.lab_tools import notebook_composer as notebook_composer_views
from core.views.internal.lab_tools import notebook_dashboard as notebook_dashboard_views
from core.views.internal.lab_tools import notebook_collab as notebook_collab_views
from core.views.internal.lab_tools import notebook_trace as notebook_trace_views
from core.views.internal.lab_tools import notebook_sharing as notebook_sharing_views
from core.views.internal.lab_tools import notebook_taxonomy as notebook_taxonomy_views
from core.views.internal.lab_tools import notebook_templates as notebook_templates_views
from core.views.internal.lab_tools import notebook_entry as notebook_entry_views
from core.views.internal.lab_tools import jupyter as jupyter_views
from core.views.internal.lab_tools import jupyter_sharing as jupyter_sharing_views
from core.views.internal.lab_tools import workflow as workflow_views
from core.views.internal.lab_tools import submissions as submission_views

# 9. QR CODE (PAGE)
from core.views.internal.samples.views import (
    sample_micro_qr_lookup_view,
    sample_micro_qr_resolve_view,
    sample_qr_scan_view,
)

# ================= ROTAS (URLPATTERNS) =================

from core.views.internal.samples.views import sample_file_download_view
from core.views.internal.samples.views import (
    sample_activate_view,
    sample_bulk_share_view,
    sample_deactivate_view,
    sample_lifecycle_view,
    sample_move_to_trash_view,
    sample_purge_view,
    sample_restore_view,
    sample_share_revoke_view,
    sample_share_view,
)

from core.views.internal.samples.bulk_storage_v8148 import sample_bulk_storage_view


urlpatterns = [
    path("samples/bulk-storage/", sample_bulk_storage_view, name="sample_bulk_storage"),
    path(
        "samples/files/<int:sample_file_id>/download/",
        sample_file_download_view,
        name="sample_file_download",
    ),
    path(
        "internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/import/",
        notebook_views.molecular_sequence_import_api,
        name="molecular_sequence_import_api",
    ),
    # ---------------- PUBLIC PAGES ----------------
    path("public/", public_home, name="public_home"),
    path("public/about/", public_about, name="public_about"),
    path("public/governance/", public_governance, name="public_governance"),
    path("public/collections/", public_collection_list, name="public_collections"),
    path("public/collections/<int:collection_id>/", public_collection_detail, name="public_collection_detail"),
    path("public/samples/", public_sample_list, name="public_samples"),
    path("public/samples/<str:sample_id>/", public_sample_detail, name="public_sample_detail"),
    path("public/biobanks/", public_biobank_list, name="public_biobanks"),
    path("public/biobanks/<int:biobank_id>/", public_biobank_detail, name="public_biobank_detail"),

    # ---------------- ADMIN & AUTH ----------------
    path("admin/", admin.site.urls),
    path("login/", CoreLoginView.as_view(), name="login"),
    path("logout/", logout_user, name="logout"),

    # ---------------- INTERNAL: DASHBOARD & SYSTEM ----------------
    path("healthz/", healthz_view, name="healthz"),
    path(
        "",
        RedirectView.as_view(
            pattern_name="workspace",
            permanent=False,
        ),
        name="root_redirect",
    ),
    path("workspace/", home, name="workspace"),

    # USER TOOLS
    path("profile/", profile_view, name="user_profile"),
    path("calendar/", calendar_view, name="lab_calendar"),
    path("calendar/history/", activity_history, name="activity_history"),

    # ---------------- BIOBANKS & COLLECTIONS (GESTÃO) ----------------
    path("biobanks/", biobanks_list_view, name="biobanks_list"),
    path("biobanks/add/", biobank_create_view, name="biobank_create"),
    path("biobanks/dashboard/", biobanks_dashboard_view, name="biobanks_dashboard"),
    path(
        "internal/api/geocoding/search/",
        biobank_geocode_search_view,
        name="biobank_geocode_search",
    ),
    path(
        "internal/api/geocoding/reverse/",
        biobank_geocode_reverse_view,
        name="biobank_geocode_reverse",
    ),
    path(
        "biobanks/<int:biobank_id>/",
        biobank_profile_view,
        name="biobank_profile",
    ),
    path("biobanks/<int:biobank_id>/members/", biobank_members_view, name="biobank_members"),
    path("collections/", collections_list_view, name="collections_list"),
    path("collections/add/", collection_create_view, name="collection_create"),
    path("collections/dashboard/", collections_dashboard_view, name="collections_dashboard"),
    path(
        "collections/archive/",
        collection_archive_view,
        name="collection_archive",
    ),
    path(
        "collections/<int:collection_id>/reactivate/",
        collection_reactivate_view,
        name="collection_reactivate",
    ),
    path(
        "collections/<int:collection_id>/edit/",
        collection_edit_view,
        name="collection_edit",
    ),
    path(
        "collections/<int:collection_id>/",
        collection_detail_view,
        name="collection_detail",
    ),
    path(
        "collections/<int:collection_id>/share/",
        collection_share_view,
        name="collection_share",
    ),
    path(
        "collections/<int:collection_id>/share/<int:grant_id>/revoke/",
        collection_share_revoke_view,
        name="collection_share_revoke",
    ),

    # ---------------- SAMPLES (AMOSTRAS) ----------------
    path("shipments/", shipments_list_view, name="shipments"),
    path("shipments/dashboard/", shipments_dashboard_view, name="shipments_dashboard"),
    path("shipments/scan/<uuid:shipment_uuid>/", shipment_scan_view, name="shipment_scan"),
    path("shipments/<int:shipment_id>/approve-documents/", shipment_approve_documents_view, name="shipment_approve_documents"),
    path("shipments/<int:shipment_id>/package-labels/", shipment_package_labels_view, name="shipment_package_labels"),
    path("shipments/<int:shipment_id>/documents/<int:document_id>/generated/", shipment_generated_document_view, name="shipment_generated_document"),
    path(
        "shipments/<int:shipment_id>/documents/"
        "<int:document_id>/files/<slug:file_kind>/download/",
        shipment_document_file_download_view,
        name="shipment_document_file_download",
    ),
    path(
        "shipments/<int:shipment_id>/documents/"
        "<int:document_id>/cibio-templates/"
        "<slug:template_key>/download/",
        shipment_cibio_template_download_view,
        name="shipment_cibio_template_download",
    ),
    path("shipments/<int:shipment_id>/documents/<int:document_id>/", shipment_document_workspace_view, name="shipment_document_workspace"),
    path("shipments/<int:shipment_id>/documents-review/", shipment_documents_review_view, name="shipment_documents_review"),
    path("shipments/<int:shipment_id>/documents-review/<int:document_id>/request-correction/", shipment_request_document_correction_view, name="shipment_request_document_correction"),
    path("shipments/<int:shipment_id>/edit/", shipment_edit_view, name="shipment_edit"),
    path("shipments/<int:shipment_id>/", shipment_detail_view, name="shipment_detail"),
    path(
        "storage/",
        storage_workspace_view,
        name="storage_workspace",
    ),

    path(
        "storage/anchors/",
        storage_anchor_catalog_v8,
        name="storage_anchor_catalog_v8",
    ),
    path(
        "storage/location/layout/",
        storage_location_layout_update,
        name="storage_location_layout_update",
    ),
    path(
        "storage/sample-search/",
        storage_sample_search,
        name="storage_sample_search",
    ),
    path("samples/", samples_list_view, name="samples_list"),
    path("samples/dashboard/", samples_dashboard_view, name="samples_dashboard"),
    path("samples/map/", samples_origin_map_view, name="samples_origin_map"),
    path("samples/import/", sample_import_view, name="samples_import"),
    path("samples/import/<int:batch_id>/", sample_import_batch_detail_view, name="samples_import_batch"),
    path(
        "storage/locations/create-child/v8146/",
        storage_location_child_create_v8146,
        name="storage_location_child_create_v8146",
    ),
    path(
        "storage/locations/create-with-layout/v8146c3/",
        storage_location_create_with_layout_v8146c3,
        name="storage_location_create_with_layout_v8146c3",
    ),
    path(
        "storage/locations/register-path/v8146/",
        storage_path_register_v8146,
        name="storage_path_register_v8146",
    ),
    path("samples/add/", sample_create_view, name="sample_add"),
    path("samples/network/", samples_network_view, name="samples_network"), # <-- ROTA DO GRAFO AQUI
    path(
        "samples/share/",
        sample_bulk_share_view,
        name="sample_bulk_share",
    ),
    path(
        "samples/<int:sample_id>/share/",
        sample_share_view,
        name="sample_share",
    ),
    path(
        "samples/<int:sample_id>/share/<int:grant_id>/revoke/",
        sample_share_revoke_view,
        name="sample_share_revoke",
    ),
    path(
        "samples/lifecycle/",
        sample_lifecycle_view,
        name="samples_lifecycle",
    ),
    path(
        "samples/<int:sample_id>/deactivate/",
        sample_deactivate_view,
        name="sample_deactivate",
    ),
    path(
        "samples/<int:sample_id>/activate/",
        sample_activate_view,
        name="sample_activate",
    ),
    path(
        "samples/<int:sample_id>/trash/",
        sample_move_to_trash_view,
        name="sample_move_to_trash",
    ),
    path(
        "samples/<int:sample_id>/restore/",
        sample_restore_view,
        name="sample_restore",
    ),
    path(
        "samples/<int:sample_id>/purge/",
        sample_purge_view,
        name="sample_purge",
    ),
    path(
        "samples/labels/print/",
        print_sample_labels,
        name="print_sample_labels",
    ),
    path("samples/<int:sample_id>/print/", print_sample_label, name="print_sample_label"),
    path("samples/<int:sample_id>/create-shipment/", sample_create_shipment_view, name="sample_create_shipment"),
    path("samples/<int:sample_id>/storage/move/",
         sample_storage_move_v8146,
         name="sample_storage_move_v8146"),
    path("samples/<int:sample_id>/edit/", sample_edit_view, name="sample_edit"),
    path(
        "samples/<int:sample_id>/external/ncbi-genome/resolve/",
        sample_ncbi_genome_resolve_view,
        name="sample_ncbi_genome_resolve",
    ),
    path(
        "samples/<int:sample_id>/external/genome-assembly/<int:assignment_id>/review/",
        sample_genome_assembly_review_view,
        name="sample_genome_assembly_review",
    ),
    path(
        "samples/<int:sample_id>/external/ncbi-taxonomy/resolve/",
        sample_ncbi_taxonomy_resolve_view,
        name="sample_ncbi_taxonomy_resolve",
    ),
    path(
        "samples/<int:sample_id>/external/taxonomy/<int:assignment_id>/review/",
        sample_taxonomy_review_view,
        name="sample_taxonomy_review",
    ),
    path("samples/<int:sample_id>/", sample_detail_view, name="sample_detail"),
    path("samples/<int:sample_id>/notebook/create/", notebook_views.notebook_create_from_sample, name="notebook_create_from_sample"),
    path("samples/<int:sample_id>/relate/", sample_relate_view, name="sample_relate"),
    path("samples/export/", export_samples_csv, name="export_samples_csv"),

    # ---------------- CHEMICALS (REAGENTES) ----------------
    path("chemicals/", chemicals_list_view, name="chemicals_list"),
    path("chemicals/dashboard/", chemicals_dashboard_view, name="chemicals_dashboard"),
    path("chemicals/<int:chemical_id>/movements/add/", chemical_movement_create_view, name="chemical_movement_add"),
    path("chemicals/<int:chemical_id>/documents/add/", chemical_file_upload_view, name="chemical_file_add"),
    path("chemicals/<int:chemical_id>/documents/<int:file_id>/download/", chemical_file_download_view, name="chemical_file_download"),
    path("chemicals/<int:chemical_id>/documents/<int:file_id>/remove/", chemical_file_deactivate_view, name="chemical_file_remove"),
    path("chemicals/<int:chemical_id>/print/", print_chemical_label, name="print_chemical_label"),
    path("chemicals/<int:chemical_id>/edit/", chemical_edit_view, name="chemical_edit"),
    path("chemicals/<int:chemical_id>/delete/", chemical_delete_view, name="chemical_delete"),
    path("chemicals/<int:chemical_id>/", chemical_detail_view, name="chemical_detail"),
    path("chemicals/add/", chemical_create_view, name="chemical_add"),
    path("chemicals/scan/<uuid:uuid>/", chemical_qr_scan_view, name="chemical_qr_scan"),

    # ---------------- INTERNAL: MANAGEMENT (TAGS) ----------------
    path("tags/", tags_view, name="tags_view"),
    path("tags/create/", create_tag_view, name="tag_create"),
    path("tags/edit/", edit_tag_view, name="tag_edit"),
    path("tags/deactivate/", delete_tag_view, name="tag_deactivate"),
    path("keywords/", keywords_view, name="keywords_view"),
    path("keywords/create/", create_keyword_view, name="keyword_create"),
    path("keywords/edit/", edit_keyword_view, name="keyword_edit"),
    path(
        "keywords/deactivate/",
        delete_keyword_view,
        name="keyword_deactivate",
    ),
    path(
        "keywords/values/deactivate/",
        delete_keyword_value_view,
        name="keyword_value_deactivate",
    ),
    path("ajax/add_tag/", create_tag_ajax_view, name="ajax_add_tag"),

    # ---------------- INTERNAL: LAB TOOLS ----------------
    # Private drafts were retired; old bookmarks land on the entries dashboard.
    re_path(
        r"^internal/lab-tools/eln-experimental/.*$",
        RedirectView.as_view(pattern_name="notebook_dashboard", permanent=False),
        name="eln_experimental_index",
    ),
    path('internal/lab-tools/notebook/entries/', notebook_dashboard_views.notebook_dashboard, name='notebook_dashboard'),
    path('internal/lab-tools/notebook/entry/', notebook_entry_views.notebook_entry_open_latest, name='notebook_entry_open_latest'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/', notebook_entry_views.notebook_entry, name='notebook_entry'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/update/', notebook_entry_views.notebook_entry_update_api, name='notebook_entry_update_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/spreadsheets/', notebook_entry_views.notebook_spreadsheets_api, name='notebook_spreadsheets_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/duplicate/', notebook_entry_views.notebook_duplicate_api, name='notebook_duplicate_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/relevant/', notebook_entry_views.notebook_relevant_api, name='notebook_relevant_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/files/', notebook_entry_views.notebook_entry_files_api, name='notebook_entry_files_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/revisions/', notebook_collab_views.notebook_revisions_api, name='notebook_revisions_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/trace/', notebook_trace_views.notebook_trace_api, name='notebook_trace_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/comments/', notebook_collab_views.notebook_comments_api, name='notebook_comments_api'),
    path('internal/lab-tools/notebook/templates/', notebook_templates_views.notebook_templates_page, name='notebook_templates'),
    path('internal/lab-tools/notebook/templates/api/', notebook_templates_views.notebook_templates_api, name='notebook_templates_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/save-template/', notebook_templates_views.notebook_entry_save_template, name='notebook_entry_save_template'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/template-options/', notebook_templates_views.notebook_entry_template_options, name='notebook_entry_template_options'),
    path('internal/lab-tools/notebook/lists/', notebook_taxonomy_views.notebook_taxonomy_page, name='notebook_taxonomy'),
    path('internal/lab-tools/notebook/lists/api/', notebook_taxonomy_views.notebook_taxonomy_api, name='notebook_taxonomy_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/sharing/', notebook_sharing_views.notebook_sharing_api, name='notebook_sharing_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/lock/', notebook_collab_views.notebook_lock_api, name='notebook_lock_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/files/replace/', notebook_collab_views.notebook_file_replace_api, name='notebook_file_replace_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/files/caption/', notebook_collab_views.notebook_file_caption_api, name='notebook_file_caption_api'),
    path('internal/lab-tools/notebook/entry/<int:entry_id>/files/delete/', notebook_collab_views.notebook_file_delete_api, name='notebook_file_delete_api'),
    path('internal/lab-tools/notebook/todos/', notebook_collab_views.notebook_todos_api, name='notebook_todos_api'),
    path('internal/lab-tools/notebook/entries/batch/', notebook_dashboard_views.notebook_dashboard_batch_api, name='notebook_dashboard_batch_api'),
    path('internal/lab-tools/notebook/', notebook_views.notebook_index, name='notebook_index'),
    path('internal/lab-tools/notebook/create/', notebook_views.notebook_create, name='notebook_create'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/fields/', notebook_composer_views.notebook_fields_api, name='notebook_fields_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/header/', notebook_composer_views.notebook_header_api, name='notebook_header_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/steps/', notebook_composer_views.notebook_steps_api, name='notebook_steps_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/favorite-tags/', notebook_composer_views.notebook_favorite_tags_api, name='notebook_favorite_tags_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/entry-links/', notebook_composer_views.notebook_entry_links_api, name='notebook_entry_links_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/lookup/', notebook_composer_views.notebook_lookup_api, name='notebook_lookup_api'),
    path('internal/lab-tools/notebook/api/<int:entry_id>/field-definitions/', notebook_composer_views.notebook_field_definitions_api, name='notebook_field_definitions_api'),
    path('internal/lab-tools/submissions/', submission_views.submission_list, name='submission_list'),
    path('internal/lab-tools/submissions/create/', submission_views.submission_create, name='submission_create'),
    path('internal/lab-tools/submissions/lookup/', submission_views.submission_lookup_api, name='submission_lookup_api'),
    path('internal/lab-tools/submissions/<int:package_id>/', submission_views.submission_detail, name='submission_detail'),
    path('internal/lab-tools/submissions/<int:package_id>/api/', submission_views.submission_api, name='submission_api'),
    path('internal/lab-tools/workflows/', workflow_views.workflow_list, name='workflow_list'),
    path('internal/lab-tools/workflows/create/', workflow_views.workflow_create, name='workflow_create'),
    path('internal/lab-tools/workflows/galaxy-tools/', workflow_views.workflow_galaxy_tools_api, name='workflow_galaxy_tools_api'),
    path('internal/lab-tools/workflows/lookup/', workflow_views.workflow_lookup_api, name='workflow_lookup_api'),
    path('internal/lab-tools/workflows/<int:workflow_id>/', workflow_views.workflow_detail, name='workflow_detail'),
    path('internal/lab-tools/workflows/<int:workflow_id>/api/', workflow_views.workflow_api, name='workflow_api'),
    path('internal/lab-tools/workflows/<int:workflow_id>/steps/<int:step_id>/files/', workflow_views.workflow_step_file_upload, name='workflow_step_file_upload'),
    path('internal/lab-tools/workflows/<int:workflow_id>/files/<int:file_id>/', workflow_views.workflow_step_file, name='workflow_step_file'),
    path('internal/lab-tools/workflows/<int:workflow_id>/runs/<int:run_id>/figure/<int:index>.png', workflow_views.workflow_run_image, name='workflow_run_image'),
    path('internal/api/search-samples/', notebook_views.search_samples_api, name='search_samples_api'),
    path('internal/api/search-chemicals/', notebook_views.search_chemicals_api, name='search_chemicals_api'),
    path('internal/api/search-molecular-sequences/', notebook_views.search_molecular_sequences_api, name='search_molecular_sequences_api'),
    path('internal/lab-tools/notebook/api/link-sample/<int:entry_id>/', notebook_views.notebook_link_sample_api, name='notebook_link_sample_api'),
    path('internal/lab-tools/notebook/api/unlink-sample/<int:entry_id>/<int:link_id>/', notebook_views.notebook_unlink_sample_api, name='notebook_unlink_sample_api'),
    path('internal/lab-tools/notebook/api/link-chemical/<int:entry_id>/', notebook_views.notebook_link_chemical_api, name='notebook_link_chemical_api'),
    path('internal/lab-tools/notebook/api/unlink-chemical/<int:entry_id>/<int:link_id>/', notebook_views.notebook_unlink_chemical_api, name='notebook_unlink_chemical_api'),
    path('internal/lab-tools/notebook/api/link-molecular/<int:entry_id>/', notebook_views.notebook_link_molecular_sequence_api, name='notebook_link_molecular_sequence_api'),
    path('internal/lab-tools/notebook/api/unlink-molecular/<int:entry_id>/<int:link_id>/', notebook_views.notebook_unlink_molecular_sequence_api, name='notebook_unlink_molecular_sequence_api'),
    path(
        "internal/lab-tools/molecular-registry/api/import-preview/",
        notebook_views.molecular_registry_import_preview_api,
        name="molecular_registry_import_preview_api",
    ),
    path('internal/lab-tools/molecular-registry/', notebook_views.molecular_registry_index, name='molecular_registry_index'),
    path('internal/lab-tools/molecular-registry/<int:sequence_id>/', notebook_views.molecular_sequence_detail, name='molecular_sequence_detail'),
    path('internal/lab-tools/ketcher/', tool_record_views.ketcher_frame, name='ketcher_frame'),
    path('internal/lab-tools/tools/create/', tool_record_views.tool_record_create, name='tool_record_create'),
    path('internal/lab-tools/tools/<int:record_id>/', tool_record_views.tool_record_detail, name='tool_record_detail'),
    path('internal/lab-tools/tools/<int:record_id>/state/', tool_record_views.tool_record_state_api, name='tool_record_state_api'),
    path('internal/lab-tools/tools/<int:record_id>/file/', tool_record_views.tool_record_file_api, name='tool_record_file_api'),
    path('internal/lab-tools/tools/<int:record_id>/delete/', tool_record_views.tool_record_delete_api, name='tool_record_delete_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/update/', notebook_views.molecular_sequence_update_api, name='molecular_sequence_update_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/data/', notebook_views.molecular_sequence_data_api, name='molecular_sequence_data_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/alignments/', notebook_views.molecular_sequence_alignments_api, name='molecular_sequence_alignments_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/structures/', notebook_views.molecular_sequence_structures_api, name='molecular_sequence_structures_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/structure-search/', notebook_views.molecular_sequence_structure_search_api, name='molecular_sequence_structure_search_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/structure-preview/', notebook_views.molecular_sequence_structure_preview_api, name='molecular_sequence_structure_preview_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/pdb-search/', notebook_views.molecular_sequence_pdb_search_api, name='molecular_sequence_pdb_search_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/pdb-preview/', notebook_views.molecular_sequence_pdb_preview_api, name='molecular_sequence_pdb_preview_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/pdb-mapping/', notebook_views.molecular_sequence_pdb_mapping_api, name='molecular_sequence_pdb_mapping_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/secondary-structures/', notebook_views.molecular_sequence_secondary_structures_api, name='molecular_sequence_secondary_structures_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/restriction-sites/', notebook_views.molecular_sequence_restriction_sites_api, name='molecular_sequence_restriction_sites_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:molecule_id>/features/', notebook_views.molecular_sequence_features_api, name='molecular_sequence_features_api'),
    path('internal/lab-tools/molecular-registry/api/records/<int:sequence_id>/delete/', notebook_views.molecular_sequence_delete_api, name='molecular_sequence_delete_api'),

    # Compatibility aliases for pre-Registry molecular URLs.
    # reverse() uses the canonical routes above.
    path(
        'internal/lab-tools/notebook/molecular-sequence/<int:sequence_id>/',
        RedirectView.as_view(
            pattern_name='molecular_sequence_detail',
            permanent=False,
            query_string=True,
        ),
        name='legacy_molecular_sequence_detail',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/import/<int:sequence_id>/',
        notebook_views.molecular_sequence_import_api,
        name='legacy_molecular_sequence_import_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/update/<int:sequence_id>/',
        notebook_views.molecular_sequence_update_api,
        name='legacy_molecular_sequence_update_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/alignments/<int:sequence_id>/',
        notebook_views.molecular_sequence_alignments_api,
        name='legacy_molecular_sequence_alignments_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/secondary-structures/<int:sequence_id>/',
        notebook_views.molecular_sequence_secondary_structures_api,
        name='legacy_molecular_sequence_secondary_structures_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/restriction-sites/<int:sequence_id>/',
        notebook_views.molecular_sequence_restriction_sites_api,
        name='legacy_molecular_sequence_restriction_sites_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/features/<int:molecule_id>/',
        notebook_views.molecular_sequence_features_api,
        name='legacy_molecular_sequence_features_api',
    ),
    path(
        'internal/lab-tools/notebook/api/molecular-sequence/delete/<int:sequence_id>/',
        notebook_views.molecular_sequence_delete_api,
        name='legacy_molecular_sequence_delete_api',
    ),
    path('internal/lab-tools/notebook/api/molecular-sequence/create/<int:entry_id>/', notebook_views.notebook_create_molecular_sequence_api, name='notebook_create_molecular_sequence_api'),
    path('internal/lab-tools/notebook/api/upload/<int:entry_id>/', notebook_views.notebook_upload_attachment_api, name='notebook_upload_attachment_api'),
    path('internal/lab-tools/notebook/attachments/<int:attachment_id>/download/', notebook_views.notebook_attachment_download, name='notebook_attachment_download'),
    path(
        'internal/lab-tools/jupyter/',
        jupyter_views.jupyter_index,
        name='jupyter_index',
    ),
    path('internal/lab-tools/jupyter/from-template/', jupyter_sharing_views.jupyter_from_template, name='jupyter_from_template'),
    path('internal/lab-tools/jupyter/shared/<int:notebook_id>/', jupyter_sharing_views.jupyter_shared_view, name='jupyter_shared'),
    path('internal/lab-tools/jupyter/shared/<int:notebook_id>/copy/', jupyter_sharing_views.jupyter_copy, name='jupyter_copy'),
    path('internal/lab-tools/jupyter/shared/<int:notebook_id>/sharing/', jupyter_sharing_views.jupyter_sharing_api, name='jupyter_sharing_api'),
    path(
        'internal/lab-tools/jupyter/launch/',
        jupyter_views.jupyter_launch,
        name='jupyter_launch',
    ),
    path(
        'internal/lab-tools/jupyter/<int:notebook_id>/',
        jupyter_views.jupyter_workspace,
        name='jupyter_workspace',
    ),
    path(
        'internal/lab-tools/jupyter/<int:notebook_id>/connect/',
        jupyter_views.jupyter_connect,
        name='jupyter_connect',
    ),
    path(
        'internal/lab-tools/jupyter/api/<int:notebook_id>/',
        jupyter_views.jupyter_document_api,
        name='jupyter_document_api',
    ),
    path(
        'internal/lab-tools/jupyter/api/<int:notebook_id>/execute/',
        jupyter_views.jupyter_execute_api,
        name='jupyter_execute_api',
    ),
    path(
        'internal/lab-tools/jupyter/api/sessions/<int:session_id>/',
        jupyter_views.jupyter_session_status_api,
        name='jupyter_session_status_api',
    ),
    path(
        'internal/lab-tools/jupyter/api/sessions/<int:session_id>/stop/',
        jupyter_views.jupyter_session_stop_api,
        name='jupyter_session_stop_api',
    ),
    path(
        'internal/lab-tools/jupyter/<int:notebook_id>/download/',
        jupyter_views.jupyter_download,
        name='jupyter_download',
    ),
    path(
        'internal/lab-tools/jupyter/<int:notebook_id>/delete/',
        jupyter_views.jupyter_delete,
        name='jupyter_delete',
    ),
    path(
        'internal/lab-tools/notebook/<int:entry_id>/link-jupyter/',
        notebook_views.notebook_link_jupyter,
        name='notebook_link_jupyter',
    ),
    path(
        'internal/lab-tools/notebook/<int:entry_id>/unlink-jupyter/<int:link_id>/',
        notebook_views.notebook_unlink_jupyter,
        name='notebook_unlink_jupyter',
    ),


    # ---------------- QR CODE (PAGE) --------------------------------
    path(
        "samples/micro-qr/",
        sample_micro_qr_lookup_view,
        name="sample_micro_qr_lookup",
    ),
    path(
        "samples/micro-qr/<str:token>/",
        sample_micro_qr_resolve_view,
        name="sample_micro_qr_resolve",
    ),
    path(
        'samples/scan/<uuid:uuid>/',
        sample_qr_scan_view,
        name='sample_qr_scan',
    ),

]

# B3 Bench (ELN extensions, Lab Calendar, tools and workflows).
urlpatterns += [
    path("internal/bench/", include("bench.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
