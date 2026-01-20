import qrcode
import io
import base64
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
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
    View principal de Samples do CEBID B3.
    Gerencia a listagem e a criação de novas amostras com gatilho de impressão.
    """
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # =========================================================
    # 1. CREATE SAMPLE (Lógica de Inserção)
    # =========================================================
    if action == "add_sample":
        with transaction.atomic():
            collection_id = request.POST.get("collection")
            biobank_id = request.POST.get("biobank")
            collection = None
            biobank = None

            if collection_id:
                collection = get_object_or_404(Collection, id=collection_id)
                if not can_edit_collection(user, collection):
                    raise PermissionDenied
                biobank = collection.biobank
            elif biobank_id:
                biobank = get_object_or_404(Biobank, id=biobank_id)

            # Criando a amostra
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

            # Processamento de Tags
            tag_ids = request.POST.getlist("tags")
            if tag_ids:
                sample.tags.set(Tag.objects.filter(id__in=tag_ids))

            # Processamento de Keywords (Metadados)
            for raw in request.POST.getlist("keyword_pairs"):
                if ":::" not in raw: continue
                key, value = raw.split(":::")
                keyword_obj, _ = Keyword.objects.get_or_create(name=key.strip())
                kv, _ = KeywordValue.objects.get_or_create(
                    keyword=keyword_obj,
                    value=value.strip()
                )
                sample.keywords.add(kv)

            # Processamento de Arquivos (Attachments)
            files = request.FILES.getlist("files")
            for f in files:
                SampleFile.objects.create(sample=sample, file=f)

            # -------------------------------------------------------
            # GATILHO DE IMPRESSÃO:
            # Enviamos o ID da amostra recém-criada via messages
            # -------------------------------------------------------
            messages.success(
                request,
                str(sample.id),
                extra_tags="sample_created_id"
            )

            return redirect("/?page=samples")

    # =========================================================
    # 2. RENDERIZAÇÃO DA LISTAGEM (GET)
    # =========================================================
    ctx = base_context(request)

    # Filtros básicos para o Workspace
    ctx["samples"] = Sample.objects.filter(is_active=True).order_by("-created_at")
    ctx["collections"] = Collection.objects.all()
    ctx["all_tags"] = Tag.objects.all()
    ctx["biobanks"] = Biobank.objects.all()

    return render(request, "internal/samples/samples.html", ctx)


# =========================================================
# NOVA VIEW: GERAÇÃO FÍSICA DA ETIQUETA (QR CODE)
# =========================================================
@login_required
def print_sample_label(request, sample_id):
    """
    View que renderiza o PDF/HTML de impressão.
    """
    sample = get_object_or_404(Sample, id=sample_id)

    if not can_view_sample(request.user, sample):
        raise PermissionDenied

    # Gerar QR Code baseado no UUID único da USP/CEBID
    qr_data = str(sample.uuid)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Encode para Base64
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    ctx = {
        'sample': sample,
        'qr_code': qr_base64,
    }

    return render(request, "internal/samples/print_label.html", ctx)