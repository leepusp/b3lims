from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from core.forms_profile import UserProfileForm
from core.models import Biobank, Collection, ResearchGroup, UserProfile
from core.context import base_context
from core.services.profile_access import (
    build_profile_collection_access_context,
)


User = get_user_model()


def _unsaved_or_existing_profile(user):
    profile = UserProfile.objects.filter(user=user).first()
    return profile if profile is not None else UserProfile(user=user)


def _update_profile(request):
    profile = _unsaved_or_existing_profile(request.user)
    form = UserProfileForm(
        request.POST,
        instance=profile,
        user=request.user,
    )
    if form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "Your profile was updated successfully.")
        return None, redirect("user_profile")
    return form, None


def _manage_group_membership(request):
    action = request.POST.get("action", "")
    group_id = request.POST.get("group_id")
    if not group_id:
        messages.error(request, "A research group is required.")
        return redirect("user_profile")

    group = get_object_or_404(ResearchGroup, id=group_id)
    if group.coordinator_id != request.user.id:
        messages.error(
            request,
            "Permission denied: only the group coordinator may manage members.",
        )
        return redirect("user_profile")

    if action == "add_member":
        identifier = request.POST.get("member_identifier", "").strip()
        member = (
            User.objects.filter(
                Q(email__iexact=identifier) | Q(username__iexact=identifier)
            )
            .order_by("id")
            .first()
        )
        if member is None:
            messages.error(
                request,
                "User not found. Check the email address or username.",
            )
        elif member == request.user:
            messages.warning(
                request,
                "You are already the coordinator of this group.",
            )
        else:
            group.members.add(member)
            messages.success(
                request,
                f"{member.get_full_name() or member.username} was added to the group.",
            )
    elif action == "remove_member":
        member = get_object_or_404(
            User,
            id=request.POST.get("member_id"),
        )
        group.members.remove(member)
        messages.success(request, "The member was removed from the group.")
    else:
        messages.error(request, "Unsupported profile action.")

    return redirect("user_profile")


@login_required
def profile_view(request):
    profile_form = None

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "update_profile":
            profile_form, response = _update_profile(request)
            if response is not None:
                return response
        else:
            return _manage_group_membership(request)

    profile = _unsaved_or_existing_profile(request.user)
    if profile_form is None:
        profile_form = UserProfileForm(
            instance=profile,
            user=request.user,
        )

    context = base_context(request)
    context.update(
        {
            "user_profile": profile,
            "profile_form": profile_form,
            "user_biobanks": Biobank.objects.filter(owner=request.user),
            "user_collections": Collection.objects.filter(owner=request.user),
            "coordinated_groups": ResearchGroup.objects.filter(
                coordinator=request.user,
            ).prefetch_related("members"),
            "member_groups": request.user.research_groups.exclude(
                coordinator=request.user,
            ).select_related("coordinator").prefetch_related("members"),
        }
    )

    context.update(
        build_profile_collection_access_context(
            request.user
        )
    )

    return render(request, "internal/profile/profile.html", context)
