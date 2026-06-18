from pathlib import Path
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


def classify_media_path(relative_path):
    path = relative_path.lower()
    suffix = Path(relative_path).suffix.lower()

    if path.startswith("shipment_documents/") or path.startswith("shipments/documents/"):
        return "shipment_document"
    if path.startswith("sample_imports/"):
        return "import_file"
    if suffix in {".pdb", ".cif", ".mmcif"}:
        return "structure"
    if suffix in {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".csv", ".tsv", ".xlsx", ".xls"}:
        return "table"
    if suffix in {".fasta", ".fa", ".gb", ".gbk", ".ape"}:
        return "sequence"
    return "raw"


def safe_relative_media_path(value):
    relative_path = Path(value)

    if relative_path.is_absolute():
        raise ValueError("Absolute paths are not allowed.")

    if ".." in relative_path.parts:
        raise ValueError("Parent directory traversal is not allowed.")

    absolute_path = (Path(settings.MEDIA_ROOT) / relative_path).resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()

    try:
        absolute_path.relative_to(media_root)
    except ValueError as exc:
        raise ValueError("File must be inside MEDIA_ROOT.") from exc

    if not absolute_path.exists():
        raise FileNotFoundError(f"File not found: {absolute_path}")

    if not absolute_path.is_file():
        raise ValueError(f"Path is not a file: {absolute_path}")

    return absolute_path, relative_path.as_posix()


def list_unlinked_media_files():
    media_root = Path(settings.MEDIA_ROOT)
    linked_files = set(
        SampleFile.objects.exclude(file="")
        .values_list("file", flat=True)
    )

    max_file_length = SampleFile._meta.get_field("file").max_length
    rows = []

    if not media_root.exists():
        return rows

    for path in sorted(media_root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(media_root).as_posix()

        if relative_path in linked_files:
            continue

        stat = path.stat()
        category = classify_media_path(relative_path)
        mime_type = mimetypes.guess_type(path.name)[0] or ""

        rows.append({
            "relative_path": relative_path,
            "category": category,
            "size_bytes": stat.st_size,
            "mime_type": mime_type,
            "linkable": len(relative_path) <= max_file_length,
            "path_length": len(relative_path),
            "max_length": max_file_length,
        })

    return rows


@login_required
def sample_file_curation_view(request):
    samples = Sample.objects.order_by("sample_id")
    categories = SampleFile._meta.get_field("category").choices

    if request.method == "POST":
        sample_pk = request.POST.get("sample")
        relative_path_input = request.POST.get("relative_path", "").strip()
        category = request.POST.get("category", "raw").strip() or "raw"
        description = request.POST.get("description", "").strip()

        try:
            sample = Sample.objects.get(pk=sample_pk)
            absolute_path, relative_path = safe_relative_media_path(relative_path_input)

            max_length = SampleFile._meta.get_field("file").max_length
            if len(relative_path) > max_length:
                raise ValueError(
                    f"Relative path is too long for SampleFile.file "
                    f"({len(relative_path)} > {max_length})."
                )

            stat = absolute_path.stat()

            sample_file, created = SampleFile.objects.get_or_create(
                sample=sample,
                file=relative_path,
                defaults={"description": description},
            )

            if description:
                sample_file.description = description

            sample_file.mime_type = mimetypes.guess_type(absolute_path.name)[0] or sample_file.mime_type
            sample_file.file_size = stat.st_size
            sample_file.category = category
            sample_file.save()

            # SampleFile.save() may auto-detect category from extension. Preserve manual curation.
            SampleFile.objects.filter(pk=sample_file.pk).update(category=category)

            action = "created" if created else "updated"
            messages.success(
                request,
                f"SampleFile link {action}: {sample.sample_id} -> {relative_path}",
            )

        except Exception as exc:
            messages.error(request, f"Could not link file: {exc}")

        return redirect(reverse("sample_file_curation"))

    selected_category = request.GET.get("category", "").strip()
    rows = list_unlinked_media_files()

    if selected_category:
        rows = [row for row in rows if row["category"] == selected_category]

    context = {
        "rows": rows,
        "samples": samples,
        "categories": categories,
        "selected_category": selected_category,
        "total_rows": len(rows),
        "media_root": settings.MEDIA_ROOT,
    }
    return render(request, "internal/samples/file_curation.html", context)
