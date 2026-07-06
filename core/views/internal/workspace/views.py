from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from django.apps import apps
from datetime import timedelta

from core.context import base_context

# Models
from core.models.biobanks.biobank import Biobank
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
    keywords_view, edit_keyword_view, delete_keyword_view
)


def _core_model(model_name):
    try:
        return apps.get_model("core", model_name)
    except LookupError:
        return None


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
        "edit_keyword": edit_keyword_view,
        "delete_keyword": delete_keyword_view,
    }

    # If the page doesn't exist in ROUTES, default to workspace_view
    view_func = ROUTES.get(page, workspace_view)
    
    # We call the specific view function passing the request
    return view_func(request)

def workspace_view(request):
    """
    Operational workspace hub for the internal LIMS area.
    This view aggregates high-level KPIs and recent records without changing
    the underlying permission model used by each module.
    """
    ctx = base_context(request)

    Chemical = _core_model("Chemical")
    Shipment = _core_model("Shipment")
    NotebookEntry = _core_model("NotebookEntry")

    sample_qs = Sample.objects.filter(is_active=True)
    chemical_qs = Chemical.objects.all() if Chemical else None
    shipment_qs = Shipment.objects.all() if Shipment else None
    notebook_qs = NotebookEntry.objects.all() if NotebookEntry else None

    last_30_days = timezone.now() - timedelta(days=30)
    missing_storage_q = Q(storage_location__isnull=True) | Q(storage_location="")

    total_samples = sample_qs.count()
    pending_qc = sample_qs.filter(status__in=["pending", "qc"]).count()
    new_samples = sample_qs.filter(created_at__gte=last_30_days).count()
    missing_storage_samples = sample_qs.filter(missing_storage_q).count()

    total_collections = Collection.objects.filter(is_active=True).count()
    total_biobanks = Biobank.objects.count()

    total_chemicals = chemical_qs.count() if chemical_qs is not None else 0
    low_stock_chemicals_count = chemical_qs.filter(status="low_stock").count() if chemical_qs is not None else 0
    depleted_chemicals_count = chemical_qs.filter(status="depleted").count() if chemical_qs is not None else 0

    total_shipments = shipment_qs.count() if shipment_qs is not None else 0
    active_shipments = (
        shipment_qs.exclude(status__in=["received", "completed", "cancelled", "archived"]).count()
        if shipment_qs is not None else 0
    )

    notebook_entries = notebook_qs.count() if notebook_qs is not None else 0

    type_distribution = (
        sample_qs
        .values("sample_type")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    recent_samples = (
        sample_qs
        .select_related("biobank", "owner", "research_group")
        .order_by("-created_at")[:6]
    )

    recent_shipments = (
        shipment_qs
        .select_related("origin_biobank", "destination_biobank", "requested_by")
        .order_by("-created_at")[:6]
        if shipment_qs is not None else []
    )

    low_stock_chemicals = (
        chemical_qs.filter(status="low_stock").order_by("name")[:6]
        if chemical_qs is not None else []
    )

    recent_activity = (
        Event.objects.all()
        .select_related("performed_by", "sample")
        .order_by("-timestamp")[:8]
    )

    ctx.update({
        "stats": {
            "total_samples": total_samples,
            "pending_qc": pending_qc,
            "new_samples_30d": new_samples,
            "missing_storage_samples": missing_storage_samples,
            "total_collections": total_collections,
            "total_biobanks": total_biobanks,
            "total_chemicals": total_chemicals,
            "low_stock_chemicals": low_stock_chemicals_count,
            "depleted_chemicals": depleted_chemicals_count,
            "total_shipments": total_shipments,
            "active_shipments": active_shipments,
            "notebook_entries": notebook_entries,
            "recent_activity": recent_activity,
            "chart_labels": [item["sample_type"] or "Other" for item in type_distribution],
            "chart_data": [item["total"] for item in type_distribution],
        },
        "recent_samples": recent_samples,
        "recent_shipments": recent_shipments,
        "low_stock_chemicals_list": low_stock_chemicals,
        "sample_type_distribution": type_distribution,
    })

    return render(request, "internal/workspace/workspace.html", ctx)
