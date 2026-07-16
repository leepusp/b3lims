from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.context import base_context
from core.models import KeywordValue, Tag
from core.models.tags.model import normalize_metadata_name
from core.permissions.biobanks import visible_biobanks_for_user
from core.permissions.collections import visible_collections_for_user
from core.permissions.metadata import require_metadata_manager
from core.permissions.samples import visible_samples_for_user


@login_required
def tags_view(request):
    require_metadata_manager(request.user)

    tags = (
        Tag.objects
        .filter(is_active=True)
        .annotate(
            biobank_count=Count("biobanks", distinct=True),
            collection_count=Count("collections", distinct=True),
            sample_count=Count("samples", distinct=True),
        )
        .order_by("name")
    )

    enriched = []
    for tag in tags:
        total_use = (
            tag.biobank_count
            + tag.collection_count
            + tag.sample_count
        )
        enriched.append({
            "tag": tag,
            "biobank_count": tag.biobank_count,
            "collection_count": tag.collection_count,
            "sample_count": tag.sample_count,
            "total_use": total_use,
        })

    ctx = base_context(request)
    ctx["back_url"] = request.META.get("HTTP_REFERER", "/")
    ctx["tags"] = enriched
    ctx["is_admin"] = True
    return render(request, "internal/tags/tags.html", ctx)


@login_required
def search_view(request):
    query = normalize_metadata_name(request.GET.get("q", ""))
    tag_id = request.GET.get("tag")
    keyword_value_id = request.GET.get("kv")

    biobanks = visible_biobanks_for_user(request.user)
    collections = visible_collections_for_user(request.user)
    samples = visible_samples_for_user(request.user)

    selected_tag = (
        Tag.objects.filter(pk=tag_id, is_active=True).first()
        if tag_id else None
    )
    selected_keyword_value = (
        KeywordValue.objects.filter(
            pk=keyword_value_id,
            is_active=True,
            keyword__is_active=True,
        ).first()
        if keyword_value_id else None
    )

    if selected_tag:
        biobanks = biobanks.filter(tags=selected_tag)
        collections = collections.filter(tags=selected_tag)
        samples = samples.filter(tags=selected_tag)

    if selected_keyword_value:
        biobanks = biobanks.filter(keywords=selected_keyword_value)
        collections = collections.filter(keywords=selected_keyword_value)
        samples = samples.filter(keywords=selected_keyword_value)

    if query:
        biobanks = biobanks.filter(
            Q(name__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(keywords__value__icontains=query)
        )
        collections = collections.filter(
            Q(name__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(keywords__value__icontains=query)
        )
        samples = samples.filter(
            Q(sample_id__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(keywords__value__icontains=query)
        )

    ctx = base_context(request)
    ctx["selected_tag"] = selected_tag
    ctx["selected_keyword_value"] = selected_keyword_value
    ctx["search_results"] = {
        "biobanks": list(biobanks.distinct()),
        "collections": list(collections.distinct()),
        "samples": list(samples.distinct()),
    }
    ctx["tags"] = []
    return render(request, "internal/tags/tags.html", ctx)


@login_required
@require_POST
def create_tag_view(request):
    require_metadata_manager(request.user)

    name = normalize_metadata_name(request.POST.get("name", ""))
    description = (request.POST.get("description") or "").strip()

    if not name:
        messages.error(request, "Tag name is required.")
        return redirect("tags_view")

    existing = Tag.objects.filter(name__iexact=name).first()
    if existing:
        if existing.is_active:
            messages.info(request, "A tag with this name already exists.")
        else:
            messages.error(request, "This tag is currently inactive.")
        return redirect("tags_view")

    Tag.objects.create(name=name, description=description)
    messages.success(request, f"Tag '{name}' was created.")
    return redirect("tags_view")


@login_required
@require_POST
def edit_tag_view(request):
    require_metadata_manager(request.user)

    tag = get_object_or_404(
        Tag,
        pk=request.POST.get("id"),
        is_active=True,
    )
    name = normalize_metadata_name(request.POST.get("name", ""))

    if not name:
        messages.error(request, "Tag name is required.")
        return redirect("tags_view")

    duplicate = (
        Tag.objects
        .filter(name__iexact=name)
        .exclude(pk=tag.pk)
        .exists()
    )
    if duplicate:
        messages.error(request, "A tag with this name already exists.")
        return redirect("tags_view")

    tag.name = name
    tag.description = (
        request.POST.get("description", tag.description) or ""
    ).strip()
    tag.save()

    messages.success(request, "Tag was updated.")
    return redirect("tags_view")


@login_required
@require_POST
def delete_tag_view(request):
    require_metadata_manager(request.user)

    tag = get_object_or_404(
        Tag,
        pk=request.POST.get("id"),
        is_active=True,
    )
    tag.is_active = False
    tag.save(update_fields=["is_active"])

    messages.success(
        request,
        "Tag was deactivated. Existing associations were preserved.",
    )
    return redirect("tags_view")


@login_required
@require_POST
def create_tag_ajax_view(request):
    name = normalize_metadata_name(request.POST.get("name", ""))

    if not name:
        return JsonResponse(
            {"error": "Tag name is required."},
            status=400,
        )

    existing = Tag.objects.filter(name__iexact=name).first()
    if existing:
        if not existing.is_active:
            return JsonResponse(
                {"error": "This tag is inactive and cannot be assigned."},
                status=409,
            )
        return JsonResponse({
            "success": True,
            "id": existing.id,
            "name": existing.name,
            "created": False,
        })

    try:
        tag = Tag.objects.create(name=name)
    except IntegrityError:
        tag = Tag.objects.filter(name__iexact=name, is_active=True).first()
        if tag is None:
            return JsonResponse(
                {"error": "The tag could not be created."},
                status=409,
            )
        created = False
    else:
        created = True

    return JsonResponse({
        "success": True,
        "id": tag.id,
        "name": tag.name,
        "created": created,
    })
