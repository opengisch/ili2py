"""ASGI config for open_dmav project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "open_dmav.settings")

application = get_asgi_application()
