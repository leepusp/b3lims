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
