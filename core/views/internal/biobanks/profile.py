"""Read-only dashboard for one institutional Biobank."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from core.context import base_context
from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.collections.collection import Collection
from core.models.samples.sample import Sample
from core.permissions.biobanks import (
    VIEW_ROLES,
    can_view_biobank,
    user_has_biobank_role,
    user_is_biobank_group_member,
    user_is_biobank_owner,
)


def build_chart(queryset, field, labels=None):
    """Return real counts and relative bar widths."""
    labels = labels or {}

    rows = list(
        queryset.values(field)
        .annotate(total=Count("pk"))
        .order_by("-total", field)
    )

    overall = sum(row["total"] for row in rows)
    maximum = max((row["total"] for row in rows), default=1)

    return [
        {
            "name": labels.get(row[field], row[field])
            or "Not specified",
            "total": row["total"],
            "percentage": round(
                row["total"] * 100 / overall, 1
            ) if overall else 0,
            "width": round(row["total"] * 100 / maximum),
        }
        for row in rows
    ]


@login_required
def biobank_profile_view(request, biobank_id):
    bank = get_object_or_404(
        Biobank.objects.select_related("owner", "research_group"),
        pk=biobank_id,
    )

    if not can_view_biobank(request.user, bank):
        raise PermissionDenied(
            "You cannot view this Biobank."
        )

    # Public catalog visibility alone does not authorize
    # disclosure of the private member roster or sample totals.
    internal = bool(
        request.user.is_superuser
        or user_is_biobank_owner(request.user, bank)
        or user_is_biobank_group_member(request.user, bank)
        or user_has_biobank_role(request.user, bank, VIEW_ROLES)
    )

    ctx = base_context(request)

    ctx.update({
        "profile_bank": bank,
        "internal_access": internal,
        "sample_total": None,
        "collection_total": None,
        "member_total": None,
        "sample_types": [],
        "sample_statuses": [],
        "collection_stats": [],
        "profile_members": [],
    })

    if internal:
        samples = Sample.objects.filter(biobank=bank)

        collections = (
            Collection.objects
            .filter(samples__biobank=bank)
            .annotate(
                linked_samples=Count(
                    "samples",
                    filter=Q(samples__biobank=bank),
                    distinct=True,
                )
            )
            .order_by("-linked_samples", "name", "pk")
        )

        owner = bank.owner

        members = {
            owner.pk: {
                "name": (
                    owner.get_full_name().strip()
                    or owner.username
                ),
                "username": owner.username,
                "role": "Owner",
                "is_owner": True,
            }
        }

        for assignment in (
            BiobankUserRole.objects
            .filter(biobank=bank)
            .select_related("user")
        ):
            user = assignment.user

            if user.pk == owner.pk:
                continue

            members[user.pk] = {
                "name": (
                    user.get_full_name().strip()
                    or user.username
                ),
                "username": user.username,
                "role": assignment.get_role_display(),
                "is_owner": False,
            }

        roster = sorted(
            members.values(),
            key=lambda entry: (
                not entry["is_owner"],
                entry["name"].casefold(),
            ),
        )

        ctx.update({
            "sample_total": samples.count(),
            "collection_total": collections.count(),
            "member_total": len(roster),
            "sample_types": build_chart(
                samples, "sample_type"
            ),
            "sample_statuses": build_chart(
                samples,
                "status",
                dict(Sample.STATUS_CHOICES),
            ),
            "collection_stats": list(collections[:12]),
            "profile_members": roster,
        })

    return render(
        request,
        "internal/biobanks/biobank_profile.html",
        ctx,
    )
