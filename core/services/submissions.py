"""Submission packages: access rules, review flow and serialisation."""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core.models.lab_tools.submission import SubmissionItem, SubmissionPackage
from core.services import repository, submission_adapters, submission_guides

S = SubmissionPackage.Status
MAX_TEXT = {"title": 200, "description": 5000, "review_note": 2000}
METADATA_KEYS = (
    "license", "authors", "keywords", "funding", "bioproject", "biosample", "sra_strategy", "sra_source",
    "sra_selection", "sra_layout", "sra_platform", "sra_instrument", "sra_reads",
)
METADATA_LIMITS = {"sra_reads": 6000}
APPROVE_PERM = "core.approve_submission"


def can_approve(user) -> bool:
    return bool(user.is_superuser or user.has_perm(APPROVE_PERM))


def is_owner(user, package) -> bool:
    return user.is_superuser or package.owner_id == user.pk


def visible_packages(user):
    """Own packages; published internal ones are the lab's shared repository; approvers see the review queue."""
    if user.is_superuser:
        return SubmissionPackage.objects.all()

    query = Q(owner=user) | Q(status=S.PUBLISHED, destination=SubmissionPackage.Destination.INTERNAL)

    if can_approve(user):
        query |= Q(status__in=[S.PROPOSED, S.APPROVED, S.REJECTED])

    return SubmissionPackage.objects.filter(query)


def can_edit(user, package) -> bool:
    return is_owner(user, package) and package.status in (S.DRAFT, S.REJECTED)


def _text(value, field, required=False) -> str:
    value = str(value or "").strip()

    if required and not value:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required.")
    if len(value) > MAX_TEXT[field]:
        raise ValidationError(f"{field.replace('_', ' ').capitalize()} is too long.")

    return value


def update_fields(package, data) -> None:
    if "title" in data:
        package.title = _text(data["title"], "title", required=True)
    if "description" in data:
        package.description = _text(data["description"], "description")
    if "destination" in data:
        if data["destination"] not in SubmissionPackage.Destination.values:
            raise ValidationError("Invalid destination.")

        package.destination = data["destination"]
    if "metadata" in data:
        raw = data["metadata"]

        if not isinstance(raw, dict):
            raise ValidationError("Invalid metadata.")

        package.metadata = {
            k: str(raw[k]).strip()[: METADATA_LIMITS.get(k, 1000)] for k in METADATA_KEYS if k in raw and str(raw[k]).strip()
        }
    if "workflow" in data:
        from core.services.workflow import visible_workflows

        wf = data["workflow"]

        package.workflow = visible_workflows(package.owner).filter(pk=wf).first() if wf else None

        if wf and not package.workflow:
            raise ValidationError("That workflow is not available.")
    if "taxon_id" in data:
        repository.set_taxon(package, data["taxon_id"])


# --- items ---------------------------------------------------------------------


def add_item(package, user, kind, ref) -> SubmissionItem:
    if package.items.count() >= repository.MAX_ITEMS:
        raise ValidationError(f"At most {repository.MAX_ITEMS} items per package.")

    try:
        ref = int(ref)
    except (TypeError, ValueError):
        raise ValidationError("Invalid item.")

    item = SubmissionItem(package=package, kind=kind)

    if kind == "sequence":
        from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

        obj = _visible_molecular_sequences_for_user(user).filter(pk=ref).first()
        item.molecule, item.label = obj, (f"{obj.name} · {obj.get_sequence_type_display()}" if obj else "")
    elif kind == "structure":
        from core.models.lab_tools.notebook import MolecularStructure
        from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

        visible = _visible_molecular_sequences_for_user(user)
        obj = MolecularStructure.objects.filter(pk=ref, molecule__in=visible).select_related("molecule").first()
        item.structure, item.label = obj, (f"{obj.label or obj.original_filename} · {obj.molecule.name}" if obj else "")
    elif kind == "sample":
        from core.permissions.samples import visible_samples_for_user

        obj = visible_samples_for_user(user).filter(pk=ref).first()
        item.sample, item.label = obj, (obj.sample_id if obj else "")
    elif kind == "entry":
        from core.permissions.notebook import visible_notebook_entries_for_user

        obj = visible_notebook_entries_for_user(user).filter(pk=ref).first()
        item.entry, item.label = obj, (obj.title if obj else "")
    elif kind == "notebook":
        from core.services.jupyter_server import visible_notebooks_for_user

        obj = visible_notebooks_for_user(user).filter(pk=ref).first()
        item.jupyter_notebook, item.label = obj, (obj.title if obj else "")
    else:
        raise ValidationError("Invalid item type.")

    if not obj:
        raise ValidationError("That record is not available to you.")
    if package.items.filter(**{{"sequence": "molecule", "notebook": "jupyter_notebook"}.get(kind, kind): obj}).exists():
        raise ValidationError("That record is already in the package.")

    item.save()

    return item


# --- review flow ---------------------------------------------------------------


def propose(package, user) -> None:
    if not can_edit(user, package):
        raise ValidationError("Only the owner can propose a draft or a rejected package.")
    problems = submission_adapters.validate(package)["errors"]

    if problems:
        raise ValidationError(problems)

    package.status = S.PROPOSED
    package.proposed_at = timezone.now()
    package.review_note = ""
    package.save(update_fields=["status", "proposed_at", "review_note", "updated_at"])


def _reviewable(package, user) -> None:
    if package.status != S.PROPOSED:
        raise ValidationError("Only proposed packages can be reviewed.")
    if not can_approve(user):
        raise ValidationError("You are not allowed to approve submissions.")
    if package.owner_id == user.pk and not user.is_superuser:
        raise ValidationError("You cannot approve your own package.")


def approve(package, user, note="") -> None:
    _reviewable(package, user)

    package.status = S.APPROVED
    package.approved_by = user
    package.approved_at = timezone.now()
    package.review_note = _text(note, "review_note")
    package.save(update_fields=["status", "approved_by", "approved_at", "review_note", "updated_at"])


def reject(package, user, note) -> None:
    _reviewable(package, user)

    package.status = S.REJECTED
    package.review_note = _text(note, "review_note", required=True)
    package.save(update_fields=["status", "review_note", "updated_at"])


def publish(package, user) -> str:
    if not (is_owner(user, package) or can_approve(user)):
        raise ValidationError("You cannot publish this package.")

    return repository.publish_package(package)


def set_reference(package, user, value) -> None:
    """Record the accession, PDB id or DOI the destination gave back."""
    if not (is_owner(user, package) or can_approve(user)):
        raise ValidationError("You cannot change this package.")
    if package.status != S.PUBLISHED:
        raise ValidationError("Publish the package first.")

    package.external_reference = str(value or "").strip()[:300]
    package.save(update_fields=["external_reference", "updated_at"])


def upload_zenodo(package, user) -> str:
    """Create a Zenodo draft with the exported files. The draft is never published here."""
    if not (is_owner(user, package) or can_approve(user)):
        raise ValidationError("You cannot upload this package.")
    if package.destination != SubmissionPackage.Destination.ZENODO or package.status != S.PUBLISHED:
        raise ValidationError("Only published Zenodo packages can be uploaded.")
    if package.external_reference:
        raise ValidationError("This package already has a reference; create a new package for a new upload.")

    base = (repository.repository_root() / package.repository_path).resolve()
    files = {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}
    url = submission_adapters.upload_zenodo_draft(package, files)

    package.external_reference = url
    package.save(update_fields=["external_reference", "updated_at"])

    return url


# --- serialisation -------------------------------------------------------------


def _url(name, pk) -> str:
    try:
        return reverse(name, args=[pk])
    except NoReverseMatch:
        return ""


def serialize(package, user) -> dict:
    validation = submission_adapters.validate(package)
    items = []

    for item in package.items.select_related("molecule", "structure", "sample", "entry", "jupyter_notebook"):
        url = ""

        if item.molecule_id:
            url = _url("molecular_sequence_detail", item.molecule_id)
        elif item.structure_id:
            url = _url("molecular_sequence_detail", item.structure.molecule_id)
        elif item.sample_id:
            url = _url("sample_detail", item.sample_id)
        elif item.entry_id:
            url = _url("notebook_entry", item.entry_id)
        elif item.jupyter_notebook_id:
            url = _url("jupyter_workspace", item.jupyter_notebook_id)

        items.append({"id": item.pk, "kind": item.kind, "kind_label": item.get_kind_display(), "label": item.label, "url": url})

    return {
        "id": package.pk,
        "title": package.title,
        "description": package.description,
        "destination": package.destination,
        "status": package.status,
        "owner": package.owner.get_username(),
        "workflow": package.workflow_id,
        "taxon_id": package.taxon_id,
        "taxon_name": package.taxon_name,
        "taxonomy_version": package.taxonomy_version,
        "lineage": package.lineage,
        "metadata": package.metadata,
        "review_note": package.review_note,
        "approved_by": package.approved_by.get_username() if package.approved_by else "",
        "approved_at": package.approved_at.isoformat(timespec="seconds") if package.approved_at else "",
        "repository_path": package.repository_path,
        "manifest_sha256": package.manifest_sha256,
        "external_reference": package.external_reference,
        "validation": validation,
        "guide": submission_guides.guide(package, validation),
        "can_upload_zenodo": (
            package.status == S.PUBLISHED and package.destination == "zenodo" and not package.external_reference
            and submission_adapters.zenodo_configured() and (is_owner(user, package) or can_approve(user))
        ),
        "can_set_reference": package.status == S.PUBLISHED and (is_owner(user, package) or can_approve(user)),
        "items": items,
        "can_edit": can_edit(user, package),
        "can_review": package.status == S.PROPOSED and can_approve(user) and (package.owner_id != user.pk or user.is_superuser),
        "can_publish": package.status == S.APPROVED and (is_owner(user, package) or can_approve(user)),
        "can_delete": is_owner(user, package) and package.status in (S.DRAFT, S.REJECTED),
    }


def manifest_json(package) -> str:
    """The published manifest, when there is one on disk."""
    if not package.repository_path:
        return ""

    path = repository.repository_root() / package.repository_path / "manifest.json"

    try:
        return json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False)
    except (OSError, ValueError):
        return ""


def add_sample_related(package, user, sample) -> int:
    """Also add what hangs on a sample: its molecular records and the ELN entries linked to it.

    Only records the user may see are added; duplicates and the item limit are skipped quietly.
    Returns how many records were added.
    """
    from core.models.lab_tools.notebook import NotebookSampleLink
    from core.permissions.notebook import visible_notebook_entries_for_user
    from core.views.internal.lab_tools.notebook import _visible_molecular_sequences_for_user

    added = 0
    molecules = _visible_molecular_sequences_for_user(user).filter(linked_sample=sample).order_by("name")
    entry_ids = NotebookSampleLink.objects.filter(entry__in=visible_notebook_entries_for_user(user), sample=sample)
    entries = visible_notebook_entries_for_user(user).filter(pk__in=entry_ids.values("entry_id")).order_by("title")

    for kind, queryset in (("sequence", molecules), ("entry", entries)):
        for obj in queryset[:50]:
            try:
                add_item(package, user, kind, obj.pk)
                added += 1
            except ValidationError:
                continue

    return added


def suggest_taxon(package) -> None:
    """Set the taxon when every sample of the package names the same organism and the taxonomy knows it exactly."""
    from core.services import taxonomy_local

    if package.taxon_id or not taxonomy_local.available():
        return

    names = {
        (i.sample.organism_name or "").strip().lower() for i in package.items.filter(kind="sample").select_related("sample")
        if i.sample
    } - {""}

    if len(names) != 1:
        return

    name = names.pop()
    exact = [r for r in taxonomy_local.search(name, limit=20) if r["name"].lower() == name]

    if len(exact) == 1:
        repository.set_taxon(package, exact[0]["taxid"])
        package.save()


def create_from_workflow(workflow, user, destination) -> SubmissionPackage:
    """A draft package holding the records the workflow's steps point to (only those the user may see)."""
    from core.services.workflow import can_edit as can_edit_workflow

    if destination not in SubmissionPackage.Destination.values:
        raise ValidationError("Invalid destination.")
    if not can_edit_workflow(user, workflow):
        raise ValidationError("You cannot edit this workflow.")

    label = SubmissionPackage.Destination(destination).label.split(" (")[0]
    package = SubmissionPackage.objects.create(
        title=f"{workflow.name} - {label}"[:200], destination=destination, owner=user, workflow=workflow
    )
    wanted = []

    if workflow.entry_id:
        wanted.append(("entry", workflow.entry_id))

    for step in workflow.steps.exclude(kind="note").order_by("y", "x", "id"):
        if step.molecule_id:
            wanted.append(("sequence", step.molecule_id))
        if step.sample_id:
            wanted.append(("sample", step.sample_id))
        if step.entry_id:
            wanted.append(("entry", step.entry_id))
        if (step.config or {}).get("notebook_id"):
            wanted.append(("notebook", step.config["notebook_id"]))

    seen = set()

    for kind, ref in wanted:
        if (kind, ref) in seen:
            continue

        seen.add((kind, ref))

        try:
            item = add_item(package, user, kind, ref)
        except ValidationError:
            continue  # not visible to this user, or limit reached: leave it out

        if kind == "sample":
            add_sample_related(package, user, item.sample)

    suggest_taxon(package)

    return package
