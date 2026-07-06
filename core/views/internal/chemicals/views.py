from decimal import Decimal, InvalidOperation
from django.core.exceptions import PermissionDenied
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Count, Count
from core.context import base_context
from core.models.chemicals.chemical import Chemical, ChemicalStockMovement
from core.permissions.chemicals import visible_chemicals_for_user, can_edit_chemical

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
            Q(formula__icontains=query)
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
    Aggregated dashboard for reagent inventory, stock locations and safety status.
    """
    qs = visible_chemicals_for_user(request.user)

    today = timezone.localdate()
    soon_limit = today + timezone.timedelta(days=60)

    status_counts = {
        "available": qs.filter(status="available").count(),
        "low_stock": qs.filter(status="low_stock").count(),
        "expired": qs.filter(status="expired").count(),
    }

    ctx = base_context(request)
    ctx.update({
        "total_chemicals": qs.count(),
        "public_chemicals": qs.filter(is_public=True).count(),
        "restricted_chemicals": qs.filter(is_public=False).count(),
        "status_counts": status_counts,
        "group_counts": qs.values("research_group__name")
            .annotate(total=Count("id"))
            .order_by("-total", "research_group__name")[:10],
        "location_counts": qs.values("storage_location")
            .annotate(total=Count("id"))
            .order_by("-total", "storage_location")[:10],
        "soon_expiring": qs.filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=soon_limit,
        ).order_by("expiry_date", "name")[:10],
        "expired_chemicals": qs.filter(expiry_date__isnull=False, expiry_date__lt=today)
            .order_by("expiry_date", "name")[:10],
    })

    return render(request, "internal/chemicals/dashboard.html", ctx)


def _chemical_access_queryset(user):
    qs = Chemical.objects.select_related("created_by", "research_group").all()

    if user.is_superuser or user.is_staff:
        return qs

    if hasattr(user, "research_groups"):
        groups = user.research_groups.all()
        return qs.filter(
            Q(is_public=True) |
            Q(created_by=user) |
            Q(research_group__in=groups)
        ).distinct()

    return qs.filter(Q(is_public=True) | Q(created_by=user)).distinct()


def _user_can_manage_chemical(user, chemical):
    return (
        user.is_superuser
        or user.is_staff
        or chemical.created_by_id == user.id
    )



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

    if not _user_can_manage_chemical(request.user, chemical):
        raise PermissionDenied("You do not have permission to delete this reagent.")

    if request.method == "POST":
        name = chemical.name
        chemical.delete()
        messages.success(request, f"Reagent {name} deleted successfully.")
        return redirect("chemicals_list")

    ctx = base_context(request)
    ctx.update({"chemical": chemical})
    return render(request, "internal/chemicals/confirm_delete.html", ctx)



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
