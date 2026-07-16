from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.context import base_context
from core.models import Keyword, KeywordValue
from core.models.keywords.model import normalize_metadata_text
from core.permissions.metadata import require_metadata_manager


@login_required
def keywords_view(request):
    require_metadata_manager(request.user)

    query = normalize_metadata_text(request.GET.get("q", ""))

    active_values = (
        KeywordValue.objects
        .filter(is_active=True)
        .prefetch_related("samples", "collections", "biobanks")
        .order_by("value")
    )

    keywords = (
        Keyword.objects
        .filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "values",
                queryset=active_values,
                to_attr="active_values",
            )
        )
        .order_by("name")
    )

    if query:
        keywords = keywords.filter(name__icontains=query)

    enriched = []
    for keyword in keywords:
        values = keyword.active_values
        enriched.append({
            "keyword": keyword,
            "values": values,
            "sample_count": sum(v.samples.count() for v in values),
            "collection_count": sum(v.collections.count() for v in values),
            "biobank_count": sum(v.biobanks.count() for v in values),
            "total_values": len(values),
            "total_use": sum(
                v.samples.count()
                + v.collections.count()
                + v.biobanks.count()
                for v in values
            ),
        })

    ctx = base_context(request)
    ctx["back_url"] = request.META.get("HTTP_REFERER", "/")
    ctx["keywords"] = enriched
    ctx["query"] = query
    ctx["is_admin"] = True
    return render(request, "internal/keywords/keywords.html", ctx)


@login_required
@require_POST
def create_keyword_view(request):
    require_metadata_manager(request.user)

    name = normalize_metadata_text(request.POST.get("name", ""))

    if not name:
        messages.error(request, "Keyword name is required.")
        return redirect("keywords_view")

    existing = Keyword.objects.filter(name__iexact=name).first()
    if existing:
        if existing.is_active:
            messages.info(request, "A keyword with this name already exists.")
        else:
            messages.error(request, "This keyword is currently inactive.")
        return redirect("keywords_view")

    Keyword.objects.create(name=name)
    messages.success(request, f"Keyword '{name}' was created.")
    return redirect("keywords_view")


@login_required
@require_POST
def edit_keyword_view(request):
    require_metadata_manager(request.user)

    keyword = get_object_or_404(
        Keyword,
        pk=request.POST.get("id"),
        is_active=True,
    )
    name = normalize_metadata_text(request.POST.get("name", ""))

    if not name:
        messages.error(request, "Keyword name is required.")
        return redirect("keywords_view")

    duplicate = (
        Keyword.objects
        .filter(name__iexact=name)
        .exclude(pk=keyword.pk)
        .exists()
    )
    if duplicate:
        messages.error(
            request,
            "A keyword with this name already exists.",
        )
        return redirect("keywords_view")

    keyword.name = name
    keyword.save()

    messages.success(request, "Keyword was updated.")
    return redirect("keywords_view")


@login_required
@require_POST
def delete_keyword_view(request):
    require_metadata_manager(request.user)

    keyword = get_object_or_404(
        Keyword,
        pk=request.POST.get("id"),
        is_active=True,
    )
    keyword.is_active = False
    keyword.save(update_fields=["is_active"])

    messages.success(
        request,
        "Keyword was deactivated. Existing values and associations were preserved.",
    )
    return redirect("keywords_view")


@login_required
@require_POST
def delete_keyword_value_view(request):
    require_metadata_manager(request.user)

    value = get_object_or_404(
        KeywordValue,
        pk=request.POST.get("id"),
        is_active=True,
        keyword__is_active=True,
    )
    value.is_active = False
    value.save(update_fields=["is_active"])

    messages.success(
        request,
        "Keyword value was deactivated. Existing associations were preserved.",
    )
    return redirect("keywords_view")
