from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from core.context import base_context
from core.permissions.workspace import visible_workspace_samples_for_user, visible_workspace_collections_for_user, visible_workspace_events_for_user
from core.services.postgresql_backup_status import get_postgresql_backup_status
from core.services.media_backup_status import get_media_backup_status

# Models
from core.models.biobanks.biobank import Biobank
from core.permissions.shipments import visible_shipments_for_user
from core.models.collections.collection import Collection
from core.models.samples.sample import Sample
from core.models.events.model import Event

# CORRIGIDO: Nomes das Views atualizados para os novos nomes de lista
from core.views.internal.biobanks.views import biobanks_list_view
from core.views.internal.collections.views import collections_list_view
from core.views.internal.samples.views import samples_list_view
from core.views.internal.tags.views import (
    tags_view, search_view, create_tag_view, edit_tag_view, delete_tag_view
)
from core.views.internal.keywords.views import (
    create_keyword_view,
    delete_keyword_view,
    edit_keyword_view,
    keywords_view,
)

@login_required
def home(request):
    """
    Main router for the LIMS internal area. 
    It dispatches requests based on the 'page' parameter.
    """
    page = request.GET.get("page", "workspace")

    # CORRIGIDO: Referências no dicionário ROUTES atualizadas
    ROUTES = {
        "workspace": workspace_view,
        "biobanks": biobanks_list_view,    # Nome atualizado
        "collections": collections_list_view, # Nome atualizado
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

    # If the page doesn't exist in ROUTES, default to workspace_view
    view_func = ROUTES.get(page, workspace_view)
    
    # We call the specific view function passing the request
    return view_func(request)

def workspace_view(request):
    """
    Dashboard logic: KPIs, charts, and recent activities scoped to the current
    user's operational visibility.
    """
    ctx = base_context(request)

    samples_qs = visible_workspace_samples_for_user(request.user)
    collections_qs = visible_workspace_collections_for_user(request.user)
    events_qs = visible_workspace_events_for_user(request.user)

    # --- 1. KPI COUNTERS ---
    total_samples = samples_qs.count()

    pending_qc = samples_qs.filter(
        status__in=["pending", "qc"]
    ).count()

    last_30_days = timezone.now() - timedelta(days=30)
    new_samples = samples_qs.filter(
        created_at__gte=last_30_days
    ).count()

    total_collections = collections_qs.count()

    # --- 2. CHART DATA (Distribution by Sample Type) ---
    type_distribution = (
        samples_qs
        .values("sample_type")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    chart_labels = [item["sample_type"] or "Other" for item in type_distribution]
    chart_data = [item["total"] for item in type_distribution]

    # --- 3. RECENT ACTIVITY (Audit Trail) ---
    recent_activity = (
        events_qs
        .select_related("performed_by", "sample")
        .order_by("-timestamp")[:8]
    )

    # --- 4. CONTEXT UPDATE ---
    ctx["stats"] = {
        "total_samples": total_samples,
        "pending_qc": pending_qc,
        "new_samples_30d": new_samples,
        "total_collections": total_collections,
        "recent_activity": recent_activity,
        "chart_labels": chart_labels,
        "chart_data": chart_data,
    }

    if request.user.is_superuser:
        ctx["postgresql_backup_status"] = get_postgresql_backup_status()
        ctx["media_backup_status"] = get_media_backup_status()

    return render(request, "internal/workspace/workspace.html", ctx)
