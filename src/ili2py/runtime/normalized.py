"""Neutral normalized record helpers for parsed XTF transfers.

This module intentionally returns builtin-only structures so downstream sinks
can consume parsed transfer content without depending on Django, GEOS, or any
other persistence/runtime framework.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Any

from xsdata.formats.dataclass.models.generics import AnyElement


NormalizedScalar = str | int | float | bool | Decimal | None
NormalizedGeometry = dict[str, Any]
NormalizedRecord = dict[str, Any]


def normalize_transfers(transfers: dict[str, Any]) -> list[NormalizedRecord]:
    """Flatten parsed XTF transfer objects into neutral builtin structures.

    The implementation emits scalar attributes plus neutral maps for
    references, geometries, and nested child records.
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
                        "references": _reference_map(record),
                        "geometries": _geometry_map(record),
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
    if _is_reference_value(value):
        return []
    if _is_geometry_value(value):
        return []
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
        "references": _reference_map(record),
        "geometries": _geometry_map(record),
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


def _is_reference_value(value: Any) -> bool:
    if not is_dataclass(value):
        return False
    if not hasattr(value, "ref"):
        return False
    ref_value = getattr(value, "ref", None)
    return ref_value is None or isinstance(ref_value, str)


def _reference_map(record: Any) -> dict[str, str]:
    if not is_dataclass(record):
        return {}

    references: dict[str, str] = {}
    for record_field in fields(record):
        if record_field.name == "tid":
            continue
        value = getattr(record, record_field.name, None)
        if not _is_reference_value(value):
            continue
        ref_value = getattr(value, "ref", None)
        if ref_value:
            references[record_field.name] = ref_value
    return references


def _is_geometry_value(value: Any) -> bool:
    if isinstance(value, AnyElement):
        return True
    return is_dataclass(value) and isinstance(getattr(value, "content", None), list)


def _geometry_map(record: Any) -> dict[str, NormalizedGeometry]:
    if not is_dataclass(record):
        return {}

    geometries: dict[str, NormalizedGeometry] = {}
    for record_field in fields(record):
        if record_field.name == "tid":
            continue
        value = getattr(record, record_field.name, None)
        if not _is_geometry_value(value):
            continue
        normalized = _normalize_geometry_value(value)
        if normalized:
            geometries[record_field.name] = normalized
    return geometries


def _normalize_geometry_value(value: AnyElement) -> NormalizedGeometry:
    geometry_node = _geometry_any_element(value)
    if geometry_node is None:
        return {"type": "RawGeometry", "xml": _geometry_wrapper_to_dict(value)}

    node_tag_name = _local_name(geometry_node.qname)
    if node_tag_name == "coord":
        point = _coord_to_position(geometry_node)
        if point:
            return {"type": "Point", "coordinates": point}
    if node_tag_name == "polyline":
        line = _polyline_to_coordinates(geometry_node)
        if line:
            return {"type": "LineString", "coordinates": line}
    if node_tag_name == "surface":
        polygon = _surface_to_coordinates(geometry_node)
        if polygon:
            return {"type": "Polygon", "coordinates": polygon}

    direct_children = _direct_geometry_children(geometry_node)
    if any(_local_name(child.qname) in {"arc", "curve", "circularstring", "compoundcurve"} for child in direct_children):
        return {"type": "RawGeometry", "xml": _geometry_wrapper_to_dict(value)}

    direct_kinds = [_local_name(child.qname) for child in direct_children]
    if direct_kinds and all(kind == "coord" for kind in direct_kinds):
        points = [point for point in (_coord_to_position(child) for child in direct_children) if point]
        if len(points) == 1:
            return {"type": "Point", "coordinates": points[0]}
        if len(points) > 1:
            return {"type": "MultiPoint", "coordinates": points}

    if direct_kinds and all(kind == "polyline" for kind in direct_kinds):
        lines = [line for line in (_polyline_to_coordinates(child) for child in direct_children) if line]
        if len(lines) == 1:
            return {"type": "LineString", "coordinates": lines[0]}
        if len(lines) > 1:
            return {"type": "MultiLineString", "coordinates": lines}

    if direct_kinds and all(kind == "surface" for kind in direct_kinds):
        polygons = [polygon for polygon in (_surface_to_coordinates(child) for child in direct_children) if polygon]
        if len(polygons) == 1:
            return {"type": "Polygon", "coordinates": polygons[0]}
        if len(polygons) > 1:
            return {"type": "MultiPolygon", "coordinates": polygons}

    geometry_node = _find_geometry_node(geometry_node)
    if geometry_node is None:
        return {"type": "RawGeometry", "xml": _geometry_wrapper_to_dict(value)}

    tag_name = _local_name(geometry_node.qname)
    if tag_name == "coord":
        point = _coord_to_position(geometry_node)
        if point:
            return {"type": "Point", "coordinates": point}

    if tag_name == "polyline":
        line = _polyline_to_coordinates(geometry_node)
        if line:
            return {"type": "LineString", "coordinates": line}

    if tag_name == "surface":
        polygon = _surface_to_coordinates(geometry_node)
        if polygon:
            return {"type": "Polygon", "coordinates": polygon}

    return {"type": "RawGeometry", "xml": _geometry_wrapper_to_dict(value)}


def _geometry_any_element(value: Any) -> AnyElement | None:
    if isinstance(value, AnyElement):
        return value
    if not is_dataclass(value):
        return None
    for item in getattr(value, "content", []) or []:
        if isinstance(item, AnyElement):
            return item
    return None


def _geometry_wrapper_to_dict(value: Any) -> NormalizedGeometry:
    if isinstance(value, AnyElement):
        return _any_element_to_dict(value)
    if not is_dataclass(value):
        return {"value": value}
    content = []
    for item in getattr(value, "content", []) or []:
        if isinstance(item, AnyElement):
            content.append(_any_element_to_dict(item))
        else:
            content.append({"value": item})
    return {"content": content}


def _find_geometry_node(value: AnyElement) -> AnyElement | None:
    node_name = _local_name(value.qname)
    if node_name in {"coord", "polyline", "surface"}:
        return value
    for child in getattr(value, "children", []) or []:
        if not isinstance(child, AnyElement):
            continue
        found = _find_geometry_node(child)
        if found is not None:
            return found
    return None


def _direct_geometry_children(node: AnyElement) -> list[AnyElement]:
    return [child for child in getattr(node, "children", []) or [] if isinstance(child, AnyElement)]


def _polyline_to_coordinates(polyline: AnyElement) -> list[list[NormalizedScalar]]:
    coordinates: list[list[NormalizedScalar]] = []
    for child in getattr(polyline, "children", []) or []:
        if not isinstance(child, AnyElement):
            continue
        local_name = _local_name(child.qname)
        if local_name == "coord":
            point = _coord_to_position(child)
            if point:
                coordinates.append(point)
        elif local_name == "arc":
            # INTERLIS arc uses c1/c2 as the segment endpoint; include it in-order
            # so curve-dominant polylines keep a usable vertex sequence.
            point = _arc_endpoint_to_position(child)
            if point:
                coordinates.append(point)
    return coordinates


def _arc_endpoint_to_position(arc: AnyElement) -> list[NormalizedScalar]:
    c1 = _child_text(arc, "c1")
    c2 = _child_text(arc, "c2")
    c3 = _child_text(arc, "c3")

    if c1 is None or c2 is None:
        return []

    pos: list[NormalizedScalar] = [_parse_number(c1), _parse_number(c2)]
    if c3 is not None:
        pos.append(_parse_number(c3))
    return pos


def _surface_to_coordinates(surface: AnyElement) -> list[list[list[NormalizedScalar]]]:
    rings: list[list[list[NormalizedScalar]]] = []

    for exterior in _iter_named(surface, "exterior"):
        polyline = _first_named(exterior, "polyline")
        if polyline is None:
            continue
        line = _polyline_to_coordinates(polyline)
        if line:
            rings.append(line)

    for interior in _iter_named(surface, "interior"):
        polyline = _first_named(interior, "polyline")
        if polyline is None:
            continue
        line = _polyline_to_coordinates(polyline)
        if line:
            rings.append(line)

    return rings


def _coord_to_position(coord: AnyElement) -> list[NormalizedScalar]:
    c1 = _child_text(coord, "c1")
    c2 = _child_text(coord, "c2")
    c3 = _child_text(coord, "c3")

    if c1 is None or c2 is None:
        return []

    pos: list[NormalizedScalar] = [_parse_number(c1), _parse_number(c2)]
    if c3 is not None:
        pos.append(_parse_number(c3))
    return pos


def _iter_named(node: AnyElement, name: str):
    for child in getattr(node, "children", []) or []:
        if isinstance(child, AnyElement) and _local_name(child.qname) == name:
            yield child
        if isinstance(child, AnyElement):
            for nested in _iter_named(child, name):
                yield nested


def _first_named(node: AnyElement, name: str) -> AnyElement | None:
    for child in _iter_named(node, name):
        return child
    return None


def _child_text(node: AnyElement, name: str) -> str | None:
    child = _first_named(node, name)
    if child is None:
        return None
    if child.text is None:
        return None
    return str(child.text)


def _parse_number(value: str) -> NormalizedScalar:
    try:
        return Decimal(value)
    except Exception:
        return value


def _local_name(qname: str | None) -> str:
    if not qname:
        return ""
    if "}" in qname:
        return qname.rsplit("}", 1)[-1]
    return qname


def _any_element_to_dict(node: AnyElement) -> NormalizedGeometry:
    children = []
    for child in getattr(node, "children", []) or []:
        if isinstance(child, AnyElement):
            children.append(_any_element_to_dict(child))
        else:
            children.append({"value": child})
    return {
        "qname": node.qname,
        "text": node.text,
        "attributes": dict(getattr(node, "attributes", {}) or {}),
        "children": children,
    }