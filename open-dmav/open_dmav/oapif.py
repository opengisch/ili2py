from __future__ import annotations

try:
    # Django 6+ can expose curve-capable geometry field classes depending on backend support.
    from django.contrib.gis.db import models as _gis_models
    from ninja.orm import register_field as _register_ninja_field

    for _field_name in (
        "CircularStringField",
        "CompoundCurveField",
        "CurvePolygonField",
        "MultiCurveField",
        "MultiSurfaceField",
    ):
        _field_cls = getattr(_gis_models, _field_name, None)
        if _field_cls is not None:
            _register_ninja_field(_field_cls, dict)
except Exception:
    # Keep OAPIF startup resilient on Django versions without curve model fields.
    pass
"""OAPIF API wiring for open_dmav."""

from django.apps import apps
from django.contrib.gis.db.models import GeometryField
from django_oapif import AnonReadOnlyCollection, OAPIF, OapifCollection
from django_oapif.auth import BasicAuth, DjangoAuth
from ninja.orm import register_field

# django-ninja does not ship default mappings for GeoDjango geometry field
# internal types, so register them as generic JSON-like objects.
for _geo_field_type in (
    "GeometryField",
    "PointField",
    "MultiPointField",
    "LineStringField",
    "MultiLineStringField",
    "PolygonField",
    "MultiPolygonField",
    "CircularStringField",
    "CompoundCurveField",
    "CurvePolygonField",
    "MultiCurveField",
    "MultiSurfaceField",
    "GeometryCollectionField",
):
    register_field(_geo_field_type, dict)

api = OAPIF(
    title="open-dmav OAPIF",
    description=(
        "OGC API Features endpoint for generated open-dmav models, "
        "including read-only enum lookup collections."
    ),
    auth=[BasicAuth(), DjangoAuth()],
)


class PublicReadModelWriteCollection(OapifCollection):
    """Allow anonymous reads while enforcing Django model permissions for writes."""

    def has_view_permission(self, _request, _obj=None) -> bool:
        return True


def _is_enum_lookup_model(model) -> bool:
    return hasattr(model, "__ili2django_values__")


def _register_feature_collection(model) -> None:
    geometry_fields = [field for field in model._meta.get_fields() if isinstance(field, GeometryField)]

    if not geometry_fields:
        return

    # django-oapif requires choosing a geometry field when multiple are present.
    if len(geometry_fields) == 1:
        api.register_collection(models=model, oapif_class=PublicReadModelWriteCollection)
        return

    for geometry_field in geometry_fields:
        collection_class = type(
            f"{model.__name__}{geometry_field.name.title().replace('_', '')}Collection",
            (PublicReadModelWriteCollection,),
            {
                "id": f"{model._meta.label_lower}__{geometry_field.name}",
                "title": f"{model._meta.label} ({geometry_field.name})",
                "geometry_field": geometry_field.name,
            },
        )
        api.register_collection(models=model, oapif_class=collection_class)


def _register_enum_lookup_collection(model) -> None:
    collection_class = type(
        f"{model.__name__}LookupCollection",
        (AnonReadOnlyCollection,),
        {
            "id": f"lookup.{model._meta.label_lower}",
            "title": f"Lookup: {model._meta.label}",
            "description": "Code list / enum lookup values.",
        },
    )
    api.register_collection(models=model, oapif_class=collection_class)


def _register_generated_collections() -> None:
    for model in apps.get_models():
        if not model._meta.app_label.startswith("odmav_"):
            continue
        if model._meta.abstract:
            continue

        if _is_enum_lookup_model(model):
            _register_enum_lookup_collection(model)
            continue

        _register_feature_collection(model)


_register_generated_collections()
