"""Share Jupyter notebooks inside the biobank: read them and take a copy.

Sharing never hands out the owner's workspace: a kernel, the files and the execution stay with the owner. People
who can read a notebook may open it as text and "Use a copy", which creates an independent notebook of their own
(and the copy is the one they can run, link in a workflow and edit).
"""

from copy import deepcopy

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import CharField, Exists, OuterRef, Q
from django.db.models.functions import Cast
from django.utils import timezone

from core.models import ResearchGroup
from core.models.access_grants import ResourceAccessGrant
from core.models.lab_tools.notebook import JupyterNotebook
from core.services.resource_access import active_resource_grants, grant_resource_access, revoke_resource_access

VISIBILITIES = JupyterNotebook.VISIBILITY_CHOICES
MAX_CELLS_SHOWN = 200
MAX_SOURCE_CHARS = 20000


def _grants_for(user):
    content_type = ContentType.objects.get_for_model(JupyterNotebook, for_concrete_model=False)

    return (
        ResourceAccessGrant.objects.filter(
            content_type=content_type, object_id=Cast(OuterRef("pk"), CharField()), revoked_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .filter(Q(user=user) | Q(research_group__coordinator=user) | Q(research_group__members=user))
    )


def readable_notebooks_for_user(user):
    """Own notebooks plus what others shared: the lab's, or those granted to the user or their groups."""
    notebooks = JupyterNotebook.objects.filter(is_archived=False)

    if not user or not user.is_authenticated:
        return notebooks.none()
    if user.is_superuser:
        return notebooks

    return notebooks.filter(
        Q(owner=user) | Q(visibility="lab") | (Q(visibility="shared") & Exists(_grants_for(user)))
    ).distinct()


def shared_with_user(user):
    return readable_notebooks_for_user(user).exclude(owner=user).select_related("owner")


def can_manage(user, notebook) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or notebook.owner_id == user.pk))


def _require_manager(user, notebook):
    if not can_manage(user, notebook):
        raise PermissionDenied("Only the owner can change who a notebook is shared with.")


def grants(notebook):
    return active_resource_grants(notebook).select_related("user", "research_group").order_by("research_group__name", "user__username")


def grant_payload(grant):
    if grant.user_id:
        name, kind, detail = grant.user.get_full_name() or grant.user.get_username(), "user", grant.user.get_username()
    else:
        name, kind, detail = grant.research_group.name, "group", "Research group"

    return {"id": grant.pk, "kind": kind, "name": name, "detail": detail}


def sharing_state(notebook) -> dict:
    return {"visibility": notebook.visibility, "grants": [grant_payload(g) for g in grants(notebook)]}


def set_visibility(notebook, actor, value):
    _require_manager(actor, notebook)

    if value not in dict(VISIBILITIES):
        raise ValidationError("Choose a valid visibility.")

    notebook.visibility = value
    notebook.save(update_fields=["visibility"])

    return notebook


def share_with(notebook, actor, *, user=None, research_group=None):
    _require_manager(actor, notebook)

    if user is not None and (not user.is_active or user.pk == notebook.owner_id):
        raise ValidationError("Choose another active user.")

    grant = grant_resource_access(resource=notebook, access_level="view", granted_by=actor, user=user, research_group=research_group)

    if notebook.visibility == "private":
        notebook.visibility = "shared"
        notebook.save(update_fields=["visibility"])

    return grant


def unshare(notebook, actor, grant_id):
    _require_manager(actor, notebook)
    grant = active_resource_grants(notebook).filter(pk=grant_id).first()

    if grant is None:
        raise ValidationError("That access entry no longer exists.")

    return revoke_resource_access(grant=grant, revoked_by=actor)


def search_principals(notebook, query, limit=8):
    needle = (query or "").strip()

    if len(needle) < 2:
        return []

    users = (
        get_user_model().objects.filter(is_active=True).exclude(pk=notebook.owner_id)
        .filter(Q(username__icontains=needle) | Q(first_name__icontains=needle) | Q(last_name__icontains=needle))
        .order_by("username")[:limit]
    )
    groups = ResearchGroup.objects.filter(name__icontains=needle).order_by("name")[:limit]

    return [{"kind": "group", "principal_id": g.pk, "name": g.name, "detail": "Research group"} for g in groups] + [
        {"kind": "user", "principal_id": u.pk, "name": u.get_full_name() or u.get_username(), "detail": u.get_username()} for u in users
    ]


def readable_cells(notebook) -> list[dict]:
    """Cells as plain text for the read-only view (never executed, never rendered as HTML)."""
    cells = []

    for cell in (notebook.notebook_json or {}).get("cells", [])[:MAX_CELLS_SHOWN]:
        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else str(source)
        cells.append({"kind": "code" if cell.get("cell_type") == "code" else "text", "source": text[:MAX_SOURCE_CHARS]})

    return cells


def copy_notebook(notebook, user) -> JupyterNotebook:
    """An independent copy owned by ``user``: content only, no outputs, no sessions, not shared."""
    document = deepcopy(notebook.notebook_json or {})

    for cell in document.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"], cell["execution_count"] = [], None

    meta = document.setdefault("metadata", {}).setdefault("biobank", {})
    meta["owner"] = user.get_username()
    meta["copied_from"] = notebook.pk

    return JupyterNotebook.objects.create(
        title=f"{notebook.title} (copy)"[:255], description=notebook.description, owner=user, updated_by=user,
        notebook_json=document,
    )
