from core.services.metadata_vocabularies import active_tags_from_ids, get_or_create_active_keyword_value
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction
from django.db.models import Count
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from core.context import base_context
from core.forms import (
    CollectionEditForm,
    CollectionForm,
)

from core.models import (
    Collection,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
    SampleTaxonomyAssignment,
    ResearchGroup,
    ResourceAccessGrant,
)

from core.permissions.collections import (
    can_view_collection,
    can_edit_collection,
    can_manage_collection_permissions,
    visible_collections_for_user,
)

from core.permissions.samples import visible_samples_for_user
from core.services.sample_origin_map import (
    build_sample_origin_distribution_context,
)
from core.services.sample_network import (
    build_sample_network_context,
)
from core.services.collection_sharing import (
    active_collection_access_grants,
    grant_collection_access,
    revoke_collection_access,
)


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
def collection_edit_view(
    request,
    collection_id,
):
    """
    Edit descriptive metadata for one active Collection.

    The standard edit surface deliberately excludes ownership,
    Research Group assignment, lifecycle state, public visibility,
    tags, and keywords.
    """
    collection_qs = (
        Collection.objects
        .select_related(
            "owner",
            "research_group",
        )
    )

    if request.method == "POST":
        with transaction.atomic():
            collection = get_object_or_404(
                collection_qs.select_for_update(),
                pk=collection_id,
                is_active=True,
            )

            if not can_edit_collection(
                request.user,
                collection,
            ):
                raise PermissionDenied

            form = CollectionEditForm(
                request.POST,
                instance=collection,
            )

            if form.is_valid():
                form.save()

                messages.success(
                    request,
                    "Collection metadata updated successfully.",
                )

                return redirect(
                    "collection_detail",
                    collection_id=collection.pk,
                )

    else:
        collection = get_object_or_404(
            collection_qs,
            pk=collection_id,
            is_active=True,
        )

        if not can_edit_collection(
            request.user,
            collection,
        ):
            raise PermissionDenied

        form = CollectionEditForm(
            instance=collection,
        )

    ctx = base_context(
        request
    )

    ctx.update(
        {
            "collection": collection,
            "collection_edit_form": form,
        }
    )

    return render(
        request,
        "internal/collections/edit.html",
        ctx,
    )

def _collection_share_error_message(
    exc,
):
    return (
        "; ".join(
            getattr(
                exc,
                "messages",
                [],
            )
        )
        or str(
            exc
        )
    )


def _parse_collection_share_expiry(
    request,
):
    raw = str(
        request.POST.get(
            "expires_at",
            "",
        )
        or ""
    ).strip()

    if not raw:
        return None

    value = parse_datetime(
        raw
    )

    if value is None:
        raise ValidationError(
            "Enter a valid access expiration date and time."
        )

    if timezone.is_naive(
        value
    ):
        value = timezone.make_aware(
            value,
            timezone.get_current_timezone(),
        )

    if value <= timezone.now():
        raise ValidationError(
            "Access expiration must be in the future."
        )

    return value


def _parse_collection_share_principal(
    request,
):
    raw = str(
        request.POST.get(
            "principal",
            "",
        )
        or ""
    ).strip()

    try:
        principal_type, raw_pk = raw.split(
            ":",
            1,
        )

        principal_pk = int(
            raw_pk
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Select a valid sharing principal."
        )

    if principal_type == "user":
        user = get_object_or_404(
            get_user_model(),
            pk=principal_pk,
            is_active=True,
        )

        return {
            "user": user,
            "research_group": None,
        }

    if principal_type == "group":
        research_group = get_object_or_404(
            ResearchGroup,
            pk=principal_pk,
        )

        return {
            "user": None,
            "research_group": research_group,
        }

    raise ValidationError(
        "Select a valid sharing principal."
    )


@login_required
@require_POST
def collection_share_view(
    request,
    collection_id,
):
    collection = get_object_or_404(
        Collection.objects
        .select_related(
            "owner",
            "research_group",
        ),
        pk=collection_id,
        is_active=True,
    )

    if not can_manage_collection_permissions(
        request.user,
        collection,
    ):
        raise PermissionDenied

    try:
        principal = (
            _parse_collection_share_principal(
                request
            )
        )

        access_level = str(
            request.POST.get(
                "access_level",
                ResourceAccessGrant
                .AccessLevel
                .VIEW,
            )
            or ResourceAccessGrant
            .AccessLevel
            .VIEW
        ).strip()

        grant = grant_collection_access(
            collection=collection,
            access_level=access_level,
            granted_by=request.user,
            user=principal[
                "user"
            ],
            research_group=principal[
                "research_group"
            ],
            expires_at=(
                _parse_collection_share_expiry(
                    request
                )
            ),
        )

    except ValidationError as exc:
        messages.error(
            request,
            _collection_share_error_message(
                exc
            ),
        )

        return redirect(
            "collection_detail",
            collection_id=collection.pk,
        )

    messages.success(
        request,
        (
            f"{grant.get_access_level_display()} access "
            f"for {grant.principal_label} is active."
        ),
    )

    return redirect(
        "collection_detail",
        collection_id=collection.pk,
    )


@login_required
@require_POST
def collection_share_revoke_view(
    request,
    collection_id,
    grant_id,
):
    collection = get_object_or_404(
        Collection.objects
        .select_related(
            "owner",
            "research_group",
        ),
        pk=collection_id,
        is_active=True,
    )

    if not can_manage_collection_permissions(
        request.user,
        collection,
    ):
        raise PermissionDenied

    grant = get_object_or_404(
        active_collection_access_grants(
            collection
        )
        .select_related(
            "user",
            "research_group",
        ),
        pk=grant_id,
    )

    principal_label = (
        grant.principal_label
    )

    try:
        revoke_collection_access(
            collection=collection,
            grant=grant,
            revoked_by=request.user,
        )

    except ValidationError as exc:
        messages.error(
            request,
            _collection_share_error_message(
                exc
            ),
        )

        return redirect(
            "collection_detail",
            collection_id=collection.pk,
        )

    messages.success(
        request,
        (
            f"Access for {principal_label} was revoked."
        ),
    )

    return redirect(
        "collection_detail",
        collection_id=collection.pk,
    )


@login_required
def collection_detail_view(
    request,
    collection_id,
):
    """
    Interactive scientific overview for one Collection.

    Collection authorization controls access to the Collection itself.
    Every Sample-derived aggregate starts from visible_samples_for_user()
    so taxonomy and geography cannot broaden Sample visibility.
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
            "origin",
        )
        .distinct()
        .order_by(
            "sample_id",
            "pk",
        )
    )

    collection_samples = list(
        samples_qs
    )

    total_samples = len(
        collection_samples
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

    # ---------------------------------------------------------
    # Basic Collection distributions
    # ---------------------------------------------------------

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
        row["percent"] = coverage_percent(
            row["total"]
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
        row["percent"] = coverage_percent(
            row["total"]
        )

    # ---------------------------------------------------------
    # Taxonomic evidence
    #
    # There is currently no canonical taxonomy assignment model.
    # Therefore:
    # - all current assignments contribute to review-state metrics;
    # - candidate + verified assignments may drive exploratory
    #   taxonomic drill-down;
    # - conflict, unresolved and stale evidence do not drive
    #   taxonomic filtering.
    # ---------------------------------------------------------

    sample_ids = [
        sample.pk
        for sample in collection_samples
    ]

    current_taxonomy_assignments = list(
        SampleTaxonomyAssignment.objects
        .filter(
            sample_id__in=sample_ids,
            is_current=True,
        )
        .order_by(
            "sample_id",
            "source",
            "pk",
        )
    )

    accepted_taxonomy_statuses = {
        SampleTaxonomyAssignment
        .STATUS_CANDIDATE,
        SampleTaxonomyAssignment
        .STATUS_VERIFIED,
    }

    taxonomy_rank_definitions = (
        (
            "domain",
            "domain_or_realm",
            "Domain / Realm",
        ),
        (
            "phylum",
            "phylum",
            "Phylum",
        ),
        (
            "family",
            "family",
            "Family",
        ),
        (
            "genus",
            "genus",
            "Genus",
        ),
        (
            "species",
            "species",
            "Species",
        ),
    )

    taxonomy_values_by_sample = {
        sample.pk: {
            rank_key: set()
            for (
                rank_key,
                _field_name,
                _label,
            )
            in taxonomy_rank_definitions
        }
        for sample in collection_samples
    }

    taxonomy_value_sample_ids = {
        rank_key: {}
        for (
            rank_key,
            _field_name,
            _label,
        )
        in taxonomy_rank_definitions
    }

    taxonomy_status_sample_ids = {
        status: set()
        for (
            status,
            _label,
        )
        in (
            SampleTaxonomyAssignment
            .MATCH_STATUS_CHOICES
        )
    }

    taxonomy_current_sample_ids = set()
    taxonomy_usable_sample_ids = set()

    for assignment in current_taxonomy_assignments:
        taxonomy_current_sample_ids.add(
            assignment.sample_id
        )

        taxonomy_status_sample_ids.setdefault(
            assignment.match_status,
            set(),
        ).add(
            assignment.sample_id
        )

        if (
            assignment.match_status
            not in accepted_taxonomy_statuses
        ):
            continue

        taxonomy_usable_sample_ids.add(
            assignment.sample_id
        )

        sample_values = (
            taxonomy_values_by_sample
            .get(
                assignment.sample_id
            )
        )

        if sample_values is None:
            continue

        for (
            rank_key,
            field_name,
            _label,
        ) in taxonomy_rank_definitions:
            value = (
                getattr(
                    assignment,
                    field_name,
                    "",
                )
                or ""
            ).strip()

            if not value:
                continue

            sample_values[
                rank_key
            ].add(
                value
            )

            (
                taxonomy_value_sample_ids[
                    rank_key
                ]
                .setdefault(
                    value,
                    set(),
                )
                .add(
                    assignment.sample_id
                )
            )

    for sample in collection_samples:
        values = (
            taxonomy_values_by_sample[
                sample.pk
            ]
        )

        for (
            rank_key,
            _field_name,
            _label,
        ) in taxonomy_rank_definitions:
            normalized_values = sorted(
                values[
                    rank_key
                ],
                key=str.casefold,
            )

            setattr(
                sample,
                (
                    "collection_taxonomy_"
                    f"{rank_key}_data"
                ),
                "||".join(
                    normalized_values
                ),
            )

        origin = getattr(
            sample,
            "origin",
            None,
        )

        sample.collection_origin_country = (
            (
                origin.country_or_ocean
                or ""
            ).strip()
            if origin is not None
            else ""
        )

    taxonomy_sections = []

    for (
        rank_key,
        _field_name,
        label,
    ) in taxonomy_rank_definitions:
        rows = [
            {
                "label": value,
                "filter_value": value,
                "total": len(
                    taxon_sample_ids
                ),
                "percent": coverage_percent(
                    len(
                        taxon_sample_ids
                    )
                ),
            }
            for (
                value,
                taxon_sample_ids,
            )
            in (
                taxonomy_value_sample_ids[
                    rank_key
                ].items()
            )
        ]

        rows.sort(
            key=lambda row: (
                -row["total"],
                row["label"].casefold(),
            )
        )

        taxonomy_sections.append(
            {
                "key": rank_key,
                "label": label,
                "rows": rows,
            }
        )

    taxonomy_status_counts = [
        {
            "status": status,
            "label": label,
            "samples": len(
                taxonomy_status_sample_ids
                .get(
                    status,
                    set(),
                )
            ),
        }
        for (
            status,
            label,
        )
        in (
            SampleTaxonomyAssignment
            .MATCH_STATUS_CHOICES
        )
    ]

    # ---------------------------------------------------------
    # Genome evidence
    # ---------------------------------------------------------

    genome_count = (
        samples_qs
        .filter(
            genome_assembly_assignments__is_current=True,
        )
        .distinct()
        .count()
    )

    # ---------------------------------------------------------
    # Geographic provenance
    # ---------------------------------------------------------

    origin_context = (
        build_sample_origin_distribution_context(
            samples_qs
        )
    )

    origin_stats = (
        origin_context[
            "sample_origin_map_stats"
        ]
    )

    # ---------------------------------------------------------
    # Biological relationships
    #
    # samples_qs is already restricted by both Sample visibility
    # and Collection membership. The shared serializer therefore
    # cannot expose nodes or edges outside this Collection scope.
    # ---------------------------------------------------------

    network_context = (
        build_sample_network_context(
            samples_qs
        )
    )

    country_sample_ids = {}

    for sample in collection_samples:
        country = (
            sample.collection_origin_country
        )

        if not country:
            continue

        (
            country_sample_ids
            .setdefault(
                country,
                set(),
            )
            .add(
                sample.pk
            )
        )

    country_distribution = [
        {
            "label": country,
            "filter_value": country,
            "total": len(
                country_samples
            ),
            "percent": coverage_percent(
                len(
                    country_samples
                )
            ),
        }
        for (
            country,
            country_samples,
        )
        in country_sample_ids.items()
    ]

    country_distribution.sort(
        key=lambda row: (
            -row["total"],
            row["label"].casefold(),
        )
    )

    can_manage_permissions = (
        can_manage_collection_permissions(
            request.user,
            collection,
        )
    )

    if can_manage_permissions:
        collection_access_grants = list(
            active_collection_access_grants(
                collection
            )
            .select_related(
                "user",
                "research_group",
                "granted_by",
            )
            .order_by(
                "id"
            )
        )

        collection_share_users = list(
            get_user_model()
            .objects
            .filter(
                is_active=True,
            )
            .exclude(
                pk=collection.owner_id,
            )
            .exclude(
                pk=request.user.pk,
            )
            .order_by(
                "username",
                "pk",
            )
        )

        collection_share_groups = list(
            ResearchGroup.objects
            .all()
            .order_by(
                "name",
                "pk",
            )
        )

    else:
        collection_access_grants = []
        collection_share_users = []
        collection_share_groups = []

    ctx = base_context(
        request
    )

    ctx.update(
        origin_context
    )

    ctx.update(
        network_context
    )

    ctx.update({
        "collection": collection,
        "collection_samples":
            collection_samples,
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
            "taxonomy": len(
                taxonomy_current_sample_ids
            ),
            "taxonomy_percent":
                coverage_percent(
                    len(
                        taxonomy_current_sample_ids
                    )
                ),
            "taxonomy_usable": len(
                taxonomy_usable_sample_ids
            ),
            "taxonomy_verified": len(
                taxonomy_status_sample_ids
                .get(
                    SampleTaxonomyAssignment
                    .STATUS_VERIFIED,
                    set(),
                )
            ),
            "taxonomy_conflicts": len(
                taxonomy_status_sample_ids
                .get(
                    SampleTaxonomyAssignment
                    .STATUS_CONFLICT,
                    set(),
                )
            ),
            "genomes": genome_count,
            "genomes_percent":
                coverage_percent(
                    genome_count
                ),
            "origins": (
                origin_stats[
                    "with_origin"
                ]
            ),
            "origins_percent":
                coverage_percent(
                    origin_stats[
                        "with_origin"
                    ]
                ),
            "mapped": (
                origin_stats[
                    "with_coordinates"
                ]
            ),
            "mapped_percent":
                coverage_percent(
                    origin_stats[
                        "with_coordinates"
                    ]
                ),
        },
        "sample_type_distribution":
            sample_type_distribution,
        "biobank_distribution":
            biobank_distribution,
        "taxonomy_sections":
            taxonomy_sections,
        "taxonomy_status_counts":
            taxonomy_status_counts,
        "country_distribution":
            country_distribution,
        "can_edit_collection":
            can_edit_collection(
                request.user,
                collection,
            ),
        "can_manage_collection_permissions":
            can_manage_permissions,
        "collection_access_grants":
            collection_access_grants,
        "collection_share_users":
            collection_share_users,
        "collection_share_groups":
            collection_share_groups,
        "collection_access_levels":
            ResourceAccessGrant
            .AccessLevel
            .choices,
    })

    return render(
        request,
        "internal/collections/detail.html",
        ctx,
    )
