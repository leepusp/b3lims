from core.services.metadata_vocabularies import active_tags_from_ids, get_or_create_active_keyword_value
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.forms import CollectionForm

from core.models import (
    Collection,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
)

from core.permissions.collections import (
    can_view_collection,
    can_edit_collection,
    visible_collections_for_user,
)

from core.permissions.samples import visible_samples_for_user


@login_required
def collections_dashboard_view(request):
    """
    Aggregated dashboard for collections visible to the current user.
    """
    user = request.user

    qs = visible_collections_for_user(user).select_related(
        "owner",
        "research_group",
    )

    total = qs.count()

    ctx = base_context(request)
    ctx.update({
        "collection_dashboard_stats": {
            "total": total,
            "public": qs.filter(is_public=True).count(),
            "restricted": qs.filter(is_public=False).count(),
            "groups": qs.exclude(research_group__isnull=True).values("research_group_id").distinct().count(),
            "owners": qs.exclude(owner__isnull=True).values("owner_id").distinct().count(),
        },
        "collection_dashboard_by_group": list(
            qs.values("research_group__name")
            .annotate(total=Count("id"))
            .order_by("research_group__name")
        ),
        "collection_dashboard_by_owner": list(
            qs.values("owner__username")
            .annotate(total=Count("id"))
            .order_by("owner__username")
        ),
        "recent_collections": qs.order_by("-created_at")[:10],
    })

    return render(request, "internal/collections/dashboard.html", ctx)


@login_required
def collections_list_view(request, template_name="internal/collections/collections.html"):
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # 1. CREATE COLLECTION
    if action == "add_collection":
        form = CollectionForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    collection = form.save(commit=False)
                    collection.owner = user
                    collection.is_active = True

                    if not collection.research_group_id:
                        user_group = user.research_groups.first()
                        if user_group:
                            collection.research_group = user_group

                    collection.save()

                    # --- REMOVIDA A TENTATIVA DE SALVAR BIOBANKS DIRETAMENTE NA COLEÇÃO ---
                    # Um Biobank é associado à Amostra (Sample), e não à pasta lógica (Collection).

                    # --- Tags ---
                    selected_tags = request.POST.getlist("tags")
                    collection.tags.set(
                        active_tags_from_ids(selected_tags)
                    )

                    # --- Keywords ---
                    pairs = request.POST.getlist("keyword_pairs")
                    for raw in pairs:
                        if ":::" not in raw: continue
                        key, value = raw.split(":::")
                        if key.strip() and value.strip():
                            keyword_value, _ = (
                                get_or_create_active_keyword_value(
                                    key,
                                    value,
                                )
                            )
                            collection.keywords.add(keyword_value)

                messages.success(request, "Collection created successfully!")
                return redirect("collections_list")

            except Exception as e:
                messages.error(request, f"Error creating Collection: {e}")
                return redirect("collections_list")
        else:
            errors = form.errors.as_text()
            messages.error(request, f"Invalid data: {errors}")
            return redirect("collections_list")

    # 2. DEACTIVATE
    elif action == "deactivate_collection":
        cid = request.POST.get("collection_id")
        collection = get_object_or_404(Collection, id=cid)

        if not can_edit_collection(user, collection):
            raise PermissionDenied

        collection.is_active = False
        collection.save(update_fields=["is_active"])
        messages.success(request, "Collection deactivated successfully.")
        return redirect("collections_list")

    # 3. LISTAGEM (GET)
    ctx = base_context(request)

    ctx["biobanks"] = Biobank.objects.filter(is_active=True).order_by("name")
    ctx["all_tags"] = (
        Tag.objects
        .filter(is_active=True)
        .order_by("name")
    )
    ctx["collection_form"] = CollectionForm()

    collections_qs = visible_collections_for_user(user).order_by("-created_at")

    visible_collections = []
    for c in collections_qs:
        c.can_edit = can_edit_collection(user, c)
        visible_collections.append(c)

    ctx["collections"] = visible_collections

    return render(request, template_name, ctx)


@login_required
def collection_create_view(request):
    """
    Render the collection creation interface separately from the collection list.
    POST handling remains centralized in collections_list_view().
    """
    return collections_list_view(
        request,
        template_name="internal/collections/collection_create.html",
    )

@login_required
def collection_detail_view(
    request,
    collection_id,
):
    """
    Interactive scientific overview for one Collection.

    Collection authorization controls access to the Collection itself.
    Sample-level authorization is evaluated independently before any
    Sample metadata or aggregate is exposed.
    """
    collection = get_object_or_404(
        Collection.objects
        .select_related(
            "owner",
            "research_group",
        )
        .prefetch_related(
            "tags",
            "keywords",
        ),
        pk=collection_id,
        is_active=True,
    )

    if not can_view_collection(
        request.user,
        collection,
    ):
        raise PermissionDenied

    samples_qs = (
        visible_samples_for_user(
            request.user
        )
        .filter(
            collections=collection,
        )
        .select_related(
            "biobank",
            "owner",
            "research_group",
        )
        .distinct()
        .order_by(
            "sample_id",
            "pk",
        )
    )

    total_samples = samples_qs.count()

    sample_type_distribution = list(
        samples_qs
        .values(
            "sample_type",
        )
        .annotate(
            total=Count(
                "id",
            )
        )
        .order_by(
            "-total",
            "sample_type",
        )
    )

    for row in sample_type_distribution:
        row["label"] = (
            row["sample_type"]
            or "Unspecified"
        )
        row["filter_value"] = (
            row["sample_type"]
            or "__blank__"
        )
        row["percent"] = (
            round(
                (
                    row["total"]
                    / total_samples
                )
                * 100
            )
            if total_samples
            else 0
        )

    biobank_distribution = list(
        samples_qs
        .values(
            "biobank_id",
            "biobank__name",
        )
        .annotate(
            total=Count(
                "id",
            )
        )
        .order_by(
            "-total",
            "biobank__name",
        )
    )

    for row in biobank_distribution:
        row["label"] = (
            row["biobank__name"]
            or "Unassigned"
        )
        row["filter_value"] = (
            str(
                row["biobank_id"]
            )
            if row["biobank_id"]
            is not None
            else "__none__"
        )
        row["percent"] = (
            round(
                (
                    row["total"]
                    / total_samples
                )
                * 100
            )
            if total_samples
            else 0
        )

    taxonomy_count = (
        samples_qs
        .filter(
            taxonomy_assignments__isnull=False,
        )
        .distinct()
        .count()
    )

    genome_count = (
        samples_qs
        .filter(
            genome_assembly_assignments__isnull=False,
        )
        .distinct()
        .count()
    )

    origin_count = (
        samples_qs
        .filter(
            origin__isnull=False,
        )
        .distinct()
        .count()
    )

    mapped_count = (
        samples_qs
        .filter(
            origin__latitude__isnull=False,
            origin__longitude__isnull=False,
        )
        .distinct()
        .count()
    )

    def coverage_percent(
        value,
    ):
        if not total_samples:
            return 0

        return round(
            (
                value
                / total_samples
            )
            * 100
        )

    ctx = base_context(
        request
    )

    ctx.update({
        "collection": collection,
        "collection_samples": list(
            samples_qs
        ),
        "collection_stats": {
            "samples": total_samples,
            "sample_types": len(
                sample_type_distribution
            ),
            "biobanks": len([
                row
                for row
                in biobank_distribution
                if row["biobank_id"]
                is not None
            ]),
            "taxonomy": taxonomy_count,
            "taxonomy_percent": coverage_percent(
                taxonomy_count
            ),
            "genomes": genome_count,
            "genomes_percent": coverage_percent(
                genome_count
            ),
            "origins": origin_count,
            "origins_percent": coverage_percent(
                origin_count
            ),
            "mapped": mapped_count,
            "mapped_percent": coverage_percent(
                mapped_count
            ),
        },
        "sample_type_distribution":
            sample_type_distribution,
        "biobank_distribution":
            biobank_distribution,
        "can_edit_collection":
            can_edit_collection(
                request.user,
                collection,
            ),
    })

    return render(
        request,
        "internal/collections/detail.html",
        ctx,
    )
