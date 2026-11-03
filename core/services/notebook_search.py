"""Advanced search for Notebook entries.

Query language (case-insensitive keywords, implicit AND between terms)::

    title:gel and status:completed
    tag:pcr or tag:cloning
    author:ana -status:draft            # leading "-" or "not" negates a term
    (tag:pcr or tag:qpcr) and rating>=3
    "gel electrophoresis"                # quoted phrase, free text
    extrafield:Medium:TSB                # extra field "Medium" contains "TSB"
    date>=2026-01-01 date<=2026-03-31    # experiment date
    has:files  has:comments  has:steps

A query with no structured syntax at all (plain words) keeps the legacy
behaviour: one substring matched against title, custom ID, project, text and tags.
"""

import re
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone


class SearchSyntaxError(ValueError):
    pass


FIELDS = {
    "title": "text",
    "body": "text",
    "text": "text",
    "id": "id",
    "customid": "text",
    "custom_id": "text",
    "project": "text",
    "tag": "tag",
    "status": "choice",
    "type": "choice",
    "category": "choice",
    "visibility": "choice",
    "author": "author",
    "owner": "author",
    "rating": "number",
    "date": "date",
    "created": "datetime",
    "modified": "datetime",
    "step": "text",
    "comment": "text",
    "file": "text",
    "has": "has",
    "extrafield": "extrafield",
}

HELP_ROWS = [
    ("title:gel", "Title contains “gel”"),
    ("body:agarose", "Text of the entry contains “agarose”"),
    ("tag:pcr", "Has the tag #pcr"),
    ("status:completed", "Status is draft, in_progress, completed, reviewed or archived"),
    ("type:protocol", "Entry type"),
    ("author:ana", "Written by a user whose name, username or e-mail contains “ana”"),
    ("rating>=3", "Rating (also <=, >, <, =)"),
    ("date>=2026-01-01", "Experiment date (also created: and modified:)"),
    ("has:files", "Has files, comments or steps (has:files, has:comments, has:steps)"),
    ("step:centrifuge", "A step, comment: or file: contains the text"),
    ("extrafield:Medium:TSB", "Extra field “Medium” contains “TSB”"),
    ("a and b, a or b, -a, (a or b) and c", "Combine terms; “not” is the same as “-”"),
]

_TOKEN_RE = re.compile(
    r"""
    \s*(
        \(|\)
      | "(?:[^"\\]|\\.)*"
      | [^\s()"]+(?:"(?:[^"\\]|\\.)*")?
    )
    """,
    re.VERBOSE,
)

_OPS = ("<=", ">=", "<", ">", "=", ":")
_STATUSES = None


def _tokenize(text):
    tokens, pos = [], 0
    text = text.strip()
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise SearchSyntaxError("Unbalanced quote in the search.")
        tokens.append(match.group(1))
        pos = match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return tokens


def _unquote(value):
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return re.sub(r"\\(.)", r"\1", value[1:-1])
    return value


def has_structured_syntax(text):
    """True when the query uses fields, operators, parentheses or negation."""
    for token in _tokenize(text):
        low = token.lower()
        if token in "()" or low in ("and", "or", "not"):
            return True
        if token.startswith("-") and len(token) > 1:
            return True
        if token.startswith('"'):
            continue
        name = re.split(r"<=|>=|<|>|=|:", token, maxsplit=1)[0].lower()
        if name in FIELDS and name != token.lower():
            return True
    return False


def _split_term(token):
    """Return (field, op, value) or (None, None, text) for free text."""
    if token.startswith('"'):
        return None, None, _unquote(token)
    match = re.match(r"([A-Za-z_]+)(<=|>=|<|>|=|:)(.*)$", token, re.S)
    if match and match.group(1).lower() in FIELDS:
        return match.group(1).lower(), match.group(2), _unquote(match.group(3))
    return None, None, token


def free_text_q(text):
    condition = (
        Q(title__icontains=text)
        | Q(custom_id__icontains=text)
        | Q(project__icontains=text)
        | Q(content__icontains=text)
        | Q(tags__name__icontains=text.lstrip("#"))
    )
    if text.lstrip("#").isdigit():
        condition |= Q(pk=int(text.lstrip("#")))
    return condition


def _compare(lookup, op, value):
    suffix = {"<=": "__lte", ">=": "__gte", "<": "__lt", ">": "__gt", "=": "", ":": ""}[op]
    return Q(**{lookup + suffix: value})


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SearchSyntaxError(f"“{value}” is not a date; use YYYY-MM-DD.")


def _term_q(field, op, value):
    kind = FIELDS[field]
    if value == "" and kind != "has":
        raise SearchSyntaxError(f"“{field}” needs a value.")

    if kind == "text":
        lookup = {
            "title": "title",
            "body": "content",
            "text": "content",
            "customid": "custom_id",
            "custom_id": "custom_id",
            "project": "project",
            "step": "steps__body",
            "comment": "comments__body",
            "file": "attachments__file",
        }[field]
        if op not in (":", "="):
            raise SearchSyntaxError(f"Use “{field}:text” to search {field}.")
        if field == "file":
            return Q(attachments__is_current=True) & (
                Q(attachments__file__icontains=value) | Q(attachments__caption__icontains=value)
            )
        return Q(**{lookup + ("__iexact" if op == "=" else "__icontains"): value})

    if kind == "id":
        number = value.lstrip("#")
        if not number.isdigit():
            raise SearchSyntaxError("id needs a number, for example id:42.")
        return _compare("pk", op, int(number))

    if kind == "tag":
        name = value.lstrip("#").lower()
        return Q(tags__name=name) if op == "=" else Q(tags__name__icontains=name)

    if kind == "choice":
        from core.models.lab_tools.notebook import NotebookEntry

        lookup, choices = {
            "status": ("status", NotebookEntry.STATUS_CHOICES),
            "type": ("entry_type", NotebookEntry.ENTRY_TYPE_CHOICES),
            "category": ("entry_type", NotebookEntry.ENTRY_TYPE_CHOICES),
            "visibility": ("visibility", NotebookEntry.VISIBILITY_CHOICES),
        }[field]
        wanted = value.strip().lower().replace(" ", "_").replace("-", "_")
        for key, label in choices:
            if wanted == key or wanted == label.lower().replace(" ", "_"):
                return Q(**{lookup: key})
        valid = ", ".join(key for key, _ in choices)
        raise SearchSyntaxError(f"Unknown {field} “{value}”. Valid values: {valid}.")

    if kind == "author":
        needle = value.strip()
        return (
            Q(author__username__icontains=needle)
            | Q(author__first_name__icontains=needle)
            | Q(author__last_name__icontains=needle)
            | Q(author__email__icontains=needle)
        )

    if kind == "number":
        try:
            number = int(value)
        except ValueError:
            raise SearchSyntaxError("rating needs a whole number from 0 to 5.")
        return _compare("rating", "=" if op == ":" else op, number)

    if kind == "date":
        return _compare("experiment_date", "=" if op == ":" else op, _parse_date(value))

    if kind == "datetime":
        lookup = "created_at" if field == "created" else "updated_at"
        day = _parse_date(value)
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(day, time.min), tz)
        end = start + timedelta(days=1)
        if op in (":", "="):
            return Q(**{lookup + "__gte": start, lookup + "__lt": end})
        if op == ">":
            return Q(**{lookup + "__gte": end})
        if op == ">=":
            return Q(**{lookup + "__gte": start})
        if op == "<":
            return Q(**{lookup + "__lt": start})
        return Q(**{lookup + "__lt": end})  # <=

    if kind == "has":
        what = value.strip().lower()
        if what in ("file", "files", "attachment", "attachments"):
            return Q(attachments__is_current=True)
        if what in ("comment", "comments"):
            return Q(comments__isnull=False)
        if what in ("step", "steps"):
            return Q(steps__isnull=False)
        if what in ("tag", "tags"):
            return Q(tags__isnull=False)
        raise SearchSyntaxError("has: accepts files, comments, steps or tags.")

    if kind == "extrafield":
        name, sep, wanted = value.partition(":")
        name = name.strip()
        if not name or "__" in name:
            raise SearchSyntaxError("Use extrafield:Name:value, for example extrafield:Medium:TSB.")
        base = f"metadata__extra_fields__{name}__value"
        if not sep:
            return Q(**{f"metadata__extra_fields__{name}__isnull": False})
        if op == "=" or wanted.startswith("="):
            return Q(**{base: wanted.lstrip("=")})
        return Q(**{base + "__icontains": wanted})

    raise SearchSyntaxError(f"Unsupported search field “{field}”.")  # pragma: no cover


class _Parser:
    def __init__(self, tokens, user):
        self.tokens = tokens
        self.pos = 0
        self.user = user

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def parse(self):
        node = self.or_expr()
        if self.peek() is not None:
            raise SearchSyntaxError("Unexpected “)” in the search.")
        return node

    def or_expr(self):
        node = self.and_expr()
        while (self.peek() or "").lower() == "or":
            self.take()
            node = node | self.and_expr()
        return node

    def and_expr(self):
        node = self.not_expr()
        while True:
            token = self.peek()
            if token is None or token == ")" or token.lower() == "or":
                return node
            if token.lower() == "and":
                self.take()
            node = node & self.not_expr()

    def not_expr(self):
        token = self.peek()
        if token is None:
            raise SearchSyntaxError("The search ends where a term was expected.")
        if token.lower() == "not":
            self.take()
            return ~self.not_expr()
        if token.startswith("-") and len(token) > 1:
            self.tokens[self.pos] = token[1:]
            return ~self.not_expr()
        return self.atom()

    def atom(self):
        token = self.take()
        if token == "(":
            node = self.or_expr()
            if self.take() != ")":
                raise SearchSyntaxError("Missing “)” in the search.")
            return node
        if token == ")" or token.lower() in ("and", "or"):
            raise SearchSyntaxError(f"Unexpected “{token}” in the search.")
        field, op, value = _split_term(token)
        if field is None:
            return free_text_q(value)
        if field in ("author", "owner") and value.strip().lower() == "me" and self.user is not None:
            return Q(author=self.user)
        return _term_q(field, op, value)


def build_query(text, user=None):
    """Return (Q, structured). Raises SearchSyntaxError for a malformed query."""
    text = (text or "").strip()
    if not text:
        return Q(), False
    if not has_structured_syntax(text):
        return free_text_q(text), False
    return _Parser(_tokenize(text), user).parse(), True
