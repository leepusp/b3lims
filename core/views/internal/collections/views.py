from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.forms import CollectionForm

from core.models import (
    Collection,
    Biobank,
    Tag,
    Keyword,
    KeywordValue,
)

from core.permissions.collections import (
    can_view_collection,
    can_edit_collection,
)

@login_required
def collections_list_view(request): # Nome alterado para bater com urls.py
    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # 1. CREATE COLLECTION
    if action == "add_collection":
        form = CollectionForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    collection = form.save(commit=False)
                    collection.owner = user
                    collection.is_active = True
                    collection.save()

                    # --- Lógica de Múltiplos Biobancos ---
                    bb_ids_raw = request.POST.get("biobanks_ids", "")
                    bb_ids = [bb_id for bb_id in bb_ids_raw.split(",") if bb_id.strip()]
                    
                    if bb_ids:
                        collection.biobanks.set(bb_ids)
                    
                    # --- Tags ---
                    selected_tags = request.POST.getlist("tags")
                    if selected_tags:
                        collection.tags.set(selected_tags)

                    # --- Keywords ---
                    pairs = request.POST.getlist("keyword_pairs")
                    for raw in pairs:
                        if ":::" not in raw: continue
                        key, value = raw.split(":::")
                        if key.strip() and value.strip():
                            keyword_obj, _ = Keyword.objects.get_or_create(name=key.strip())
                            kv, _ = KeywordValue.objects.get_or_create(keyword=keyword_obj, value=value.strip())
                            collection.keywords.add(kv)

                    messages.success(request, "Collection created successfully!")
                    return redirect("collections_list") # CORRIGIDO: Nome da rota

            except Exception as e:
                messages.error(request, f"Error creating Collection: {e}") # CORRIGIDO: Indentação
                return redirect("collections_list") # CORRIGIDO: Nome da rota
        else:
            errors = form.errors.as_text()
            messages.error(request, f"Invalid data: {errors}")
            return redirect("collections_list") # CORRIGIDO: Nome da rota

    # 2. DEACTIVATE
    elif action == "deactivate_collection":
        cid = request.POST.get("collection_id")
        collection = get_object_or_404(Collection, id=cid)
        
        if not can_edit_collection(user, collection):
            raise PermissionDenied
            
        collection.is_active = False
        collection.save(update_fields=["is_active"])
        messages.success(request, "Collection deactivated successfully.")
        return redirect("collections_list") # CORRIGIDO: Nome da rota

    # 3. LISTAGEM (GET)
    ctx = base_context(request)
    
    ctx["biobanks"] = Biobank.objects.filter(is_active=True).order_by("name")
    ctx["all_tags"] = Tag.objects.all().order_by("name")
    ctx["collection_form"] = CollectionForm()

    # Filtro opcional via URL
    biobank_id = request.GET.get("biobank")
    collections_qs = Collection.objects.filter(is_active=True)
    
    if biobank_id:
        collections_qs = collections_qs.filter(biobanks__id=biobank_id)

    visible_collections = []
    for c in collections_qs:
        if can_view_collection(user, c):
            c.can_edit = can_edit_collection(user, c)
            visible_collections.append(c)

    ctx["collections"] = visible_collections

    return render(request, "internal/collections/collections.html", ctx)
