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
