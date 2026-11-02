"""Safe HTML subset for private scientific ELN content."""

import bleach

from core.services.eln_private_drafts import DraftValidationError


MAX_RICH_CONTENT_BYTES = 512_000

ALLOWED_TAGS = {
    "p", "br", "div", "span",
    "h1", "h2", "h3", "h4",
    "b", "strong", "i", "em", "u", "s",
    "sub", "sup",
    "blockquote", "pre", "code",
    "ul", "ol", "li",
    "a", "hr",
    "table", "thead", "tbody", "tfoot",
    "tr", "th", "td", "caption",
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}

CLEANER = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    protocols={"http", "https", "mailto"},
    strip=True,
    strip_comments=True,
)


def sanitize_rich_content(content):
    if not isinstance(content, str):
        raise DraftValidationError(
            "Rich content must be text."
        )

    if len(content.encode("utf-8")) > MAX_RICH_CONTENT_BYTES:
        raise DraftValidationError(
            "Rich content exceeds the allowed size."
        )

    result = CLEANER.clean(content)

    if len(result.encode("utf-8")) > MAX_RICH_CONTENT_BYTES:
        raise DraftValidationError(
            "Sanitized content exceeds the allowed size."
        )

    return result
