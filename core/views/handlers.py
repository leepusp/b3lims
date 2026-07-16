from django.core.exceptions import PermissionDenied
from core.services.metadata_vocabularies import get_or_create_active_tag
# core/views/handlers.py

from django.contrib import messages
from django.shortcuts import redirect
from django.db import transaction
from django.contrib.auth.models import User

from core.models import (
    Biobank,
    Collection,
    Tag,
    Keyword,
    KeywordValue,
    CollectionUserRole,
)

from core.forms import BiobankForm, CollectionForm
from .permissions import get_collection_role


# ----------------------------------------------------------
# ADD BIOBANK
# ----------------------------------------------------------
def handle_add_biobank(request):
    form = BiobankForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Erro ao criar Biobank.")
        return redirect("/?page=biobanks")

    biobank = form.save()

    messages.success(request, "Biobank criado com sucesso!")
    return redirect("/?page=biobanks")


# ----------------------------------------------------------
# ADD COLLECTION
# ----------------------------------------------------------
def handle_add_collection(request):
    user = request.user
    form = CollectionForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Erro ao criar coleção.")
        return redirect("/?page=collections")

    with transaction.atomic():
        collection = form.save(commit=False)
        collection.save()

        # Tags selecionadas
        selected_tags = form.cleaned_data.get("tags") or []
        collection.tags.set(selected_tags)

        # Criar OWNER automaticamente
        CollectionUserRole.objects.get_or_create(
            user=user,
            collection=collection,
            defaults={"role": CollectionUserRole.OWNER},
        )

    messages.success(request, "Collection criada com sucesso!")
    return redirect("/?page=collections")


# ----------------------------------------------------------
# TAGS
# ----------------------------------------------------------
def handle_add_tag(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    name = request.POST.get("tag_name", "")
    description = request.POST.get("tag_description", "")

    tag, created = get_or_create_active_tag(
        name,
        description=description,
    )

    if not created and description.strip():
        tag.description = description.strip()
        tag.save(update_fields=["description"])

    messages.success(request, f"Tag '{tag.name}' was saved.")
    return redirect("tags_view")


def handle_delete_tag(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    tag = Tag.objects.filter(
        pk=request.POST.get("tag_id"),
        is_active=True,
    ).first()

    if tag is None:
        messages.error(request, "Active tag was not found.")
        return redirect("tags_view")

    tag.is_active = False
    tag.save(update_fields=["is_active"])

    messages.success(
        request,
        "Tag was deactivated. Existing associations were preserved.",
    )
    return redirect("tags_view")


# ----------------------------------------------------------
# PERMISSIONS
# ----------------------------------------------------------
def handle_add_role(request):
    collection_id = request.GET.get("collection_id")
    collection = Collection.objects.get(id=collection_id)

    role_obj = get_collection_role(request.user, collection)
    if not role_obj or role_obj.role != CollectionUserRole.OWNER:
        messages.error(request, "Sem permissão.")
        return redirect("/?page=collections")

    user_obj = User.objects.get(id=request.POST.get("user_id"))
    role = request.POST.get("role")

    CollectionUserRole.objects.update_or_create(
        user=user_obj,
        collection=collection,
        defaults={"role": role},
    )

    messages.success(request, "Permissão atribuída.")
    return redirect(f"/?page=collection_permissions&collection_id={collection_id}")


def handle_remove_role(request):
    role_id = request.POST.get("role_id")
    collection_id = request.GET.get("collection_id")

    CollectionUserRole.objects.filter(id=role_id).delete()
    messages.success(request, "Permissão removida.")

    return redirect(f"/?page=collection_permissions&collection_id={collection_id}")
