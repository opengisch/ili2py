"""Django settings for open_dmav project."""

from __future__ import annotations

import os
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = BASE_DIR / "apps"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))


def discover_generated_apps() -> list[str]:
    apps: list[str] = []
    if not APPS_DIR.exists():
        return apps
    for child in sorted(APPS_DIR.iterdir()):
        if child.is_dir() and (child / "apps.py").exists():
            apps.append(child.name)
    return apps


SECRET_KEY = "open-dmav-dev-key-change-in-production"
DEBUG = True
ALLOWED_HOSTS: list[str] = ["*"]

# Reverse proxy support (e.g. Traefik): required so request.build_absolute_uri()
# in django-oapif emits public URLs instead of internal localhost/container host.
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "unfold",
    "open_dmav",
    "django_oapif",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.gis",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    *discover_generated_apps(),
]

UNFOLD = {
    "SITE_TITLE": "open-dmav Admin",
    "SITE_HEADER": "open-dmav",
    "SITE_SYMBOL": "public",
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "open_dmav.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "open_dmav.wsgi.application"
ASGI_APPLICATION = "open_dmav.asgi.application"

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": os.getenv("POSTGRES_DB", "open_dmav"),
            "USER": os.getenv("POSTGRES_USER", "open_dmav"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "open_dmav"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

GDAL_LIBRARY_PATH = os.getenv("GDAL_LIBRARY_PATH")
GEOS_LIBRARY_PATH = os.getenv("GEOS_LIBRARY_PATH")

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
