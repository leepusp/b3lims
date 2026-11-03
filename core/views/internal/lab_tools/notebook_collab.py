"""Revisions, comments, exclusive edit, file versions and todolist APIs (step 2.1)."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.models.lab_tools.notebook import NotebookAttachment
from core.models.lab_tools.notebook_collab import NotebookComment, NotebookRevision, NotebookTodo
from core.services import notebook_collab
from core.services.notebook_html import sanitize_notebook_html
from core.views.internal.lab_tools.notebook import _get_entry_for_user
from core.views.internal.lab_tools.notebook_dashboard import delete_attachment_files

MAX_COMMENT = 5000
MAX_TODOS = 200


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise ValidationError("Invalid request body.")
    if not isinstance(data, dict):
        raise ValidationError("Invalid request body.")
    return data


def _err(message, status=400):
    return JsonResponse({"status": "error", "message": str(message)}, status=status)


def _locked(exc):
    return JsonResponse({"status": "locked", "message": str(exc), "holder": exc.holder}, status=423)


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else "—"


def _stamp(value):
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ revisions

def _revision_row(rev):
    return {
        "id": rev.pk,
        "author": _name(rev.author),
        "at": _stamp(rev.updated_at),
        "title": rev.title,
        "chars": len(rev.content or ""),
    }


@login_required
@require_http_methods(["GET", "POST"])
def notebook_revisions_api(request, entry_id):
    """GET: list, or ``?id=N[&against=M]`` for a diff. POST ``{revision_id}``: restore."""
    if request.method == "GET":
        entry = _get_entry_for_user(entry_id, request.user)
        rev_id = request.GET.get("id")
        if not rev_id:
            return JsonResponse(
                {"status": "success", "revisions": [_revision_row(r) for r in entry.revisions.select_related("author")[:100]]}
            )
        rev = get_object_or_404(entry.revisions, pk=rev_id)
        against = request.GET.get("against")
        other = get_object_or_404(entry.revisions, pk=against).content if against else entry.content
        return JsonResponse(
            {
                "status": "success",
                "revision": _revision_row(rev),
                "against": against or "current",
                "diff": notebook_collab.diff_content(rev.content, other),
                "preview": sanitize_notebook_html(rev.content),
            }
        )

    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        notebook_collab.check_lock(entry, request.headers.get("X-Lock-Token"))
        rev = get_object_or_404(entry.revisions, pk=_body(request).get("revision_id"))
    except notebook_collab.LockedError as exc:
        return _locked(exc)
    except ValidationError as exc:
        return _err(exc)
    with transaction.atomic():
        previous = entry.content
        entry.content = sanitize_notebook_html(rev.content)
        entry.save(update_fields=["content", "updated_at"])
        notebook_collab.record_revision(entry, previous, request.user)
    return JsonResponse({"status": "success", "content": entry.content, "updated_at": _stamp(entry.updated_at)})


# ------------------------------------------------------------------- comments

def _comment_row(comment, user, entry):
    own = comment.author_id == user.pk
    return {
        "id": comment.pk,
        "author": _name(comment.author),
        "body": comment.body,
        "at": _stamp(comment.created_at),
        "edited": bool(comment.edited_at),
        "can_edit": own,
        "can_delete": own or user.is_superuser or entry.author_id == user.pk,
    }


@login_required
@require_http_methods(["GET", "POST"])
def notebook_comments_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user)
    if request.method == "GET":
        return JsonResponse(
            {"status": "success", "comments": [_comment_row(c, request.user, entry) for c in entry.comments.select_related("author")]}
        )
    try:
        data = _body(request)
        action = data.get("action")
        if action == "add":
            body = str(data.get("body") or "").strip()
            if not body:
                raise ValidationError("Write something first.")
            if len(body) > MAX_COMMENT:
                raise ValidationError(f"Comments are limited to {MAX_COMMENT} characters.")
            NotebookComment.objects.create(entry=entry, author=request.user, body=body)
        else:
            comment = get_object_or_404(entry.comments, pk=data.get("id"))
            if action == "edit":
                if comment.author_id != request.user.pk:
                    return _err("Only the author can edit a comment.", 403)
                body = str(data.get("body") or "").strip()
                if not body or len(body) > MAX_COMMENT:
                    raise ValidationError("Invalid comment.")
                comment.body, comment.edited_at = body, timezone.now()
                comment.save(update_fields=["body", "edited_at"])
            elif action == "delete":
                if not (comment.author_id == request.user.pk or request.user.is_superuser or entry.author_id == request.user.pk):
                    return _err("You cannot delete this comment.", 403)
                comment.delete()
            else:
                raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return _err(exc)
    return JsonResponse(
        {"status": "success", "comments": [_comment_row(c, request.user, entry) for c in entry.comments.select_related("author")]}
    )


# ------------------------------------------------------------- exclusive edit

@login_required
@require_POST
def notebook_lock_api(request, entry_id):
    """``{action: acquire|heartbeat|release, token, force?}``."""
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _body(request)
        token = str(data.get("token") or "")
        action = data.get("action")
        if action == "acquire":
            granted, info = notebook_collab.acquire_lock(entry, request.user, token, force=bool(data.get("force")))
            return JsonResponse({"status": "success", "granted": granted, **info})
        if action == "heartbeat":
            return JsonResponse({"status": "success", "granted": notebook_collab.heartbeat_lock(entry, token), **notebook_collab.lock_status(entry, token)})
        if action == "release":
            notebook_collab.release_lock(entry, token)
            return JsonResponse({"status": "success"})
        raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return _err(exc)


# -------------------------------------------------------------- file versions

@login_required
@require_POST
def notebook_file_replace_api(request, entry_id):
    """Upload a new version of a file. The previous one stays in the history."""
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    upload = request.FILES.get("file")
    if not upload:
        return _err("No file uploaded.")
    old = get_object_or_404(NotebookAttachment, pk=request.POST.get("attachment_id"), entry=entry, is_current=True)
    with transaction.atomic():
        new = NotebookAttachment.objects.create(
            entry=entry,
            file=upload,
            attachment_type="image" if (upload.content_type or "").startswith("image/") else old.attachment_type,
            caption=old.caption,
            uploaded_by=request.user,
            version=old.version + 1,
            previous=old,
        )
        NotebookAttachment.objects.filter(pk=old.pk).update(is_current=False)
        entry.save(update_fields=["updated_at"])
    return JsonResponse({"status": "success", "attachment_id": new.pk, "version": new.version})


@login_required
@require_POST
def notebook_file_caption_api(request, entry_id):
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        data = _body(request)
    except ValidationError as exc:
        return _err(exc)
    attachment = get_object_or_404(NotebookAttachment, pk=data.get("attachment_id"), entry=entry)
    attachment.caption = str(data.get("caption") or "").strip()[:255]
    attachment.save(update_fields=["caption"])
    return JsonResponse({"status": "success", "caption": attachment.caption})


@login_required
@require_POST
def notebook_file_delete_api(request, entry_id):
    """Remove a file with all its versions."""
    entry = _get_entry_for_user(entry_id, request.user, require_edit=True)
    try:
        notebook_collab.check_lock(entry, request.headers.get("X-Lock-Token"))
        data = _body(request)
    except notebook_collab.LockedError as exc:
        return _locked(exc)
    except ValidationError as exc:
        return _err(exc)
    current = get_object_or_404(NotebookAttachment, pk=data.get("attachment_id"), entry=entry, is_current=True)
    chain, seen, cursor = [], set(), current
    while cursor is not None and cursor.pk not in seen:
        chain.append(cursor)
        seen.add(cursor.pk)
        cursor = cursor.previous
    left = delete_attachment_files(chain)
    NotebookAttachment.objects.filter(pk__in=[a.pk for a in chain]).delete()
    entry.save(update_fields=["updated_at"])
    return JsonResponse({"status": "success", "removed": len(chain), "files_left_on_disk": left})


# ----------------------------------------------------------------- todolist

def _todo_rows(user):
    return [
        {
            "id": t.pk,
            "text": t.text,
            "done": t.done,
            "entry_id": t.entry_id,
            "entry_url": reverse("notebook_entry", args=[t.entry_id]) if t.entry_id else "",
        }
        for t in NotebookTodo.objects.filter(user=user).order_by("done", "id")[:MAX_TODOS]
    ]


@login_required
@require_http_methods(["GET", "POST"])
def notebook_todos_api(request):
    if request.method == "GET":
        return JsonResponse({"status": "success", "todos": _todo_rows(request.user)})
    try:
        data = _body(request)
        action = data.get("action")
        if action == "add":
            text = str(data.get("text") or "").strip()[:255]
            if not text:
                raise ValidationError("Write the task first.")
            if NotebookTodo.objects.filter(user=request.user).count() >= MAX_TODOS:
                raise ValidationError(f"At most {MAX_TODOS} tasks.")
            entry = None
            if data.get("entry_id"):
                entry = _get_entry_for_user(data["entry_id"], request.user)
            NotebookTodo.objects.create(user=request.user, text=text, entry=entry)
        elif action == "clear_done":
            NotebookTodo.objects.filter(user=request.user, done=True).delete()
        elif action in {"toggle", "delete"}:
            todo = get_object_or_404(NotebookTodo, pk=data.get("id"), user=request.user)
            if action == "toggle":
                todo.done = not todo.done
                todo.done_at = timezone.now() if todo.done else None
                todo.save(update_fields=["done", "done_at"])
            else:
                todo.delete()
        else:
            raise ValidationError("Unknown action.")
    except ValidationError as exc:
        return _err(exc)
    return JsonResponse({"status": "success", "todos": _todo_rows(request.user)})
