"""Equipment management for the Lab Calendar."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bench.forms import ResourceForm, groups_managed_by
from bench.models import BookableResource
from bench.permissions.scheduling import can_manage_resource
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
    context.update(rows=rows, can_create=_can_create(request.user))
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
