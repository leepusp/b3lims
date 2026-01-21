import os
from pathlib import Path

# =========================
# BASE
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# SEGURANÇA / DEBUG
# =========================
SECRET_KEY = "dev-secret-key"  # Trocar para uma chave real em produção
DEBUG = True
ALLOWED_HOSTS = []

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

    # 2. App Principal (Agora contém o Lab Tools)
    "core.apps.CoreConfig",

    # REMOVIDO: "lab_tools"
    # (Não incluímos mais aqui pois foi integrado ao core)

    # 4. Utilitários Externos
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
            # O Django vai procurar os templates em: ~/biobank/core/interfaces
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
# DATABASE (SQLITE PARA DEV)
# =========================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# =========================
# STATIC FILES (CSS, JS, IMAGES)
# =========================
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    # O Django vai procurar estáticos em: ~/biobank/core/interfaces
    BASE_DIR / "core" / "interfaces",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# =========================
# MEDIA (UPLOADS DE AMOSTRAS)
# =========================
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# INTERNACIONALIZAÇÃO
# =========================
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# =========================
# AUTENTICAÇÃO
# =========================
LOGIN_URL = "/login/"
LOGOUT_URL = "/logout/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# =========================
# DEFAULTS
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"