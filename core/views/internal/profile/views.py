from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User

from core.context import base_context

# Importamos os modelos principais
from core.models import Biobank, Collection
from core.models.research_groups.model import ResearchGroup

@login_required
def profile_view(request):
    user = request.user

    # ========================================================
    # 1. GESTÃO DE MEMBROS DO GRUPO (Apenas Coordenadores)
    # ========================================================
    if request.method == "POST":
        action = request.POST.get("action")
        group_id = request.POST.get("group_id")

        if group_id:
            group = get_object_or_404(ResearchGroup, id=group_id)

            # Trava de segurança: Apenas o coordenador do grupo pode modificar membros
            if group.coordinator == user:
                
                # ADICIONAR NOVO MEMBRO
                if action == "add_member":
                    email_or_username = request.POST.get("member_identifier", "").strip()
                    
                    # Tenta buscar o usuário pelo e-mail ou pelo username
                    new_member = User.objects.filter(email=email_or_username).first() or \
                                 User.objects.filter(username=email_or_username).first()

                    if new_member:
                        if new_member == user:
                            messages.warning(request, "You are already the coordinator of this group.")
                        else:
                            group.members.add(new_member)
                            messages.success(request, f"User {new_member.get_full_name() or new_member.username} added to the group successfully!")
                    else:
                        messages.error(request, "User not found. Please check the email or username.")

                # REMOVER MEMBRO EXISTENTE
                elif action == "remove_member":
                    member_id = request.POST.get("member_id")
                    if member_id:
                        member_to_remove = get_object_or_404(User, id=member_id)
                        group.members.remove(member_to_remove)
                        messages.success(request, "Member removed from the group.")
            else:
                messages.error(request, "Permission Denied: You are not the coordinator of this group.")

        return redirect("user_profile")  # Recarrega a página de perfil após a ação

    # ========================================================
    # 2. CARREGAMENTO DOS DADOS PARA A INTERFACE (GET)
    # ========================================================
    ctx = base_context(request)

    # Itens onde o usuário é dono direto
    ctx['user_biobanks'] = Biobank.objects.filter(owner=user)
    ctx['user_collections'] = Collection.objects.filter(owner=user)
    
    # Grupos de Pesquisa
    # A) Onde ele é o Coordenador (Mostra a aba de Gestão)
    ctx['coordinated_groups'] = ResearchGroup.objects.filter(coordinator=user).prefetch_related('members')
    
    # B) Onde ele é apenas um Membro (Mostra apenas quem são os colegas/coordenador)
    ctx['member_groups'] = user.research_groups.all().select_related('coordinator')
    
    return render(request, "internal/profile/profile.html", ctx)
