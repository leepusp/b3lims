from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, models
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.models import (
    Sample,
    Collection,
    SampleFile,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
)

from core.permissions.samples import (
    can_view_sample,
    can_edit_sample,
    can_delete_sample,
)
from core.permissions.collections import can_edit_collection

@login_required
def samples_view(request):
    """
    View interna para gerenciamento de Samples.
    Suporta criação, atualização, desativação (soft-delete) e exclusão (admin).
    """
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # =========================================================
    # 1. CREATE SAMPLE (Amostra com Coleção ou Avulsa)
    # =========================================================
    if action == "add_sample":
        with transaction.atomic():
            collection_id = request.POST.get("collection")
            biobank_id = request.POST.get("biobank")
            collection = None
            biobank = None

            # Se houver coleção, valida permissão nela
            if collection_id:
                collection = get_object_or_404(Collection, id=collection_id)
                if not can_edit_collection(user, collection):
                    raise PermissionDenied
                biobank = collection.biobank
            elif biobank_id:
                # Se for avulsa, vincula ao biobank selecionado
                biobank = get_object_or_404(Biobank, id=biobank_id)

            # Criando a amostra com os novos campos de Status e Visibilidade
            sample = Sample.objects.create(
                sample_id=request.POST.get("sample_id"),
                organism_name=request.POST.get("organism_name"),
                collection=collection,
                biobank=biobank,
                sample_type=request.POST.get("sample_type"),
                storage_location=request.POST.get("storage_location"),
                status=request.POST.get("status", "pending"),
                visibility=request.POST.get("visibility", "private"),
                notes=request.POST.get("notes"),
                owner=user,
                is_active=True,
            )

            # TAGS
            tag_ids = request.POST.getlist("tags")
            if tag_ids:
                sample.tags.set(Tag.objects.filter(id__in=tag_ids))

            # KEYWORDS (Padrão Chave:::Valor)
            for raw in request.POST.getlist("keyword_pairs"):
                if ":::" not in raw:
                    continue
                key, value = raw.split(":::")
                keyword_obj, _ = Keyword.objects.get_or_create(name=key.strip())
                kv, _ = KeywordValue.objects.get_or_create(
                    keyword=keyword_obj,
                    value=value.strip()
                )
                sample.keywords.add(kv)

            # FILES (Corrigido para não enviar file_type, que agora é automático)
            for index, f in enumerate(request.FILES.getlist("file")):
                SampleFile.objects.create(
                    sample=sample,
                    file=f,
                    description=request.POST.get(f"file_description_{index}", ""),
                    # Removido: file_type (o modelo detecta via save() agora)
                )

        messages.success(request, "Amostra criada com sucesso!")
        return redirect("/?page=samples")

    # =========================================================
    # 2. UPDATE SAMPLE COLLECTION
    # =========================================================
    elif action == "update_sample_collection":
        sample = get_object_or_404(Sample, id=request.POST.get("sample_id"))
        if not can_edit_sample(user, sample):
            raise PermissionDenied

        collection_id = request.POST.get("collection")
        if collection_id:
            collection = get_object_or_404(Collection, id=collection_id)
            if not can_edit_collection(user, collection):
                raise PermissionDenied
            sample.collection = collection
            sample.biobank = collection.biobank
        else:
            sample.collection = None

        sample.save()
        messages.success(request, "Vínculo da amostra atualizado!")
        return redirect("/?page=samples")

    # =========================================================
    # 3. DEACTIVATE / DELETE
    # =========================================================
    elif action in ["deactivate_sample", "delete_sample"]:
        sample = get_object_or_404(Sample, id=request.POST.get("sample_id"))
        
        if action == "deactivate_sample":
            if not can_edit_sample(user, sample): raise PermissionDenied
            sample.is_active = False
            sample.save(update_fields=["is_active"])
            messages.success(request, "Amostra desativada.")
        else:
            if not (user.is_superuser or user.is_staff): raise PermissionDenied
            sample.delete()
            messages.success(request, "Amostra removida permanentemente.")
            
        return redirect("/?page=samples")

    # =========================================================
    # 4. GET — LIST / FILTER / SEARCH
    # =========================================================
    ctx = base_context(request)
    
    # Queryset Base (Apenas ativas)
    samples_qs = Sample.objects.filter(is_active=True).select_related('collection', 'owner', 'biobank').order_by('-created_at')

    # Filtro por Coleção
    col_id = request.GET.get("collection")
    if col_id:
        samples_qs = samples_qs.filter(collection_id=col_id)
        ctx["selected_collection"] = Collection.objects.filter(id=col_id).first()

    # Busca Textual Otimizada
    search = (request.GET.get("squery") or "").strip()
    if search:
        samples_qs = samples_qs.filter(
            models.Q(sample_id__icontains=search) |
            models.Q(organism_name__icontains=search) |
            models.Q(keywords__value__icontains=search)
        ).distinct()

    # Filtro de permissão e injeção de flags para o template
    visible_samples = []
    for s in samples_qs:
        if can_view_sample(user, s):
            s.can_edit = can_edit_sample(user, s)
            s.can_delete = (user.is_superuser or user.is_staff)
            visible_samples.append(s)

    ctx["samples"] = visible_samples
    ctx["collections"] = Collection.objects.filter(is_active=True).order_by("name")
    ctx["biobanks"] = Biobank.objects.filter(is_active=True).order_by("name")
    ctx["all_tags"] = Tag.objects.all().order_by("name")

    return render(request, "internal/samples/samples.html", ctx)