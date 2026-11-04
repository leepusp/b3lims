"""Equipment management for the Lab Calendar."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bench.forms import ResourceForm, groups_managed_by
from bench.models import BookableResource, LayerStyle
from bench.permissions.scheduling import can_manage_resource
from bench.services.layers import BUILTIN, styles_for
from core.context import base_context


def _visible(user):
    if user.is_superuser:
        return BookableResource.objects.all()
    return BookableResource.objects.filter(
        Q(research_group__coordinator=user) | Q(research_group__members=user)
    ).distinct()


def _can_create(user):
    return user.is_superuser or groups_managed_by(user).exists()


@login_required
def equipment_list(request):
    rows = [
        {"resource": r, "can_manage": can_manage_resource(request.user, r)}
        for r in _visible(request.user).select_related("research_group")
    ]
    context = base_context(request)
    context.update(rows=rows, can_create=_can_create(request.user), builtin=list(styles_for(request.user).values()))
    return render(request, "internal/calendar/equipment_list.html", context)


@login_required
def equipment_form(request, resource_id=None):
    resource = get_object_or_404(BookableResource, pk=resource_id) if resource_id else None
    if resource is None and not _can_create(request.user):
        raise PermissionDenied
    if resource is not None and not can_manage_resource(request.user, resource):
        raise PermissionDenied
    form = ResourceForm(request.POST or None, instance=resource, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if resource is None:
            saved.created_by = request.user
        saved.save()
        messages.success(request, f"{saved.name} saved.")
        return redirect("bench:equipment_list")
    context = base_context(request)
    context.update(form=form, resource=resource)
    return render(request, "internal/calendar/equipment_form.html", context)


@login_required
@require_POST
def equipment_toggle(request, resource_id):
    resource = get_object_or_404(BookableResource, pk=resource_id)
    if not can_manage_resource(request.user, resource):
        raise PermissionDenied
    resource.is_active = not resource.is_active
    resource.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{resource.name} {'restored' if resource.is_active else 'archived'}.")
    return redirect("bench:equipment_list")


@login_required
def layer_style(request, key):
    """Name, colour and meaning of a built-in layer, for the person only."""
    if key not in BUILTIN:
        raise Http404
    if request.method == "POST":
        if request.POST.get("reset"):
            LayerStyle.objects.filter(user=request.user, key=key).delete()
            messages.success(request, "Layer reset to its defaults.")
            return redirect("bench:equipment_list")
        color = (request.POST.get("color") or "").strip()
        if color and not (len(color) == 7 and color.startswith("#")):
            messages.error(request, "Use a colour like #7c3aed.")
            return redirect("bench:equipment_list")
        default = BUILTIN[key]
        label = (request.POST.get("label") or "").strip()[:80]
        description = (request.POST.get("description") or "").strip()[:300]
        LayerStyle.objects.update_or_create(
            user=request.user,
            key=key,
            defaults={
                "label": "" if label == default["label"] else label,
                "color": "" if color.lower() == default["color"] else color,
                "description": "" if description == default["description"] else description,
            },
        )
        messages.success(request, "Layer saved.")
    return redirect("bench:equipment_list")
