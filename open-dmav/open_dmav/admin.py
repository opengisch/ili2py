"""Admin registrations for open_dmav."""

from __future__ import annotations

import tempfile

from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.sites import AlreadyRegistered
from django.core.management import call_command
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import ModelAdmin


class GeneratedModelAdmin(ModelAdmin):
    """Default Unfold admin for generated models."""


class GeneratedEnumModelAdmin(ModelAdmin):
    """Admin config for generated enum value-list models."""

    search_fields = ("code", "label")
    list_display = ("code", "label", "order")
    ordering = ("order", "code")


class ImportXtfForm(forms.Form):
    xtf = forms.FileField(help_text="Upload an INTERLIS transfer file (.xtf).")
    imd = forms.FileField(
        required=False,
        help_text="Optional: upload model metadata (.imd) to preload labels/translations.",
    )


def _write_upload_to_temp(upload, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        for chunk in upload.chunks():
            tmp.write(chunk)
        return tmp.name


def import_xtf_admin_view(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        return HttpResponse(status=403)

    form = ImportXtfForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        xtf_temp: str | None = None
        imd_temp: str | None = None
        try:
            xtf_temp = _write_upload_to_temp(form.cleaned_data["xtf"], suffix=".xtf")
            command_args = [xtf_temp]
            if form.cleaned_data.get("imd"):
                imd_temp = _write_upload_to_temp(form.cleaned_data["imd"], suffix=".imd")
                command_args.extend(["--imd", imd_temp])
            call_command("import_xtf", *command_args)
            messages.success(request, "XTF import completed successfully.")
            return HttpResponseRedirect(reverse("admin:import-xtf"))
        except Exception as exc:
            messages.error(request, f"XTF import failed: {exc}")
        finally:
            
            for temp_path in (xtf_temp, imd_temp):
                if temp_path:
                    try:
                        from pathlib import Path

                        Path(temp_path).unlink(missing_ok=True)
                    except Exception:
                        pass

    context = {
        **admin.site.each_context(request),
        "title": "Import XTF",
        "form": form,
    }
    return TemplateResponse(request, "admin/import_xtf.html", context)


_admin_site_get_urls = admin.site.get_urls


def _get_admin_urls():
    return [
        path("import-xtf/", admin.site.admin_view(import_xtf_admin_view), name="import-xtf"),
        *_admin_site_get_urls(),
    ]


admin.site.get_urls = _get_admin_urls


def _is_generated_enum_model(model: type[models.Model]) -> bool:
    return hasattr(model, "__ili2django_values__")


def _enum_fk_field_names(model: type[models.Model]) -> list[str]:
    names: list[str] = []
    for field in model._meta.get_fields():
        if not isinstance(field, models.ForeignKey):
            continue
        if _is_generated_enum_model(field.related_model):
            names.append(field.name)
    return names


def _build_model_admin(model: type[models.Model]) -> type[ModelAdmin]:
    if _is_generated_enum_model(model):
        return GeneratedEnumModelAdmin

    autocomplete_fields = _enum_fk_field_names(model)
    if not autocomplete_fields:
        return GeneratedModelAdmin

    return type(
        f"{model.__name__}Admin",
        (GeneratedModelAdmin,),
        {"autocomplete_fields": autocomplete_fields},
    )


def register_generated_models() -> None:
    for model in apps.get_models():
        if not model._meta.app_label.startswith("odmav_"):
            continue
        if model._meta.abstract:
            continue
        try:
            admin.site.register(model, _build_model_admin(model))
        except AlreadyRegistered:
            continue


register_generated_models()
