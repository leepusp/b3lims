import base64
import io
import re


SAMPLE_MICRO_QR_PATTERN = re.compile(
    r"^[2-9A-HJ-NP-Z]{10}$"
)

SAMPLE_MICRO_QR_VERSION = "M3"
SAMPLE_MICRO_QR_ERROR = "M"
SAMPLE_MICRO_QR_MODE = "alphanumeric"
SAMPLE_MICRO_QR_DESIGNATOR = "M3-M"
SAMPLE_MICRO_QR_BORDER = 2
SAMPLE_MICRO_QR_SCALE = 10

# Conventional QR used by Sample labels intended for
# native mobile-phone camera scanning.
SAMPLE_MOBILE_QR_ERROR = "M"
SAMPLE_MOBILE_QR_BORDER = 4
SAMPLE_MOBILE_QR_SCALE = 10


class InvalidSampleMicroQrToken(ValueError):
    pass


def normalize_sample_micro_qr_token(token):
    value = str(token or "").strip().upper()

    if not SAMPLE_MICRO_QR_PATTERN.fullmatch(
        value
    ):
        raise InvalidSampleMicroQrToken(
            "Invalid Sample Micro QR token."
        )

    return value


def build_sample_micro_qr(token):
    """
    Build the fixed Micro QR symbol used by Sample labels.

    Segno is imported lazily so Django management commands that
    do not render a label can still inspect the project before
    the production dependency is deployed.
    """
    import segno

    value = normalize_sample_micro_qr_token(
        token
    )

    qr = segno.make_micro(
        value,
        version=SAMPLE_MICRO_QR_VERSION,
        error=SAMPLE_MICRO_QR_ERROR,
        mode=SAMPLE_MICRO_QR_MODE,
        boost_error=False,
    )

    if not qr.is_micro:
        raise RuntimeError(
            "Sample QR generation did not produce "
            "a Micro QR symbol."
        )

    if qr.designator != SAMPLE_MICRO_QR_DESIGNATOR:
        raise RuntimeError(
            "Unexpected Sample Micro QR designator: "
            f"{qr.designator}"
        )

    return qr


def sample_micro_qr_png_bytes(
    token,
    *,
    scale=SAMPLE_MICRO_QR_SCALE,
):
    qr = build_sample_micro_qr(
        token
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        kind="png",
        scale=scale,
        border=SAMPLE_MICRO_QR_BORDER,
    )

    payload = buffer.getvalue()

    if not payload.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        raise RuntimeError(
            "Sample Micro QR renderer did not "
            "produce a PNG image."
        )

    return payload


def sample_micro_qr_png_base64(token):
    return base64.b64encode(
        sample_micro_qr_png_bytes(token)
    ).decode("ascii")


def build_sample_mobile_qr(url):
    """
    Build a conventional QR Code containing the absolute Sample URL.

    This renderer is intentionally separate from the compact Micro QR
    renderer so existing token and scanner workflows remain available.
    """
    import segno

    value = str(url or "").strip()

    if not value.lower().startswith(
        ("https://", "http://")
    ):
        raise ValueError(
            "Sample mobile QR payload must be "
            "an absolute HTTP(S) URL."
        )

    qr = segno.make(
        value,
        error=SAMPLE_MOBILE_QR_ERROR,
        mode="alphanumeric",
        micro=False,
        boost_error=False,
    )

    if qr.is_micro:
        raise RuntimeError(
            "Sample mobile QR renderer unexpectedly "
            "produced a Micro QR symbol."
        )

    return qr


def sample_mobile_qr_png_bytes(
    url,
    *,
    scale=SAMPLE_MOBILE_QR_SCALE,
):
    qr = build_sample_mobile_qr(url)

    buffer = io.BytesIO()

    qr.save(
        buffer,
        kind="png",
        scale=scale,
        border=SAMPLE_MOBILE_QR_BORDER,
    )

    payload = buffer.getvalue()

    if not payload.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        raise RuntimeError(
            "Sample mobile QR renderer did not "
            "produce a PNG image."
        )

    return payload


def sample_mobile_qr_png_base64(url):
    return base64.b64encode(
        sample_mobile_qr_png_bytes(url)
    ).decode("ascii")
