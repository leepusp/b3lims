from django.utils import timezone
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Q

from core.context import base_context
from core.models import Shipment
from core.services.shipment_workflow import sync_shipment_requirements
from core.services.shipment_qr import build_internal_shipment_scan_url, build_qr_data_uri
from core.services.shipment_receipt import mark_shipment_received, create_intake_records_from_shipment


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

        if action == "mark_received":
            mark_shipment_received(
                shipment,
                user=request.user,
                notes=request.POST.get("notes", ""),
            )
            messages.success(request, "Shipment marked as received and pending QC.")
            return redirect("shipment_detail", shipment_id=shipment.id)

        if action == "create_intake_records":
            result = create_intake_records_from_shipment(
                shipment,
                user=request.user,
            )

            if result.get("blocked"):
                messages.warning(request, result["message"])
                return redirect("shipment_detail", shipment_id=shipment.id)

            messages.success(
                request,
                f"Intake records generated. Created: {result['created']}. Skipped: {result['skipped']}."
            )
            return redirect("shipment_detail", shipment_id=shipment.id)

    ctx = base_context(request)
    ctx.update({
        "shipment": shipment,
        "items": shipment.items.all(),
        "documents": shipment.documents.all(),
        "checklist_items": shipment.checklist_items.all(),
        "events": shipment.events.all(),
        "classification": getattr(shipment, "classification", None),
        "receipt": getattr(shipment, "receipt", None),
        "shipment_scan_url": build_internal_shipment_scan_url(request, shipment),
        "shipment_qr_data_uri": build_qr_data_uri(build_internal_shipment_scan_url(request, shipment)),
    })

    return render(request, "internal/shipments/detail.html", ctx)


@login_required
def shipment_scan_view(request, shipment_uuid):
    shipment = get_object_or_404(Shipment, uuid=shipment_uuid)
    messages.info(request, f"Shipment {shipment.shipment_code} loaded from QR code.")
    return redirect("shipment_detail", shipment_id=shipment.id)

from core.services.shipment_document_gate import (
    approve_document_package,
    can_release_final_package_outputs,
    get_pending_required_signed_documents,
)


@login_required
def shipment_approve_documents_view(request, shipment_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)

    if request.method != "POST":
        return redirect("shipment_detail", shipment_id=shipment.id)

    result = approve_document_package(shipment, actor=request.user)

    if result["approved"]:
        messages.success(
            request,
            "Required signed documents were approved. Final package labels and QR are now released.",
        )
    else:
        pending_names = ", ".join(
            document.get_document_type_display()
            for document in result["pending_documents"]
        )
        messages.error(
            request,
            f"Cannot approve yet. Pending signed documents: {pending_names}",
        )

    return redirect("shipment_detail", shipment_id=shipment.id)


@login_required
def shipment_package_labels_view(request, shipment_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)

    if not can_release_final_package_outputs(shipment):
        messages.error(
            request,
            "Final package labels are blocked until all required signed documents are uploaded and approved internally.",
        )
        return redirect("shipment_detail", shipment_id=shipment.id)

    access_token = shipment.access_tokens.filter(
        access_type="public_tracking",
        is_active=True,
    ).first()

    public_tracking_url = ""

    if access_token:
        public_tracking_url = request.build_absolute_uri(
            reverse("public_shipment_track", kwargs={"token": access_token.token})
        )

    package_qr_data_uri = build_qr_data_uri(
        public_tracking_url or shipment.shipment_code
    )

    classification = getattr(shipment, "classification", None)

    return render(
        request,
        "internal/shipments/package_labels.html",
        {
            "shipment": shipment,
            "items": shipment.items.all(),
            "classification": classification,
            "label_flags": _shipment_package_label_flags(classification),
            "public_tracking_url": public_tracking_url,
            "package_qr_data_uri": package_qr_data_uri,
            "pending_required_documents": get_pending_required_signed_documents(shipment),
        },
    )


@login_required
def shipment_documents_review_view(request, shipment_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)

    pending_required_documents = get_pending_required_signed_documents(shipment)
    can_release_outputs = can_release_final_package_outputs(shipment)

    return render(
        request,
        "internal/shipments/documents_review.html",
        {
            "shipment": shipment,
            "documents": shipment.documents.all().order_by("document_type", "id"),
            "pending_required_documents": pending_required_documents,
            "can_release_final_outputs": can_release_outputs,
        },
    )


@login_required
def shipment_request_document_correction_view(request, shipment_id, document_id):
    shipment = get_object_or_404(Shipment, id=shipment_id)
    document = get_object_or_404(
        ShipmentDocument,
        id=document_id,
        shipment=shipment,
    )

    if request.method != "POST":
        return redirect("shipment_documents_review", shipment_id=shipment.id)

    correction_note = request.POST.get("correction_note", "").strip()

    # Keep status handling tolerant to the choices currently available in the model.
    status_field = ShipmentDocument._meta.get_field("status")
    available_statuses = [value for value, _label in status_field.choices]

    for candidate in ["correction_requested", "rejected", "waiting_documents", "draft"]:
        if candidate in available_statuses:
            document.status = candidate
            document.save(update_fields=["status"])
            break

    old_status = shipment.status
    shipment.status = "waiting_documents"
    shipment.updated_at = timezone.now()
    shipment.save(update_fields=["status", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="updated",
        actor=request.user,
        notes=(
            f"Document correction requested: {document.get_document_type_display()}. "
            f"{correction_note or 'No additional correction note provided.'} "
            f"Status changed from {old_status} to waiting_documents."
        ),
    )

    messages.warning(
        request,
        f"Correction requested for {document.get_document_type_display()}. "
        "The shipment was moved back to waiting documents.",
    )

    return redirect("shipment_documents_review", shipment_id=shipment.id)


def _shipment_package_label_flags(classification):
    """
    Determine which external package labels must be printed.

    Rules:
    - Fragile label: always shown.
    - Biohazard label: OGM or classification requires biohazard label.
    - UN3373 label: risk class 2+ or biosafety level NB2+ or classification requires UN3373.
    - Restricted opening warning: shown for OGM, biohazard, UN3373, or triple packaging cases.
    """
    if classification is None:
        return {
            "show_fragile": True,
            "show_biohazard": False,
            "show_un3373": False,
            "show_restricted_opening": False,
            "show_triple_packaging_notice": False,
        }

    risk_class = (classification.risk_class or "").upper().replace("-", "")
    biosafety_level = (classification.biosafety_level or "").upper().replace("-", "")

    is_cr2_or_higher = risk_class in {"CR2", "CR3", "CR4"}
    is_nb2_or_higher = biosafety_level in {"NB2", "NB3", "NB4"}

    show_biohazard = bool(
        classification.is_ogm
        or getattr(classification, "requires_biohazard_label", False)
        or is_nb2_or_higher
    )

    show_un3373 = bool(
        getattr(classification, "requires_un3373_label", False)
        or is_cr2_or_higher
        or is_nb2_or_higher
    )

    show_triple_packaging_notice = bool(
        getattr(classification, "requires_triple_packaging", False)
        or show_un3373
        or show_biohazard
    )

    show_restricted_opening = bool(
        classification.is_ogm
        or show_biohazard
        or show_un3373
        or show_triple_packaging_notice
    )

    return {
        "show_fragile": True,
        "show_biohazard": show_biohazard,
        "show_un3373": show_un3373,
        "show_restricted_opening": show_restricted_opening,
        "show_triple_packaging_notice": show_triple_packaging_notice,
    }
