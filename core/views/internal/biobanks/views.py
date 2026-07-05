from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.forms import BiobankForm

from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.tags.model import Tag
from core.models.keywords.model import Keyword, KeywordValue
from core.permissions.biobanks import can_view_biobank, can_edit_biobank, can_manage_biobank_permissions, visible_biobanks_for_user


# BIOBANK_DASHBOARD_VIEW_START
def _build_biobank_dashboard_context(user):
    """
    Build the institutional biobank dashboard from real active database records.

    This is metadata-oriented and intentionally broader than edit permissions:
    registered active biobanks are visible on the institutional map, while edit
    and member-management actions remain permission-restricted.
    """
    dashboard_biobanks = list(
        Biobank.objects.filter(is_active=True)
        .select_related("owner", "research_group")
        .order_by("name")
    )

    groups = sorted(
        {
            biobank.research_group.name
            for biobank in dashboard_biobanks
            if biobank.research_group_id and biobank.research_group
        }
    )

    stats = {
        "total": len(dashboard_biobanks),
        "active": sum(1 for biobank in dashboard_biobanks if biobank.is_active),
        "public": sum(1 for biobank in dashboard_biobanks if biobank.is_public),
        "restricted": sum(1 for biobank in dashboard_biobanks if not biobank.is_public),
        "groups": len(groups),
        "with_coordinates": sum(
            1
            for biobank in dashboard_biobanks
            if biobank.latitude is not None and biobank.longitude is not None
        ),
    }

    map_data = []
    for biobank in dashboard_biobanks:
        owner_name = "Unassigned"
        if biobank.owner_id:
            owner_name = biobank.owner.get_full_name() or biobank.owner.username

        group_name = "Unassigned"
        if biobank.research_group_id and biobank.research_group:
            group_name = biobank.research_group.name

        location = biobank.location_label or "Location not provided"

        map_data.append(
            {
                "id": biobank.id,
                "name": biobank.name,
                "description": biobank.description or "",
                "location": location,
                "latitude": float(biobank.latitude) if biobank.latitude is not None else None,
                "longitude": float(biobank.longitude) if biobank.longitude is not None else None,
                "owner": owner_name,
                "group": group_name,
                "visibility": "Public" if biobank.is_public else "Restricted",
                "status": "Operational" if biobank.is_active else "Inactive",
                "can_view": True,
                "can_edit": can_edit_biobank(user, biobank),
                "can_manage": can_manage_biobank_permissions(user, biobank),
            }
        )

    return stats, map_data


@login_required
def biobanks_dashboard_view(request):
    ctx = base_context(request)
    stats, map_data = _build_biobank_dashboard_context(request.user)

    ctx["biobank_dashboard_stats"] = stats
    ctx["biobank_map_data"] = map_data

    return render(request, "internal/biobanks/biobank_dashboard.html", ctx)


# BIOBANK_DASHBOARD_VIEW_END

@login_required
def biobanks_list_view(request): 
    user = request.user
    action = request.POST.get("action")

    # 1. ACTION: ADD BIOBANK
    if request.method == "POST" and action == "add_biobank":
        form = BiobankForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid biobank data.")
            return redirect("biobanks_list") 

        try:
            with transaction.atomic():
                biobank = form.save(commit=False)
                biobank.owner = user
                biobank.is_active = True
                biobank.save()

                BiobankUserRole.objects.get_or_create(
                    user=user,
                    biobank=biobank,
                    defaults={"role": BiobankUserRole.OWNER},
                )

                tag_ids = request.POST.getlist("tags")
                if tag_ids: biobank.tags.set(tag_ids)

                for raw in request.POST.getlist("keyword_pairs"):
                    if ":::" not in raw: continue
                    key, value = map(str.strip, raw.split(":::"))
                    
                    if not key or not value: continue 
                    
                    keyword_obj, _ = Keyword.objects.get_or_create(name=key)
                    kv, _ = KeywordValue.objects.get_or_create(keyword=keyword_obj, value=value)
                    biobank.keywords.add(kv)

                messages.success(request, "Biobank created successfully!")
        except Exception as e:
            messages.error(request, f"Error creating biobank: {e}")
        return redirect("biobanks_list") 

    # 2. ACTION: DEACTIVATE BIOBANK
    if request.method == "POST" and action == "deactivate_biobank":
        bb_id = request.POST.get("biobank_id")
        biobank = get_object_or_404(Biobank, id=bb_id)
        
        if not can_edit_biobank(user, biobank):
            raise PermissionDenied
            
        biobank.is_active = False
        biobank.save(update_fields=["is_active"])
        messages.success(request, "Biobank deactivated successfully.")
        return redirect("biobanks_list") 

    # 3. ACTION: PERMANENT DELETE (Administrative only)
    if request.method == "POST" and action == "delete_biobank":
        if not (user.is_superuser or user.is_staff):
            raise PermissionDenied
            
        bb_id = request.POST.get("biobank_id")
        biobank = get_object_or_404(Biobank, id=bb_id)
        biobank.delete()
        messages.success(request, "Biobank permanently deleted.")
        return redirect("biobanks_list") 

    # 4. VIEW LOGIC (GET)
    ctx = base_context(request)
    ctx["biobank_form"] = BiobankForm()
    ctx["all_tags"] = Tag.objects.all().order_by("name")

    visible_biobanks = list(visible_biobanks_for_user(user).order_by("name"))

    for b in visible_biobanks:
        b.can_edit = can_edit_biobank(user, b)
        b.can_manage_members = can_manage_biobank_permissions(user, b)

    # BIOBANK_DASHBOARD_CONTEXT_START
    dashboard_biobanks = list(
        Biobank.objects.filter(is_active=True)
        .select_related("owner", "research_group")
        .order_by("name")
    )

    dashboard_groups = sorted(
        {
            b.research_group.name
            for b in dashboard_biobanks
            if b.research_group_id and b.research_group
        }
    )

    ctx["biobank_dashboard_stats"] = {
        "total": len(dashboard_biobanks),
        "active": sum(1 for b in dashboard_biobanks if b.is_active),
        "public": sum(1 for b in dashboard_biobanks if b.is_public),
        "restricted": sum(1 for b in dashboard_biobanks if not b.is_public),
        "groups": len(dashboard_groups),
        "with_coordinates": sum(
            1
            for b in dashboard_biobanks
            if b.latitude is not None and b.longitude is not None
        ),
    }

    ctx["biobank_map_data"] = [
        {
            "id": b.id,
            "name": b.name,
            "description": b.description or "",
            "location": b.location_label or "",
            "latitude": float(b.latitude) if b.latitude is not None else None,
            "longitude": float(b.longitude) if b.longitude is not None else None,
            "owner": b.owner.get_full_name() or b.owner.username if b.owner_id else "Unassigned",
            "group": b.research_group.name if b.research_group_id and b.research_group else "Unassigned",
            "visibility": "Public" if b.is_public else "Restricted",
            "status": "Operational" if b.is_active else "Inactive",
            "can_view": can_view_biobank(user, b),
            "can_edit": can_edit_biobank(user, b),
            "can_manage": can_manage_biobank_permissions(user, b),
        }
        for b in dashboard_biobanks
    ]
    # BIOBANK_DASHBOARD_CONTEXT_END

    ctx["biobanks"] = visible_biobanks
    
    return render(request, "internal/biobanks/biobanks.html", ctx)
