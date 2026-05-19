import hashlib
from uuid import UUID
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.models import (
    Biobank,
    Shipment,
    ShipmentItem,
    TransportClassification,
    ShipmentAccessToken,
    ShipmentDeclaration,
    ShipmentDocument,
    ShipmentEvent,
)
from core.services.shipment_qr import build_qr_data_uri
from core.services.shipment_workflow import sync_shipment_requirements


def _bool_from_post(value):
    return str(value).lower() in {"1", "true", "yes", "on", "sim"}




def _sample_type_from_material_type(material_type):
    if material_type == "bacteria":
        return "Bacterium (Host)"
    if material_type == "phage":
        return "Phage (Virus)"
    if material_type == "plasmid":
        return "Plasmid"
    return "Other"


def _infer_material_classification(risk_class, biosafety_level, is_ogm):
    risk = (risk_class or "").upper()
    nb = (biosafety_level or "").upper()

    if is_ogm or risk in {"CR2", "CR3", "CR4"} or nb in {"NB2", "NB3", "NB4"}:
        return "category_b_un3373"

    if risk == "CR1" and nb == "NB1" and not is_ogm:
        return "exempt_biological_material"

    return "requires_review"

def _get_or_create_public_tracking_token(shipment):
    token, _ = ShipmentAccessToken.objects.get_or_create(
        shipment=shipment,
        access_type="public_tracking",
        defaults={
            "is_active": True,
        },
    )
    return token




def _get_or_create_public_edit_token(shipment):
    access_token = (
        ShipmentAccessToken.objects
        .filter(
            shipment=shipment,
            access_type="public_edit",
            is_active=True,
        )
        .order_by("-created_at")
        .first()
    )

    if access_token:
        return access_token

    return ShipmentAccessToken.objects.create(
        shipment=shipment,
        access_type="public_edit",
        is_active=True,
    )


def _public_tracking_url(request, access_token):
    path = reverse(
        "public_shipment_track",
        kwargs={"token": access_token.token},
    )
    return request.build_absolute_uri(path)






def _get_public_access_token_or_403(token, access_type="public_tracking"):
    access_token = get_object_or_404(
        ShipmentAccessToken.objects.select_related("shipment"),
        token=token,
        access_type=access_type,
        is_active=True,
    )

    if hasattr(access_token, "is_valid") and not access_token.is_valid():
        return None

    return access_token


def _status_value_for_document(preferred_values):
    field = ShipmentDocument._meta.get_field("status")
    available = [value for value, _label in field.choices]

    for value in preferred_values:
        if value in available:
            return value

    return None


def _hash_uploaded_file(uploaded_file):
    hasher = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        hasher.update(chunk)

    uploaded_file.seek(0)
    return hasher.hexdigest()


def _save_signed_file_to_document(document, uploaded_file):
    update_fields = []

    if hasattr(document, "signed_file"):
        document.signed_file.save(uploaded_file.name, uploaded_file, save=False)
        update_fields.append("signed_file")
    elif hasattr(document, "uploaded_file"):
        document.uploaded_file.save(uploaded_file.name, uploaded_file, save=False)
        update_fields.append("uploaded_file")
    else:
        raise AttributeError("ShipmentDocument has no signed_file or uploaded_file field.")

    file_hash = _hash_uploaded_file(uploaded_file)

    for hash_field in ["signed_file_hash", "signed_hash", "file_hash", "sha256"]:
        if hasattr(document, hash_field):
            setattr(document, hash_field, file_hash)
            update_fields.append(hash_field)
            break

    submitted_status = _status_value_for_document([
        "submitted",
        "uploaded",
        "received",
        "under_review",
        "waiting_review",
        "generated",
    ])

    if submitted_status:
        document.status = submitted_status
        update_fields.append("status")

    if hasattr(document, "submitted_at"):
        document.submitted_at = timezone.now()
        update_fields.append("submitted_at")

    if hasattr(document, "uploaded_at"):
        document.uploaded_at = timezone.now()
        update_fields.append("uploaded_at")

    document.save(update_fields=list(dict.fromkeys(update_fields)))

    return document


def public_shipments_portal_view(request):
    tracking_token = request.GET.get("token", "").strip()
    error_message = ""

    if tracking_token:
        try:
            UUID(tracking_token)
            return redirect("public_shipment_track", token=tracking_token)
        except ValueError:
            error_message = "Invalid tracking token format."

    return render(
        request,
        "public/shipments/portal.html",
        {
            "error_message": error_message,
        },
    )


def public_shipment_new_view(request):
    destination_biobank = Biobank.objects.filter(name__iexact="BBAMS").first()

    if request.method == "POST":
        sender_institution = request.POST.get("sender_institution", "").strip()
        sender_responsible_name = request.POST.get("sender_responsible_name", "").strip()
        sender_email = request.POST.get("sender_email", "").strip()
        sender_phone = request.POST.get("sender_phone", "").strip()

        material_name = request.POST.get("material_name", "").strip()
        imported_sample_id = request.POST.get("imported_sample_id", "").strip()
        material_type = request.POST.get("material_type", "other").strip() or "other"
        sample_type = _sample_type_from_material_type(material_type)

        quantity = request.POST.get("quantity", "1").strip() or "1"
        quantity_unit = request.POST.get("quantity_unit", "tube").strip() or "tube"
        container_type = request.POST.get("container_type", "tube").strip() or "tube"
        storage_condition = request.POST.get("storage_condition", "").strip()
        temperature_condition = request.POST.get("temperature_condition", "").strip()

        risk_class = request.POST.get("risk_class", "unknown").strip() or "unknown"
        biosafety_level = request.POST.get("biosafety_level", "unknown").strip() or "unknown"

        shipment = Shipment.objects.create(
            flow_type="incoming_receipt",
            status="under_review",
            destination_biobank=destination_biobank,
            sender_institution=sender_institution,
            sender_responsible_name=sender_responsible_name,
            sender_email=sender_email,
            sender_phone=sender_phone,
            recipient_institution=destination_biobank.name if destination_biobank else "BBAMS",
            temperature_condition=temperature_condition,
            notes=request.POST.get("notes", "").strip(),
        )

        ShipmentItem.objects.create(
            shipment=shipment,
            imported_sample_id=imported_sample_id,
            material_name=material_name,
            sample_type=sample_type,
            quantity=quantity,
            quantity_unit=quantity_unit,
            container_count=1,
            container_type=container_type,
            storage_condition=storage_condition,
            notes=request.POST.get("item_notes", "").strip(),
        )

        is_ogm = _bool_from_post(request.POST.get("is_ogm"))
        is_genetic_heritage = _bool_from_post(request.POST.get("is_genetic_heritage"))
        is_international = _bool_from_post(request.POST.get("is_international"))

        classification = TransportClassification.objects.create(
            shipment=shipment,
            material_type=material_type,
            risk_class=risk_class,
            biosafety_level=biosafety_level,
            is_ogm=is_ogm,
            is_genetic_heritage=is_genetic_heritage,
            is_international=is_international,
        )
        classification.apply_default_rules(save=True)

        material_classification = _infer_material_classification(
            risk_class=risk_class,
            biosafety_level=biosafety_level,
            is_ogm=is_ogm,
        )

        ShipmentDeclaration.objects.create(
            shipment=shipment,
            sender_full_name=sender_responsible_name,
            sender_document=request.POST.get("sender_document", "").strip(),
            sender_institution=sender_institution,
            sender_address=request.POST.get("sender_address", "").strip(),
            sender_phone_email=f"{sender_phone} / {sender_email}".strip(" /"),
            recipient_name=request.POST.get("recipient_name", "").strip(),
            recipient_institution=request.POST.get("recipient_institution", "").strip() or shipment.recipient_institution,
            recipient_address=request.POST.get("recipient_address", "").strip(),
            recipient_phone_email=request.POST.get("recipient_phone_email", "").strip(),
            material_type=material_type,
            risk_class=risk_class,
            biosafety_level=biosafety_level,
            is_ogm=is_ogm,
            is_genetic_heritage=is_genetic_heritage,
            is_international=is_international,
            additional_description=request.POST.get("additional_description", "").strip(),
            content_description=request.POST.get("content_description", "").strip() or material_name,
            quantity_volume=request.POST.get("quantity_volume", "").strip() or f"{quantity} {quantity_unit}",
            purpose=request.POST.get("purpose", "Pesquisa científica").strip() or "Pesquisa científica",
            material_classification=material_classification,
            transport_conditions=temperature_condition,
            confirms_no_prohibited_dangerous_goods=_bool_from_post(request.POST.get("confirms_no_prohibited_dangerous_goods")),
            confirms_no_leakage_or_contamination_risk=_bool_from_post(request.POST.get("confirms_no_leakage_or_contamination_risk")),
            confirms_transport_safety=_bool_from_post(request.POST.get("confirms_transport_safety")),
            confirms_primary_container=_bool_from_post(request.POST.get("confirms_primary_container")),
            confirms_secondary_packaging=_bool_from_post(request.POST.get("confirms_secondary_packaging")),
            confirms_absorbent_material=_bool_from_post(request.POST.get("confirms_absorbent_material")),
            confirms_rigid_outer_packaging=_bool_from_post(request.POST.get("confirms_rigid_outer_packaging")),
            confirms_triple_packaging=_bool_from_post(request.POST.get("confirms_triple_packaging")),
            confirms_sender_recipient_identification=_bool_from_post(request.POST.get("confirms_sender_recipient_identification")),
            confirms_fragile_label=_bool_from_post(request.POST.get("confirms_fragile_label")),
            confirms_biohazard_label=_bool_from_post(request.POST.get("confirms_biohazard_label")),
            confirms_un3373_label_when_applicable=_bool_from_post(request.POST.get("confirms_un3373_label_when_applicable")),
            confirms_accompanying_documents=_bool_from_post(request.POST.get("confirms_accompanying_documents")),
            accepts_sender_declaration=_bool_from_post(request.POST.get("accepts_sender_declaration")),
            accepts_content_declaration=_bool_from_post(request.POST.get("accepts_content_declaration")),
            accepts_responsibility=_bool_from_post(request.POST.get("accepts_responsibility")),
            declaration_place=request.POST.get("declaration_place", "").strip(),
            signer_name=request.POST.get("signer_name", "").strip() or sender_responsible_name,
            signer_document=request.POST.get("signer_document", "").strip() or request.POST.get("sender_document", "").strip(),
        )

        sync_shipment_requirements(shipment, actor=None)

        ShipmentEvent.objects.create(
            shipment=shipment,
            event_type="created",
            actor=None,
            notes="Public external shipment submission created.",
        )

        access_token = _get_or_create_public_tracking_token(shipment)

        return redirect(
            "public_shipment_submitted",
            token=access_token.token,
        )

    return render(
        request,
        "public/shipments/new.html",
        {
            "destination_biobank": destination_biobank,
        },
    )


def public_shipment_submitted_view(request, token):
    access_token = get_object_or_404(
        ShipmentAccessToken.objects.select_related("shipment"),
        token=token,
        access_type="public_tracking",
        is_active=True,
    )

    shipment = access_token.shipment
    edit_token = _get_or_create_public_edit_token(shipment)
    public_url = _public_tracking_url(request, access_token)

    return render(
        request,
        "public/shipments/submitted.html",
        {
            "shipment": shipment,
            "access_token": access_token,
            "edit_token": edit_token,
            "public_tracking_url": public_url,
            "public_qr_data_uri": build_qr_data_uri(public_url),
        },
    )


def public_shipment_track_view(request, token):
    access_token = get_object_or_404(
        ShipmentAccessToken.objects.select_related("shipment"),
        token=token,
        access_type="public_tracking",
        is_active=True,
    )

    if not access_token.is_valid():
        return HttpResponseForbidden("Invalid or expired public tracking token.")

    shipment = access_token.shipment

    return render(
        request,
        "public/shipments/track.html",
        {
            "shipment": shipment,
            "access_token": access_token,
            "items": shipment.items.all(),
        },
    )


def public_shipment_documents_view(request, token):
    access_token = _get_public_access_token_or_403(token, access_type="public_edit")
    if access_token is None:
        return HttpResponseForbidden("Invalid or expired public access token.")

    shipment = access_token.shipment

    sync_shipment_requirements(shipment, actor=None)

    documents = shipment.documents.all().order_by("document_type", "id")

    required_documents = documents.filter(requires_signature=True)
    pending_signature_count = 0

    for document in required_documents:
        signed_file = getattr(document, "signed_file", None)
        uploaded_file = getattr(document, "uploaded_file", None)

        if not signed_file and not uploaded_file:
            pending_signature_count += 1

    return render(
        request,
        "public/shipments/documents.html",
        {
            "shipment": shipment,
            "access_token": access_token,
            "documents": documents,
            "pending_signature_count": pending_signature_count,
            "pending_required_documents": get_pending_required_signed_documents(shipment),
            "can_release_final_outputs": can_release_final_package_outputs(shipment),
        },
    )


def public_shipment_document_upload_view(request, token, document_id):
    access_token = _get_public_access_token_or_403(token, access_type="public_edit")
    if access_token is None:
        return HttpResponseForbidden("Invalid or expired public access token.")

    shipment = access_token.shipment

    document = get_object_or_404(
        ShipmentDocument,
        id=document_id,
        shipment=shipment,
    )

    if request.method == "POST":
        uploaded_file = request.FILES.get("signed_file")

        if not uploaded_file:
            return render(
                request,
                "public/shipments/upload_document.html",
                {
                    "shipment": shipment,
                    "access_token": access_token,
                    "document": document,
                    "error_message": "Selecione um arquivo assinado para envio.",
                },
            )

        _save_signed_file_to_document(document, uploaded_file)
        gate_result = update_status_after_public_document_upload(shipment)

        ShipmentEvent.objects.create(
            shipment=shipment,
            event_type="updated",
            actor=None,
            notes=(
                f"Signed document uploaded through public portal: "
                f"{document.get_document_type_display()}. "
                f"Pending required signed documents: {gate_result['pending_count']}."
            ),
        )

        return redirect(
            "public_shipment_documents",
            token=access_token.token,
        )

    return render(
        request,
        "public/shipments/upload_document.html",
        {
            "shipment": shipment,
            "access_token": access_token,
            "document": document,
        },
    )

from core.services.shipment_document_gate import (
    can_release_final_package_outputs,
    get_pending_required_signed_documents,
    update_status_after_public_document_upload,
)
