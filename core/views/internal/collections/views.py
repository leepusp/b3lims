from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.forms import CollectionForm

from core.models import (
    Collection,
    CollectionUserRole,
    Tag,
    Keyword,
    KeywordValue,
)

from core.permissions.collections import (
    can_view_collection,
    can_edit_collection,
    can_manage_collection_permissions,
)

@login_required
def collections_view(request):
    """
    View interna para gerenciamento de Collections.
    Suporta criação, desativação (soft-delete) e exclusão definitiva (admin).
    """
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # ============================================================
    # 1. CREATE COLLECTION
    # ============================================================
    if action == "add_collection":
        form = CollectionForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Salva a instância básica
                    collection = form.save(commit=False)
                    collection.owner = user
                    collection.is_active = True
                    collection.save()

                    # ACL: Define o criador como OWNER científico
                    CollectionUserRole.objects.create(
                        user=user,
                        collection=collection,
                        role=CollectionUserRole.OWNER
                    )

                    # Processamento de TAGS
                    selected_tags = request.POST.getlist("tags")
                    if selected_tags:
                        collection.tags.set(selected_tags)

                    # Processamento de KEYWORDS (Padrão Chave:::Valor)
                    pairs = request.POST.getlist("keyword_pairs")
                    for raw in pairs:
                        if ":::" not in raw:
                            continue

                        key, value = raw.split(":::")
                        key, value = key.strip(), value.strip()

                        if key and value:
                            keyword_obj, _ = Keyword.objects.get_or_create(name=key)
                            kv, _ = KeywordValue.objects.get_or_create(
                                keyword=keyword_obj,
                                value=value
                            )
                            collection.keywords.add(kv)

                    messages.success(request, "Collection criada com sucesso!")
                    return redirect("/?page=collections")

            except Exception as e:
                messages.error(request, f"Erro ao criar Collection: {e}")
                return redirect("/?page=collections")
        else:
            messages.error(request, "Dados inválidos no formulário.")
            return redirect("/?page=collections")

    # ============================================================
    # 2. DEACTIVATE COLLECTION (SOFT DELETE)
    # ============================================================
    elif action == "deactivate_collection":
        cid = request.POST.get("collection_id")
        collection = get_object_or_404(Collection, id=cid)

        if not can_manage_collection_permissions(user, collection):
            raise PermissionDenied

        collection.is_active = False
        collection.save(update_fields=["is_active"])

        messages.success(request, "Collection desativada com sucesso.")
        return redirect("/?page=collections")

    # ============================================================
    # 3. DELETE COLLECTION (HARD DELETE – ADMIN ONLY)
    # ============================================================
    elif action == "delete_collection":
        if not (user.is_superuser or user.is_staff):
            raise PermissionDenied

        cid = request.POST.get("collection_id")
        collection = get_object_or_404(Collection, id=cid)
        collection.delete()

        messages.success(request, "Collection removida permanentemente.")
        return redirect("/?page=collections")

    # ============================================================
    # 4. LISTAGEM E FORMULÁRIO (GET)
    # ============================================================
    initial = {}
    biobank_id = request.GET.get("biobank")
    if biobank_id:
        initial["biobank"] = biobank_id

    form = CollectionForm(initial=initial)

    # Base Context (Sidebar, User data, etc)
    ctx = base_context(request)
    ctx["collection_form"] = form
    ctx["all_tags"] = Tag.objects.all().order_by("name")
    
    # Suporte para tags recém-criadas via AJAX/Modal
    ctx["preselect_tag"] = request.session.pop("new_tag_id", None)

    # Filtragem de listagem (Apenas Ativas)
    collections_qs = Collection.objects.filter(is_active=True)
    if biobank_id:
        collections_qs = collections_qs.filter(biobank_id=biobank_id)

    visible_collections = []
    for c in collections_qs:
        if can_view_collection(user, c):
            c.can_edit = can_edit_collection(user, c)
            c.can_manage_members = can_manage_collection_permissions(user, c)
            
            # Otimização: Carrega papéis dos membros para exibição
            c.members_roles = c.user_roles.select_related("user").all()
            visible_collections.append(c)

    ctx["collections"] = visible_collections

    return render(request, "internal/collections/collections.html", ctx)