from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Keyword, KeywordValue, Tag
from core.models.keywords.model import normalize_metadata_text
from core.models.tags.model import normalize_metadata_name


def active_tags_from_ids(tag_ids):
    """Return only active tags represented by the submitted identifiers."""
    return Tag.objects.filter(
        pk__in=tag_ids,
        is_active=True,
    )


def get_or_create_active_tag(name, description=""):
    """Return an active normalized tag without creating logical duplicates."""
    normalized_name = normalize_metadata_name(name)

    if not normalized_name:
        raise ValidationError("Tag name is required.")

    existing = Tag.objects.filter(
        name__iexact=normalized_name,
    ).first()

    if existing:
        if not existing.is_active:
            raise ValidationError(
                "This tag is inactive and cannot be assigned."
            )
        return existing, False

    try:
        with transaction.atomic():
            tag = Tag.objects.create(
                name=normalized_name,
                description=(description or "").strip(),
            )
    except IntegrityError:
        tag = Tag.objects.filter(
            name__iexact=normalized_name,
            is_active=True,
        ).first()

        if tag is None:
            raise ValidationError(
                "The tag could not be created."
            )
        return tag, False

    return tag, True


def get_or_create_active_keyword_value(keyword_name, value):
    """Return an active normalized keyword/value pair."""
    normalized_keyword = normalize_metadata_text(keyword_name)
    normalized_value = normalize_metadata_text(value)

    if not normalized_keyword or not normalized_value:
        raise ValidationError(
            "Both keyword name and value are required."
        )

    keyword = Keyword.objects.filter(
        name__iexact=normalized_keyword,
    ).first()

    if keyword and not keyword.is_active:
        raise ValidationError(
            "This keyword is inactive and cannot be assigned."
        )

    if keyword is None:
        try:
            with transaction.atomic():
                keyword = Keyword.objects.create(
                    name=normalized_keyword,
                )
        except IntegrityError:
            keyword = Keyword.objects.filter(
                name__iexact=normalized_keyword,
                is_active=True,
            ).first()

            if keyword is None:
                raise ValidationError(
                    "The keyword could not be created."
                )

    keyword_value = KeywordValue.objects.filter(
        keyword=keyword,
        value__iexact=normalized_value,
    ).first()

    if keyword_value:
        if not keyword_value.is_active:
            raise ValidationError(
                "This keyword value is inactive and cannot be assigned."
            )
        return keyword_value, False

    try:
        with transaction.atomic():
            keyword_value = KeywordValue.objects.create(
                keyword=keyword,
                value=normalized_value,
            )
    except IntegrityError:
        keyword_value = KeywordValue.objects.filter(
            keyword=keyword,
            value__iexact=normalized_value,
            is_active=True,
        ).first()

        if keyword_value is None:
            raise ValidationError(
                "The keyword value could not be created."
            )
        return keyword_value, False

    return keyword_value, True
