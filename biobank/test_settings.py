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

BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN = False
BIOBANK_JUPYTER_ALLOW_ENTRY_OWNERS = True


# The test suite must never write into a real installation (or fail where the
# institutional paths do not exist, such as a CI runner): use a throw-away folder.
import atexit as _atexit
import shutil as _shutil
import tempfile as _tempfile
from pathlib import Path as _Path

_TEST_STORAGE = _Path(_tempfile.mkdtemp(prefix="biobank-test-storage-"))
_atexit.register(_shutil.rmtree, _TEST_STORAGE, ignore_errors=True)

MEDIA_ROOT = str(_TEST_STORAGE / "data")
BIOBANK_STORAGE_ROOT = _TEST_STORAGE
BIOBANK_GROUP_ROOT = _TEST_STORAGE / "groups"
BIOBANK_INVENTORY_ROOT = _TEST_STORAGE / "inventory"
BIOBANK_SAMPLE_DOCS_ROOT = _TEST_STORAGE / "sample_docs"
BIOBANK_MANIFESTS_ROOT = _TEST_STORAGE / "manifests"
BIOBANK_SHARED_ROOT = _TEST_STORAGE / "shared"
