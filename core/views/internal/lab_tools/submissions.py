"""Data submission pages and JSON API."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.context import base_context
from core.models.lab_tools.submission import SubmissionPackage
from core.services import notebook_composer as composer
from core.services import submission_adapters as adapters
from core.services import submissions as service
from core.services import taxonomy_local
from core.services.workflow import visible_workflows

S = SubmissionPackage.Status
PAGE_SIZE = 25


def _payload(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Invalid JSON body.")

    if not isinstance(data, dict):
        raise ValidationError("Invalid JSON body.")

    return data


def _error(exc, status=400):
    messages = getattr(exc, "messages", None) or [str(exc)]

    return JsonResponse({"status": "error", "message": " ".join(messages)}, status=status)


@login_required
def submission_list(request):
    user = request.user
    tab = request.GET.get("tab") or "mine"
    q = (request.GET.get("q") or "").strip()
    taxon = (request.GET.get("taxon") or "").strip()
    qs = service.visible_packages(user).select_related("owner", "approved_by")

    if tab == "repository":
        rows = qs.filter(status=S.PUBLISHED, destination="internal")
    elif tab == "review" and service.can_approve(user):
        rows = qs.filter(status=S.PROPOSED)
    else:
        tab, rows = "mine", qs.filter(owner=user)

    if q:
        rows = rows.filter(title__icontains=q)

    rows = list(rows)

    if taxon.isdigit():
        rows = [p for p in rows if any(str(x.get("taxid")) == taxon for x in p.lineage)]

    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
    context = base_context(request)

    context.update({
        "page": page, "tab": tab, "q": q, "taxon": taxon,
        "can_review": service.can_approve(user),
        "review_count": qs.filter(status=S.PROPOSED).count() if service.can_approve(user) else 0,
        "destinations": SubmissionPackage.Destination.choices,
        "taxonomy_ready": taxonomy_local.available(),
    })

    return render(request, "internal/lab_tools/submission_list.html", context)


@login_required
@require_POST
def submission_create(request):
    title = (request.POST.get("title") or "").strip()[:200] or "Untitled package"
    destination = request.POST.get("destination")

    if destination not in SubmissionPackage.Destination.values:
        destination = "internal"

    package = SubmissionPackage.objects.create(title=title, destination=destination, owner=request.user)

    return redirect("submission_detail", package_id=package.pk)


@login_required
def submission_detail(request, package_id):
    package = get_object_or_404(service.visible_packages(request.user), pk=package_id)
    context = base_context(request)

    context.update({
        "package": package,
        "data": service.serialize(package, request.user),
        "manifest": service.manifest_json(package),
        "destinations": SubmissionPackage.Destination.choices,
        "taxonomy_ready": taxonomy_local.available(),
        "workflows": visible_workflows(package.owner).exclude(status="archived").order_by("name"),
        "sra": {
            "strategy": adapters.SRA_STRATEGY, "source": adapters.SRA_SOURCE, "selection": adapters.SRA_SELECTION,
            "layout": adapters.SRA_LAYOUT, "platform": adapters.SRA_PLATFORM,
        },
    })

    return render(request, "internal/lab_tools/submission_detail.html", context)


@login_required
@require_POST
def submission_api(request, package_id):
    user = request.user
    package = get_object_or_404(service.visible_packages(user), pk=package_id)

    try:
        data = _payload(request)
        action = data.get("action")
        related = 0

        if action in ("update", "add_item", "remove_item") and not service.can_edit(user, package):
            raise ValidationError("This package can no longer be edited.")

        if action == "update":
            service.update_fields(package, data)
            package.save()
        elif action == "add_item":
            item = service.add_item(package, user, data.get("kind"), data.get("ref"))

            if item.kind == "sample" and data.get("related", True):
                related = service.add_sample_related(package, user, item.sample)

                service.suggest_taxon(package)
                package.save()

        elif action == "remove_item":
            get_object_or_404(package.items, pk=data.get("item_id")).delete()
        elif action == "propose":
            service.propose(package, user)
        elif action == "approve":
            service.approve(package, user, data.get("note"))
        elif action == "reject":
            service.reject(package, user, data.get("note"))
        elif action == "publish":
            service.publish(package, user)
        elif action == "set_reference":
            service.set_reference(package, user, data.get("value"))
        elif action == "upload_zenodo":
            service.upload_zenodo(package, user)
        elif action == "delete":
            if not service.serialize(package, user)["can_delete"]:
                raise ValidationError("This package cannot be deleted.")

            package.delete()

            return JsonResponse({"status": "success", "deleted": True})
        else:
            raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return _error(exc)

    package.refresh_from_db()

    return JsonResponse({
        "status": "success", "related": related, "package": service.serialize(package, user),
        "manifest": service.manifest_json(package),
    })


@login_required
@require_GET
def submission_lookup_api(request):
    kind = request.GET.get("kind") or ""
    query = (request.GET.get("q") or "").strip()
    user = request.user

    if kind == "taxon":
        return JsonResponse({"results": [
            {"id": t["taxid"], "label": f"{t['name']} · {t['rank']} · taxid {t['taxid']}"} for t in taxonomy_local.search(query)
        ]})
    if kind == "entry":
        return JsonResponse({"results": composer.search_references("experiments", user, query)})
    if kind == "sample":
        return JsonResponse({"results": composer.search_references("items", user, query)})
    if kind == "notebook":
        from core.services.jupyter_server import visible_notebooks_for_user

        qs = visible_notebooks_for_user(user)

        if query:
            qs = qs.filter(title__icontains=query)

        return JsonResponse({"results": [{"id": n.pk, "label": n.title} for n in qs.order_by("title")[:15]]})
    if kind in ("sequence", "structure"):
        from core.models.lab_tools.notebook import MolecularStructure
        from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

        visible = _visible_molecular_sequences_for_user(user)

        if kind == "sequence":
            qs = visible.filter(name__icontains=query) if query else visible

            return JsonResponse({"results": [
                {"id": m.pk, "label": f"{m.name} · {m.get_sequence_type_display()}"} for m in qs.order_by("name")[:15]
            ]})

        qs = MolecularStructure.objects.filter(molecule__in=visible).select_related("molecule")

        if query:
            qs = qs.filter(molecule__name__icontains=query)

        return JsonResponse({"results": [
            {"id": s.pk, "label": f"{s.label or s.original_filename} · {s.molecule.name}"} for s in qs.order_by("-id")[:15]
        ]})

    raise Http404("Unknown lookup kind.")


