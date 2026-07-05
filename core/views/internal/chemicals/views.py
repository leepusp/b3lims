from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
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
