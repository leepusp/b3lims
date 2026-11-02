"""Owner-scoped private ELN browser workflow."""

import re

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from core.permissions.eln_experimental import (
    can_access_eln_experimental,
    is_eln_experimental_enabled,
)
from core.permissions.samples import (
    can_view_sample,
    visible_samples_for_user,
)
from core.permissions.chemicals import (
    can_view_chemical,
    visible_chemicals_for_user,
)
from core.services.eln_private_drafts import (
    DraftConflict,
    DraftNotFound,
    DraftValidationError,
    PrivateDraftRepository,
    PROJECT_RE,
)
from core.services.lab_tools_storage import LabToolsStorageError
from core.services.eln_rich_content import sanitize_rich_content


MAX_CHOICES = 75


def _access(request):
    if not is_eln_experimental_enabled():
        raise Http404("ELN Experimental is disabled.")

    if (
        not request.user.is_active
        or not can_access_eln_experimental(request.user)
    ):
        raise PermissionDenied("ELN access is restricted.")


def _project(value):
    if (
        not isinstance(value, str)
        or not PROJECT_RE.fullmatch(value)
        or ".." in value
    ):
        raise DraftValidationError("Invalid project name.")

    return value


def _ids(request, key):
    raw = request.POST.getlist(key)

    if len(raw) > 100 or any(
        not re.fullmatch(r"[1-9][0-9]{0,17}", value)
        for value in raw
    ):
        raise DraftValidationError(
            "Invalid linked material IDs."
        )

    return list(dict.fromkeys(int(value) for value in raw))


def _authorized_links(user, sample_ids, chemical_ids):
    if sample_ids:
        records = list(
            visible_samples_for_user(user).filter(
                pk__in=sample_ids
            )
        )

        if (
            len(records) != len(sample_ids)
            or not all(
                can_view_sample(user, obj)
                for obj in records
            )
        ):
            return False

    if chemical_ids:
        records = list(
            visible_chemicals_for_user(user).filter(
                pk__in=chemical_ids
            )
        )

        if (
            len(records) != len(chemical_ids)
            or not all(
                can_view_chemical(user, obj)
                for obj in records
            )
        ):
            return False

    return True


def _values(request, project=None):
    content_format = request.POST.get(
        "content_format", "plain_text"
    )

    if content_format not in (
        "plain_text",
        "rich_html_v1",
    ):
        raise DraftValidationError(
            "Unsupported ELN content format."
        )

    return {
        "project": _project(
            project if project is not None
            else request.POST.get("project", "")
        ),
        "title": request.POST.get("title", ""),
        "content_format": content_format,
        "content": (
            sanitize_rich_content(
                request.POST.get("content", "")
            )
            if content_format == "rich_html_v1"
            else request.POST.get("content", "")
        ),
        "protocol": request.POST.get("protocol", ""),
        "results": request.POST.get("results", ""),
        "sample_ids": _ids(request, "sample_ids"),
        "chemical_ids": _ids(request, "chemical_ids"),
    }


def _choices(selected, queryset, filter_queryset):
    chosen = (
        list(queryset.filter(pk__in=selected))
        if selected else []
    )

    candidates = list(
        filter_queryset(queryset)
        .order_by("pk")[:MAX_CHOICES]
    )

    return list({
        obj.pk: obj
        for obj in candidates + chosen
    }.values())


def _editor(request, *, entry=None, values=None):
    values = values or {
        "project": "",
        "title": "",
        "content": "",
        "protocol": "",
        "results": "",
        "sample_ids": [],
        "chemical_ids": [],
    }

    values = dict(values)
    values.setdefault(
        "content_format", "plain_text"
    )

    if values["content_format"] == "rich_html_v1":
        values["content"] = sanitize_rich_content(
            values.get("content", "")
        )

    sample_q = request.GET.get(
        "sample_q", ""
    ).strip()[:80]

    chemical_q = request.GET.get(
        "chemical_q", ""
    ).strip()[:80]

    samples = _choices(
        values["sample_ids"],
        visible_samples_for_user(request.user),
        lambda qs: qs.filter(
            Q(sample_id__icontains=sample_q)
            | Q(organism_name__icontains=sample_q)
        ) if sample_q else qs,
    )

    chemicals = _choices(
        values["chemical_ids"],
        visible_chemicals_for_user(request.user),
        lambda qs: qs.filter(
            Q(name__icontains=chemical_q)
            | Q(lot_number__icontains=chemical_q)
        ) if chemical_q else qs,
    )

    action_url = (
        reverse(
            "eln_private_detail",
            kwargs={
                "project": entry["project"],
                "entry_id": entry["entry_id"],
            },
        )
        if entry
        else reverse("eln_private_new")
    )

    return render(
        request,
        "internal/lab_tools/eln_experimental/private_editor.html",
        {
            "entry": entry,
            "values": values,
            "samples": samples,
            "chemicals": chemicals,
            "sample_q": sample_q,
            "chemical_q": chemical_q,
            "action_url": action_url,
        },
    )


@login_required
@never_cache
@require_GET
def eln_private_drafts(request):
    _access(request)

    repository = PrivateDraftRepository()
    username = request.user.get_username()

    try:
        projects, _files = repository.storage.listdir(
            f"users/{username}/eln/projects"
        )
    except FileNotFoundError:
        projects = []

    entries = []

    for project in sorted(projects):
        if (
            not PROJECT_RE.fullmatch(project)
            or ".." in project
        ):
            continue

        entries.extend(
            repository.list_entries(
                request.user, project
            )
        )

    entries.sort(
        key=lambda obj: obj["saved_at"],
        reverse=True,
    )

    return render(
        request,
        "internal/lab_tools/eln_experimental/private_drafts.html",
        {
            "entries": entries[:200],
            "total_entries": len(entries),
        },
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def eln_private_new(request):
    _access(request)

    if request.method == "GET":
        return _editor(request)

    try:
        values = _values(request)

        entry = PrivateDraftRepository().create(
            request.user,
            values.pop("project"),
            material_authorizer=_authorized_links,
            **values,
        )

    except DraftValidationError as exc:
        return HttpResponse(str(exc), status=400)

    except PermissionDenied:
        raise

    except (DraftConflict, FileExistsError):
        return HttpResponse(
            "A revision conflict occurred.",
            status=409,
        )

    except LabToolsStorageError:
        return HttpResponse(
            "Private storage unavailable.",
            status=503,
        )

    return redirect(
        "eln_private_detail",
        project=entry["project"],
        entry_id=entry["entry_id"],
    )


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def eln_private_detail(request, project, entry_id):
    _access(request)

    try:
        project = _project(project)
    except DraftValidationError:
        raise Http404("Entry not found.")

    repository = PrivateDraftRepository()

    try:
        existing = repository.latest(
            request.user,
            project,
            str(entry_id),
        )

    except (DraftNotFound, DraftValidationError):
        raise Http404("Entry not found.")

    except LabToolsStorageError:
        return HttpResponse(
            "Private storage unavailable.",
            status=503,
        )

    if request.method == "GET":
        return _editor(
            request,
            entry=existing,
            values=existing,
        )

    try:
        values = _values(request, project=project)

        revision = request.POST.get(
            "expected_revision", ""
        )

        if not re.fullmatch(
            r"[1-9][0-9]{0,5}",
            revision,
        ):
            raise DraftValidationError(
                "Invalid revision identifier."
            )

        updated = repository.revise(
            request.user,
            project,
            str(entry_id),
            expected_revision=int(revision),
            material_authorizer=_authorized_links,
            title=values["title"],
            content=values["content"],
            content_format=values["content_format"],
            protocol=values["protocol"],
            results=values["results"],
            sample_ids=values["sample_ids"],
            chemical_ids=values["chemical_ids"],
        )

    except (DraftConflict, FileExistsError):
        return HttpResponse(
            "This entry has a newer revision. "
            "Reload before editing.",
            status=409,
        )

    except DraftValidationError as exc:
        return HttpResponse(str(exc), status=400)

    except PermissionDenied:
        raise

    except LabToolsStorageError:
        return HttpResponse(
            "Private storage unavailable.",
            status=503,
        )

    return redirect(
        "eln_private_detail",
        project=project,
        entry_id=updated["entry_id"],
    )
