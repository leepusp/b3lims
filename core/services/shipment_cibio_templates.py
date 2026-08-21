from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True)
class CibioTemplate:
    key: str
    institution: str
    title: str
    description: str
    relative_path: str
    download_name: str
    content_type: str


CIBIO_TEMPLATE_ROOT = (
    Path(settings.BASE_DIR)
    / "docs"
    / "transport"
    / "source_templates"
    / "ogm_cibio"
)


CIBIO_TEMPLATES = {
    "bbams-gmo-transport-notification": CibioTemplate(
        key="bbams-gmo-transport-notification",
        institution="BBAMS",
        title="GMO Transport Notification Form",
        description=(
            "Current editable institutional reference available "
            "in Biobank."
        ),
        relative_path=(
            "BBAMS_FORMULÁRIO DE NOTIFICAÇÃO PARA TRANSPORTE "
            "DE OGMs.docx"
        ),
        download_name="BBAMS_GMO_Transport_Notification.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    ),
}


def cibio_template_catalog():
    return tuple(CIBIO_TEMPLATES.values())


def get_cibio_template(template_key):
    try:
        template = CIBIO_TEMPLATES[template_key]
    except KeyError as exc:
        raise KeyError("Unknown CIBio template.") from exc

    root = CIBIO_TEMPLATE_ROOT.resolve(strict=True)
    template_path = (
        CIBIO_TEMPLATE_ROOT
        / template.relative_path
    ).resolve(strict=True)

    if template_path.parent != root:
        raise ValueError(
            "CIBio template path escaped the approved template root."
        )

    if not template_path.is_file():
        raise FileNotFoundError(template_path)

    return template, template_path
