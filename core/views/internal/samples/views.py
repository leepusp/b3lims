from core.models.samples.subtypes import format_bacterial_taxonomic_name
from core.services.sample_origin import save_sample_origin
from core.services.metadata_vocabularies import active_tags_from_ids, get_or_create_active_keyword_value
import json  # <-- Adicionado para o Grafo e Auto-preenchimento
import csv
import logging
from django.urls import reverse
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from pathlib import PurePosixPath
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone

from core.context import base_context
from core.models import (
    Sample,
    Collection,
    SampleFile,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
    Bacteria,
    Phage,
    Plasmid,
    HostRange,  # <-- Adicionado para o Grafo
    SampleImportBatch,
    SampleIntakeRecord,
)
from core.models.events.model import Event
from core.models.samples.relationship import SampleRelationship

from core.forms import SampleOriginForm
from core.forms import SampleForm, get_form_class_for_sample
from core.models.samples.origin import SampleOrigin
from core.permissions.samples import (
    assignable_sample_owners_for_user,
    can_delete_sample,
    can_edit_sample,
    can_view_sample,
    editable_sample_collections_for_user,
    sample_research_groups_for_user,
    visible_samples_for_user,
)
from core.permissions.collections import can_edit_collection
from core.permissions.biobanks import editable_biobanks_for_user
from core.services.sample_intake import import_sample_table
from core.services.sample_origin_map import (
    build_sample_origin_distribution_context,
)
from core.services.sample_network import (
    build_sample_network_context,
)
from core.services.sample_micro_qr import (
    InvalidSampleMicroQrToken,
    normalize_sample_micro_qr_token,
    sample_micro_qr_png_base64,
)
from core.services.sample_export import export_samples_table
from core.services.storage_locations import assign_sample_storage_from_text, get_all_storage_paths
from core.services.shipment_factory import create_shipment_from_sample
from core.services.sample_lifecycle import (
    activate_sample,
    deactivate_sample,
    move_sample_to_trash,
    purge_sample,
    restore_sample,
)

logger = logging.getLogger(__name__)

# =========================================================
# 1. DASHBOARD (LISTING & FILTERS)
# =========================================================
@login_required
def samples_list_view(request):
    """
    Display the active Samples visible to the current user.

    Filtering always starts from visible_samples_for_user(), so
    search, filter options and pagination never broaden access.
    """

    from django.core.paginator import Paginator

    from core.permissions.samples import can_edit_sample
    from core.services.storage_locations import get_all_storage_paths

    user = request.user

    base_qs = visible_samples_for_user(
        user
    )

    # Filter options are derived only from Samples the current
    # user can already see.
    filter_sample_types = list(
        base_qs
        .order_by()
        .exclude(
            Q(sample_type__isnull=True)
            | Q(sample_type="")
        )
        .values_list(
            "sample_type",
            flat=True,
        )
        .distinct()
        .order_by(
            "sample_type"
        )
    )

    filter_owners = [
        {
            "id": row["owner_id"],
            "name": row["owner__username"],
        }
        for row in (
            base_qs
            .order_by()
            .values(
                "owner_id",
                "owner__username",
            )
            .distinct()
            .order_by(
                "owner__username"
            )
        )
    ]

    filter_research_groups = [
        {
            "id": row["research_group_id"],
            "name": row["research_group__name"],
        }
        for row in (
            base_qs
            .order_by()
            .exclude(
                research_group__isnull=True
            )
            .values(
                "research_group_id",
                "research_group__name",
            )
            .distinct()
            .order_by(
                "research_group__name"
            )
        )
    ]

    filter_biobanks = [
        {
            "id": row["biobank_id"],
            "name": row["biobank__name"],
        }
        for row in (
            base_qs
            .order_by()
            .exclude(
                biobank__isnull=True
            )
            .values(
                "biobank_id",
                "biobank__name",
            )
            .distinct()
            .order_by(
                "biobank__name"
            )
        )
    ]

    filter_biosafety_levels = list(
        base_qs
        .order_by()
        .exclude(
            Q(biosafety_level__isnull=True)
            | Q(biosafety_level="")
        )
        .values_list(
            "biosafety_level",
            flat=True,
        )
        .distinct()
        .order_by(
            "biosafety_level"
        )
    )

    filter_collections = (
        Collection.objects
        .filter(
            samples__in=base_qs
        )
        .distinct()
        .order_by(
            "name"
        )
    )

    filters = {
        "q": (
            request.GET.get(
                "q",
                "",
            )
            or ""
        ).strip(),
        "status": (
            request.GET.get(
                "status",
                "",
            )
            or ""
        ).strip(),
        "sample_type": (
            request.GET.get(
                "sample_type",
                "",
            )
            or ""
        ).strip(),
        "owner": (
            request.GET.get(
                "owner",
                "",
            )
            or ""
        ).strip(),
        "research_group": (
            request.GET.get(
                "research_group",
                "",
            )
            or ""
        ).strip(),
        "biobank": (
            request.GET.get(
                "biobank",
                "",
            )
            or ""
        ).strip(),
        "biosafety": (
            request.GET.get(
                "biosafety",
                "",
            )
            or ""
        ).strip(),
        "collection": (
            request.GET.get(
                "collection",
                "",
            )
            or ""
        ).strip(),
        "storage": (
            request.GET.get(
                "storage",
                "",
            )
            or ""
        ).strip(),
        "files": (
            request.GET.get(
                "files",
                "",
            )
            or ""
        ).strip(),
        "visibility": (
            request.GET.get(
                "visibility",
                "",
            )
            or ""
        ).strip(),
    }

    qs = (
        base_qs
        .select_related(
            "biobank",
            "owner",
            "research_group",
        )
        .prefetch_related(
            "collections",
        )
    )

    # Direct Sample sharing scope.
    shared_scope = (
        request.GET.get(
            "access",
            "",
        )
        or ""
    ).strip()

    if shared_scope == "shared":
        shared_now = timezone.now()

        qs = (
            qs
            .filter(
                access_grants__user=request.user,
            )
            .filter(
                Q(
                    access_grants__expires_at__isnull=True,
                )
                | Q(
                    access_grants__expires_at__gt=shared_now,
                )
            )
            .exclude(
                owner=request.user,
            )
            .distinct()
        )

    elif shared_scope:
        shared_scope = ""

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------

    if filters["q"]:
        qs = qs.filter(
            Q(
                sample_id__icontains=filters["q"]
            )
            | Q(
                organism_name__icontains=filters["q"]
            )
            | Q(
                sample_type__icontains=filters["q"]
            )
        )

    # ---------------------------------------------------------
    # Scalar filters
    # ---------------------------------------------------------

    valid_statuses = {
        value
        for value, _label
        in Sample.STATUS_CHOICES
    }

    if filters["status"] in valid_statuses:
        qs = qs.filter(
            status=filters["status"]
        )
    elif filters["status"]:
        filters["status"] = ""

    if (
        filters["sample_type"]
        in filter_sample_types
    ):
        qs = qs.filter(
            sample_type=filters["sample_type"]
        )
    elif filters["sample_type"]:
        filters["sample_type"] = ""

    if filters["owner"].isdigit():
        qs = qs.filter(
            owner_id=int(
                filters["owner"]
            )
        )
    elif filters["owner"]:
        filters["owner"] = ""

    if filters["research_group"] == "none":
        qs = qs.filter(
            research_group__isnull=True
        )
    elif filters["research_group"].isdigit():
        qs = qs.filter(
            research_group_id=int(
                filters["research_group"]
            )
        )
    elif filters["research_group"]:
        filters["research_group"] = ""

    if filters["biobank"] == "none":
        qs = qs.filter(
            biobank__isnull=True
        )
    elif filters["biobank"].isdigit():
        qs = qs.filter(
            biobank_id=int(
                filters["biobank"]
            )
        )
    elif filters["biobank"]:
        filters["biobank"] = ""

    if filters["biosafety"] == "none":
        qs = qs.filter(
            Q(
                biosafety_level__isnull=True
            )
            | Q(
                biosafety_level=""
            )
        )
    elif (
        filters["biosafety"]
        in filter_biosafety_levels
    ):
        qs = qs.filter(
            biosafety_level=filters[
                "biosafety"
            ]
        )
    elif filters["biosafety"]:
        filters["biosafety"] = ""

    if filters["collection"] == "none":
        qs = qs.filter(
            collections__isnull=True
        )
    elif filters["collection"].isdigit():
        qs = qs.filter(
            collections__id=int(
                filters["collection"]
            )
        )
    elif filters["collection"]:
        filters["collection"] = ""

    if filters["visibility"] == "public":
        qs = qs.filter(
            is_public=True
        )
    elif filters["visibility"] == "private":
        qs = qs.filter(
            is_public=False
        )
    elif filters["visibility"]:
        filters["visibility"] = ""

    # M2M filtering above can duplicate rows.
    qs = qs.distinct()

    # ---------------------------------------------------------
    # File count / file filter
    # ---------------------------------------------------------

    qs = qs.annotate(
        file_count=Count(
            "files",
            distinct=True,
        )
    )

    if filters["files"] == "with":
        qs = qs.filter(
            file_count__gt=0
        )
    elif filters["files"] == "without":
        qs = qs.filter(
            file_count=0
        )
    elif filters["files"]:
        filters["files"] = ""

    qs = qs.order_by(
        "-created_at",
        "-pk",
    )

    # ---------------------------------------------------------
    # Storage filter
    #
    # This intentionally uses get_all_storage_paths() rather
    # than only Sample.storage_location so structured and
    # compatibility storage representations behave the same.
    # ---------------------------------------------------------

    if filters["storage"] in {
        "assigned",
        "unassigned",
    }:
        wants_storage = (
            filters["storage"]
            == "assigned"
        )

        filtered_samples = []

        for sample in qs:
            storage_paths = (
                get_all_storage_paths(
                    sample
                )
            )

            sample.primary_storage_path = (
                storage_paths[0]
                if storage_paths
                else ""
            )

            if bool(storage_paths) == wants_storage:
                filtered_samples.append(
                    sample
                )

        sample_source = filtered_samples

    else:
        if filters["storage"]:
            filters["storage"] = ""

        sample_source = qs

    # ---------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------

    paginator = Paginator(
        sample_source,
        25,
    )

    page_obj = paginator.get_page(
        request.GET.get(
            "page"
        )
    )

    # Add permission-sensitive and display-only state only to
    # Samples on the current page.
    for sample in page_obj.object_list:
        sample.can_edit_current_user = (
            can_edit_sample(
                user,
                sample,
            )
        )

        from core.permissions.samples import (
            can_manage_sample_sharing,
        )

        sample.can_manage_sharing_current_user = (
            can_manage_sample_sharing(
                user,
                sample,
            )
        )

        if not hasattr(
            sample,
            "primary_storage_path",
        ):
            storage_paths = (
                get_all_storage_paths(
                    sample
                )
            )

            sample.primary_storage_path = (
                storage_paths[0]
                if storage_paths
                else ""
            )

    query_params = request.GET.copy()
    query_params.pop(
        "page",
        None,
    )

    pagination_query = (
        query_params.urlencode()
    )

    active_filter_count = sum(
        1
        for value in filters.values()
        if value
    )

    visible_total = (
        base_qs.count()
    )

    # Direct Sample sharing list context.
    from django.contrib.auth import get_user_model
    from core.models.samples.access import SampleAccessGrant

    SharingUser = get_user_model()
    sharing_now = timezone.now()

    shared_with_me_count = (
        SampleAccessGrant.objects
        .filter(
            user=request.user,
            sample__is_active=True,
            sample__deletion_requested_at__isnull=True,
        )
        .filter(
            Q(
                expires_at__isnull=True,
            )
            | Q(
                expires_at__gt=sharing_now,
            )
        )
        .exclude(
            sample__owner=request.user,
        )
        .values(
            "sample_id"
        )
        .distinct()
        .count()
    )

    sample_share_users = (
        SharingUser.objects
        .filter(
            is_active=True,
        )
        .exclude(
            pk=request.user.pk,
        )
        .order_by(
            "username"
        )
    )

    ctx = base_context(
        request
    )

    ctx.update(
        {
            "samples": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": (
                paginator.get_elided_page_range(
                    page_obj.number,
                    on_each_side=2,
                    on_ends=1,
                )
            ),
            "pagination_query": pagination_query,
            "filters": filters,
            "active_filter_count": (
                active_filter_count
            ),
            "sample_list_summary": {
                "visible_total": visible_total,
                "filtered_total": paginator.count,
            },
            "filter_status_choices": (
                Sample.STATUS_CHOICES
            ),
            "filter_sample_types": (
                filter_sample_types
            ),
            "filter_owners": (
                filter_owners
            ),
            "filter_research_groups": (
                filter_research_groups
            ),
            "filter_biobanks": (
                filter_biobanks
            ),
            "filter_biosafety_levels": (
                filter_biosafety_levels
            ),
            "filter_collections": (
                filter_collections
            ),
            "all_samples_for_modal": (
                base_qs
                .order_by(
                    "sample_id"
                )
                .values(
                    "id",
                    "sample_id",
                    "sample_type",
                    "organism_name",
                )
            ),
            "sample_share_users": (
                sample_share_users
            ),
            "sample_shared_with_me_count": (
                shared_with_me_count
            ),
            "sample_shared_scope_active": (
                shared_scope
                == "shared"
            ),
        }
    )

    return render(
        request,
        "internal/samples/list.html",
        ctx,
    )



# =========================================================
# 2. DEDICATED SAMPLE ORIGIN MAP
# =========================================================
def _sample_origin_distribution_context(user):
    """
    Build the internal geographic distribution dataset for Samples
    already visible to the authenticated user.

    Authorization remains centralized in visible_samples_for_user().
    Serialization is delegated to the shared origin-map service.
    """
    return build_sample_origin_distribution_context(
        visible_samples_for_user(
            user
        )
    )


@login_required
def samples_origin_map_view(request):
    """
    Dedicated map-first geographic distribution interface for Samples.
    """
    ctx = base_context(
        request
    )

    ctx.update(
        _sample_origin_distribution_context(
            request.user
        )
    )

    return render(
        request,
        "internal/samples/origin_map.html",
        ctx,
    )


# =========================================================
# 2. DASHBOARD SUMMARY
# =========================================================
@login_required
def samples_dashboard_view(request):
    """
    Aggregated Sample dashboard restricted by visible_samples_for_user().

    Geographic points use the exact internal coordinates only for Samples
    already visible to the authenticated user.
    """
    from django.urls import reverse

    user = request.user

    qs = (
        visible_samples_for_user(
            user
        )
        .select_related(
            "biobank",
            "owner",
            "research_group",
            "origin",
        )
    )

    total = qs.count()

    missing_storage_q = (
        Q(
            storage_location__isnull=True
        )
        | Q(
            storage_location=""
        )
    )

    origin_qs = (
        qs
        .filter(
            origin__isnull=False,
        )
        .select_related(
            "origin",
        )
    )

    coordinate_qs = (
        origin_qs
        .exclude(
            origin__latitude__isnull=True,
        )
        .exclude(
            origin__longitude__isnull=True,
        )
    )

    sample_origin_points = []

    for sample in coordinate_qs:
        origin = sample.origin

        sample_origin_points.append(
            {
                "id": sample.pk,
                "sample_id": sample.sample_id,
                "sample_type": (
                    sample.sample_type
                    or ""
                ),
                "organism_name": (
                    sample.organism_name
                    or ""
                ),
                "status": sample.status,
                "status_label": (
                    sample.get_status_display()
                ),
                "owner": (
                    sample.owner.username
                    if sample.owner_id
                    else ""
                ),
                "research_group": (
                    sample.research_group.name
                    if sample.research_group_id
                    else ""
                ),
                "biobank": (
                    sample.biobank.name
                    if sample.biobank_id
                    else ""
                ),
                "is_public": bool(
                    sample.is_public
                ),
                "is_embargoed": bool(
                    sample.is_embargoed
                ),
                "collection_site_name": (
                    origin.collection_site_name
                    or ""
                ),
                "collection_date": (
                    origin.collection_date.isoformat()
                    if origin.collection_date
                    else ""
                ),
                "geo_loc_name": (
                    origin.geo_loc_name
                    or ""
                ),
                "country_or_ocean": (
                    origin.country_or_ocean
                    or ""
                ),
                "latitude": float(
                    origin.latitude
                ),
                "longitude": float(
                    origin.longitude
                ),
                "depth_m": (
                    float(
                        origin.depth_m
                    )
                    if origin.depth_m is not None
                    else None
                ),
                "elevation_m": (
                    float(
                        origin.elevation_m
                    )
                    if origin.elevation_m is not None
                    else None
                ),
                "habitat": (
                    origin.habitat
                    or ""
                ),
                "environmental_medium": (
                    origin.environmental_medium
                    or ""
                ),
                "env_broad_scale": (
                    origin.env_broad_scale
                    or ""
                ),
                "env_local_scale": (
                    origin.env_local_scale
                    or ""
                ),
                "location_visibility": (
                    origin.location_visibility
                ),
                "detail_url": reverse(
                    "sample_detail",
                    args=[
                        sample.pk,
                    ],
                ),
            }
        )

    def unique_point_values(key):
        return sorted(
            {
                str(
                    point.get(
                        key,
                        ""
                    )
                    or ""
                )
                for point in sample_origin_points
                if point.get(
                    key
                )
            },
            key=str.casefold,
        )

    ctx = base_context(
        request
    )

    ctx.update(
        {
            "sample_dashboard_stats": {
                "total": total,
                "available": qs.filter(
                    status="available"
                ).count(),
                "pending": qs.filter(
                    status="pending"
                ).count(),
                "qc": qs.filter(
                    status="qc"
                ).count(),
                "depleted": qs.filter(
                    status="depleted"
                ).count(),
                "rejected": qs.filter(
                    status="rejected"
                ).count(),
                "active": qs.filter(
                    is_active=True
                ).count(),
                "inactive": qs.filter(
                    is_active=False
                ).count(),
                "public": qs.filter(
                    is_public=True,
                    is_embargoed=False,
                ).count(),
                "private": qs.filter(
                    is_public=False
                ).count(),
                "embargoed": qs.filter(
                    is_embargoed=True
                ).count(),
                "biobanks": (
                    qs
                    .exclude(
                        biobank__isnull=True
                    )
                    .values(
                        "biobank_id"
                    )
                    .distinct()
                    .count()
                ),
                "groups": (
                    qs
                    .exclude(
                        research_group__isnull=True
                    )
                    .values(
                        "research_group_id"
                    )
                    .distinct()
                    .count()
                ),
                "missing_storage": qs.filter(
                    missing_storage_q
                ).count(),
                "with_storage": qs.exclude(
                    missing_storage_q
                ).count(),
                "with_origin": origin_qs.count(),
                "with_coordinates": (
                    coordinate_qs.count()
                ),
                "without_coordinates": (
                    total
                    - coordinate_qs.count()
                ),
            },
            "sample_dashboard_by_type": list(
                qs
                .values(
                    "sample_type"
                )
                .annotate(
                    total=Count("id")
                )
                .order_by(
                    "sample_type"
                )
            ),
            "sample_dashboard_by_status": list(
                qs
                .values(
                    "status"
                )
                .annotate(
                    total=Count("id")
                )
                .order_by(
                    "status"
                )
            ),
            "sample_dashboard_by_biobank": list(
                qs
                .values(
                    "biobank__name"
                )
                .annotate(
                    total=Count("id")
                )
                .order_by(
                    "biobank__name"
                )
            ),
            "sample_dashboard_by_group": list(
                qs
                .values(
                    "research_group__name"
                )
                .annotate(
                    total=Count("id")
                )
                .order_by(
                    "research_group__name"
                )
            ),
            "sample_dashboard_by_storage": list(
                qs
                .values(
                    "storage_location"
                )
                .annotate(
                    total=Count("id")
                )
                .order_by(
                    "-total",
                    "storage_location",
                )[
                    :10
                ]
            ),
            "storage_missing_samples": (
                qs
                .filter(
                    missing_storage_q
                )
                .order_by(
                    "-created_at"
                )[
                    :10
                ]
            ),
            "recent_samples": (
                qs
                .order_by(
                    "-created_at"
                )[
                    :10
                ]
            ),
            "sample_origin_points": (
                sample_origin_points
            ),
            "sample_origin_filter_types": (
                unique_point_values(
                    "sample_type"
                )
            ),
            "sample_origin_filter_statuses": (
                sorted(
                    {
                        (
                            point["status"],
                            point["status_label"],
                        )
                        for point in sample_origin_points
                    },
                    key=lambda item: (
                        item[1].casefold()
                    ),
                )
            ),
            "sample_origin_filter_biobanks": (
                unique_point_values(
                    "biobank"
                )
            ),
            "sample_origin_filter_groups": (
                unique_point_values(
                    "research_group"
                )
            ),
            "sample_origin_filter_locations": (
                unique_point_values(
                    "country_or_ocean"
                )
            ),
            "sample_origin_filter_environments": (
                unique_point_values(
                    "environmental_medium"
                )
            ),
        }
    )

    return render(
        request,
        "internal/samples/dashboard.html",
        ctx,
    )


# =========================================================
# 2. CREATE SAMPLE
# =========================================================
@login_required
def sample_create_view(request):
    user = request.user
    allowed_biobanks = editable_biobanks_for_user(user)
    allowed_owners = assignable_sample_owners_for_user(user)
    allowed_research_groups = sample_research_groups_for_user(user)
    allowed_collections = editable_sample_collections_for_user(user)

    origin_form = SampleOriginForm(
        request.POST or None,
        prefix="origin",
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_sample":
            try:
                intake_record = None
                intake_record_id = str(
                    request.POST.get(
                        "intake_record_id",
                        "",
                    )
                    or ""
                ).strip()

                if intake_record_id:
                    if not intake_record_id.isdigit():
                        raise ValueError(
                            "Invalid Sample Intake Record."
                        )

                    intake_record = get_object_or_404(
                        SampleIntakeRecord.objects
                        .select_related(
                            "batch"
                        ),
                        pk=int(
                            intake_record_id
                        ),
                    )

                    if (
                        intake_record.batch.uploaded_by_id
                        != user.id
                        and not user.is_superuser
                    ):
                        # Do not disclose whether another user's
                        # intake record exists.
                        return HttpResponse(
                            status=404
                        )

                if not origin_form.is_valid():
                    origin_errors = []

                    for field_name, field_errors in (
                        origin_form.errors.items()
                    ):
                        for error in field_errors:
                            origin_errors.append(
                                f"{field_name}: {error}"
                            )

                    raise ValueError(
                        (
                            "Sample Origin validation failed"
                            + (
                                ": "
                                + "; ".join(
                                    origin_errors
                                )
                                if origin_errors
                                else "."
                            )
                        )
                    )

                origin_data = dict(
                    origin_form.cleaned_data
                )

                sample_id_base = (
                    request.POST.get("sample_id")
                    or ""
                ).strip()

                if not sample_id_base:
                    raise ValueError(
                        "Sample ID is required."
                    )
                sample_type = request.POST.get("sample_type")
                biosafety_level = request.POST.get("biosafety_level") or None
                scientific_notes = request.POST.get("scientific_notes")
                storage_location = request.POST.get("storage_location", "")
                is_public = request.POST.get("is_public") == "true" or request.POST.get("is_public") == "on"

                if sample_type == "Bacterium (Host)":
                    official_name = request.POST.get("official_name", "").strip()
                    genus = request.POST.get("genus", "").strip()
                    species = request.POST.get("species", "").strip()
                    strain = request.POST.get("strain", "").strip()
                    organism_name = official_name or format_bacterial_taxonomic_name(genus, species, strain)

                elif sample_type == "Phage (Virus)":
                    official_name = request.POST.get("official_name", "").strip()
                    strain = request.POST.get("strain", "").strip()
                    genus = request.POST.get("genus", "").strip()
                    taxonomy = request.POST.get("taxonomy", "").strip()
                    organism_name = official_name or strain or f"{genus} {taxonomy}".strip()

                elif sample_type == "Plasmid":
                    construction = request.POST.get("construction_name", "").strip()
                    backbone = request.POST.get("backbone_name", "").strip()
                    organism_name = construction if construction else backbone

                elif sample_type == "Other":
                    organism_name = request.POST.get("custom_organism_name", "Unknown Sample").strip()
                else:
                    organism_name = "Undefined"

                owner_id = (
                    request.POST.get("owner")
                    or str(user.pk)
                )

                if not str(owner_id).isdigit():
                    raise ValueError(
                        "Invalid Sample owner."
                    )

                selected_owner = (
                    allowed_owners
                    .filter(
                        pk=int(owner_id)
                    )
                    .first()
                )

                if selected_owner is None:
                    raise PermissionDenied(
                        "You may not assign this Sample to the selected owner."
                    )

                research_group_id = (
                    request.POST.get(
                        "research_group",
                        "",
                    )
                    or ""
                ).strip()

                selected_research_group = None

                if research_group_id:
                    if not research_group_id.isdigit():
                        raise ValueError(
                            "Invalid Research Group."
                        )

                    selected_research_group = (
                        allowed_research_groups
                        .filter(
                            pk=int(
                                research_group_id
                            )
                        )
                        .first()
                    )

                    if selected_research_group is None:
                        raise PermissionDenied(
                            "You may not assign this Sample to the selected Research Group."
                        )

                collection_ids = [
                    value.strip()
                    for value in request.POST.getlist(
                        "collections"
                    )
                    if value.strip()
                ]

                # Backward-compatible support for a single legacy field.
                legacy_collection_id = (
                    request.POST.get(
                        "collection",
                        "",
                    )
                    or ""
                ).strip()

                if (
                    not collection_ids
                    and legacy_collection_id
                ):
                    collection_ids = [
                        legacy_collection_id
                    ]

                collection_ids = list(
                    dict.fromkeys(
                        collection_ids
                    )
                )

                if any(
                    not value.isdigit()
                    for value in collection_ids
                ):
                    raise ValueError(
                        "Invalid Collection selection."
                    )

                selected_collections = list(
                    allowed_collections.filter(
                        pk__in=[
                            int(value)
                            for value in collection_ids
                        ]
                    )
                )

                if (
                    len(selected_collections)
                    != len(collection_ids)
                ):
                    raise PermissionDenied(
                        "One or more selected Collections are not editable by this user."
                    )

                aliquot_raw = (
                    request.POST.get(
                        "aliquot_count",
                        "1",
                    )
                    or "1"
                ).strip()

                try:
                    default_aliquot_count = int(
                        aliquot_raw
                    )
                except ValueError as exc:
                    raise ValueError(
                        "Aliquot Count must be a positive integer."
                    ) from exc

                if default_aliquot_count < 1:
                    raise ValueError(
                        "Aliquot Count must be at least 1."
                    )

                is_embargoed = (
                    request.POST.get(
                        "is_embargoed"
                    )
                    in {
                        "true",
                        "on",
                        "1",
                        "yes",
                    }
                )

                parent_sample_id_input = request.POST.get("parent_sample_id", "").strip()
                parent_rel_type = request.POST.get("parent_relationship_type", "aliquot")
                parent_sample_obj = None

                if parent_sample_id_input:
                    parent_sample_obj = visible_samples_for_user(user).filter(sample_id=parent_sample_id_input).first()
                    if not parent_sample_obj:
                        raise ValueError(f"Source sample '{parent_sample_id_input}' not found.")

                biobank_ids = [
                    value.strip()
                    for value in request.POST.getlist(
                        "dist_biobank_id[]"
                    )
                    if value.strip()
                ]

                quantities = request.POST.getlist(
                    "dist_quantity[]"
                )

                if len(set(biobank_ids)) != len(biobank_ids):
                    raise ValueError(
                        "The same Biobank cannot be selected more than once."
                    )

                distribution_rows = []

                for index, biobank_id in enumerate(
                    biobank_ids
                ):
                    if not biobank_id.isdigit():
                        raise ValueError(
                            "Invalid Biobank selection."
                        )

                    biobank = (
                        allowed_biobanks
                        .filter(
                            pk=int(
                                biobank_id
                            )
                        )
                        .first()
                    )

                    if biobank is None:
                        raise PermissionDenied(
                            "You may not deposit Samples in the selected Biobank."
                        )

                    quantity_raw = (
                        quantities[index]
                        if index < len(quantities)
                        and quantities[index]
                        else str(
                            default_aliquot_count
                        )
                    )

                    try:
                        quantity = int(
                            quantity_raw
                        )
                    except ValueError as exc:
                        raise ValueError(
                            "Aliquot Count must be a positive integer."
                        ) from exc

                    if quantity < 1:
                        raise ValueError(
                            "Aliquot Count must be at least 1."
                        )

                    distribution_rows.append(
                        (
                            biobank,
                            quantity,
                        )
                    )

                # A Biobank is optional. Without physical distribution,
                # one Sample record is created with the default aliquot count.
                if not distribution_rows:
                    distribution_rows = [
                        (
                            None,
                            default_aliquot_count,
                        )
                    ]

                created_samples = []

                with transaction.atomic():
                    for i, (biobank, qty) in enumerate(
                        distribution_rows
                    ):
                        final_id = (
                            sample_id_base
                            if len(distribution_rows) == 1
                            else f"{sample_id_base}_{i + 1}"
                        )

                        if Sample.objects.filter(sample_id=final_id).exists():
                            raise ValueError(f"The ID '{final_id}' already exists in the system.")

                        collaborator_input = request.POST.get("collaborator", "").strip()
                        final_notes = scientific_notes
                        if collaborator_input:
                            final_notes = f"<p><strong>Collaborator / Provider:</strong> {collaborator_input}</p>" + (final_notes or "")

                        base_data = {
                            "sample_id": final_id,
                            "organism_name": organism_name,
                            "sample_type": sample_type,
                            "biosafety_level": biosafety_level,
                            "biobank": biobank,
                            "research_group": selected_research_group,
                            "scientific_notes": final_notes,
                            "is_public": is_public,
                            "is_embargoed": is_embargoed,
                            "aliquot_count": qty,
                            "owner": selected_owner,
                            "is_active": True,
                            "status": "pending",
                            "storage_location": storage_location,
                        }

                        # BACTERIA
                        if sample_type == "Bacterium (Host)":
                            r_markers = request.POST.get("resistance_markers", "")
                            r_list = [r.strip() for r in r_markers.split(",") if r.strip()]
                            sample = Bacteria.objects.create(
                                **base_data,
                                official_name=request.POST.get("official_name", ""),
                                aliases=request.POST.get("aliases", ""),
                                genus=request.POST.get("genus", ""),
                                species=request.POST.get("species", ""),
                                strain=request.POST.get("strain", ""),
                                genotype=request.POST.get("genotype", ""),
                                isolation_source=request.POST.get("isolation_source", ""),
                                resistance_markers=r_list
                            )

                        # PHAGE
                        elif sample_type == "Phage (Virus)":
                            sample = Phage.objects.create(
                                **base_data,
                                official_name=request.POST.get("official_name", ""),
                                aliases=request.POST.get("aliases", ""),
                                strain=request.POST.get("strain", ""),
                                genus=request.POST.get("genus", ""),
                                morphotype=request.POST.get("morphotype"),
                                taxonomy=request.POST.get("taxonomy"),
                                lifestyle=request.POST.get("lifestyle"),
                                isolation_source=request.POST.get("isolation_source"),
                                isolation_method=request.POST.get("isolation_method"),
                                genome_type=request.POST.get("genome_type"),
                                genome_size_bp=request.POST.get("genome_size_bp") or None,
                                ncbi_accession=request.POST.get("ncbi_accession"),
                                temp_C=request.POST.get("temp_C") or None
                            )

                        # PLASMID
                        elif sample_type == "Plasmid":
                            r_b_markers = request.POST.get("backbone_resistance_markers", "")
                            r_b_list = [r.strip() for r in r_b_markers.split(",") if r.strip()]

                            r_i_markers = request.POST.get("insert_resistance_markers", "")
                            r_i_list = [r.strip() for r in r_i_markers.split(",") if r.strip()]

                            is_empty = request.POST.get("is_empty_vector") in ["true", "on", "1"]

                            b_size_raw = request.POST.get("backbone_size_bp", "")
                            b_size = int(b_size_raw) if b_size_raw.isdigit() else 0

                            i_size_raw = request.POST.get("insert_size_bp", "")
                            i_size = int(i_size_raw) if i_size_raw.isdigit() else 0

                            sample = Plasmid.objects.create(
                                **base_data,
                                backbone_name=request.POST.get("backbone_name", ""),
                                backbone_aliases=request.POST.get("backbone_aliases", ""),
                                vector_type=request.POST.get("vector_type", ""),
                                induction_system=request.POST.get("induction_system", ""),
                                origin_of_replication=request.POST.get("origin_of_replication", ""),
                                backbone_size_bp=b_size,
                                backbone_resistance_markers=r_b_list,
                                is_empty_vector=is_empty,
                                insert_name=request.POST.get("insert_name", ""),
                                purpose=request.POST.get("purpose", ""),
                                insert_size_bp=i_size,
                                insert_resistance_markers=r_i_list,
                                construction_name=request.POST.get("construction_name", "")
                            )

                        else:
                            sample = Sample.objects.create(**base_data)

                        # Collections & Parents
                        if selected_collections:
                            sample.collections.add(*selected_collections)

                        if parent_sample_obj:
                            SampleRelationship.objects.create(
                                source_sample=parent_sample_obj,
                                target_sample=sample,
                                relationship_type=parent_rel_type,
                                created_by=user,
                                notes="Relationship generated automatically during registration."
                            )

                        # Tags & Keywords
                        tag_ids = request.POST.getlist("tags")
                        sample.tags.set(
                            active_tags_from_ids(tag_ids)
                        )

                        for raw in request.POST.getlist("keyword_pairs"):
                            if ":::" in raw:
                                key, value = raw.split(":::")
                                keyword_value, _ = (
                                    get_or_create_active_keyword_value(
                                        key,
                                        value,
                                    )
                                )
                                sample.keywords.add(keyword_value)

                        # =========================================================
                        # BIOLOGICAL RELATIONSHIPS (DYNAMIC ROWS)
                        # =========================================================
                        host_bacterium_ids = request.POST.getlist("host_bacterium[]")
                        host_bacterium_notes = request.POST.getlist("host_bacterium_notes[]")

                        stored_plasmids_ids = request.POST.getlist("stored_plasmids[]")
                        stored_plasmids_notes = request.POST.getlist("stored_plasmids_notes[]")

                        infecting_phages_ids = request.POST.getlist("infecting_phages[]")
                        infecting_phages_notes = request.POST.getlist("infecting_phages_notes[]")

                        if "Bacterium" in sample_type:
                            for idx, p_id in enumerate(stored_plasmids_ids):
                                if not p_id.strip(): continue
                                notes = stored_plasmids_notes[idx] if idx < len(stored_plasmids_notes) else ""
                                plasmid_obj = Sample.objects.filter(sample_id=p_id.strip()).first()
                                if plasmid_obj:
                                    SampleRelationship.objects.create(
                                        source_sample=sample, target_sample=plasmid_obj,
                                        relationship_type="STORAGE", created_by=user,
                                        notes=f"Linked during Bacterium registration. Details: {notes}"
                                    )

                            for idx, ph_id in enumerate(infecting_phages_ids):
                                if not ph_id.strip(): continue
                                notes = infecting_phages_notes[idx] if idx < len(infecting_phages_notes) else ""
                                phage_obj = Phage.objects.filter(sample_id=ph_id.strip()).first()
                                if phage_obj and hasattr(sample, 'bacteria'):
                                    HostRange.objects.update_or_create(
                                        phage=phage_obj, bacteria=sample.bacteria,
                                        defaults={'notes': notes}
                                    )

                        elif "Phage" in sample_type:
                            for idx, h_id in enumerate(host_bacterium_ids):
                                if not h_id.strip(): continue
                                notes = host_bacterium_notes[idx] if idx < len(host_bacterium_notes) else ""
                                bacterium_obj = Bacteria.objects.filter(sample_id=h_id.strip()).first()
                                if bacterium_obj and hasattr(sample, 'phage'):
                                    HostRange.objects.update_or_create(
                                        phage=sample.phage, bacteria=bacterium_obj,
                                        defaults={'notes': notes}
                                    )

                        elif "Plasmid" in sample_type:
                            for idx, h_id in enumerate(host_bacterium_ids):
                                if not h_id.strip(): continue
                                notes = host_bacterium_notes[idx] if idx < len(host_bacterium_notes) else ""
                                bacterium_obj = Sample.objects.filter(sample_id=h_id.strip()).first()
                                if bacterium_obj:
                                    SampleRelationship.objects.create(
                                        source_sample=bacterium_obj, target_sample=sample,
                                        relationship_type="STORAGE", created_by=user,
                                        notes=f"Linked during Plasmid registration. Details: {notes}"
                                    )

                        # Log Creation Event
                        Event.objects.create(
                            sample=sample,
                            performed_by=user,
                            event_type="entry",
                            location_snapshot=storage_location,
                            notes=f"Sample registered: {sample.organism_name}."
                        )

                        save_sample_origin(
                            sample,
                            origin_data,
                        )

                        created_samples.append(sample)

                    # Attachments
                    files = request.FILES.getlist("file")
                    categories = request.POST.getlist("file_category")
                    descriptions = request.POST.getlist("file_description")
                    from core.models.samples.sample import SampleStorageLevel

                    valid_file_categories = {
                        choice[0]
                        for choice in SampleFile.VIEW_CATEGORIES
                    }

                    legacy_file_category_aliases = {
                        "Sequence": "sequence",
                        "Other": "raw",
                    }

                    for sample in created_samples:
                        for k, f in enumerate(files):
                            category = (
                                categories[k]
                                if k < len(categories)
                                else "raw"
                            )

                            category = (
                                legacy_file_category_aliases.get(
                                    category,
                                    category,
                                )
                            )

                            if category not in valid_file_categories:
                                category = "raw"

                            description = (
                                descriptions[k]
                                if k < len(descriptions)
                                else ""
                            )

                            SampleFile.objects.create(
                                sample=sample,
                                file=f,
                                category=category,
                                description=description,
                            )

                        if storage_location:
                            normalized_location = (
                                storage_location
                                .replace(">", "|")
                                .replace(",", "|")
                                .replace(";", "|")
                            )

                            storage_levels = [
                                level.strip()
                                for level in normalized_location.split("|")
                                if level.strip()
                            ]

                            for level_index, level_name in enumerate(
                                storage_levels
                            ):
                                SampleStorageLevel.objects.create(
                                    sample=sample,
                                    name=level_name,
                                    level_index=level_index,
                                )

                if intake_record is not None and created_samples:
                    intake_record.sample = created_samples[0]
                    intake_record.status = "used_for_sample"
                    intake_record.save(
                        update_fields=[
                            "sample",
                            "status",
                        ]
                    )

                total_aliquots = sum(
                    sample.aliquot_count
                    for sample in created_samples
                )

                messages.success(
                    request,
                    (
                        f"{len(created_samples)} Sample record(s) "
                        f"registered successfully with "
                        f"{total_aliquots} total aliquot(s)."
                    ),
                )
                return redirect("samples_list")

            except ValueError as ve:
                messages.error(request, str(ve))
            except Exception as e:
                logger.exception("Critical error while creating sample.")
                messages.error(request, f"Error processing sample: {str(e)}")

    user_biobanks = allowed_biobanks

    empty_plasmids = list(Plasmid.objects.filter(is_active=True, is_empty_vector=True).values(
        'sample_id', 'backbone_name', 'backbone_aliases', 'vector_type',
        'induction_system', 'origin_of_replication', 'backbone_size_bp', 'backbone_resistance_markers'
    ))

    intake_prefill = {}
    intake_id = request.GET.get("intake_id")

    if intake_id:
        intake_record = get_object_or_404(SampleIntakeRecord, id=intake_id)

        if intake_record.batch.uploaded_by != request.user and not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to use this intake record.")

        normalized = intake_record.normalized_data or {}

        intake_prefill = {
            **normalized,
            "intake_record_id": intake_record.id,
            "sample_id": intake_record.imported_sample_id or "",
            "sample_type": intake_record.sample_type or "",
            "organism_name": intake_record.organism_name or "",
            "storage_location": intake_record.storage_location or "",
            "provider": intake_record.provider or "",
            "scientific_notes": intake_record.scientific_notes or "",
            "is_public": intake_record.is_public,
            "matched_biobank_id": intake_record.matched_biobank_id,
            "matched_biobank_name": intake_record.matched_biobank.name if intake_record.matched_biobank else "",
            "matched_collection_id": intake_record.matched_collection_id,
            "matched_collection_name": intake_record.matched_collection.name if intake_record.matched_collection else "",
        }

    ctx = base_context(request)
    ctx.update({
        "collections": allowed_collections,
        "all_tags": Tag.objects.filter(
            is_active=True,
        ).order_by("name"),
        "sample_owner_options": allowed_owners,
        "sample_research_groups": allowed_research_groups,
        "default_owner_id": user.pk,
        "biobanks": user_biobanks,
        "all_samples": visible_samples_for_user(user).values('sample_id', 'organism_name', 'sample_type'),
        "empty_plasmids_json": json.dumps(empty_plasmids),
        "intake_prefill": intake_prefill,
        "origin_form": origin_form,
    })
    return render(request, "internal/samples/samples.html", ctx)


# =========================================================
# 3. PRINT & QR CODE SCAN VIEW
# =========================================================
@login_required
def print_sample_label(request, sample_id):
    sample = get_object_or_404(
        Sample,
        id=sample_id,
    )

    if not can_view_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    qr_base64 = sample_micro_qr_png_base64(
        sample.micro_qr_token
    )

    return render(
        request,
        "internal/samples/print_label.html",
        {
            "sample": sample,
            "qr_code": qr_base64,
            "micro_qr_designator": "M3-M",
        },
    )


def sample_qr_scan_view(request, uuid):
    """
    Página mobile-friendly acessada ao ler o QR Code com o celular.
    """
    sample = get_object_or_404(Sample, uuid=uuid)

    # Use named routes so redirects preserve the configured C3 LIMS script prefix.
    sample_is_publicly_accessible = (
        sample.is_active
        and sample.is_public
        and not sample.is_embargoed
        and sample.deletion_requested_at is None
    )

    if not sample_is_publicly_accessible:
        if not request.user.is_authenticated:
            login_url = reverse('login')
            next_url = reverse('sample_qr_scan', args=[sample.uuid])
            return redirect(f"{login_url}?next={next_url}")

        from core.permissions.samples import can_view_sample
        if not can_view_sample(request.user, sample):
            raise PermissionDenied("You do not have permission to view this sample.")

    # Descobrir o subtipo exato para exibir na ficha (Bacteria, Phage, Plasmid)
    if hasattr(sample, 'bacteria'): real_sample = sample.bacteria
    elif hasattr(sample, 'phage'): real_sample = sample.phage
    elif hasattr(sample, 'plasmid'): real_sample = sample.plasmid
    else: real_sample = sample

    ctx = base_context(request) if request.user.is_authenticated else {}
    ctx['sample'] = real_sample

    return render(request, "internal/samples/qr_view.html", ctx)


@login_required
def sample_micro_qr_lookup_view(request):
    """
    Resolve a Sample Micro QR token entered manually or
    supplied by a keyboard-wedge barcode scanner.
    """
    token = request.GET.get(
        "token",
        "",
    )

    error = ""

    if token:
        try:
            normalized_token = (
                normalize_sample_micro_qr_token(
                    token
                )
            )
        except InvalidSampleMicroQrToken:
            error = (
                "Enter a valid 10-character "
                "Sample Micro QR token."
            )
        else:
            sample = Sample.objects.filter(
                micro_qr_token=normalized_token
            ).first()

            if sample is None:
                error = (
                    "No Sample was found for this "
                    "Micro QR token."
                )
            elif not can_view_sample(
                request.user,
                sample,
            ):
                raise PermissionDenied(
                    "You do not have permission "
                    "to view this sample."
                )
            else:
                return redirect(
                    "sample_micro_qr_resolve",
                    token=sample.micro_qr_token,
                )

    ctx = base_context(request)
    ctx.update(
        {
            "micro_qr_token": token,
            "micro_qr_error": error,
        }
    )

    return render(
        request,
        "internal/samples/micro_qr_lookup.html",
        ctx,
    )


def sample_micro_qr_resolve_view(
    request,
    token,
):
    """
    Resolve a compact Sample Micro QR token while preserving
    the same visibility and authorization contract used by
    legacy UUID Sample QR labels.
    """
    try:
        normalized_token = (
            normalize_sample_micro_qr_token(
                token
            )
        )
    except InvalidSampleMicroQrToken as exc:
        raise Http404(
            "Sample Micro QR token not found."
        ) from exc

    sample = get_object_or_404(
        Sample,
        micro_qr_token=normalized_token,
    )

    sample_is_publicly_accessible = (
        sample.is_active
        and sample.is_public
        and not sample.is_embargoed
        and sample.deletion_requested_at
        is None
    )

    if not sample_is_publicly_accessible:
        if not request.user.is_authenticated:
            login_url = reverse("login")
            next_url = reverse(
                "sample_micro_qr_resolve",
                args=[
                    sample.micro_qr_token,
                ],
            )
            return redirect(
                f"{login_url}?next={next_url}"
            )

        if not can_view_sample(
            request.user,
            sample,
        ):
            raise PermissionDenied(
                "You do not have permission "
                "to view this sample."
            )

    if hasattr(sample, "bacteria"):
        real_sample = sample.bacteria
    elif hasattr(sample, "phage"):
        real_sample = sample.phage
    elif hasattr(sample, "plasmid"):
        real_sample = sample.plasmid
    else:
        real_sample = sample

    ctx = (
        base_context(request)
        if request.user.is_authenticated
        else {}
    )

    ctx["sample"] = real_sample

    return render(
        request,
        "internal/samples/qr_view.html",
        ctx,
    )


@login_required
def export_samples_csv(request):
    """
    Export samples using the standardized table schema.

    Supported query parameters:
    - format=csv|xlsx
    - schema=standard|full
    - biobank=<name_or_id>
    - collection=<name_or_id>
    - sample_type=<Sample Type>
    - status=<status>
    - include_inactive=1
    """
    return export_samples_table(request)



def _safe_sample_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _posted_sample_identity(request):
    """
    Try to recover the user-facing identification from POST data.

    The edit form may vary by sample subtype, so we check generic and
    subtype-specific fields.
    """
    for key in [
        "organism_name",
        "identification",
        "name",
        "display_name",
        "phage_name",
        "construction_name",
        "backbone_name",
        "insert_name",
        "strain",
        "species",
    ]:
        value = _safe_sample_text(request.POST.get(key, ""))
        if value:
            return value

    return ""


def _infer_sample_identity(base_sample, real_sample=None):
    """
    Preserve or infer the sample identification shown in the sample list/edit.

    Priority:
    1. Existing base Sample organism_name
    2. Subtype/display fields
    3. sample_id
    """
    objects = [base_sample]

    if real_sample is not None and real_sample is not base_sample:
        objects.append(real_sample)

    for obj in objects:
        for attr in [
            "organism_name",
            "name",
            "display_name",
            "phage_name",
            "backbone_name",
            "construction_name",
            "insert_name",
            "strain",
            "species",
            "sample_id",
        ]:
            if hasattr(obj, attr):
                value = _safe_sample_text(getattr(obj, attr, ""))
                if value:
                    return value

    return ""


def _preferred_sample_identity(base_sample, real_sample=None):
    """
    Canonical display identity for sample list/dashboard.

    Rules:
    - Bacterium: official_name first.
    - Phage: official_name, then strain; legacy phage_name remains a fallback.
    - Plasmid: construction_name first, then backbone_name.
    """
    sample_type = _safe_sample_text(getattr(base_sample, "sample_type", ""))

    obj = real_sample or base_sample

    if "Bacterium" in sample_type:
        official_name = _safe_sample_text(getattr(obj, "official_name", ""))
        if official_name:
            return official_name

        genus = _safe_sample_text(getattr(obj, "genus", ""))
        species = _safe_sample_text(getattr(obj, "species", ""))
        strain = _safe_sample_text(getattr(obj, "strain", ""))
        inferred = format_bacterial_taxonomic_name(genus, species, strain)
        if inferred:
            return inferred

    if "Phage" in sample_type:
        for attr in ["official_name", "strain", "phage_name"]:
            value = _safe_sample_text(getattr(obj, attr, ""))
            if value:
                return value

        genus = _safe_sample_text(getattr(obj, "genus", ""))
        taxonomy = _safe_sample_text(getattr(obj, "taxonomy", ""))
        inferred = " ".join(part for part in [genus, taxonomy] if part)
        if inferred:
            return inferred

    if "Plasmid" in sample_type:
        for attr in ["construction_name", "backbone_name"]:
            value = _safe_sample_text(getattr(obj, attr, ""))
            if value:
                return value

    return _infer_sample_identity(base_sample, real_sample)


def _sync_sample_after_successful_edit(base_sample, real_sample, request, identity_before):
    """
    After a successful internal edit:
    - do not allow a blank form submission to erase identification
    - preserve the Sample workflow status
    """
    try:
        base_sample.refresh_from_db()
    except Exception:
        pass

    posted_identity = _posted_sample_identity(request)
    preferred_identity = _preferred_sample_identity(base_sample, real_sample)
    existing_identity = _safe_sample_text(getattr(base_sample, "organism_name", ""))
    inferred_identity = _infer_sample_identity(base_sample, real_sample)

    final_identity = (
        preferred_identity
        or posted_identity
        or existing_identity
        or _safe_sample_text(identity_before)
        or inferred_identity
    )

    update_fields = []

    if hasattr(base_sample, "organism_name") and final_identity:
        base_sample.organism_name = final_identity
        update_fields.append("organism_name")

    if update_fields:
        base_sample.save(update_fields=list(dict.fromkeys(update_fields)))

    return final_identity



def _clean_posted_sample_ids(values):
    seen = set()
    cleaned = []
    for value in values:
        value = _safe_sample_text(value)
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def _sync_sample_edit_relationships(base_sample, request, user):
    """
    Persist biological/storage relationships submitted from Edit Sample.

    This mirrors the relationship creation flow used in Register New Sample.
    """
    sample_type = base_sample.sample_type or ""

    # The Edit Sample datalist exposes only Samples visible to the
    # current user. Enforce the same boundary on crafted POST data.
    visible_target_ids = set(
        visible_samples_for_user(
            user
        ).values_list(
            "pk",
            flat=True,
        )
    )

    host_ids = _clean_posted_sample_ids(request.POST.getlist("host_bacterium[]"))
    host_notes = request.POST.getlist("host_bacterium_notes[]")

    plasmid_ids = _clean_posted_sample_ids(request.POST.getlist("stored_plasmids[]"))
    plasmid_notes = request.POST.getlist("stored_plasmids_notes[]")

    phage_ids = _clean_posted_sample_ids(request.POST.getlist("infecting_phages[]"))
    phage_notes = request.POST.getlist("infecting_phages_notes[]")

    if "Bacterium" in sample_type:
        for idx, plasmid_sample_id in enumerate(plasmid_ids):
            target = (
                Sample.objects
                .filter(
                    pk__in=visible_target_ids,
                    sample_id=plasmid_sample_id,
                )
                .first()
            )
            if not target:
                continue
            notes = plasmid_notes[idx] if idx < len(plasmid_notes) else ""
            SampleRelationship.objects.update_or_create(
                source_sample=base_sample,
                target_sample=target,
                relationship_type="STORAGE",
                defaults={
                    "created_by": user,
                    "notes": f"Linked during Bacterium edit. Details: {notes}",
                },
            )

        if hasattr(base_sample, "bacteria"):
            for idx, phage_sample_id in enumerate(phage_ids):
                phage = (
                    Phage.objects
                    .filter(
                        pk__in=visible_target_ids,
                        sample_id=phage_sample_id,
                    )
                    .first()
                )
                if not phage:
                    continue
                notes = phage_notes[idx] if idx < len(phage_notes) else ""
                HostRange.objects.update_or_create(
                    phage=phage,
                    bacteria=base_sample.bacteria,
                    defaults={"notes": notes},
                )

    elif "Phage" in sample_type and hasattr(base_sample, "phage"):
        for idx, host_sample_id in enumerate(host_ids):
            bacteria = (
                Bacteria.objects
                .filter(
                    pk__in=visible_target_ids,
                    sample_id=host_sample_id,
                )
                .first()
            )
            if not bacteria:
                continue
            notes = host_notes[idx] if idx < len(host_notes) else ""
            HostRange.objects.update_or_create(
                phage=base_sample.phage,
                bacteria=bacteria,
                defaults={"notes": notes},
            )

    elif "Plasmid" in sample_type:
        for idx, host_sample_id in enumerate(host_ids):
            host = (
                Sample.objects
                .filter(
                    pk__in=visible_target_ids,
                    sample_id=host_sample_id,
                )
                .first()
            )
            if not host:
                continue
            notes = host_notes[idx] if idx < len(host_notes) else ""
            SampleRelationship.objects.update_or_create(
                source_sample=host,
                target_sample=base_sample,
                relationship_type="STORAGE",
                defaults={
                    "created_by": user,
                    "notes": f"Linked during Plasmid edit. Details: {notes}",
                },
            )

SAMPLE_EDIT_NON_BIOLOGICAL_FIELD_NAMES = frozenset(
    {
        "sample_id",
        "sample_type",
        "biosafety_level",
        "organism_name",
        "status",
        "aliquot_count",
        "is_public",
        "is_embargoed",
        "owner",
        "research_group",
        "storage_location",
        "biobank",
        "collections",
        "scientific_notes",
        "notes",
        "collaborator",
    }
)


def _sample_edit_biological_fields(
    form,
):
    """
    Return subtype-specific fields for the Biological Properties
    section of Edit Sample.

    Base Sample, governance, inventory, storage and ELN fields are
    rendered explicitly in dedicated sections of the page.
    """
    return tuple(
        form[
            field_name
        ]
        for field_name in form.fields
        if field_name
        not in SAMPLE_EDIT_NON_BIOLOGICAL_FIELD_NAMES
    )


@login_required
def sample_edit_view(request, sample_id):
    base_sample = get_object_or_404(Sample, id=sample_id)

    if hasattr(base_sample, 'bacteria'):
        real_sample = base_sample.bacteria
    elif hasattr(base_sample, 'phage'):
        real_sample = base_sample.phage
    elif hasattr(base_sample, 'plasmid'):
        real_sample = base_sample.plasmid
    else:
        real_sample = base_sample

    if not can_edit_sample(request.user, real_sample) and not request.user.is_superuser:
        raise PermissionDenied

    FormClass = get_form_class_for_sample(real_sample)

    origin_instance = (
        SampleOrigin.objects
        .filter(
            sample=base_sample,
        )
        .first()
    )

    if request.method == "POST":
        form = FormClass(
            request.POST,
            request.FILES,
            instance=real_sample,
            user=request.user,
        )

        origin_form = SampleOriginForm(
            request.POST,
            instance=origin_instance,
            prefix="origin",
        )

        keyword_pairs_text = (
            request.POST.get(
                "keyword_pairs_text",
                "",
            )
            or ""
        )

        keyword_pairs = []
        keyword_pairs_error = ""

        for line_number, raw_line in enumerate(
            keyword_pairs_text.splitlines(),
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                continue

            if ":" not in line:
                keyword_pairs_error = (
                    f"Custom keyword line {line_number} must use "
                    "the format Key: Value."
                )
                break

            key, value = line.split(
                ":",
                1,
            )

            key = key.strip()
            value = value.strip()

            if not key or not value:
                keyword_pairs_error = (
                    f"Custom keyword line {line_number} must contain "
                    "both a key and a value."
                )
                break

            keyword_pairs.append(
                (
                    key,
                    value,
                )
            )

        keyword_pairs = list(
            dict.fromkeys(
                keyword_pairs
            )
        )

        form_valid = form.is_valid()
        origin_valid = origin_form.is_valid()

        if keyword_pairs_error:
            form.add_error(
                None,
                keyword_pairs_error,
            )

        if (
            form_valid
            and origin_valid
            and not keyword_pairs_error
        ):
            identity_before = _safe_sample_text(getattr(base_sample, "organism_name", ""))
            real_sample = form.save()

            save_sample_origin(
                base_sample,
                origin_form.cleaned_data,
            )

            _sync_sample_after_successful_edit(
                base_sample=base_sample,
                real_sample=real_sample,
                request=request,
                identity_before=identity_before,
            )

            _sync_sample_edit_relationships(
                base_sample=base_sample,
                request=request,
                user=request.user,
            )


            tag_ids = request.POST.getlist(
                "tags"
            )

            base_sample.tags.set(
                active_tags_from_ids(
                    tag_ids
                )
            )

            base_sample.keywords.clear()

            for key, value in keyword_pairs:
                keyword_value, _ = (
                    get_or_create_active_keyword_value(
                        key,
                        value,
                    )
                )

                base_sample.keywords.add(
                    keyword_value
                )

            storage_location = form.cleaned_data.get("storage_location", "")

            if storage_location:
                assign_sample_storage_from_text(
                    sample=base_sample,
                    storage_location_text=storage_location,
                    replace_existing=True,
                    sync_legacy_field=True,
                )
            else:
                assign_sample_storage_from_text(
                    sample=base_sample,
                    storage_location_text="",
                    replace_existing=True,
                    sync_legacy_field=True,
                )

            remove_file_ids = request.POST.getlist("remove_file_ids")
            removed_count = 0
            if remove_file_ids:
                removed_count, _ = SampleFile.objects.filter(
                    sample=base_sample,
                    id__in=remove_file_ids,
                ).delete()

            files = request.FILES.getlist("file")
            categories = request.POST.getlist("file_category")
            descriptions = request.POST.getlist("file_description")
            valid_categories = {choice[0] for choice in SampleFile.VIEW_CATEGORIES}

            for k, f in enumerate(files):
                category = (
                    categories[k]
                    if k < len(categories)
                    else "raw"
                )

                category = {
                    "Sequence": "sequence",
                    "Other": "raw",
                }.get(
                    category,
                    category,
                )

                if category not in valid_categories:
                    category = "raw"

                description = (
                    descriptions[k]
                    if k < len(descriptions)
                    else ""
                )

                sample_file = SampleFile.objects.create(
                    sample=base_sample,
                    file=f,
                    category=category,
                    description=description,
                )

                # SampleFile.save() may auto-detect a category from
                # the extension. Preserve the explicit user choice.
                SampleFile.objects.filter(
                    pk=sample_file.pk
                ).update(
                    category=category
                )

            if removed_count:
                messages.info(request, f"{removed_count} sample file link(s) removed. Physical files were kept in storage.")

            messages.success(request, "Sample updated successfully!")
            return redirect("samples_list")

        messages.error(request, "Error updating. Please check the fields.")
    else:
        form = FormClass(
            instance=real_sample,
            user=request.user,
        )

        origin_form = SampleOriginForm(
            instance=origin_instance,
            prefix="origin",
        )

    parents = base_sample.incoming_relationships.all()
    children = base_sample.outgoing_relationships.all()
    sample_files = SampleFile.objects.filter(sample=base_sample).order_by('-uploaded_at')

    current_host_id = ""
    current_plasmids_string = ""
    current_phages_string = ""

    if hasattr(real_sample, 'phage'):
        hosts = real_sample.host_interactions.all()
        current_host_id = ",".join([h.bacteria.sample_id for h in hosts])
    elif hasattr(real_sample, 'bacteria'):
        phages = real_sample.phage_interactions.all()
        current_phages_string = ",".join([p.phage.sample_id for p in phages])
        plasmids = SampleRelationship.objects.filter(source_sample=real_sample, relationship_type="STORAGE")
        current_plasmids_string = ",".join([p.target_sample.sample_id for p in plasmids])
    elif hasattr(real_sample, 'plasmid'):
        hosts = SampleRelationship.objects.filter(target_sample=real_sample, relationship_type="STORAGE")
        current_host_id = ",".join([h.source_sample.sample_id for h in hosts])

    current_storage_paths = get_all_storage_paths(base_sample)
    current_storage_location = "; ".join(current_storage_paths) if current_storage_paths else (base_sample.storage_location or "")

    if "storage_location" in form.fields and current_storage_location:
        form.initial["storage_location"] = current_storage_location

    all_tags = (
        Tag.objects
        .filter(
            is_active=True,
        )
        .order_by(
            "name"
        )
    )

    if request.method == "POST":
        selected_tag_ids = []

        for raw_tag_id in request.POST.getlist(
            "tags"
        ):
            try:
                selected_tag_ids.append(
                    int(
                        raw_tag_id
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        keyword_pairs_text = (
            request.POST.get(
                "keyword_pairs_text",
                "",
            )
            or ""
        )

    else:
        selected_tag_ids = list(
            base_sample.tags.values_list(
                "pk",
                flat=True,
            )
        )

        keyword_pairs_text = "\n".join(
            (
                f"{keyword_value.keyword.name}: "
                f"{keyword_value.value}"
            )
            for keyword_value in (
                base_sample.keywords
                .select_related(
                    "keyword"
                )
                .order_by(
                    "keyword__name",
                    "value",
                )
            )
        )

    ctx = base_context(request)
    ctx.update({
        'form': form,
        'biological_fields': _sample_edit_biological_fields(
            form
        ),
        'sample': real_sample,
        'parents': parents,
        'children': children,
        'sample_files': sample_files,
        "origin_form": origin_form,
        'current_host_id': current_host_id,
        'current_plasmids_string': current_plasmids_string,
        'current_phages_string': current_phages_string,
        'current_storage_location': current_storage_location,
        'current_storage_paths': current_storage_paths,
        'all_tags': all_tags,
        'selected_tag_ids': selected_tag_ids,
        'keyword_pairs_text': keyword_pairs_text,
        'all_samples': visible_samples_for_user(request.user).values('sample_id', 'organism_name', 'sample_type'),
    })
    return render(request, "internal/samples/edit.html", ctx)





@login_required
def sample_file_download_view(
    request,
    sample_file_id,
):
    sample_file = get_object_or_404(
        SampleFile.objects.select_related(
            "sample",
            "sample__owner",
            "sample__research_group",
        ).prefetch_related(
            "sample__collections",
            "sample__collections__research_group",
        ),
        pk=sample_file_id,
    )

    if not can_view_sample(
        request.user,
        sample_file.sample,
    ):
        raise PermissionDenied

    if not sample_file.file:
        raise Http404(
            "Sample file is not available."
        )

    try:
        handle = sample_file.file.open("rb")
    except (FileNotFoundError, OSError) as exc:
        raise Http404(
            "Sample file was not found in storage."
        ) from exc

    filename = (
        PurePosixPath(
            sample_file.file.name
        ).name
        or f"sample-file-{sample_file.pk}"
    )

    response_kwargs = {
        "as_attachment": False,
        "filename": filename,
    }

    if sample_file.mime_type:
        response_kwargs["content_type"] = (
            sample_file.mime_type
        )

    return FileResponse(
        handle,
        **response_kwargs,
    )


@login_required
@require_POST
def sample_genome_assembly_review_view(
    request,
    sample_id,
    assignment_id,
):
    from core.models.samples.enrichment import (
        SampleGenomeAssemblyAssignment,
    )
    from core.services.sample_enrichment.assembly_review import (
        review_genome_assembly_assignment,
    )

    base_sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if (
        not can_edit_sample(
            request.user,
            base_sample,
        )
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    assignment = get_object_or_404(
        SampleGenomeAssemblyAssignment,
        pk=assignment_id,
        sample=base_sample,
        is_current=True,
    )

    new_status = (
        request.POST
        .get(
            "status",
            "",
        )
        .strip()
        .lower()
    )

    note = (
        request.POST
        .get(
            "note",
            "",
        )
        .strip()
    )

    try:
        review = (
            review_genome_assembly_assignment(
                assignment=assignment,
                reviewer=request.user,
                new_status=new_status,
                note=note,
            )
        )

    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )

    else:
        messages.success(
            request,
            (
                "Genome Assembly review recorded: "
                f"{review.assignment.accession} "
                f"is now "
                f"{review.assignment.get_match_status_display()}."
            ),
        )

    return redirect(
        "sample_detail",
        sample_id=base_sample.pk,
    )


@login_required
@require_POST
def sample_ncbi_genome_resolve_view(
    request,
    sample_id,
):
    base_sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if (
        not can_edit_sample(
            request.user,
            base_sample,
        )
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    from core.services.sample_enrichment.ncbi_genome import (
        NCBIGenomeLookupError,
        resolve_and_store_ncbi_genome_assembly,
    )

    accession = (
        request.POST
        .get(
            "accession",
            "",
        )
        .strip()
    )

    if not accession:
        messages.error(
            request,
            (
                "Enter an explicit versioned NCBI "
                "Assembly accession before resolving "
                "Genome Assembly metadata."
            ),
        )

        return redirect(
            "sample_detail",
            sample_id=base_sample.pk,
        )

    try:
        result = (
            resolve_and_store_ncbi_genome_assembly(
                base_sample,
                request.user,
                accession,
            )
        )

    except ValueError as exc:
        messages.error(
            request,
            str(exc),
        )

    except NCBIGenomeLookupError as exc:
        messages.error(
            request,
            (
                "NCBI Genome Assembly lookup failed: "
                f"{exc}"
            ),
        )

    else:
        assignment = result.get(
            "assignment"
        )

        normalized = (
            result.get(
                "normalized"
            )
            or {}
        )

        if assignment is not None:
            details = []

            if assignment.assembly_name:
                details.append(
                    assignment.assembly_name
                )

            if assignment.organism_name:
                details.append(
                    assignment.organism_name
                )

            detail_suffix = (
                " · " + " · ".join(details)
                if details
                else ""
            )

            messages.success(
                request,
                (
                    "NCBI Genome Assembly resolved: "
                    f"{assignment.accession}"
                    f"{detail_suffix}."
                ),
            )

        else:
            resolution_status = str(
                normalized.get(
                    "resolution_status",
                    "unresolved",
                )
                or "unresolved"
            ).replace(
                "_",
                " ",
            )

            messages.warning(
                request,
                (
                    "NCBI Genome Assembly lookup did "
                    "not produce a unique assignment "
                    f"({resolution_status})."
                ),
            )

    return redirect(
        "sample_detail",
        sample_id=base_sample.pk,
    )


@login_required
@require_POST
def sample_taxonomy_review_view(
    request,
    sample_id,
    assignment_id,
):
    from core.models.samples.enrichment import (
        SampleTaxonomyAssignment,
    )
    from core.services.sample_enrichment.taxonomy_review import (
        review_taxonomy_assignment,
    )

    base_sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if (
        not can_edit_sample(
            request.user,
            base_sample,
        )
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    assignment = get_object_or_404(
        SampleTaxonomyAssignment,
        pk=assignment_id,
        sample=base_sample,
        is_current=True,
    )

    new_status = (
        request.POST
        .get(
            "status",
            "",
        )
        .strip()
        .lower()
    )

    note = (
        request.POST
        .get(
            "note",
            "",
        )
        .strip()
    )

    try:
        review = (
            review_taxonomy_assignment(
                assignment=assignment,
                reviewer=request.user,
                new_status=new_status,
                note=note,
            )
        )

    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )

    else:
        messages.success(
            request,
            (
                "Taxonomy review recorded: "
                f"{review.assignment.scientific_name} "
                f"is now "
                f"{review.assignment.get_match_status_display()}."
            ),
        )

    return redirect(
        "sample_detail",
        sample_id=base_sample.pk,
    )


@login_required
@require_POST
def sample_ncbi_taxonomy_resolve_view(
    request,
    sample_id,
):
    base_sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if (
        not can_edit_sample(
            request.user,
            base_sample,
        )
        and not request.user.is_superuser
    ):
        raise PermissionDenied

    from core.services.sample_enrichment.ncbi_taxonomy import (
        NCBITaxonomyLookupError,
        resolve_and_store_ncbi_taxonomy,
        suggest_ncbi_taxonomy_query,
    )

    query = (
        request.POST
        .get(
            "query",
            "",
        )
        .strip()
    )

    if not query:
        query = (
            suggest_ncbi_taxonomy_query(
                base_sample
            )
        )

    if not query:
        messages.error(
            request,
            (
                "Enter an NCBI TaxID or scientific "
                "name before resolving taxonomy."
            ),
        )

        return redirect(
            "sample_detail",
            sample_id=base_sample.pk,
        )

    try:
        result = (
            resolve_and_store_ncbi_taxonomy(
                base_sample,
                request.user,
                query,
            )
        )

    except NCBITaxonomyLookupError as exc:
        messages.error(
            request,
            (
                "NCBI Taxonomy lookup failed: "
                f"{exc}"
            ),
        )

    else:
        assignment = result.get(
            "assignment"
        )

        normalized = (
            result.get(
                "normalized"
            )
            or {}
        )

        if assignment is not None:
            messages.success(
                request,
                (
                    "NCBI Taxonomy resolved: "
                    f"{assignment.scientific_name} "
                    f"(TaxID {assignment.taxon_id})."
                ),
            )

        elif (
            normalized.get(
                "resolution_status"
            )
            == "not_found"
        ):
            messages.warning(
                request,
                (
                    "NCBI Taxonomy returned no "
                    "matching record."
                ),
            )

        else:
            messages.warning(
                request,
                (
                    "NCBI Taxonomy could not be "
                    "resolved to exactly one record. "
                    "No taxonomy assignment was created."
                ),
            )

    return redirect(
        "sample_detail",
        sample_id=base_sample.pk,
    )


@login_required
def sample_detail_view(request, sample_id):
    """
    Central detail page for a sample, gathering identity, storage,
    governance, relationships, files and operational actions.
    """
    base_sample = get_object_or_404(
        Sample.objects.select_related("biobank", "owner", "research_group").prefetch_related("collections"),
        id=sample_id,
    )

    if not can_view_sample(request.user, base_sample) and not request.user.is_superuser:
        raise PermissionDenied

    if hasattr(base_sample, "bacteria"):
        real_sample = base_sample.bacteria
    elif hasattr(base_sample, "phage"):
        real_sample = base_sample.phage
    elif hasattr(base_sample, "plasmid"):
        real_sample = base_sample.plasmid
    else:
        real_sample = base_sample

    parents = base_sample.incoming_relationships.select_related("source_sample", "target_sample").all()
    children = base_sample.outgoing_relationships.select_related("source_sample", "target_sample").all()
    sample_files = SampleFile.objects.filter(sample=base_sample).order_by("-uploaded_at")
    current_storage_paths = get_all_storage_paths(base_sample)

    # Direct Sample sharing detail context.
    from django.contrib.auth import get_user_model
    from core.permissions.samples import (
        can_manage_sample_sharing,
    )

    SharingUser = get_user_model()

    direct_access_grants = list(
        base_sample.access_grants
        .select_related(
            "user",
            "granted_by",
        )
        .order_by(
            "user__username"
        )
    )

    current_direct_sample_grant = next(
        (
            grant
            for grant in direct_access_grants
            if (
                grant.user_id
                == request.user.id
                and not grant.is_expired
            )
        ),
        None,
    )

    can_manage_sharing = (
        can_manage_sample_sharing(
            request.user,
            base_sample,
        )
    )

    sample_share_users = (
        SharingUser.objects
        .filter(
            is_active=True,
        )
        .exclude(
            pk=base_sample.owner_id,
        )
        .exclude(
            pk=request.user.pk,
        )
        .order_by(
            "username"
        )
    )

    ctx = base_context(request)
    ctx.update({
        "sample": base_sample,
        "real_sample": real_sample,
        "parents": parents,
        "children": children,
        "sample_files": sample_files,
        "current_storage_paths": current_storage_paths,
        "can_manage_sample_sharing": (
            can_manage_sharing
        ),
        "direct_access_grants": (
            direct_access_grants
        ),
        "current_direct_sample_grant": (
            current_direct_sample_grant
        ),
        "sample_share_users": (
            sample_share_users
        ),
        "sample_origin": (
            SampleOrigin.objects
            .filter(
                sample=base_sample,
            )
            .first()
        ),
        "can_edit_current_sample": (
            can_edit_sample(
                request.user,
                base_sample,
            )
        ),
        "can_delete_current_sample": (
            can_delete_sample(
                request.user,
                base_sample,
            )
        ),
        "purge_is_due": bool(
            base_sample.purge_after
            and base_sample.purge_after
            <= timezone.now()
        ),
    })

    from core.services.sample_enrichment.ncbi_taxonomy import (
        suggest_ncbi_taxonomy_query,
    )

    ctx.update(
        {
            "external_identifiers": (
                base_sample.external_identifiers
                .all()
            ),
            "taxonomy_assignments": (
                base_sample.taxonomy_assignments
                .filter(
                    is_current=True
                )
                .select_related(
                    "reviewed_by",
                    "snapshot",
                )
                .prefetch_related(
                    "reviews__reviewer"
                )
                .order_by(
                    "source"
                )
            ),
            "genome_assembly_assignments": (
                base_sample.genome_assembly_assignments
                .filter(
                    is_current=True
                )
                .select_related(
                    "reviewed_by",
                    "snapshot",
                )
                .prefetch_related(
                    "reviews__reviewer"
                )
                .order_by(
                    "source",
                    "accession",
                )
            ),
            "enrichment_snapshots": (
                base_sample.enrichment_snapshots
                .all()[:5]
            ),
            "ncbi_taxonomy_suggested_query": (
                suggest_ncbi_taxonomy_query(
                    real_sample
                )
            ),
        }
    )

    return render(
        request,
        "internal/samples/detail.html",
        ctx,
    )



# =========================================================
# SAMPLE LIFECYCLE
# =========================================================

@login_required
def sample_lifecycle_view(request):
    """
    Display deactivated Samples and the 30-day Sample Trash.
    """
    candidates = (
        Sample.objects
        .filter(
            is_active=False,
        )
        .select_related(
            "owner",
            "research_group",
            "biobank",
            "deactivated_by",
            "deletion_requested_by",
        )
        .prefetch_related(
            "collections",
            "collections__research_group",
        )
        .order_by(
            "purge_after",
            "-updated_at",
        )
    )

    now = timezone.now()

    deactivated_samples = []
    trash_samples = []

    for sample in candidates:
        if sample.deletion_requested_at is None:
            if can_edit_sample(
                request.user,
                sample,
            ):
                deactivated_samples.append(
                    sample
                )
            continue

        if not can_delete_sample(
            request.user,
            sample,
        ):
            continue

        sample.purge_is_due = bool(
            sample.purge_after
            and sample.purge_after <= now
        )

        if (
            sample.purge_after
            and sample.purge_after > now
        ):
            delta = sample.purge_after - now
            sample.days_until_purge = (
                delta.days
                + (
                    1
                    if delta.seconds
                    or delta.microseconds
                    else 0
                )
            )
        else:
            sample.days_until_purge = 0

        trash_samples.append(
            sample
        )

    ctx = base_context(request)
    ctx.update(
        {
            "deactivated_samples": deactivated_samples,
            "trash_samples": trash_samples,
            "trash_retention_days": 30,
        }
    )

    return render(
        request,
        "internal/samples/lifecycle.html",
        ctx,
    )


@login_required
@require_POST
def sample_deactivate_view(
    request,
    sample_id,
):
    sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if not can_edit_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    try:
        deactivate_sample(
            sample,
            request.user,
        )
    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )
    else:
        messages.success(
            request,
            (
                f"Sample {sample.sample_id} "
                "was deactivated."
            ),
        )

    return redirect(
        "sample_detail",
        sample_id=sample.pk,
    )


@login_required
@require_POST
def sample_activate_view(
    request,
    sample_id,
):
    sample = get_object_or_404(
        Sample,
        pk=sample_id,
    )

    if not can_edit_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    try:
        activate_sample(
            sample,
            request.user,
        )
    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )
    else:
        messages.success(
            request,
            (
                f"Sample {sample.sample_id} "
                "was reactivated."
            ),
        )

    return redirect(
        "sample_detail",
        sample_id=sample.pk,
    )


@login_required
@require_POST
def sample_move_to_trash_view(
    request,
    sample_id,
):
    sample = get_object_or_404(
        Sample.objects.prefetch_related(
            "collections",
            "collections__research_group",
        ),
        pk=sample_id,
    )

    if not can_delete_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    try:
        move_sample_to_trash(
            sample,
            request.user,
        )
    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )
    else:
        messages.warning(
            request,
            (
                f"Sample {sample.sample_id} was moved to Trash. "
                "Permanent deletion is blocked for 30 days."
            ),
        )

    return redirect(
        "samples_lifecycle",
    )


@login_required
@require_POST
def sample_restore_view(
    request,
    sample_id,
):
    sample = get_object_or_404(
        Sample.objects.prefetch_related(
            "collections",
            "collections__research_group",
        ),
        pk=sample_id,
    )

    if not can_delete_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    try:
        restore_sample(
            sample,
            request.user,
        )
    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )
    else:
        messages.success(
            request,
            (
                f"Sample {sample.sample_id} "
                "was restored from Trash."
            ),
        )

    return redirect(
        "sample_detail",
        sample_id=sample.pk,
    )


@login_required
@require_POST
def sample_purge_view(
    request,
    sample_id,
):
    sample = get_object_or_404(
        Sample.objects.prefetch_related(
            "collections",
            "collections__research_group",
            "files",
            "events",
            "outgoing_relationships",
            "incoming_relationships",
            "storage_levels",
            "storage_assignments",
            "intake_records",
            "shipment_items",
            "notebook_mentions",
            "notebook_sample_links",
            "molecular_sequences",
            "tags",
            "keywords",
        ),
        pk=sample_id,
    )

    if not can_delete_sample(
        request.user,
        sample,
    ):
        raise PermissionDenied

    sample_label = sample.sample_id

    try:
        audit, cleanup_errors = purge_sample(
            sample,
            request.user,
        )
    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(
                exc.messages
            ),
        )
    else:
        messages.success(
            request,
            (
                f"Sample {sample_label} was permanently deleted. "
                f"Audit record #{audit.pk} was preserved."
            ),
        )

        if cleanup_errors:
            messages.warning(
                request,
                (
                    "The database deletion completed, but one or more "
                    "physical files require administrator cleanup."
                ),
            )

    return redirect(
        "samples_lifecycle",
    )


# =========================================================
# 5. RELATIONSHIPS
# =========================================================
@login_required
def sample_relate_view(request, sample_id):
    current_sample = get_object_or_404(Sample, id=sample_id)

    if not can_edit_sample(request.user, current_sample) and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        target_ids_str = request.POST.get("target_ids", "")
        target_ids = [tid for tid in target_ids_str.split(",") if tid]
        general_notes = request.POST.get("notes", "")

        if not target_ids:
            messages.warning(request, "No samples selected to relate.")
            return redirect("samples_list")

        try:
            with transaction.atomic():
                for t_id in target_ids:
                    target_sample = (
                        visible_samples_for_user(
                            request.user
                        )
                        .get(
                            id=t_id
                        )
                    )
                    if current_sample == target_sample: continue

                    direction = request.POST.get(f"direction_{t_id}") or request.POST.get("direction", "out")
                    rel_type = request.POST.get(f"type_{t_id}") or request.POST.get("relationship_type")
                    eop = request.POST.get(f"eop_{t_id}") or request.POST.get("eop")

                    if direction == "in":
                        source, destination = target_sample, current_sample
                    else:
                        source, destination = current_sample, target_sample

                    SampleRelationship.objects.create(
                        source_sample=source,
                        target_sample=destination,
                        relationship_type=rel_type,
                        notes=general_notes,
                        created_by=request.user
                    )

                    Event.objects.create(
                        sample=current_sample,
                        performed_by=request.user,
                        event_type="update",
                        notes=f"Relationship added: {rel_type} with {target_sample.sample_id}"
                    )

                    if rel_type == "infects":
                        phage_obj = None
                        bacteria_obj = None

                        if hasattr(source, 'phage') and hasattr(destination, 'bacteria'):
                            phage_obj, bacteria_obj = source.phage, destination.bacteria
                        elif hasattr(destination, 'phage') and hasattr(source, 'bacteria'):
                            phage_obj, bacteria_obj = destination.phage, source.bacteria

                        if phage_obj and bacteria_obj:
                            HostRange.objects.update_or_create(
                                phage=phage_obj, bacteria=bacteria_obj,
                                defaults={'efficiency_eop': eop if eop else None}
                            )

            messages.success(request, f"Relationships connected successfully for {len(target_ids)} sample(s)!")

        except Exception as e:
            messages.error(request, f"Error processing relationship: {str(e)}")

    return redirect("samples_list")


# =========================================================
# 6. NETWORK GRAPH VIEW
# =========================================================
@login_required
def samples_network_view(request):
    """
    Interactive biological relationship network restricted to Samples
    already visible to the authenticated user.

    Authorization remains centralized in visible_samples_for_user().
    Network serialization is delegated to the shared service.
    """
    ctx = base_context(
        request
    )

    ctx.update(
        build_sample_network_context(
            visible_samples_for_user(
                request.user
            )
        )
    )

    return render(
        request,
        "internal/samples/network.html",
        ctx,
    )


# === SAMPLE INTAKE IMPORT VIEWS ===
@login_required
def sample_import_view(request):
    """
    Upload a CSV/XLSX table and stage its rows as SampleIntakeRecord objects.
    The records can later be used to pre-fill the normal sample registration form.
    """
    if request.method == "POST":
        upload = request.FILES.get("sample_table")

        if not upload:
            messages.error(request, "Please select a CSV or Excel file.")
            return redirect("samples_import")

        try:
            batch = SampleImportBatch.objects.create(
                uploaded_by=request.user,
                original_file=upload,
                original_filename=upload.name,
                status="uploaded",
            )

            import_sample_table(batch)

            messages.success(
                request,
                f"Table imported: {batch.total_rows} row(s), "
                f"{batch.valid_rows} ready, {batch.invalid_rows} with errors."
            )
            return redirect("samples_import_batch", batch_id=batch.id)

        except Exception as e:
            messages.error(request, f"Error importing sample table: {e}")
            return redirect("samples_import")

    ctx = base_context(request)
    ctx.update({
        "recent_batches": SampleImportBatch.objects.filter(uploaded_by=request.user)[:10],
        "selected_batch": None,
        "records": [],
    })
    return render(request, "internal/samples/import.html", ctx)


@login_required
def sample_import_batch_detail_view(request, batch_id):
    batch = get_object_or_404(SampleImportBatch, id=batch_id)

    if batch.uploaded_by != request.user and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to view this import batch.")

    ctx = base_context(request)
    ctx.update({
        "recent_batches": SampleImportBatch.objects.filter(uploaded_by=request.user)[:10],
        "selected_batch": batch,
        "records": batch.records.select_related("matched_biobank", "matched_collection", "sample").all(),
    })
    return render(request, "internal/samples/import.html", ctx)


@login_required
def sample_create_shipment_view(request, sample_id):
    sample = get_object_or_404(
        visible_samples_for_user(request.user).select_related("biobank", "owner"),
        id=sample_id,
    )

    if request.method != "POST":
        messages.warning(
            request,
            "Shipment creation requires confirmation."
        )
        return redirect("sample_detail", sample_id=sample.id)

    shipment = create_shipment_from_sample(
        sample=sample,
        user=request.user,
        flow_type="outgoing_shipment",
    )

    messages.success(
        request,
        f"Draft shipment {shipment.shipment_code} created from sample {sample.sample_id}."
    )

    return redirect("shipment_edit", shipment_id=shipment.id)

# =========================================================
# DIRECT SAMPLE SHARING
# =========================================================

def _parse_sample_share_expiry(request):
    from django.utils.dateparse import parse_datetime

    raw = str(
        request.POST.get(
            "expires_at",
            "",
        )
        or ""
    ).strip()

    if not raw:
        return None

    value = parse_datetime(
        raw
    )

    if value is None:
        raise ValidationError(
            "Enter a valid access expiration date and time."
        )

    if timezone.is_naive(
        value
    ):
        value = timezone.make_aware(
            value,
            timezone.get_current_timezone(),
        )

    if value <= timezone.now():
        raise ValidationError(
            "Access expiration must be in the future."
        )

    return value


@login_required
@require_POST
def sample_bulk_share_view(request):
    from django.contrib.auth import get_user_model

    from core.services.sample_sharing import (
        bulk_grant_sample_access,
    )

    User = get_user_model()

    raw_ids = request.POST.getlist(
        "sample_ids"
    )

    try:
        sample_ids = list(
            dict.fromkeys(
                int(value)
                for value in raw_ids
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        messages.error(
            request,
            "The selected Samples are invalid.",
        )

        return redirect(
            "samples_list"
        )

    if not sample_ids:
        messages.error(
            request,
            "Select at least one Sample to share.",
        )

        return redirect(
            "samples_list"
        )

    samples = list(
        Sample.objects
        .filter(
            pk__in=sample_ids,
            is_active=True,
            deletion_requested_at__isnull=True,
        )
        .select_related(
            "owner",
            "research_group",
        )
        .prefetch_related(
            "collections",
            "collections__research_group",
        )
        .order_by(
            "pk"
        )
    )

    if len(samples) != len(
        sample_ids
    ):
        messages.error(
            request,
            "One or more selected Samples are unavailable.",
        )

        return redirect(
            "samples_list"
        )

    target_user = get_object_or_404(
        User,
        pk=request.POST.get(
            "user_id"
        ),
        is_active=True,
    )

    access_level = str(
        request.POST.get(
            "access_level",
            "view",
        )
        or "view"
    ).strip()

    try:
        expires_at = (
            _parse_sample_share_expiry(
                request
            )
        )

        result = (
            bulk_grant_sample_access(
                samples=samples,
                user=target_user,
                access_level=access_level,
                granted_by=request.user,
                expires_at=expires_at,
            )
        )

    except (
        PermissionDenied,
        ValidationError,
    ) as exc:
        message = (
            "; ".join(
                getattr(
                    exc,
                    "messages",
                    [],
                )
            )
            or str(exc)
        )

        messages.error(
            request,
            message,
        )

        return redirect(
            "samples_list"
        )

    summary = (
        f"Access for {target_user.username}: "
        f"{result.created} created, "
        f"{result.updated} updated"
    )

    if result.skipped_owner:
        summary += (
            f", {result.skipped_owner} skipped because "
            "the user already owns the Sample"
        )

    messages.success(
        request,
        summary + ".",
    )

    return redirect(
        "samples_list"
    )


@login_required
@require_POST
def sample_share_view(
    request,
    sample_id,
):
    from django.contrib.auth import get_user_model

    from core.services.sample_sharing import (
        grant_sample_access,
    )

    User = get_user_model()

    sample = get_object_or_404(
        Sample.objects
        .select_related(
            "owner",
            "research_group",
        )
        .prefetch_related(
            "collections",
            "collections__research_group",
        ),
        pk=sample_id,
        is_active=True,
        deletion_requested_at__isnull=True,
    )

    target_user = get_object_or_404(
        User,
        pk=request.POST.get(
            "user_id"
        ),
        is_active=True,
    )

    try:
        grant, created = (
            grant_sample_access(
                sample=sample,
                user=target_user,
                access_level=str(
                    request.POST.get(
                        "access_level",
                        "view",
                    )
                    or "view"
                ).strip(),
                granted_by=request.user,
                expires_at=(
                    _parse_sample_share_expiry(
                        request
                    )
                ),
            )
        )

    except (
        PermissionDenied,
        ValidationError,
    ) as exc:
        message = (
            "; ".join(
                getattr(
                    exc,
                    "messages",
                    [],
                )
            )
            or str(exc)
        )

        messages.error(
            request,
            message,
        )

        return redirect(
            "sample_detail",
            sample_id=sample.pk,
        )

    messages.success(
        request,
        (
            f"{'Granted' if created else 'Updated'} "
            f"{grant.get_access_level_display()} access "
            f"for {target_user.username}."
        ),
    )

    return redirect(
        "sample_detail",
        sample_id=sample.pk,
    )


@login_required
@require_POST
def sample_share_revoke_view(
    request,
    sample_id,
    grant_id,
):
    from core.models.samples.access import (
        SampleAccessGrant,
    )
    from core.services.sample_sharing import (
        revoke_sample_access,
    )

    sample = get_object_or_404(
        Sample.objects
        .select_related(
            "owner",
            "research_group",
        )
        .prefetch_related(
            "collections",
            "collections__research_group",
        ),
        pk=sample_id,
    )

    grant = get_object_or_404(
        SampleAccessGrant.objects
        .select_related(
            "user"
        ),
        pk=grant_id,
        sample=sample,
    )

    username = (
        grant.user.username
    )

    try:
        deleted = revoke_sample_access(
            sample=sample,
            user=grant.user,
            revoked_by=request.user,
        )

    except PermissionDenied as exc:
        messages.error(
            request,
            str(exc),
        )

        return redirect(
            "sample_detail",
            sample_id=sample.pk,
        )

    if deleted:
        messages.success(
            request,
            (
                f"Direct access for "
                f"{username} was revoked."
            ),
        )

    else:
        messages.info(
            request,
            "The direct access grant was already absent.",
        )

    return redirect(
        "sample_detail",
        sample_id=sample.pk,
    )
