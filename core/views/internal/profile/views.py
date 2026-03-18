from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from core.context import base_context

# Importamos diretamente os modelos principais
from core.models import Biobank, Collection

@login_required
def profile_view(request):
    user = request.user
    ctx = base_context(request)

    # Buscamos apenas os itens onde o usuário é dono (a nova lógica simplificada)
    user_biobanks = Biobank.objects.filter(owner=user)
    user_collections = Collection.objects.filter(owner=user)

    # Atualizamos o contexto
    ctx['user_biobanks'] = user_biobanks
    ctx['user_collections'] = user_collections
    
    return render(request, "internal/profile/profile.html", ctx)
