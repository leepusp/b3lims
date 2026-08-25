"""
Protected file delivery for Shipment documents.

Shipment FileField URLs are storage locators, not authorization
interfaces. Files from this module must only be returned after the
calling view has established access to the parent Shipment.
"""

from pathlib import Path

from django.http import FileResponse, Http404

from core.services.shipment_document_gate import (
    document_signed_file,
)


ALLOWED_SHIPMENT_FILE_KINDS = frozenset({
    "generated",
    "signed",
})


def shipment_document_file(document, file_kind):
    """
    Resolve an allowed Shipment document file.

    The caller supplies a closed file kind, never a filename or
    filesystem path.
    """
    if file_kind not in ALLOWED_SHIPMENT_FILE_KINDS:
        raise Http404("Unsupported Shipment document file type.")

    if file_kind == "generated":
        file_field = getattr(document, "generated_file", None)
    else:
        file_field = document_signed_file(document)

    if not file_field or not getattr(file_field, "name", ""):
        raise Http404("The requested Shipment document file is unavailable.")

    return file_field


def shipment_document_file_response(document, file_kind):
    """
    Open and return one protected Shipment document file.
    """
    file_field = shipment_document_file(
        document,
        file_kind,
    )

    try:
        file_field.open("rb")
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404(
            "The requested Shipment document file is unavailable."
        ) from exc

    filename = Path(file_field.name).name

    if not filename:
        file_field.close()
        raise Http404(
            "The requested Shipment document file is unavailable."
        )

    response = FileResponse(
        file_field,
        as_attachment=True,
        filename=filename,
    )

    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"

    return response
