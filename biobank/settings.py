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

# 1. Autoriza o domínio da USP a enviar formulários POST (Resolve o Erro 403 CSRF)
CSRF_TRUSTED_ORIGINS = ['https://davinci.icb.usp.br']

# 2. Avisa o Django que o Apache já cuidou do cadeado de segurança (HTTPS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 3. Avisa o Django que ele está rodando atrás de um subdiretório no Apache
FORCE_SCRIPT_NAME = '/biobank'

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
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
STATIC_URL = "/biobank/static/"

# Onde o Django vai procurar seus arquivos CSS/JS durante o desenvolvimento
STATICFILES_DIRS = [
    BASE_DIR / "core" / "interfaces",
    BASE_DIR / "static",
]

# Onde o comando 'collectstatic' vai juntar tudo para o Apache ler
STATIC_ROOT = BASE_DIR / "staticfiles"

# =========================
# MEDIA (UPLOADS DE AMOSTRAS E ARQUIVOS)
# =========================
MEDIA_URL = "/biobank/data/"
MEDIA_ROOT = BASE_DIR / "data"

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
LOGIN_URL = "/biobank/login/"
LOGOUT_URL = "/biobank/logout/"
LOGIN_REDIRECT_URL = "/biobank/"
LOGOUT_REDIRECT_URL = "/biobank/login/"

# =========================
# DEFAULTS
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"



# ---------------------------------------------------------------------
# Default mode for DaVinci testing stores notebook artifacts in:
# /home/<username>/biobank_notebooks/
#
# Future shared deployment can set:
# BIOBANK_NOTEBOOK_STORAGE_MODE=public
# BIOBANK_NOTEBOOK_ROOT=/home/public/biobank/users


# ---------------------------------------------------------------------
# Biobank persistent filesystem storage
# ---------------------------------------------------------------------
# Personal ELN/notebook artifacts are stored in the Linux user's home:
# /home/<username>/biobank_notebooks/
#
# Shared institutional Biobank data are stored under:
# /home/public/apps/biobank/storage/
BIOBANK_NOTEBOOK_STORAGE_MODE = os.environ.get("BIOBANK_NOTEBOOK_STORAGE_MODE", "home")
BIOBANK_STORAGE_ROOT = Path(os.environ.get("BIOBANK_STORAGE_ROOT", "/home/public/apps/biobank/storage"))

BIOBANK_NOTEBOOK_ROOT = Path(os.environ.get("BIOBANK_NOTEBOOK_ROOT", str(BIOBANK_STORAGE_ROOT / "users")))
BIOBANK_GROUP_ROOT = Path(os.environ.get("BIOBANK_GROUP_ROOT", str(BIOBANK_STORAGE_ROOT / "groups")))
BIOBANK_INVENTORY_ROOT = Path(os.environ.get("BIOBANK_INVENTORY_ROOT", str(BIOBANK_STORAGE_ROOT / "inventory")))
BIOBANK_SAMPLE_DOCS_ROOT = Path(os.environ.get("BIOBANK_SAMPLE_DOCS_ROOT", str(BIOBANK_STORAGE_ROOT / "sample_docs")))
BIOBANK_MANIFESTS_ROOT = Path(os.environ.get("BIOBANK_MANIFESTS_ROOT", str(BIOBANK_STORAGE_ROOT / "manifests")))
BIOBANK_SHARED_ROOT = Path(os.environ.get("BIOBANK_SHARED_ROOT", str(BIOBANK_STORAGE_ROOT / "shared")))

