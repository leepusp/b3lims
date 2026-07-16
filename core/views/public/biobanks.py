from core.services.metadata_vocabularies import get_or_create_active_keyword_value
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import PermissionDenied

from ..context import base_context
from ..forms import BiobankForm

from core.models import (
    Biobank,
    BiobankUserRole,
    Tag,
    Keyword,
    KeywordValue,
)

from core.permissions.biobanks import (
    can_view_biobank,
    can_edit_biobank,
    can_manage_biobank_permissions,
)


def biobanks_view(request):

    user = request.user
    action = request.POST.get("action") if request.method == "POST" else None

    # =====================================================
    # CREATE BIOBANK
    # =====================================================
    if action == "add_biobank":

        if not user.is_authenticated:
            raise PermissionDenied

        form = BiobankForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():

                    # -------------------------------------------------
                    # 1) Criar Biobank
                    # -------------------------------------------------
                    biobank = form.save(commit=False)
                    biobank.owner = user   # 🔑 ESSENCIAL
                    biobank.save()

                    # Tags (M2M padrão)
                    form.save_m2m()

                    # -------------------------------------------------
                    # 2) OWNER automático (ACL)
                    # -------------------------------------------------
                    BiobankUserRole.objects.create(
                        user=user,
                        biobank=biobank,
                        role=BiobankUserRole.OWNER,
                    )

                    # -------------------------------------------------
                    # 3) KEYWORDS (M2M)
                    # -------------------------------------------------
                    pairs = request.POST.getlist("keyword_pairs")

                    for raw in pairs:
                        if ":::" not in raw:
                            continue

                        key, value = raw.split(":::")
                        key = key.strip()
                        value = value.strip()

                        if not key or not value:
                            continue

                        keyword_value, _ = (
                            get_or_create_active_keyword_value(
                                key,
                                value,
                            )
                        )

                        biobank.keywords.add(keyword_value)

                    messages.success(
                        request,
                        "Biobank created successfully!"
                    )
                    return redirect("/?page=biobanks")

            except Exception as e:
                messages.error(
                    request,
                    f"Error creating biobank: {e}"
                )
                return redirect("/?page=biobanks")

        else:
            messages.error(request, "Invalid data.")
            return redirect("/?page=biobanks")

    # =====================================================
    # DELETE BIOBANK
    # =====================================================
    elif action == "delete_biobank":

        bid = request.POST.get("id")
        biobank = get_object_or_404(Biobank, id=bid)

        if not can_manage_biobank_permissions(user, biobank):
            raise PermissionDenied

        biobank.delete()
        messages.success(request, "Biobank deleted successfully!")
        return redirect("/?page=biobanks")

    # =====================================================
    # CONTEXT / LISTAGEM (GET)
    # =====================================================
    ctx = base_context(request)
    ctx["biobank_form"] = BiobankForm()
    ctx["all_tags"] = (
        Tag.objects
        .filter(is_active=True)
        .order_by("name")
    )

    # -----------------------------------------------------
    # FILTRAR BIOBANKS POR PERMISSÃO
    # -----------------------------------------------------
    biobanks = [
        b for b in Biobank.objects.all().order_by("name")
        if can_view_biobank(user, b)
    ]

    # -----------------------------------------------------
    # FLAGS DE PERMISSÃO PARA TEMPLATE
    # -----------------------------------------------------
    for b in biobanks:
        b.can_edit = can_edit_biobank(user, b)
        b.can_manage_members = can_manage_biobank_permissions(user, b)

        # Membros (read-only)
        b.members_roles = (
            b.user_roles
            .select_related("user")
            .all()
        )

    ctx["biobanks"] = biobanks

    return render(
        request,
        "core/biobanks/biobanks.html",
        ctx
    )
