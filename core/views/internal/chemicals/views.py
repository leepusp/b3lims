from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Count
from core.context import base_context
from core.models.chemicals.chemical import Chemical
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
    Processa a criação de um novo reagente.
    """
    if request.method == "POST":
        try:
            name = request.POST.get("name")
            quantity = request.POST.get("quantity")
            
            if not name or not quantity:
                raise ValueError("Name and Quantity are required.")

            Chemical.objects.create(
                name=name,
                formula=request.POST.get("formula"),
                cas_number=request.POST.get("cas_number"),
                quantity=quantity,
                location=request.POST.get("location"),
                expiry_date=request.POST.get("expiry_date") or None,
                msds_link=request.POST.get("msds_link"),
                hazard_notes=request.POST.get("hazard_notes"),
                created_by=request.user,
                research_group=request.user.research_groups.first(),
                is_public=request.POST.get("is_public") in ["true", "on", "1"],
            )
            messages.success(request, "Reagent registered successfully!")
            return redirect("chemicals_list")

        except Exception as e:
            messages.error(request, f"Error creating chemical: {e}")
    
    # Se for GET, renderiza o form (poderia ser uma página separada, mas vamos fazer modal no list.html para agilidade)
    return redirect("chemicals_list")


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
        "location_counts": qs.values("location")
            .annotate(total=Count("id"))
            .order_by("-total", "location")[:10],
        "soon_expiring": qs.filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=soon_limit,
        ).order_by("expiry_date", "name")[:10],
        "expired_chemicals": qs.filter(expiry_date__isnull=False, expiry_date__lt=today)
            .order_by("expiry_date", "name")[:10],
    })

    return render(request, "internal/chemicals/dashboard.html", ctx)
