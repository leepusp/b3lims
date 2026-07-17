"""Safe Django settings for the automated test suite."""

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": ":memory:",
        },
    }
}

FORCE_SCRIPT_NAME = None

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

BIOBANK_JUPYTER_NOTEBOOK_ROOT = "/tmp/biobank-test-jupyter/notebooks"
BIOBANK_JUPYTER_JOB_ROOT = "/tmp/biobank-test-jupyter/jobs"
