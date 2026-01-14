from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from core.context import base_context
from core.models import Tag, KeywordValue
from core.forms import TagForm


def tags_view(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    ctx = base_context(request)
    ctx["back_url"] = request.META.get('HTTP_REFERER', '/?page=workspace')

    enriched = []
    for tag in Tag.objects.all().order_by("name"):
        biobanks = list(tag.biobanks.all())
        collections = list(tag.collections.all())
        samples = list(tag.samples.all())
        enriched.append({
            "tag": tag,
            "biobanks": biobanks,
            "collections": collections,
            "samples": samples,
            "biobank_count": len(biobanks),
            "collection_count": len(collections),
            "sample_count": len(samples),
            "total_use": len(biobanks) + len(collections) + len(samples),
        })
    ctx["tags"] = enriched
    ctx["is_admin"] = request.user.is_superuser
    return render(request, "internal/tags/tags.html", ctx)


def search_view(request):
    ctx = base_context(request)
    ctx["back_url"] = request.META.get('HTTP_REFERER', '/?page=workspace')
    query = (request.GET.get("q") or "").strip().lower()
    tag_id = request.GET.get("tag")
    kv_id = request.GET.get("kv")

    biobanks = ctx.get("biobanks", [])
    collections = ctx.get("collections", [])
    samples = ctx.get("samples", [])

    selected_tag = Tag.objects.filter(id=tag_id).first() if tag_id else None
    selected_kv = KeywordValue.objects.filter(id=kv_id).first() if kv_id else None

    if selected_tag:
        biobanks = biobanks.filter(tags=selected_tag)
    if selected_kv:
        samples = samples.filter(keyword_values=selected_kv)

    if query:
        biobanks = [b for b in biobanks if
                    query in b.name.lower() or any(query in t.name.lower() for t in b.tags.all())]
        collections = [c for c in collections if query in c.name.lower()]
        samples = [s for s in samples if
                   query in s.sample_id.lower() or any(query in kv.value.lower() for kv in s.keyword_values.all())]

    ctx["selected_tag"] = selected_tag
    ctx["selected_keyword_value"] = selected_kv
    ctx["search_results"] = {"biobanks": list(biobanks), "collections": list(collections), "samples": list(samples)}
    return render(request, "internal/tags/tags.html", ctx)


def create_tag_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            Tag.objects.get_or_create(name=name)
            messages.success(request, f"Tag '{name}' criada com sucesso.")
    return redirect("/?page=tags")


def edit_tag_view(request):
    if request.method == "POST":
        tag_id = request.POST.get("id")
        tag = Tag.objects.get(id=tag_id)
        tag.name = request.POST.get("name")
        tag.save()
        messages.success(request, "Tag atualizada.")
    return redirect("/?page=tags")


def delete_tag_view(request):
    if request.method == "POST":
        tag_id = request.POST.get("id")
        tag = Tag.objects.get(id=tag_id)
        tag.delete()
        messages.success(request, "Tag removida.")
    return redirect("/?page=tags")


def create_tag_ajax_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)
    name = request.POST.get("name", "").strip()
    tag, created = Tag.objects.get_or_create(name=name)
    return JsonResponse({"id": tag.id, "name": tag.name, "created": created})