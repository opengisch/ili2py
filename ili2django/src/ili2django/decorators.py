"""Decorator and field helpers for generated Django models."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def interlis_model(*, oid: str, qname: str, **meta: Any) -> Callable[[type[T]], type[T]]:
    """Attach INTERLIS mapping metadata to a Django model class."""

    def wrapper(cls: type[T]) -> type[T]:
        payload = {"oid": oid, "qname": qname}
        payload.update(meta)
        setattr(cls, "__ili2django__", payload)
        return cls

    return wrapper


def ili_field(field: Any, *, oid: str, qname: str | None = None, **meta: Any) -> Any:
    """Attach INTERLIS mapping metadata to a Django field instance."""

    payload = {"oid": oid}
    if qname:
        payload["qname"] = qname
    payload.update(meta)
    setattr(field, "_ili2django", payload)
    return field


def ensure_curve_field_aliases() -> None:
    """Expose curve field names on GeoDjango models when they are missing.

    Aliases map to the closest non-curve field classes so generated models can
    consistently reference curved field names across Django versions.
    """

    try:
        from django.contrib.gis.db import models as gis_models
    except Exception:
        return

    alias_map: dict[str, str] = {
        "CircularStringField": "LineStringField",
        "CompoundCurveField": "MultiLineStringField",
        "CurvePolygonField": "PolygonField",
        "MultiCurveField": "MultiLineStringField",
        "MultiSurfaceField": "MultiPolygonField",
    }

    for alias_name, target_name in alias_map.items():
        if hasattr(gis_models, alias_name):
            continue
        target = getattr(gis_models, target_name, None)
        if target is not None:
            setattr(gis_models, alias_name, target)
