from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import PermissionDenied

from core.context import base_context
from core.forms import BiobankForm
from core.models import (
    Biobank,
    BiobankUserRole,
    Tag,
    Keyword,
    KeywordValue,
)
from core.permissions.biobanks import (
    can_view_biobank,
    can_edit_biobank,
    can_manage_biobank_permissions,
)


def biobanks_view(request):
    """
    Internal view for managing Biobanks.
    Handles:
    - creation
    - visibility control
    - soft deactivation
    - hard delete (admin)
    - listing with permissions
    """

    user = request.user
    action = request.POST.get("action")

    # =====================================================
    # CREATE BIOBANK
    # =====================================================
    if request.method == "POST" and action == "add_biobank":

        if not user.is_authenticated:
            raise PermissionDenied

        form = BiobankForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Invalid biobank data.")
            return redirect("/?page=biobanks")

        try:
            with transaction.atomic():

                # ------------------------------
                # 1) Create Biobank
                # ------------------------------
                biobank = form.save(commit=False)
                biobank.owner = user
                biobank.is_active = True
                biobank.save()

                # ------------------------------
                # 2) TAGS (via chips)
                # ------------------------------
                tag_ids = request.POST.getlist("tags")
                if tag_ids:
                    biobank.tags.set(tag_ids)

                # ------------------------------
                # 3) OWNER ACL
                # ------------------------------
                BiobankUserRole.objects.create(
                    user=user,
                    biobank=biobank,
                    role=BiobankUserRole.OWNER,
                )

                # ------------------------------
                # 4) KEYWORDS (custom M2M)
                # ------------------------------
                for raw in request.POST.getlist("keyword_pairs"):
                    if ":::" not in raw:
                        continue

                    key, value = map(str.strip, raw.split(":::"))
                    if not key or not value:
                        continue

                    keyword_obj, _ = Keyword.objects.get_or_create(name=key)
                    kv, _ = KeywordValue.objects.get_or_create(
                        keyword=keyword_obj,
                        value=value
                    )
                    biobank.keywords.add(kv)

                messages.success(request, "Biobank created successfully!")

        except Exception as e:
            messages.error(request, f"Error creating biobank: {e}")

        return redirect("/?page=biobanks")

    # =====================================================
    # DEACTIVATE BIOBANK (SOFT DELETE)
    # =====================================================
    if request.method == "POST" and action == "deactivate_biobank":

        biobank = get_object_or_404(Biobank, id=request.POST.get("id"))

        if not can_edit_biobank(user, biobank):
            raise PermissionDenied

        biobank.is_active = False
        biobank.save(update_fields=["is_active"])

        messages.success(request, "Biobank deactivated successfully.")
        return redirect("/?page=biobanks")

    # =====================================================
    # DELETE BIOBANK (ADMIN ONLY)
    # =====================================================
    if request.method == "POST" and action == "delete_biobank":

        if not (user.is_superuser or user.is_staff):
            raise PermissionDenied

        biobank = get_object_or_404(Biobank, id=request.POST.get("id"))
        biobank.delete()

        messages.success(request, "Biobank permanently deleted.")
        return redirect("/?page=biobanks")

    # =====================================================
    # LIST / CONTEXT (GET)
    # =====================================================
    ctx = base_context(request)
    ctx["biobank_form"] = BiobankForm()
    ctx["all_tags"] = Tag.objects.all().order_by("name")

    # -----------------------------------------------------
    # FILTER BIOBANKS BY PERMISSION + VISIBILITY
    # -----------------------------------------------------
    visible_biobanks = []

    for b in Biobank.objects.filter(is_active=True).order_by("name"):

        # permission layer
        if not can_view_biobank(user, b):
            continue

        # visibility layer
        if b.visibility == "private" and b.owner != user:
            continue

        visible_biobanks.append(b)

    # -----------------------------------------------------
    # FLAGS FOR TEMPLATE
    # -----------------------------------------------------
    for b in visible_biobanks:
        b.can_edit = can_edit_biobank(user, b)
        b.can_manage_members = can_manage_biobank_permissions(user, b)
        b.members_roles = (
            b.user_roles
            .select_related("user")
            .all()
        )

    ctx["biobanks"] = visible_biobanks

    return render(
        request,
        "internal/biobanks/biobanks.html",
        ctx
    )
