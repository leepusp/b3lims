from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User

from core.models import Collection, CollectionUserRole
from core.permissions.collections import can_manage_collection_permissions
from core.context import base_context


def manage_collection_members(request, collection_id):
    """
    Manage members and roles of a Collection.
    Only OWNER or admin users can access this view.
    """

    user = request.user
    collection = get_object_or_404(Collection, id=collection_id)

    # =====================================================
    # STATE + PERMISSION CHECK
    # =====================================================
    if not collection.is_active:
        raise PermissionDenied("Collection is inactive.")

    if not can_manage_collection_permissions(user, collection):
        raise PermissionDenied

    # =====================================================
    # ADD / UPDATE MEMBER
    # =====================================================
    if request.method == "POST" and request.POST.get("action") == "add_member":

        username = (request.POST.get("username") or "").strip()
        role = request.POST.get("role")

        allowed_roles = (
            CollectionUserRole.OWNER,
            CollectionUserRole.EDITOR,
            CollectionUserRole.VIEWER,
        )

        if role not in allowed_roles:
            messages.error(request, "Invalid role.")
            return redirect(request.path)

        target_user = User.objects.filter(username=username).first()
        if not target_user:
            messages.error(request, "User not found.")
            return redirect(request.path)

        # -------------------------------------------------
        # NÃO ALTERAR O PRÓPRIO PAPEL
        # -------------------------------------------------
        if target_user == user:
            messages.error(
                request,
                "You cannot change your own role."
            )
            return redirect(request.path)

        CollectionUserRole.objects.update_or_create(
            user=target_user,
            collection=collection,
            defaults={"role": role},
        )

        messages.success(
            request,
            f"User '{username}' added/updated as {role}."
        )
        return redirect(request.path)

    # =====================================================
    # REMOVE MEMBER
    # =====================================================
    if request.method == "POST" and request.POST.get("action") == "remove_member":

        role_id = request.POST.get("role_id")

        membership = (
            CollectionUserRole.objects
            .filter(id=role_id, collection=collection)
            .select_related("user")
            .first()
        )

        if not membership:
            messages.error(request, "Membership not found.")
            return redirect(request.path)

        # -------------------------------------------------
        # NÃO REMOVER A SI MESMO
        # -------------------------------------------------
        if membership.user == user:
            messages.error(
                request,
                "You cannot remove yourself from the collection."
            )
            return redirect(request.path)

        # -------------------------------------------------
        # NÃO REMOVER ÚLTIMO OWNER
        # -------------------------------------------------
        if membership.role == CollectionUserRole.OWNER:
            owners_count = CollectionUserRole.objects.filter(
                collection=collection,
                role=CollectionUserRole.OWNER,
            ).count()

            if owners_count <= 1:
                messages.error(
                    request,
                    "A collection must have at least one owner."
                )
                return redirect(request.path)

        membership.delete()
        messages.success(request, "Member removed.")
        return redirect(request.path)

    # =====================================================
    # CONTEXT
    # =====================================================
    ctx = base_context(request)
    ctx["collection"] = collection
    ctx["members"] = (
        CollectionUserRole.objects
        .filter(collection=collection)
        .select_related("user")
        .order_by("role", "user__username")
    )

    return render(
        request,
        "internal/collections/collection_members.html",
        ctx
    )
