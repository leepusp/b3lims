import base64
import io
import os
from decimal import Decimal, InvalidOperation

import qrcode
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count
from django.urls import reverse
from django.utils.dateparse import parse_date
from core.context import base_context
from core.models.chemicals.chemical import Chemical, ChemicalFile, ChemicalStockMovement
from core.permissions.chemicals import (
    can_delete_chemical,
    can_edit_chemical,
    can_view_chemical,
    visible_chemicals_for_user,
)

@login_required
def chemicals_list_view(request):
    """
    Dashboard de Químicos: Listagem, Busca e Filtros.
    """
    user = request.user
    qs = visible_chemicals_for_user(user).order_by('expiry_date', 'name')

    # Filtros
    query = request.GET.get('q')
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | 
            Q(cas_number__icontains=query) |
            Q(formula__icontains=query) |
            Q(supplier__icontains=query) |
            Q(catalog_number__icontains=query) |
            Q(lot_number__icontains=query)
        )

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    ctx = base_context(request)
    ctx['chemicals'] = qs
    return render(request, "internal/chemicals/list.html", ctx)

@login_required
def chemical_create_view(request):
    """
    Create a structured chemical/reagent inventory record.
    """
    if request.method == "POST":
        try:
            name = (request.POST.get("name") or "").strip()

            quantity_value = (request.POST.get("quantity_value") or "").strip()
            quantity_unit = (request.POST.get("quantity_unit") or "").strip()
            minimum_quantity = (request.POST.get("minimum_quantity") or "").strip() or None

            legacy_quantity = (request.POST.get("quantity") or "").strip()
            if quantity_value and quantity_unit:
                legacy_quantity = f"{quantity_value} {quantity_unit}".strip()
            elif quantity_value:
                legacy_quantity = quantity_value

            storage_location = (request.POST.get("storage_location") or "").strip()
            storage_temperature = (request.POST.get("storage_temperature") or "").strip()
            legacy_location = storage_location or (request.POST.get("location") or "").strip()

            if not name or not legacy_quantity:
                raise ValueError("Name and quantity are required.")

            research_group = None
            if hasattr(request.user, "research_groups"):
                research_group = request.user.research_groups.first()

            Chemical.objects.create(
                name=name,
                formula=request.POST.get("formula") or None,
                cas_number=request.POST.get("cas_number") or None,
                supplier=request.POST.get("supplier") or None,
                catalog_number=request.POST.get("catalog_number") or None,
                lot_number=request.POST.get("lot_number") or None,
                quantity_value=quantity_value or None,
                quantity_unit=quantity_unit or None,
                minimum_quantity=minimum_quantity,
                quantity=legacy_quantity,
                storage_temperature=storage_temperature or None,
                storage_location=storage_location or None,
                barcode=request.POST.get("barcode") or None,
                location=legacy_location,
                expiry_date=request.POST.get("expiry_date") or None,
                msds_link=request.POST.get("msds_link") or None,
                hazard_notes=request.POST.get("hazard_notes") or None,
                created_by=request.user,
                research_group=research_group,
                is_public=request.POST.get("is_public") in ["true", "on", "1"],
            )

            messages.success(request, f"Reagent {name} registered successfully.")
            return redirect("chemicals_list")

        except Exception as e:
            messages.error(request, f"Error creating reagent: {e}")

    ctx = base_context(request)
    return render(request, "internal/chemicals/create.html", ctx)

@login_required
def chemicals_dashboard_view(request):
    """
    Dashboard with real reagent inventory KPIs, stock alerts and recent movements.
    """
    qs = visible_chemicals_for_user(request.user)

    today = timezone.localdate()
    expiring_limit = today + timedelta(days=30)

    total_reagents = qs.count()
    available_count = qs.filter(status="available").count()
    low_stock_count = qs.filter(status="low_stock").count()
    depleted_count = qs.filter(status="depleted").count()
    expired_count = qs.filter(expiry_date__lt=today).count()
    expiring_soon_count = qs.filter(
        expiry_date__gte=today,
        expiry_date__lte=expiring_limit,
    ).count()

    movement_qs = ChemicalStockMovement.objects.select_related(
        "chemical",
        "performed_by",
    ).filter(
        chemical__in=qs
    ).order_by("-created_at", "-id")

    ctx = base_context(request)
    ctx.update({
        "total_reagents": total_reagents,
        "available_count": available_count,
        "low_stock_count": low_stock_count,
        "depleted_count": depleted_count,
        "expired_count": expired_count,
        "expiring_soon_count": expiring_soon_count,
        "status_counts": qs.values("status")
            .annotate(total=Count("id"))
            .order_by("-total", "status"),
        "temperature_counts": qs.values("storage_temperature")
            .annotate(total=Count("id"))
            .order_by("-total", "storage_temperature")[:10],
        "location_counts": qs.values("storage_location")
            .annotate(total=Count("id"))
            .order_by("-total", "storage_location")[:10],
        "low_stock_reagents": qs.filter(status="low_stock").order_by("name")[:10],
        "expired_reagents": qs.filter(expiry_date__lt=today).order_by("expiry_date", "name")[:10],
        "expiring_soon_reagents": qs.filter(
            expiry_date__gte=today,
            expiry_date__lte=expiring_limit,
        ).order_by("expiry_date", "name")[:10],
        "recent_movements": movement_qs[:12],
    })

    return render(request, "internal/chemicals/dashboard.html", ctx)


def _chemical_access_queryset(user):
    return visible_chemicals_for_user(user)


def _user_can_manage_chemical(user, chemical):
    return can_edit_chemical(user, chemical)



def _format_chemical_quantity(value, unit):
    if value is None:
        return ""
    raw = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{raw} {unit or ''}".strip()


def _update_chemical_status_from_stock(chemical):
    if chemical.quantity_value is None:
        return

    if chemical.quantity_value <= 0:
        chemical.status = "depleted"
    elif chemical.minimum_quantity is not None and chemical.quantity_value <= chemical.minimum_quantity:
        chemical.status = "low_stock"
    elif chemical.status in ["depleted", "low_stock"]:
        chemical.status = "available"


def _apply_chemical_stock_movement(*, chemical, movement_type, amount_value, amount_unit, reason, user):
    if amount_value < 0:
        raise ValueError("Amount must be zero or greater.")

    current = chemical.quantity_value or Decimal("0")
    before = current

    if chemical.quantity_unit and amount_unit and chemical.quantity_unit != amount_unit:
        raise ValueError(f"Unit mismatch: current stock uses {chemical.quantity_unit}, movement uses {amount_unit}.")

    if not chemical.quantity_unit and amount_unit:
        chemical.quantity_unit = amount_unit

    if movement_type == "intake":
        after = before + amount_value
    elif movement_type in ["consumption", "disposal"]:
        after = before - amount_value
        if after < 0:
            raise ValueError("Movement would make stock negative.")
    elif movement_type == "adjustment":
        after = amount_value
    else:
        raise ValueError("Invalid movement type.")

    chemical.quantity_value = after
    chemical.quantity = _format_chemical_quantity(after, chemical.quantity_unit or amount_unit)
    _update_chemical_status_from_stock(chemical)
    chemical.save()

    return ChemicalStockMovement.objects.create(
        chemical=chemical,
        movement_type=movement_type,
        amount_value=amount_value,
        amount_unit=amount_unit or chemical.quantity_unit,
        quantity_before=before,
        quantity_after=after,
        reason=reason,
        performed_by=user,
    )

@login_required
def chemical_detail_view(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)

    ctx = base_context(request)
    ctx.update({
        "chemical": chemical,
        "can_manage_chemical": _user_can_manage_chemical(request.user, chemical),
        "can_deactivate_chemical": can_delete_chemical(request.user, chemical),
        "chemical_files": chemical.files.filter(is_active=True).select_related("uploaded_by"),
        "document_types": ChemicalFile.DOCUMENT_TYPES,
        "stock_movements": chemical.stock_movements.select_related("performed_by").all()[:20],
    })
    return render(request, "internal/chemicals/detail.html", ctx)


@login_required
def chemical_edit_view(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)

    if not _user_can_manage_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to edit this reagent.")

    if request.method == "POST":
        try:
            name = (request.POST.get("name") or "").strip()
            quantity_value = (request.POST.get("quantity_value") or "").strip()
            quantity_unit = (request.POST.get("quantity_unit") or "").strip()
            minimum_quantity = (request.POST.get("minimum_quantity") or "").strip() or None

            legacy_quantity = (request.POST.get("quantity") or "").strip()
            if quantity_value and quantity_unit:
                legacy_quantity = f"{quantity_value} {quantity_unit}".strip()
            elif quantity_value:
                legacy_quantity = quantity_value

            storage_location = (request.POST.get("storage_location") or "").strip()
            storage_temperature = (request.POST.get("storage_temperature") or "").strip()
            legacy_location = storage_location or (request.POST.get("location") or "").strip()

            if not name or not legacy_quantity:
                raise ValueError("Name and quantity are required.")

            chemical.name = name
            chemical.formula = request.POST.get("formula") or None
            chemical.cas_number = request.POST.get("cas_number") or None
            chemical.supplier = request.POST.get("supplier") or None
            chemical.catalog_number = request.POST.get("catalog_number") or None
            chemical.lot_number = request.POST.get("lot_number") or None
            chemical.quantity_value = quantity_value or None
            chemical.quantity_unit = quantity_unit or None
            chemical.minimum_quantity = minimum_quantity
            chemical.quantity = legacy_quantity
            chemical.storage_temperature = storage_temperature or None
            chemical.storage_location = storage_location or None
            chemical.barcode = request.POST.get("barcode") or None
            chemical.location = legacy_location
            chemical.expiry_date = request.POST.get("expiry_date") or None
            if "msds_link" in request.POST:
                chemical.msds_link = request.POST.get("msds_link") or None
            chemical.hazard_notes = request.POST.get("hazard_notes") or None
            chemical.status = request.POST.get("status") or chemical.status
            chemical.is_public = request.POST.get("is_public") in ["true", "on", "1"]
            chemical.save()

            messages.success(request, f"Reagent {chemical.name} updated successfully.")
            return redirect("chemical_detail", chemical_id=chemical.id)

        except Exception as e:
            messages.error(request, f"Error updating reagent: {e}")

    ctx = base_context(request)
    ctx.update({
        "chemical": chemical,
        "status_choices": Chemical.STATUS_CHOICES,
    })
    return render(request, "internal/chemicals/edit.html", ctx)


@login_required
def chemical_delete_view(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)

    if not can_delete_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to deactivate this reagent.")

    if request.method == "POST":
        name = chemical.name
        chemical.is_active = False
        chemical.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Reagent {name} deactivated successfully.")
        return redirect("chemicals_list")

    ctx = base_context(request)
    ctx.update({"chemical": chemical})
    return render(request, "internal/chemicals/confirm_delete.html", ctx)


@login_required
@transaction.atomic
def chemical_file_upload_view(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)
    if not can_edit_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to add reagent documents.")
    if request.method != "POST":
        return redirect("chemical_detail", chemical_id=chemical.id)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        messages.error(request, "Select a document to upload.")
        return redirect("chemical_detail", chemical_id=chemical.id)

    document_type = request.POST.get("document_type") or "other"
    valid_types = {value for value, _ in ChemicalFile.DOCUMENT_TYPES}
    if document_type not in valid_types:
        messages.error(request, "Invalid document type.")
        return redirect("chemical_detail", chemical_id=chemical.id)

    is_primary = (
        document_type == "sds"
        and request.POST.get("is_primary") in {"true", "on", "1"}
    )
    if is_primary:
        chemical.files.filter(is_active=True, is_primary=True).update(is_primary=False)

    original_filename = os.path.basename(uploaded_file.name)[:255]
    chemical_file = ChemicalFile.objects.create(
        chemical=chemical,
        file=uploaded_file,
        original_filename=original_filename,
        title=(request.POST.get("title") or original_filename)[:255],
        document_type=document_type,
        description=request.POST.get("description") or "",
        version=(request.POST.get("version") or "")[:50],
        document_date=parse_date(request.POST.get("document_date") or ""),
        is_primary=is_primary,
        uploaded_by=request.user,
    )
    messages.success(request, f"Document {chemical_file.title} uploaded successfully.")
    return redirect("chemical_detail", chemical_id=chemical.id)


@login_required
def chemical_file_download_view(request, chemical_id, file_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)
    chemical_file = get_object_or_404(
        chemical.files.filter(is_active=True),
        id=file_id,
    )
    response = FileResponse(
        chemical_file.file.open("rb"),
        as_attachment=chemical_file.mime_type != "application/pdf",
        filename=chemical_file.original_filename,
        content_type=chemical_file.mime_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def chemical_file_deactivate_view(request, chemical_id, file_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)
    if not can_edit_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to remove reagent documents.")
    chemical_file = get_object_or_404(chemical.files.filter(is_active=True), id=file_id)
    if request.method == "POST":
        chemical_file.is_active = False
        chemical_file.is_primary = False
        chemical_file.save(update_fields=["is_active", "is_primary", "updated_at"])
        messages.success(request, "Document removed from the reagent interface.")
    return redirect("chemical_detail", chemical_id=chemical.id)


@login_required
def print_chemical_label(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)
    qr_url = request.build_absolute_uri(reverse("chemical_qr_scan", args=[chemical.uuid]))
    qr = qrcode.QRCode(version=1, box_size=10, border=0)
    qr.add_data(qr_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return render(
        request,
        "internal/chemicals/print_label.html",
        {"chemical": chemical, "qr_code": qr_base64},
    )


def chemical_qr_scan_view(request, uuid):
    chemical = get_object_or_404(Chemical, uuid=uuid, is_active=True)
    if not request.user.is_authenticated:
        login_url = reverse("login")
        next_url = reverse("chemical_qr_scan", args=[chemical.uuid])
        return redirect(f"{login_url}?next={next_url}")
    if not can_view_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to view this reagent.")

    primary_sds = chemical.files.filter(
        is_active=True,
        is_primary=True,
        document_type="sds",
    ).first()
    ctx = base_context(request)
    ctx.update({"chemical": chemical, "primary_sds": primary_sds})
    return render(request, "internal/chemicals/qr_view.html", ctx)



@login_required
def chemical_movement_create_view(request, chemical_id):
    chemical = get_object_or_404(_chemical_access_queryset(request.user), id=chemical_id)

    if not _user_can_manage_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to modify this reagent stock.")

    if request.method == "POST":
        try:
            movement_type = request.POST.get("movement_type")
            amount_raw = (request.POST.get("amount_value") or "").strip()
            amount_unit = (request.POST.get("amount_unit") or chemical.quantity_unit or "").strip()
            reason = request.POST.get("reason") or ""

            if not amount_raw:
                raise ValueError("Amount is required.")

            try:
                amount_value = Decimal(amount_raw)
            except InvalidOperation:
                raise ValueError("Invalid amount.")

            _apply_chemical_stock_movement(
                chemical=chemical,
                movement_type=movement_type,
                amount_value=amount_value,
                amount_unit=amount_unit,
                reason=reason,
                user=request.user,
            )

            messages.success(request, "Stock movement registered successfully.")
            return redirect("chemical_detail", chemical_id=chemical.id)

        except Exception as e:
            messages.error(request, f"Error registering stock movement: {e}")

    ctx = base_context(request)
    ctx.update({
        "chemical": chemical,
        "movement_types": ChemicalStockMovement.MOVEMENT_TYPES,
    })
    return render(request, "internal/chemicals/movement_form.html", ctx)
