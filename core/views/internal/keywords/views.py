from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from core.context import base_context
from core.models import Keyword, KeywordValue


def keywords_view(request):
    if not request.user.is_authenticated:
        raise PermissionDenied

    ctx = base_context(request)
    ctx["back_url"] = request.META.get('HTTP_REFERER', '/?page=workspace')

    # Captura busca se existir
    query = request.GET.get("q", "").strip().lower()

    enriched = []
    # Prefetch para otimizar performance na LEEP3
    values_prefetched = KeywordValue.objects.prefetch_related("samples", "collections", "biobanks")

    keywords_qs = Keyword.objects.all().order_by("name")

    if query:
        keywords_qs = keywords_qs.filter(name__icontains=query)

    for key in keywords_qs:
        values = values_prefetched.filter(keyword=key)
        enriched.append({
            "keyword": key,
            "values": values,
            "sample_count": sum(v.samples.count() for v in values),
            "collection_count": sum(v.collections.count() for v in values),
            "biobank_count": sum(v.biobanks.count() for v in values),
            "total_values": values.count(),
        })

    ctx["keywords"] = enriched
    ctx["query"] = query
    ctx["is_admin"] = request.user.is_superuser
    return render(request, "internal/keywords/keywords.html", ctx)


def edit_keyword_view(request):
    if request.method == "POST":
        key = Keyword.objects.get(id=request.POST.get("id"))
        key.name = request.POST.get("name")
        key.save()
        messages.success(request, "Chave de metadados atualizada.")
    return redirect("/?page=keywords")


def delete_keyword_view(request):
    if request.method == "POST":
        key = Keyword.objects.get(id=request.POST.get("id"))
        # Verifica se existem valores vinculados para segurança
        if KeywordValue.objects.filter(keyword=key).exists() and not request.user.is_superuser:
            messages.error(request, "Esta chave possui valores em uso e não pode ser removida.")
        else:
            key.delete()
            messages.success(request, "Chave removida do sistema.")
    return redirect("/?page=keywords")