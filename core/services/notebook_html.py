"""Safe HTML subset for the canonical Notebook (Quill) content.

The Notebook stores the editor's HTML in NotebookEntry.content and
renders it back into the page. Everything it stores or renders goes
through sanitize_notebook_html(), so a shared entry cannot carry
script into another user's browser.

The policy keeps what the Notebook itself produces: Quill formats
(headers, lists, links, colours, pasted images), the inserted tables,
protocol and timer blocks and molecular reference cards, including
their inline styles and data-notebook-* markers. It removes scripts,
event handlers, javascript:/data: links, CSS that can load or run
anything, and every tag or attribute not listed here.
"""

import re

import bleach


ALLOWED_TAGS = {
    "p", "br", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "b", "strong", "i", "em", "u", "s", "strike",
    "sub", "sup", "small", "mark",
    "blockquote", "pre", "code",
    "ul", "ol", "li",
    "a", "hr", "img",
    "table", "thead", "tbody", "tfoot",
    "tr", "th", "td", "caption", "colgroup", "col",
    "figure", "figcaption", "dl", "dt", "dd",
    "abbr", "cite", "q", "del", "ins",
}

GLOBAL_ATTRIBUTES = {"class", "style", "title", "contenteditable", "tabindex"}

TAG_ATTRIBUTES = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "th": {"colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start"},
}

CLASS_RE = re.compile(r"^[A-Za-z0-9_\- ]{0,300}$")
DATA_NAME_RE = re.compile(r"^data-[a-z0-9-]{1,40}$")
DATA_VALUE_RE = re.compile(r"^[\w .:/#@+\-]{0,200}$")
INTEGER_RE = re.compile(r"^-?\d{1,4}$")
DATA_IMAGE_RE = re.compile(
    r"^data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$",
    re.IGNORECASE,
)


def _allow_attribute(tag, name, value):
    if name.startswith("data-"):
        return bool(DATA_NAME_RE.match(name) and DATA_VALUE_RE.match(value))

    if name not in GLOBAL_ATTRIBUTES and name not in TAG_ATTRIBUTES.get(tag, ()):
        return False

    if name == "class":
        return bool(CLASS_RE.match(value))

    if name == "contenteditable":
        return value in {"true", "false"}

    if name in {"tabindex", "colspan", "rowspan", "span", "start", "width", "height"}:
        return bool(INTEGER_RE.match(value.strip()))

    if name == "target":
        return value in {"_blank", "_self"}

    if name == "href":
        return not value.strip().lower().startswith("data:")

    if name == "src":
        stripped = value.strip()
        if stripped.lower().startswith("data:"):
            return bool(DATA_IMAGE_RE.match(stripped))
        return True

    return True


ALLOWED_CSS_PROPERTIES = {
    "color", "background", "background-color",
    "border", "border-top", "border-right", "border-bottom", "border-left",
    "border-color", "border-style", "border-width",
    "border-collapse", "border-spacing", "border-radius",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "width", "min-width", "max-width", "height", "min-height", "max-height",
    "text-align", "text-decoration", "text-transform", "vertical-align",
    "font-weight", "font-style", "font-size", "font-family", "line-height",
    "white-space", "word-break", "overflow-wrap", "list-style-type",
    "display", "flex", "flex-direction", "flex-wrap", "flex-shrink",
    "flex-grow", "justify-content", "align-items", "gap",
}

ALLOWED_CSS_FUNCTIONS = {"rgb", "rgba", "hsl", "hsla", "calc"}

CSS_VALUE_RE = re.compile(r"^[#a-zA-Z0-9 .,%()+\-'\"/]*$")
CSS_FUNCTION_RE = re.compile(r"([a-zA-Z-]+)\s*\(")


class NotebookCssSanitizer:
    """Dependency-free stand-in for bleach's CSSSanitizer.

    Keeps declarations whose property is listed and whose value uses
    only plain characters and colour/calc functions. Anything with
    url(), expression(), escapes, comments or at-rules is dropped.
    """

    def sanitize_css(self, style):
        kept = []

        for declaration in style.split(";"):
            if ":" not in declaration:
                continue

            prop, value = declaration.split(":", 1)
            prop = prop.strip().lower()
            value = value.strip()

            if prop not in ALLOWED_CSS_PROPERTIES or not value:
                continue

            if len(value) > 200 or not CSS_VALUE_RE.match(value):
                continue

            functions = {
                name.lower() for name in CSS_FUNCTION_RE.findall(value)
            }
            if not functions <= ALLOWED_CSS_FUNCTIONS:
                continue

            kept.append(f"{prop}: {value}")

        return "; ".join(kept)


CLEANER = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=_allow_attribute,
    protocols={"http", "https", "mailto", "data"},
    css_sanitizer=NotebookCssSanitizer(),
    strip=True,
    strip_comments=True,
)


def sanitize_notebook_html(content):
    """Return the Notebook-safe version of editor HTML."""
    if not content:
        return ""

    if not isinstance(content, str):
        content = str(content)

    return CLEANER.clean(content)
