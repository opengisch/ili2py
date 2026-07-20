"""Neutral normalized record helpers for parsed XTF transfers.

This module intentionally returns builtin-only structures so downstream sinks
can consume parsed transfer content without depending on Django, GEOS, or any
other persistence/runtime framework.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Any


NormalizedScalar = str | int | float | bool | Decimal | None
NormalizedGeometry = dict[str, Any]
NormalizedRecord = dict[str, Any]


def normalize_transfers(transfers: dict[str, Any]) -> list[NormalizedRecord]:
    """Flatten parsed XTF transfer objects into neutral builtin structures.

    The current implementation only emits scalar attributes from generated
    reader dataclasses. Reference, geometry, and child containers are exposed
    as empty collections until the reader/generator surfaces them explicitly.
    """

    normalized_records: list[NormalizedRecord] = []
    for model_name, transfer in transfers.items():
        normalized_records.extend(normalize_transfer(model_name, transfer))
    return normalized_records


def normalize_transfer(model_name: str, transfer: Any) -> list[NormalizedRecord]:
    datasection = getattr(transfer, "datasection", None) or getattr(transfer, "DATASECTION", None)
    if datasection is None:
        return []

    normalized_records: list[NormalizedRecord] = []
    for basket in getattr(datasection, "baskets", []):
        topic_name = type(basket).__name__
        if not is_dataclass(basket):
            continue
        for basket_field in fields(basket):
            if basket_field.name == "bid":
                continue
            records = getattr(basket, basket_field.name, None)
            if not records:
                continue
            for record in records:
                normalized_records.append(
                    {
                        "model_name": model_name,
                        "topic_name": topic_name,
                        "class_name": type(record).__name__,
                        "tid": getattr(record, "tid", None),
                        "attributes": _scalar_attributes(record),
                        "references": {},
                        "geometries": {},
                        "children": _child_record_map(record),
                    }
                )
    return normalized_records


def _scalar_attributes(record: Any) -> dict[str, NormalizedScalar]:
    if not is_dataclass(record):
        return {}

    attributes: dict[str, NormalizedScalar] = {}
    for record_field in fields(record):
        if record_field.name == "tid":
            continue
        value = getattr(record, record_field.name, None)
        if _is_scalar_value(value):
            attributes[record_field.name] = value
    return attributes


def _child_records(value: Any) -> list[NormalizedRecord]:
    if value is None:
        return []
    if isinstance(value, list):
        child_records: list[NormalizedRecord] = []
        for item in value:
            child_records.extend(_child_records(item))
        return child_records
    if is_dataclass(value):
        wrapper_items = getattr(value, "items", None)
        if isinstance(wrapper_items, list):
            return [_normalize_child_record(item) for item in wrapper_items if is_dataclass(item)]
        return [_normalize_child_record(value)]
    return []


def _normalize_child_record(record: Any) -> NormalizedRecord:
    return {
        "class_name": type(record).__name__,
        "tid": getattr(record, "tid", None),
        "attributes": _scalar_attributes(record),
        "references": {},
        "geometries": {},
        "children": _child_record_map(record),
    }


def _child_record_map(record: Any) -> dict[str, list[NormalizedRecord]]:
    if not is_dataclass(record):
        return {}
    children: dict[str, list[NormalizedRecord]] = {}
    for record_field in fields(record):
        if record_field.name == "tid":
            continue
        child_entries = _child_records(getattr(record, record_field.name, None))
        if child_entries:
            children[record_field.name] = child_entries
    return children


def _is_scalar_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, Decimal))