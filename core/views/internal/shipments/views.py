from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Q

from core.context import base_context
from core.models import Shipment
from core.services.shipment_workflow import sync_shipment_requirements


@login_required
def shipments_list_view(request):
    shipments = (
        Shipment.objects
        .select_related("origin_biobank", "destination_biobank", "requested_by")
        .prefetch_related("items", "documents", "checklist_items")
        .all()
    )

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    flow_type = request.GET.get("flow_type", "").strip()

    if q:
        shipments = shipments.filter(
            Q(shipment_code__icontains=q)
            | Q(sender_institution__icontains=q)
            | Q(recipient_institution__icontains=q)
            | Q(tracking_code__icontains=q)
            | Q(items__imported_sample_id__icontains=q)
            | Q(items__material_name__icontains=q)
        ).distinct()

    if status:
        shipments = shipments.filter(status=status)

    if flow_type:
        shipments = shipments.filter(flow_type=flow_type)

    ctx = base_context(request)
    ctx.update({
        "shipments": shipments,
        "status_choices": Shipment.STATUS_CHOICES,
        "flow_type_choices": Shipment.FLOW_TYPES,
        "selected_status": status,
        "selected_flow_type": flow_type,
        "query": q,
    })

    return render(request, "internal/shipments/list.html", ctx)


@login_required
def shipment_detail_view(request, shipment_id):
    shipment = get_object_or_404(
        Shipment.objects
        .select_related(
            "origin_biobank",
            "destination_biobank",
            "requested_by",
            "reviewed_by",
            "authorized_by",
        )
        .prefetch_related(
            "items",
            "documents",
            "checklist_items",
            "events",
        ),
        id=shipment_id,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "sync_requirements":
            result = sync_shipment_requirements(shipment, actor=request.user)
            messages.success(request, result["message"])
            return redirect("shipment_detail", shipment_id=shipment.id)

    ctx = base_context(request)
    ctx.update({
        "shipment": shipment,
        "items": shipment.items.all(),
        "documents": shipment.documents.all(),
        "checklist_items": shipment.checklist_items.all(),
        "events": shipment.events.all(),
        "classification": getattr(shipment, "classification", None),
    })

    return render(request, "internal/shipments/detail.html", ctx)
