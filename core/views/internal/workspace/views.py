from datetime import timedelta

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from core.context import base_context
from core.permissions.workspace import (
    research_group_ids_for_user,
    visible_workspace_collections_for_user,
    visible_workspace_events_for_user,
    visible_workspace_samples_for_user,
)
from core.services.media_backup_status import (
    get_media_backup_status,
)
from core.services.postgresql_backup_status import (
    get_postgresql_backup_status,
)

from core.views.internal.biobanks.views import (
    biobanks_list_view,
)
from core.views.internal.collections.views import (
    collections_list_view,
)
from core.views.internal.keywords.views import (
    create_keyword_view,
    delete_keyword_view,
    edit_keyword_view,
    keywords_view,
)
from core.views.internal.samples.views import (
    samples_list_view,
)
from core.views.internal.tags.views import (
    create_tag_view,
    delete_tag_view,
    edit_tag_view,
    search_view,
    tags_view,
)


@login_required
def home(request):
    """
    Main router for the B3 LIMS internal area.

    The Workspace remains the default internal landing surface while
    existing legacy page query dispatch remains supported.
    """
    page = request.GET.get(
        "page",
        "workspace",
    )

    routes = {
        "workspace": workspace_view,
        "biobanks": biobanks_list_view,
        "collections": collections_list_view,
        "samples": samples_list_view,
        "tags": tags_view,
        "search_tags": search_view,
        "add_tag": create_tag_view,
        "edit_tag": edit_tag_view,
        "delete_tag": delete_tag_view,
        "keywords": keywords_view,
        "add_keyword": create_keyword_view,
        "edit_keyword": edit_keyword_view,
        "delete_keyword": delete_keyword_view,
    }

    view_func = routes.get(
        page,
        workspace_view,
    )

    return view_func(
        request
    )


def _research_groups_for_workspace(
    user,
):
    """
    Resolve Research Groups through the same membership helper already
    used by the Workspace authorization boundary.

    This function does not broaden Sample or Collection visibility.
    """
    group_ids = (
        research_group_ids_for_user(
            user
        )
    )

    if not group_ids:
        return []

    ResearchGroup = apps.get_model(
        "core",
        "ResearchGroup",
    )

    return list(
        ResearchGroup.objects
        .filter(
            pk__in=group_ids,
        )
        .select_related(
            "coordinator",
        )
        .order_by(
            "name",
        )[:8]
    )


def _scientific_evidence_summary(
    samples_qs,
):
    """
    Summarize evidence attached to Samples already admitted through
    visible_workspace_samples_for_user().

    External evidence remains distinct from curated Sample metadata.
    """
    SampleTaxonomyAssignment = (
        apps.get_model(
            "core",
            "SampleTaxonomyAssignment",
        )
    )

    SampleGenomeAssemblyAssignment = (
        apps.get_model(
            "core",
            "SampleGenomeAssemblyAssignment",
        )
    )

    visible_sample_ids = (
        samples_qs.values_list(
            "pk",
            flat=True,
        )
    )

    taxonomy_qs = (
        SampleTaxonomyAssignment.objects
        .filter(
            sample_id__in=visible_sample_ids,
            is_current=True,
        )
    )

    genome_qs = (
        SampleGenomeAssemblyAssignment.objects
        .filter(
            sample_id__in=visible_sample_ids,
            is_current=True,
        )
    )

    return {
        "current_taxonomy_assignments": (
            taxonomy_qs.count()
        ),
        "samples_with_taxonomy": (
            taxonomy_qs
            .values(
                "sample_id",
            )
            .distinct()
            .count()
        ),
        "current_genome_assignments": (
            genome_qs.count()
        ),
        "samples_with_genome": (
            genome_qs
            .values(
                "sample_id",
            )
            .distinct()
            .count()
        ),
    }



_WORKSPACE_CHART_COLORS = (
    "#2f66e5",
    "#2693b8",
    "#18a096",
    "#8358c7",
    "#93a7bd",
    "#d99a20",
)


def _workspace_percent(
    value,
    total,
):
    if not total:
        return 0.0

    return round(
        (
            value
            /
            total
        )
        *
        100,
        1,
    )


def _workspace_sample_type_chart(
    samples_qs,
    total_samples,
):
    """
    Build one complete Sample-type distribution for the Workspace donut.

    The chart remains authorization-safe because the caller supplies the
    already-scoped Workspace Sample queryset.
    """
    raw_rows = list(
        samples_qs
        .values(
            "sample_type",
        )
        .annotate(
            total=Count(
                "id",
            )
        )
        .order_by(
            "-total",
            "sample_type",
        )
    )

    normalized = {}

    for row in raw_rows:
        label = (
            row[
                "sample_type"
            ]
            or
            "Other"
        )

        normalized[
            label
        ] = (
            normalized.get(
                label,
                0,
            )
            +
            row[
                "total"
            ]
        )

    ordered = sorted(
        normalized.items(),
        key=lambda item: (
            -item[1],
            item[0].casefold(),
        ),
    )

    if len(
        ordered
    ) > 6:
        visible = list(
            ordered[:5]
        )

        remainder = sum(
            value
            for _, value in ordered[5:]
        )

        other_index = next(
            (
                index
                for index, item in enumerate(
                    visible
                )
                if item[0] == "Other"
            ),
            None,
        )

        if other_index is None:
            visible.append(
                (
                    "Other",
                    remainder,
                )
            )
        else:
            label, value = visible[
                other_index
            ]

            visible[
                other_index
            ] = (
                label,
                value
                +
                remainder,
            )

        ordered = visible

    result = []
    cumulative = 0.0

    for index, (
        label,
        value,
    ) in enumerate(
        ordered
    ):
        percent = _workspace_percent(
            value,
            total_samples,
        )

        result.append(
            {
                "label": label,
                "total": value,
                "percent": percent,
                "dash_remainder": round(
                    max(
                        0.0,
                        100.0
                        -
                        percent,
                    ),
                    1,
                ),
                "dashoffset": round(
                    -cumulative,
                    1,
                ),
                "color": (
                    _WORKSPACE_CHART_COLORS[
                        index
                        %
                        len(
                            _WORKSPACE_CHART_COLORS
                        )
                    ]
                ),
            }
        )

        cumulative += percent

    return result


def _workspace_storage_chart(
    samples_qs,
):
    """
    Build the real Workspace storage-location distribution.

    B3 LIMS currently stores a free-text/hierarchical storage_location rather
    than a normalized storage-temperature condition, so this chart does not
    infer temperatures from arbitrary location names.
    """
    rows = list(
        samples_qs
        .exclude(
            storage_location__isnull=True,
        )
        .exclude(
            storage_location="",
        )
        .values(
            "storage_location",
        )
        .annotate(
            total=Count(
                "id",
            )
        )
        .order_by(
            "-total",
            "storage_location",
        )
    )

    if not rows:
        return []

    if len(
        rows
    ) > 5:
        visible = list(
            rows[:4]
        )

        visible.append(
            {
                "storage_location": (
                    "Other locations"
                ),
                "total": sum(
                    row[
                        "total"
                    ]
                    for row in rows[4:]
                ),
            }
        )

        rows = visible

    max_total = max(
        row[
            "total"
        ]
        for row in rows
    )

    result = []

    for index, row in enumerate(
        rows
    ):
        total = row[
            "total"
        ]

        height_percent = round(
            (
                total
                /
                max_total
            )
            *
            100,
            1,
        )

        result.append(
            {
                "label": (
                    row[
                        "storage_location"
                    ]
                ),
                "total": total,
                "height_percent": max(
                    10.0,
                    height_percent,
                ),
                "color": (
                    _WORKSPACE_CHART_COLORS[
                        index
                        %
                        len(
                            _WORKSPACE_CHART_COLORS
                        )
                    ]
                ),
            }
        )

    return result


def workspace_view(request):
    """
    Scientific research Workspace.

    All operational objects are derived from the established
    user-scoped Workspace visibility functions. The V2 presentation
    layer does not substitute base_context collections/samples for
    authorization-sensitive Workspace data.
    """
    ctx = base_context(
        request
    )

    samples_qs = (
        visible_workspace_samples_for_user(
            request.user
        )
    )

    collections_qs = (
        visible_workspace_collections_for_user(
            request.user
        )
    )

    events_qs = (
        visible_workspace_events_for_user(
            request.user
        )
    )

    total_samples = (
        samples_qs.count()
    )

    pending_qc = (
        samples_qs
        .filter(
            status__in=[
                "pending",
                "qc",
            ],
        )
        .count()
    )

    last_30_days = (
        timezone.now()
        -
        timedelta(
            days=30,
        )
    )

    new_samples = (
        samples_qs
        .filter(
            created_at__gte=last_30_days,
        )
        .count()
    )

    total_collections = (
        collections_qs.count()
    )

    type_distribution = list(
        samples_qs
        .values(
            "sample_type",
        )
        .annotate(
            total=Count(
                "id",
            )
        )
        .order_by(
            "-total",
            "sample_type",
        )[:6]
    )

    chart_labels = [
        item[
            "sample_type"
        ]
        or
        "Other"
        for item in type_distribution
    ]

    chart_data = [
        item[
            "total"
        ]
        for item in type_distribution
    ]

    recent_activity = list(
        events_qs
        .select_related(
            "performed_by",
            "sample",
        )
        .order_by(
            "-timestamp",
        )[:8]
    )

    recent_samples = list(
        samples_qs
        .select_related(
            "research_group",
        )
        .order_by(
            "-created_at",
            "-pk",
        )[:6]
    )

    recent_collections = list(
        collections_qs
        .select_related(
            "research_group",
        )
        .order_by(
            "-created_at",
            "-pk",
        )[:6]
    )

    research_groups = (
        _research_groups_for_workspace(
            request.user
        )
    )

    evidence = (
        _scientific_evidence_summary(
            samples_qs
        )
    )

    sample_type_chart = (
        _workspace_sample_type_chart(
            samples_qs,
            total_samples,
        )
    )

    storage_location_chart = (
        _workspace_storage_chart(
            samples_qs
        )
    )

    storage_annotated = (
        samples_qs
        .exclude(
            storage_location__isnull=True,
        )
        .exclude(
            storage_location="",
        )
        .count()
    )

    today = timezone.localdate()

    today_activity = list(
        events_qs
        .filter(
            timestamp__date=today,
        )
        .select_related(
            "performed_by",
            "sample",
        )
        .order_by(
            "-timestamp",
        )[:5]
    )

    evidence[
        "taxonomy_coverage_percent"
    ] = _workspace_percent(
        evidence[
            "samples_with_taxonomy"
        ],
        total_samples,
    )

    evidence[
        "taxonomy_coverage_remainder"
    ] = round(
        100
        -
        evidence[
            "taxonomy_coverage_percent"
        ],
        1,
    )

    evidence[
        "genome_coverage_percent"
    ] = _workspace_percent(
        evidence[
            "samples_with_genome"
        ],
        total_samples,
    )

    evidence[
        "genome_coverage_remainder"
    ] = round(
        100
        -
        evidence[
            "genome_coverage_percent"
        ],
        1,
    )

    # Preserve the existing stats contract while the V2-specific
    # structures are introduced separately.
    ctx[
        "stats"
    ] = {
        "total_samples": (
            total_samples
        ),
        "pending_qc": (
            pending_qc
        ),
        "new_samples_30d": (
            new_samples
        ),
        "total_collections": (
            total_collections
        ),
        "recent_activity": (
            recent_activity
        ),
        "chart_labels": (
            chart_labels
        ),
        "chart_data": (
            chart_data
        ),
    }

    ctx[
        "workspace_v2"
    ] = {
        "research_groups": (
            research_groups
        ),
        "recent_samples": (
            recent_samples
        ),
        "recent_collections": (
            recent_collections
        ),
        "sample_type_distribution": (
            type_distribution
        ),
        "sample_type_chart": (
            sample_type_chart
        ),
        "storage_location_chart": (
            storage_location_chart
        ),
        "storage_annotated": (
            storage_annotated
        ),
        "today_activity": (
            today_activity
        ),
        "evidence": (
            evidence
        ),
        "scope_mode": (
            "Administrative scope"
            if (
                request.user.is_staff
                or
                request.user.is_superuser
            )
            else
            "Research scope"
        ),
    }

    if request.user.is_superuser:
        ctx[
            "postgresql_backup_status"
        ] = (
            get_postgresql_backup_status()
        )

        ctx[
            "media_backup_status"
        ] = (
            get_media_backup_status()
        )

    return render(
        request,
        "internal/workspace/workspace.html",
        ctx,
    )
