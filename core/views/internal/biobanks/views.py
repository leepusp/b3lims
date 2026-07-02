from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

from core.context import base_context
from core.forms import BiobankForm

from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.tags.model import Tag
from core.models.keywords.model import Keyword, KeywordValue
from core.permissions.biobanks import can_edit_biobank, can_manage_biobank_permissions, visible_biobanks_for_user

@login_required
def biobanks_list_view(request): 
    user = request.user
    action = request.POST.get("action")

    # 1. ACTION: ADD BIOBANK
    if request.method == "POST" and action == "add_biobank":
        form = BiobankForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid biobank data.")
            return redirect("biobanks_list") 

        try:
            with transaction.atomic():
                biobank = form.save(commit=False)
                biobank.owner = user
                biobank.is_active = True
                biobank.save()

                BiobankUserRole.objects.get_or_create(
                    user=user,
                    biobank=biobank,
                    defaults={"role": BiobankUserRole.OWNER},
                )

                tag_ids = request.POST.getlist("tags")
                if tag_ids: biobank.tags.set(tag_ids)

                for raw in request.POST.getlist("keyword_pairs"):
                    if ":::" not in raw: continue
                    key, value = map(str.strip, raw.split(":::"))
                    
                    if not key or not value: continue 
                    
                    keyword_obj, _ = Keyword.objects.get_or_create(name=key)
                    kv, _ = KeywordValue.objects.get_or_create(keyword=keyword_obj, value=value)
                    biobank.keywords.add(kv)

                messages.success(request, "Biobank created successfully!")
        except Exception as e:
            messages.error(request, f"Error creating biobank: {e}")
        return redirect("biobanks_list") 

    # 2. ACTION: DEACTIVATE BIOBANK
    if request.method == "POST" and action == "deactivate_biobank":
        bb_id = request.POST.get("biobank_id")
        biobank = get_object_or_404(Biobank, id=bb_id)
        
        if not can_edit_biobank(user, biobank):
            raise PermissionDenied
            
        biobank.is_active = False
        biobank.save(update_fields=["is_active"])
        messages.success(request, "Biobank deactivated successfully.")
        return redirect("biobanks_list") 

    # 3. ACTION: PERMANENT DELETE (Administrative only)
    if request.method == "POST" and action == "delete_biobank":
        if not (user.is_superuser or user.is_staff):
            raise PermissionDenied
            
        bb_id = request.POST.get("biobank_id")
        biobank = get_object_or_404(Biobank, id=bb_id)
        biobank.delete()
        messages.success(request, "Biobank permanently deleted.")
        return redirect("biobanks_list") 

    # 4. VIEW LOGIC (GET)
    ctx = base_context(request)
    ctx["biobank_form"] = BiobankForm()
    ctx["all_tags"] = Tag.objects.all().order_by("name")

    visible_biobanks = list(visible_biobanks_for_user(user).order_by("name"))

    for b in visible_biobanks:
        b.can_edit = can_edit_biobank(user, b)
        b.can_manage_members = can_manage_biobank_permissions(user, b)

    ctx["biobanks"] = visible_biobanks
    
    return render(request, "internal/biobanks/biobanks.html", ctx)
