"""URL configuration for open_dmav."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from open_dmav.oapif import api as oapif_api


def health(_request):
    return JsonResponse({"status": "ok"})


oapif_patterns, oapif_app_name, oapif_namespace = oapif_api.urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("oapif/", include((oapif_patterns, oapif_app_name), namespace=oapif_namespace)),
]
