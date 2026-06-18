from pathlib import Path
import re


BIOBANK_ROOT = Path("/home/public/biobank")
BIOBANK_DATA_ROOT = BIOBANK_ROOT / "data"
BIOBANK_TEMPLATE_ROOT = BIOBANK_ROOT / "templates"
BIOBANK_EXPORT_ROOT = BIOBANK_ROOT / "exports"
BIOBANK_BACKUP_ROOT = BIOBANK_ROOT / "backups"
BIOBANK_LOG_ROOT = BIOBANK_ROOT / "logs"


def slugify_identifier(value, default="unassigned"):
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = value.strip("-._")
    return value or default


def get_group_slug_for_object(obj):
    """
    Tries to infer the group/lab namespace for samples or shipments.

    This is intentionally tolerant while the permission model is still evolving.
    """
    candidates = []

    for attr in ["group_slug", "lab_slug", "group", "lab"]:
        if hasattr(obj, attr):
            candidates.append(getattr(obj, attr, ""))

    biobank = getattr(obj, "biobank", None) or getattr(obj, "origin_biobank", None)

    if biobank is not None:
        for attr in ["slug", "name", "code"]:
            if hasattr(biobank, attr):
                candidates.append(getattr(biobank, attr, ""))

    requested_by = getattr(obj, "requested_by", None) or getattr(obj, "owner", None)

    if requested_by is not None:
        candidates.append(getattr(requested_by, "username", ""))

    for candidate in candidates:
        slug = slugify_identifier(candidate, default="")
        if slug:
            return slug

    return "unassigned"


def group_root(group_slug):
    return BIOBANK_DATA_ROOT / "groups" / slugify_identifier(group_slug)


def sample_root(sample):
    group_slug = get_group_slug_for_object(sample)
    sample_id = slugify_identifier(getattr(sample, "sample_id", sample.pk))
    return group_root(group_slug) / "samples" / sample_id


def shipment_root(shipment):
    group_slug = get_group_slug_for_object(shipment)
    shipment_code = slugify_identifier(getattr(shipment, "shipment_code", shipment.pk))
    return group_root(group_slug) / "shipments" / shipment_code


def shipment_documents_root(shipment):
    return shipment_root(shipment) / "documents"


def shipment_generated_documents_root(shipment):
    return shipment_documents_root(shipment) / "generated"


def shipment_signed_documents_root(shipment):
    return shipment_documents_root(shipment) / "signed"


def shipment_labels_root(shipment):
    return shipment_root(shipment) / "labels"


def ensure_path(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
