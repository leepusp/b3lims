"""
Standalone/local-first runtime settings.

This profile is intentionally independent from the CEPID B3 / DaVinci
deployment configuration.

Initial scope:
- local Django authentication
- SQLite database
- local persistent filesystem
- localhost-only access
- no URL prefix

HPC, remote scientific services, desktop packaging, and portable Lab Tools
storage are handled in later modularization stages.
"""

import os
from pathlib import Path

from .settings import *  # noqa: F401,F403


# ---------------------------------------------------------------------
# Runtime identity
# ---------------------------------------------------------------------

BIOBANK_RUNTIME_PROFILE = "standalone"

B3_LIMS_URL_PREFIX = ""
FORCE_SCRIPT_NAME = None


# ---------------------------------------------------------------------
# Local HTTP runtime
# ---------------------------------------------------------------------

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "[::1]",
]

CSRF_TRUSTED_ORIGINS = []
SECURE_PROXY_SSL_HEADER = None

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


# ---------------------------------------------------------------------
# Local authentication
# ---------------------------------------------------------------------

MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE
    if middleware
    != "core.middleware.pam_remote_user.PamRemoteUserMiddleware"
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

BIOBANK_PAM_SYNC_GROUPS = False


# ---------------------------------------------------------------------
# Standalone persistent root
# ---------------------------------------------------------------------

BIOBANK_LOCAL_ROOT = Path(
    os.environ.get(
        "BIOBANK_LOCAL_ROOT",
        str(Path.home() / ".biobank-local"),
    )
).expanduser()

BIOBANK_LOCAL_DATABASE_ROOT = (
    BIOBANK_LOCAL_ROOT / "database"
)

BIOBANK_STORAGE_ROOT = (
    BIOBANK_LOCAL_ROOT / "storage"
)

BIOBANK_SAMPLE_DATA_ROOT = (
    BIOBANK_STORAGE_ROOT / "sample_data"
)

MEDIA_ROOT = (
    BIOBANK_LOCAL_ROOT / "data"
)

BIOBANK_BACKUP_ROOT = (
    BIOBANK_LOCAL_ROOT / "backups"
)


# ---------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": (
            BIOBANK_LOCAL_DATABASE_ROOT
            / "biobank.sqlite3"
        ),
    }
}


# ---------------------------------------------------------------------
# Generic persistent storage
# ---------------------------------------------------------------------

BIOBANK_GROUP_ROOT = (
    BIOBANK_STORAGE_ROOT / "groups"
)

BIOBANK_INVENTORY_ROOT = (
    BIOBANK_STORAGE_ROOT / "inventory"
)

BIOBANK_SAMPLE_DOCS_ROOT = (
    BIOBANK_STORAGE_ROOT / "sample_docs"
)

BIOBANK_MANIFESTS_ROOT = (
    BIOBANK_STORAGE_ROOT / "manifests"
)

BIOBANK_SHARED_ROOT = (
    BIOBANK_STORAGE_ROOT / "shared"
)


# ---------------------------------------------------------------------
# Standalone persistent-directory bootstrap
# ---------------------------------------------------------------------
# A fresh local installation may point BIOBANK_LOCAL_ROOT at a path
# that does not exist yet. SQLite cannot create its database file
# unless the parent directory already exists, and the remaining local
# inventory roots must likewise be available before first use.
#
# This bootstrap belongs only to the standalone profile; the B3 /
# DaVinci deployment continues to manage its filesystem externally.

_STANDALONE_PERSISTENT_DIRECTORIES = (
    BIOBANK_LOCAL_ROOT,
    BIOBANK_LOCAL_DATABASE_ROOT,
    BIOBANK_STORAGE_ROOT,
    BIOBANK_SAMPLE_DATA_ROOT,
    MEDIA_ROOT,
    BIOBANK_BACKUP_ROOT,
    BIOBANK_GROUP_ROOT,
    BIOBANK_INVENTORY_ROOT,
    BIOBANK_SAMPLE_DOCS_ROOT,
    BIOBANK_MANIFESTS_ROOT,
    BIOBANK_SHARED_ROOT,
)

for _directory in _STANDALONE_PERSISTENT_DIRECTORIES:
    Path(_directory).mkdir(
        parents=True,
        exist_ok=True,
    )


# ---------------------------------------------------------------------
# Local URLs
# ---------------------------------------------------------------------

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

LOGIN_URL = "/login/"
LOGOUT_URL = "/logout/"
LOGIN_REDIRECT_URL = "/workspace/"
LOGOUT_REDIRECT_URL = LOGIN_URL


# ---------------------------------------------------------------------
# Current infrastructure contract
# ---------------------------------------------------------------------
# These flags describe the standalone profile. Feature gating that
# consumes them will be implemented separately.

BIOBANK_HPC_ENABLED = False
BIOBANK_JUPYTER_ENABLED = False
BIOBANK_ONLINE_INTEGRATIONS_ENABLED = False

# Never invoke the DaVinci PAM-login provisioning path in this profile.
BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN = False


# ---------------------------------------------------------------------
# Portable upload permissions
# ---------------------------------------------------------------------

FILE_UPLOAD_PERMISSIONS = None
FILE_UPLOAD_DIRECTORY_PERMISSIONS = None
