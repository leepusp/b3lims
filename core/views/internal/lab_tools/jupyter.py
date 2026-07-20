"""Independent persistent Jupyter workspace views."""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone

from core.models.lab_tools.notebook import (
    JupyterKernelSession,
    JupyterNotebook,
)
from core.services.jupyter_notebooks import (
    JupyterNotebookError,
    normalize_notebook,
)
from core.services.jupyter_server import (
    ACTIVE_STATUSES,
    active_session_for_notebook,
    can_edit_notebook,
    connection_redirect_path,
    delete_notebook_workspace,
    load_notebook_document,
    refresh_session,
    start_session,
    starter_notebook,
    stop_session,
    visible_notebooks_for_user,
)


def _notebook_for_user(notebook_id, user):
    return get_object_or_404(
        visible_notebooks_for_user(user).select_related(
            "owner",
            "updated_by",
        ),
        pk=notebook_id,
    )


def _session_for_user(session_id, user):
    return get_object_or_404(
        JupyterKernelSession.objects.select_related(
            "notebook",
            "notebook__owner",
            "started_by",
        ).filter(
            notebook__in=visible_notebooks_for_user(user)
        ),
        pk=session_id,
    )


def _session_payload(session):
    if session is None:
        return None

    return {
        "id": session.id,
        "job_id": session.job_id,
        "run_id": session.run_id,
        "status": session.status,
        "partition": session.partition,
        "cpus": session.cpus,
        "memory_mb": session.memory_mb,
        "time_minutes": session.time_minutes,
        "ready": bool(
            session.status == "running"
            and session.ready_at is not None
        ),
        "summary": {
            "partition": session.partition,
            "official_server": True,
            "error": session.last_error,
        },
        "submitted_by": (
            session.started_by.get_username()
            if session.started_by
            else ""
        ),
        "submitted_at": session.submitted_at.isoformat(),
        "started_at": (
            session.started_at.isoformat()
            if session.started_at
            else None
        ),
        "ready_at": (
            session.ready_at.isoformat()
            if session.ready_at
            else None
        ),
        "expires_at": (
            session.expires_at.isoformat()
            if session.expires_at
            else None
        ),
        "finished_at": (
            session.finished_at.isoformat()
            if session.finished_at
            else None
        ),
    }


def _document_payload(notebook, user):
    latest_session = (
        notebook.sessions
        .select_related("started_by")
        .first()
    )

    return {
        "id": notebook.id,
        "title": notebook.title,
        "description": notebook.description,
        "notebook": notebook.notebook_json,
        "updated_at": notebook.updated_at.isoformat(),
        "can_edit": can_edit_notebook(user, notebook),
        "can_execute": can_edit_notebook(user, notebook),
        "latest_execution": _session_payload(latest_session),
    }


def _launch_defaults():
    default_minutes = int(
        getattr(
            settings,
            "BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES",
            60,
        )
    )

    return {
        "title": (
            "Jupyter analysis "
            f"{timezone.localtime():%Y-%m-%d %H:%M}"
        ),
        "partition": getattr(
            settings,
            "BIOBANK_JUPYTER_PARTITION",
            "basic",
        ),
        "cpus": int(
            getattr(
                settings,
                "BIOBANK_JUPYTER_DEFAULT_CPUS",
                2,
            )
        ),
        "memory_mb": int(
            getattr(
                settings,
                "BIOBANK_JUPYTER_DEFAULT_MEMORY_MB",
                8192,
            )
        ),
        "hours": max(1, default_minutes // 60),
    }


def _validated_launch(request, defaults):
    launch = {
        "title": str(
            request.POST.get("title")
            or defaults["title"]
        ).strip(),
        "partition": str(
            request.POST.get("partition")
            or defaults["partition"]
        ).strip(),
        "cpus": request.POST.get(
            "cpus",
            defaults["cpus"],
        ),
        "memory_mb": request.POST.get(
            "memory_mb",
            defaults["memory_mb"],
        ),
        "hours": request.POST.get(
            "hours",
            defaults["hours"],
        ),
    }

    try:
        launch["cpus"] = int(launch["cpus"])
        launch["memory_mb"] = int(
            launch["memory_mb"]
        )
        launch["hours"] = int(launch["hours"])
    except (TypeError, ValueError) as exc:
        raise JupyterNotebookError(
            "Invalid resource selection."
        ) from exc

    allowed_partitions = set(
        getattr(
            settings,
            "BIOBANK_JUPYTER_PARTITIONS",
            ("basic", "max50"),
        )
    )

    if not launch["title"]:
        raise JupyterNotebookError(
            "Notebook title is required."
        )
    if len(launch["title"]) > 255:
        raise JupyterNotebookError(
            "Notebook title is too long."
        )
    if launch["partition"] not in allowed_partitions:
        raise JupyterNotebookError(
            "Invalid Slurm partition."
        )
    if not 1 <= launch["cpus"] <= 128:
        raise JupyterNotebookError(
            "CPU cores must be between 1 and 128."
        )
    if not 1024 <= launch["memory_mb"] <= 1048576:
        raise JupyterNotebookError(
            "Memory must be between 1024 and "
            "1048576 MB."
        )
    if not 1 <= launch["hours"] <= 168:
        raise JupyterNotebookError(
            "Session duration must be between "
            "1 and 168 hours."
        )

    return launch


@login_required
def jupyter_index(request):
    notebooks = (
        visible_notebooks_for_user(request.user)
        .select_related("owner")
        .prefetch_related("sessions")
    )

    return render(
        request,
        "internal/lab_tools/jupyter_index.html",
        {
            "jupyter_notebooks": notebooks,
        },
    )


@login_required
def jupyter_launch(request):
    defaults = _launch_defaults()
    notebook_id = (
        request.POST.get("notebook_id")
        or request.GET.get("notebook_id")
    )

    existing_notebook = None
    if notebook_id:
        existing_notebook = _notebook_for_user(
            notebook_id,
            request.user,
        )
        defaults["title"] = existing_notebook.title

    if request.method == "GET":
        return render(
            request,
            "internal/lab_tools/jupyter_launch.html",
            {
                "launch": defaults,
                "existing_notebook": existing_notebook,
                "partitions": getattr(
                    settings,
                    "BIOBANK_JUPYTER_PARTITIONS",
                    ("basic", "max50"),
                ),
            },
        )

    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET or POST required.",
            },
            status=405,
        )

    try:
        launch = _validated_launch(
            request,
            defaults,
        )
    except JupyterNotebookError as exc:
        return render(
            request,
            "internal/lab_tools/jupyter_launch.html",
            {
                "launch": {
                    **defaults,
                    **request.POST.dict(),
                },
                "existing_notebook": existing_notebook,
                "partitions": getattr(
                    settings,
                    "BIOBANK_JUPYTER_PARTITIONS",
                    ("basic", "max50"),
                ),
                "launch_error": str(exc),
            },
            status=400,
        )

    created = False
    notebook = existing_notebook

    if notebook is None:
        notebook = JupyterNotebook.objects.create(
            title=launch["title"],
            owner=request.user,
            updated_by=request.user,
            notebook_json=starter_notebook(
                launch["title"],
                request.user.get_username(),
            ),
        )
        created = True
    else:
        notebook.title = launch["title"]
        notebook.updated_by = request.user
        notebook.save(
            update_fields=[
                "title",
                "updated_by",
                "updated_at",
            ]
        )

    try:
        existing_session = active_session_for_notebook(
            notebook
        )

        if existing_session:
            messages.info(
                request,
                "This notebook already has an active "
                "Slurm session.",
            )
        else:
            start_session(
                notebook,
                request.user,
                cpus=launch["cpus"],
                memory_mb=launch["memory_mb"],
                time_minutes=launch["hours"] * 60,
                partition=launch["partition"],
            )
            messages.success(
                request,
                "Persistent Jupyter session submitted "
                "to Slurm.",
            )
    except JupyterNotebookError as exc:
        if created and not notebook.sessions.exists():
            notebook.delete()

        return render(
            request,
            "internal/lab_tools/jupyter_launch.html",
            {
                "launch": launch,
                "existing_notebook": (
                    None if created else notebook
                ),
                "partitions": getattr(
                    settings,
                    "BIOBANK_JUPYTER_PARTITIONS",
                    ("basic", "max50"),
                ),
                "launch_error": str(exc),
            },
            status=400,
        )

    return redirect(
        "jupyter_workspace",
        notebook_id=notebook.id,
    )


@login_required
def jupyter_workspace(request, notebook_id):
    notebook = _notebook_for_user(
        notebook_id,
        request.user,
    )

    active_session = None
    session_error = ""

    try:
        active_session = active_session_for_notebook(
            notebook
        )
    except JupyterNotebookError as exc:
        session_error = str(exc)

    return render(
        request,
        "internal/lab_tools/jupyter_workspace.html",
        {
            "jupyter_notebook": notebook,
            "active_session": active_session,
            "session_error": session_error,
            "can_edit_jupyter": can_edit_notebook(
                request.user,
                notebook,
            ),
            "can_execute_jupyter": can_edit_notebook(
                request.user,
                notebook,
            ),
        },
    )


@login_required
def jupyter_connect(request, notebook_id):
    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET required.",
            },
            status=405,
        )

    notebook = _notebook_for_user(
        notebook_id,
        request.user,
    )

    try:
        session = active_session_for_notebook(
            notebook
        )

        if session is None:
            raise JupyterNotebookError(
                "This notebook has no active "
                "Slurm session."
            )

        redirect_path = connection_redirect_path(
            session
        )
    except JupyterNotebookError as exc:
        response = HttpResponse(
            str(exc),
            content_type="text/plain; charset=utf-8",
            status=409,
        )
        response["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, private"
        )
        response["Pragma"] = "no-cache"
        response["Referrer-Policy"] = "no-referrer"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    response = HttpResponseRedirect(
        redirect_path
    )
    response["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private"
    )
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"

    return response


@login_required
def jupyter_document_api(request, notebook_id):
    notebook = _notebook_for_user(
        notebook_id,
        request.user,
    )

    if request.method == "GET":
        return JsonResponse(
            {
                "status": "success",
                "document": _document_payload(
                    notebook,
                    request.user,
                ),
            }
        )

    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET or POST required.",
            },
            status=405,
        )

    if not can_edit_notebook(request.user, notebook):
        return JsonResponse(
            {
                "status": "error",
                "message": "Permission denied.",
            },
            status=403,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8") or "{}"
        )
        title = str(
            data.get("title")
            or notebook.title
        ).strip()

        if not title:
            raise JupyterNotebookError(
                "Notebook title is required."
            )
        if len(title) > 255:
            raise JupyterNotebookError(
                "Notebook title is too long."
            )

        notebook.title = title
        notebook.notebook_json = normalize_notebook(
            data.get("notebook")
        )
        notebook.updated_by = request.user
        notebook.save(
            update_fields=[
                "title",
                "notebook_json",
                "updated_by",
                "updated_at",
            ]
        )
    except (
        json.JSONDecodeError,
        JupyterNotebookError,
        TypeError,
        ValueError,
    ) as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "document": _document_payload(
                notebook,
                request.user,
            ),
        }
    )


@login_required
def jupyter_execute_api(request, notebook_id):
    _notebook_for_user(
        notebook_id,
        request.user,
    )

    return JsonResponse(
        {
            "status": "error",
            "message": (
                "Cell execution is handled by the "
                "official Jupyter Notebook server."
            ),
        },
        status=410,
    )


@login_required
def jupyter_session_status_api(request, session_id):
    if request.method != "GET":
        return JsonResponse(
            {
                "status": "error",
                "message": "GET required.",
            },
            status=405,
        )

    session = _session_for_user(
        session_id,
        request.user,
    )

    try:
        session = refresh_session(session)
    except JupyterNotebookError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "execution": _session_payload(session),
        }
    )


@login_required
def jupyter_session_stop_api(request, session_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST required.",
            },
            status=405,
        )

    session = _session_for_user(
        session_id,
        request.user,
    )

    try:
        session = stop_session(
            session,
            request.user,
        )
    except JupyterNotebookError as exc:
        return JsonResponse(
            {
                "status": "error",
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "success",
            "execution": _session_payload(session),
        }
    )


@login_required
def jupyter_download(request, notebook_id):
    notebook = _notebook_for_user(
        notebook_id,
        request.user,
    )

    payload = json.dumps(
        load_notebook_document(notebook),
        ensure_ascii=False,
        indent=2,
    )

    response = HttpResponse(
        payload,
        content_type="application/x-ipynb+json",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="'
        f'biobank-jupyter-{notebook.id}.ipynb"'
    )
    return response


@login_required
def jupyter_delete(request, notebook_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status": "error",
                "message": "POST required.",
            },
            status=405,
        )

    notebook = _notebook_for_user(
        notebook_id,
        request.user,
    )

    if not can_edit_notebook(
        request.user,
        notebook,
    ):
        return JsonResponse(
            {
                "status": "error",
                "message": "Permission denied.",
            },
            status=403,
        )

    active_sessions = list(
        notebook.sessions
        .filter(status__in=ACTIVE_STATUSES)
        .select_related(
            "notebook",
            "started_by",
        )
    )

    for session in active_sessions:
        try:
            stop_session(
                session,
                request.user,
            )
        except JupyterNotebookError as exc:
            messages.error(
                request,
                "The notebook was not deleted because "
                "its Slurm session could not be stopped: "
                f"{exc}",
            )
            return redirect(
                "jupyter_workspace",
                notebook_id=notebook.id,
            )

    deleted_title = notebook.title

    try:
        delete_notebook_workspace(notebook)
    except JupyterNotebookError as exc:
        messages.error(
            request,
            "The notebook record was preserved because "
            "its protected workspace could not be "
            f"removed: {exc}",
        )
        return redirect(
            "jupyter_workspace",
            notebook_id=notebook.id,
        )

    notebook.delete()

    messages.success(
        request,
        f'Jupyter notebook "{deleted_title}" was deleted.',
    )

    return redirect("jupyter_index")
