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
                    if selected_tags:
                        collection.tags.set(selected_tags)

                    # --- Keywords ---
                    pairs = request.POST.getlist("keyword_pairs")
                    for raw in pairs:
                        if ":::" not in raw: continue
                        key, value = raw.split(":::")
                        if key.strip() and value.strip():
                            keyword_obj, _ = Keyword.objects.get_or_create(name=key.strip())
                            kv, _ = KeywordValue.objects.get_or_create(keyword=keyword_obj, value=value.strip())
                            collection.keywords.add(kv)

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
    ctx["all_tags"] = Tag.objects.all().order_by("name")
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
