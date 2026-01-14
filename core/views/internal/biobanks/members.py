from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.contrib import messages

from core.models import Biobank, BiobankUserRole
from core.permissions.biobanks import can_manage_biobank_permissions


def biobank_members_view(request, biobank_id):
    """
    Manage members and roles of a Biobank.
    Only OWNER or admin users can access this view.
    """

    biobank = get_object_or_404(Biobank, id=biobank_id)
    user = request.user

    # --------------------------------------------------
    # PERMISSION + STATE CHECK
    # --------------------------------------------------
    if not biobank.is_active:
        raise PermissionDenied("Biobank is inactive.")

    can_manage = can_manage_biobank_permissions(user, biobank)
    if not can_manage:
        raise PermissionDenied

    # ==================================================
    # ADD MEMBER
    # ==================================================
    if request.method == "POST" and request.POST.get("action") == "add_member":

        uid = request.POST.get("user_id")
        role = request.POST.get("role")

        # 🔒 Nunca permitir criar outro OWNER
        if role == BiobankUserRole.OWNER:
            messages.error(
                request,
                "Only one OWNER is allowed per biobank."
            )
            return redirect(f"/biobanks/{biobank.id}/members/")

        member = get_object_or_404(User, id=uid)

        BiobankUserRole.objects.update_or_create(
            user=member,
            biobank=biobank,
            defaults={"role": role},
        )

        messages.success(request, "Member added successfully.")
        return redirect(f"/biobanks/{biobank.id}/members/")

    # ==================================================
    # UPDATE ROLE
    # ==================================================
    if request.method == "POST" and request.POST.get("action") == "update_role":

        role_id = request.POST.get("role_id")
        new_role = request.POST.get("role")

        role_obj = get_object_or_404(BiobankUserRole, id=role_id)

        # 🔒 Proteção extra
        if role_obj.user == biobank.owner:
            messages.error(
                request,
                "The OWNER role cannot be modified."
            )
            return redirect(f"/biobanks/{biobank.id}/members/")

        if new_role == BiobankUserRole.OWNER:
            messages.error(
                request,
                "You cannot promote another user to OWNER."
            )
            return redirect(f"/biobanks/{biobank.id}/members/")

        role_obj.role = new_role
        role_obj.save()

        messages.success(request, "Member role updated.")
        return redirect(f"/biobanks/{biobank.id}/members/")

    # ==================================================
    # REMOVE MEMBER
    # ==================================================
    if request.method == "POST" and request.POST.get("action") == "remove_member":

        role_id = request.POST.get("role_id")
        role_obj = get_object_or_404(
            BiobankUserRole,
            id=role_id,
            biobank=biobank,
        )

        if role_obj.user == biobank.owner:
            messages.error(
                request,
                "The Biobank OWNER cannot be removed."
            )
            return redirect(f"/biobanks/{biobank.id}/members/")

        role_obj.delete()
        messages.success(request, "Member removed.")
        return redirect(f"/biobanks/{biobank.id}/members/")

    # ==================================================
    # CONTEXT
    # ==================================================
    current_user_ids = biobank.user_roles.values_list("user_id", flat=True)

    ctx = {
        "biobank": biobank,
        "members": biobank.user_roles.select_related("user"),
        "available_users": User.objects.exclude(id__in=current_user_ids),
        "can_manage": can_manage,
    }

    return render(
        request,
        "internal/biobanks/biobank_members.html",
        ctx
    )
