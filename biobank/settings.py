import os
import environ
from pathlib import Path

# =========================
# BASE & ENV
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

# Inicializa o environ
env = environ.Env(
    DEBUG=(bool, True)
)
# Tenta ler o arquivo .env se ele existir na raiz do projeto
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# =========================
# SEGURANÇA / DEBUG / PROXY (APACHE)
# =========================
SECRET_KEY = env('SECRET_KEY', default="dev-secret-key") 
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

SESSION_COOKIE_SECURE = env.bool(
    "SESSION_COOKIE_SECURE",
    default=False,
)
CSRF_COOKIE_SECURE = env.bool(
    "CSRF_COOKIE_SECURE",
    default=False,
)

# 1. Autoriza o domínio da USP a enviar formulários POST (Resolve o Erro 403 CSRF)
CSRF_TRUSTED_ORIGINS = ['https://davinci.icb.usp.br']

# 2. Avisa o Django que o Apache já cuidou do cadeado de segurança (HTTPS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 3. Avisa o Django que ele está rodando atrás de um subdiretório no Apache
C3_LIMS_URL_PREFIX = "/c3-lims"
FORCE_SCRIPT_NAME = C3_LIMS_URL_PREFIX

# =========================
# APLICAÇÕES
# =========================
INSTALLED_APPS = [
    # 1. Django Core Apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # 2. App Principal
    "core.apps.CoreConfig",

    # 3. Utilitários Externos
    "import_export",  
    "django_extensions",
    "rest_framework",
    "django_filters",
]

# =========================
# MIDDLEWARE
# =========================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.pam_remote_user.PamRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# PAM authentication is supplied by the local Apache reverse proxy.
# ModelBackend remains temporarily available for controlled migration
# and local administrative recovery.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "django.contrib.auth.backends.RemoteUserBackend",
]

BIOBANK_PAM_REMOTE_USER_META_KEY = os.environ.get(
    "BIOBANK_PAM_REMOTE_USER_META_KEY",
    "HTTP_X_BIOBANK_PAM_USER",
)

BIOBANK_PAM_TRUSTED_PROXIES = tuple(
    value.strip()
    for value in os.environ.get(
        "BIOBANK_PAM_TRUSTED_PROXIES",
        "127.0.0.1,::1",
    ).split(",")
    if value.strip()
)

BIOBANK_PAM_TRUST_UNIX_SOCKET = env.bool(
    "BIOBANK_PAM_TRUST_UNIX_SOCKET",
    default=False,
)

BIOBANK_PAM_HOME_ROOTS = tuple(
    value.strip()
    for value in os.environ.get(
        "BIOBANK_PAM_HOME_ROOTS",
        "/home",
    ).split(":")
    if value.strip()
)

BIOBANK_PAM_MINIMUM_UID = int(
    os.environ.get(
        "BIOBANK_PAM_MINIMUM_UID",
        "1000",
    )
)


# Unix/NSS groups synchronized from authenticated PAM identities use a
# reserved prefix. Manual Django groups are never modified by this
# synchronization.
BIOBANK_PAM_SYNC_GROUPS = os.environ.get(
    "BIOBANK_PAM_SYNC_GROUPS",
    "1",
).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

BIOBANK_PAM_GROUP_PREFIX = os.environ.get(
    "BIOBANK_PAM_GROUP_PREFIX",
    "pam:",
).strip()

# Operational cluster groups must not become application collaboration
# groups. Personal primary groups matching the username are also
# excluded automatically.
BIOBANK_PAM_EXCLUDED_GROUPS = tuple(
    value.strip()
    for value in os.environ.get(
        "BIOBANK_PAM_EXCLUDED_GROUPS",
        (
            "wheel,dbadmin,unrestricted,max90,"
            "vglusers,cryosparc,biobank"
        ),
    ).split(",")
    if value.strip()
)

# Generic Sample grants are evaluated in shadow mode only when explicitly
# enabled. The authoritative legacy decision remains unchanged.
BIOBANK_SAMPLE_GRANT_SHADOW_MODE = env.bool(
    "BIOBANK_SAMPLE_GRANT_SHADOW_MODE",
    default=False,
)


# =========================
# URLS / WSGI
# =========================
ROOT_URLCONF = "biobank.urls"
WSGI_APPLICATION = "biobank.wsgi.application"

# =========================
# TEMPLATES
# =========================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "core" / "interfaces",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# =========================
# DATABASE
# =========================
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

# =========================
# STATIC FILES (CSS, JS, IMAGES) - CONFIGURAÇÃO APACHE
# =========================
# URL base que o navegador vai procurar
STATIC_URL = f"{C3_LIMS_URL_PREFIX}/static/"

# Onde o Django vai procurar seus arquivos CSS/JS durante o desenvolvimento
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Onde o comando 'collectstatic' vai juntar tudo para o Apache ler
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded media remain private to the application (0660/02770 below), while
# collected static assets must be readable by Apache.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        "OPTIONS": {
            "file_permissions_mode": 0o644,
            "directory_permissions_mode": 0o755,
        },
    },
}

# =========================
# MEDIA (UPLOADS DE AMOSTRAS E ARQUIVOS)
# =========================
MEDIA_URL = f"{C3_LIMS_URL_PREFIX}/data/"
MEDIA_ROOT = os.environ.get("BIOBANK_MEDIA_ROOT", "/home/public/apps/biobank/storage/data")

# Aumenta o limite de upload para arquivos científicos (ex: 50MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800

# =========================
# INTERNACIONALIZAÇÃO
# =========================
LANGUAGE_CODE = "en"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# =========================
# AUTENTICAÇÃO
# =========================
LOGIN_URL = f"{C3_LIMS_URL_PREFIX}/login/"
LOGOUT_URL = f"{C3_LIMS_URL_PREFIX}/logout/"
LOGIN_REDIRECT_URL = f"{C3_LIMS_URL_PREFIX}/workspace/"
LOGOUT_REDIRECT_URL = LOGIN_URL

# =========================
# DEFAULTS
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"



# ---------------------------------------------------------------------
# Biobank persistent filesystem storage
# ---------------------------------------------------------------------
# Inventory and institutional documents remain in shared application
# storage. Personal Lab Tools artifacts are isolated in the authenticated
# Unix user's home under /home/<username>/biobank/lab_tools/.
BIOBANK_STORAGE_ROOT = Path(os.environ.get("BIOBANK_STORAGE_ROOT", "/home/public/apps/biobank/storage"))

BIOBANK_GROUP_ROOT = Path(os.environ.get("BIOBANK_GROUP_ROOT", str(BIOBANK_STORAGE_ROOT / "groups")))
BIOBANK_INVENTORY_ROOT = Path(os.environ.get("BIOBANK_INVENTORY_ROOT", str(BIOBANK_STORAGE_ROOT / "inventory")))
BIOBANK_SAMPLE_DOCS_ROOT = Path(os.environ.get("BIOBANK_SAMPLE_DOCS_ROOT", str(BIOBANK_STORAGE_ROOT / "sample_docs")))
BIOBANK_MANIFESTS_ROOT = Path(os.environ.get("BIOBANK_MANIFESTS_ROOT", str(BIOBANK_STORAGE_ROOT / "manifests")))
BIOBANK_SHARED_ROOT = Path(os.environ.get("BIOBANK_SHARED_ROOT", str(BIOBANK_STORAGE_ROOT / "shared")))

BIOBANK_LAB_TOOLS_HOME_ROOTS = BIOBANK_PAM_HOME_ROOTS
BIOBANK_LAB_TOOLS_RELATIVE_ROOT = "biobank/lab_tools"
BIOBANK_LAB_TOOLS_STORAGE_RUNNER = os.environ.get(
    "BIOBANK_LAB_TOOLS_STORAGE_RUNNER",
    "/usr/local/sbin/biobank-user-storage",
)
BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN = os.environ.get(
    "BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN",
    "0",
).strip().lower() not in {"0", "false", "no", "off"}
BIOBANK_JUPYTER_SERVER_RUNNER = os.environ.get(
    "BIOBANK_JUPYTER_SERVER_RUNNER",
    "/usr/local/sbin/biobank-jupyter-server-runner",
)

BIOBANK_JUPYTER_DEFAULT_CPUS = int(
    os.environ.get("BIOBANK_JUPYTER_DEFAULT_CPUS", "2")
)
BIOBANK_JUPYTER_DEFAULT_MEMORY_MB = int(
    os.environ.get("BIOBANK_JUPYTER_DEFAULT_MEMORY_MB", "8192")
)
BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES = int(
    os.environ.get("BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES", "60")
)
BIOBANK_JUPYTER_PARTITION = os.environ.get(
    "BIOBANK_JUPYTER_PARTITION",
    "max50",
)

BIOBANK_JUPYTER_PARTITIONS = ("basic", "max50")
BIOBANK_JUPYTER_NODES = ("n01", "gn01", "gn02", "gn03")
BIOBANK_JUPYTER_PARTITION_MAX_HOURS = {
    "basic": 72,
    "max50": 168,
}

BIOBANK_JUPYTERLAB_OOD_LAUNCH_URL = os.environ.get(
    "BIOBANK_JUPYTERLAB_OOD_LAUNCH_URL",
    (
        "https://davinci.icb.usp.br/pun/sys/dashboard/"
        "batch_connect/sys/jupyterlab/session_contexts/new"
    ),
)

FILE_UPLOAD_PERMISSIONS = 0o660
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o2770
