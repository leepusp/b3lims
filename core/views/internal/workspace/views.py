from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from core.context import base_context

# IMPORTANTE: Importe os modelos assim para evitar erros circulares durante o boot
from core.models.biobanks.biobank import Biobank
from core.models.collections.collection import Collection
from core.models.samples.sample import Sample
from core.models.events.model import Event

# Import do serviço
from core.services.benchling_service import BenchlingService

# Imports de Views (Certifique-se que esses arquivos existem nos novos caminhos)
from core.views.internal.biobanks.views import biobanks_view
from core.views.internal.collections.views import collections_view
from core.views.internal.samples.views import samples_view

# Imports de Tags e Keywords
from core.views.internal.tags.views import (
    tags_view, search_view, create_tag_view, edit_tag_view, delete_tag_view
)
from core.views.internal.keywords.views import (
    keywords_view, edit_keyword_view, delete_keyword_view
)

@login_required
def home(request):
    page = request.GET.get("page", "workspace")
    
    ROUTES = {
        "workspace": workspace_view,
        "biobanks": biobanks_view,
        "collections": collections_view,
        "samples": samples_view,
        "tags": tags_view,
        "search_tags": search_view,
        "add_tag": create_tag_view,
        "edit_tag": edit_tag_view,
        "delete_tag": delete_tag_view,
        "keywords": keywords_view,
        "edit_keyword": edit_keyword_view,
        "delete_keyword": delete_keyword_view,
        "sync_benchling": sync_benchling_view,
    }
    
    view_func = ROUTES.get(page, workspace_view)
    return view_func(request)

def workspace_view(request):
    ctx = base_context(request)
    ctx["stats"] = {
        "total_biobanks": Biobank.objects.filter(is_active=True).count(),
        "total_collections": Collection.objects.filter(is_active=True).count(),
        "total_samples": Sample.objects.filter(is_active=True).count(),
        "total_tags": len(ctx.get("all_tags", [])),
        "recent_activity": Event.objects.all().order_by("-timestamp")[:8]
    }
    return render(request, "internal/workspace/workspace.html", ctx)

def sync_benchling_view(request):
    """
    View de execução que utiliza o BenchlingService para espelhar dados na nuvem.
    """
    messages.info(request, "Iniciando comunicação com o Benchling SDK...")
    
    try:
        service = BenchlingService()
        # Selecionamos as últimas 5 amostras ativas para sincronizar
        samples_to_sync = Sample.objects.filter(is_active=True).order_by('-id')[:5]
        
        if not samples_to_sync.exists():
            messages.warning(request, "Nenhuma amostra disponível para sincronização.")
            return redirect("/?page=workspace")

        success_count = 0
        for sample in samples_to_sync:
            # Chama o método de criação de Custom Entity definido no seu serviço
            result_id = service.sync_sample_to_benchling(sample)
            if result_id:
                success_count += 1
        
        if success_count > 0:
            messages.success(request, f"Sucesso! {success_count} amostras foram espelhadas no Benchling Registry.")
        else:
            messages.error(request, "Falha na criação das entidades. Verifique os IDs de Schema e Registry no serviço.")

    except Exception as e:
        messages.error(request, f"Erro na integração: {str(e)}")
    
    return redirect("/?page=workspace")