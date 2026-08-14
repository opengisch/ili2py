"""Neutral normalized record helpers for parsed XTF transfers.

This module intentionally returns builtin-only structures so downstream sinks
can consume parsed transfer content without depending on Django, GEOS, or any
other persistence/runtime framework.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from xsdata.formats.dataclass.models.generics import AnyElement


NormalizedScalar = str | int | float | bool | Decimal | None
NormalizedGeometry = dict[str, Any]
NormalizedRecord = dict[str, Any]


class InterlisVersion(str, Enum):
    """Normalization mode hint for transfer-shape selection."""

    DETECT = "detect"
    V23 = "2.3"
    V24 = "2.4"


class UnsupportedTransferShapeError(ValueError):
    """Raised when the transfer object does not match expected shape."""

    pass


def normalize_transfers(
    transfers: dict[str, Any],
    *,
    interlis_version: InterlisVersion | str = InterlisVersion.DETECT,
) -> list[NormalizedRecord]:
    """Flatten parsed XTF transfer objects into neutral builtin structures.

    The implementation emits scalar attributes plus neutral maps for
    references, geometries, and nested child records.
    """

    normalized_records: list[NormalizedRecord] = []
    for model_name, transfer in transfers.items():
        normalized_records.extend(
            normalize_transfer(model_name, transfer, interlis_version=interlis_version)
        )
    return normalized_records


def normalize_transfer(
    model_name: str,
    transfer: Any,
    *,
    interlis_version: InterlisVersion | str = InterlisVersion.DETECT,
) -> list[NormalizedRecord]:
    """Normalize one parsed transfer into neutral record dictionaries.

    The ``interlis_version`` parameter can enforce 2.3/2.4 expectations or use
    shape-based detection.
    """
    datasection = getattr(transfer, "datasection", None) or getattr(transfer, "DATASECTION", None)
    if datasection is None:
        return []

    requested_version = _coerce_interlis_version(interlis_version)
    effective_version = (
        _detect_interlis_version(datasection)
        if requested_version == InterlisVersion.DETECT
        else requested_version
    )

    if effective_version == InterlisVersion.V24:
        return _normalize_transfer_v24(model_name, datasection)
    if effective_version == InterlisVersion.V23:
        return _normalize_transfer_v23(model_name, datasection)
    raise UnsupportedTransferShapeError(f"Unsupported INTERLIS version for normalization: {effective_version}")


def _normalize_transfer_v24(model_name: str, datasection: Any) -> list[NormalizedRecord]:
    """Normalize transfers shaped like INTERLIS 2.4 baskets."""
    baskets = getattr(datasection, "baskets", None)
    if not isinstance(baskets, list):
        raise UnsupportedTransferShapeError(
            f"Expected INTERLIS 2.4 transfer shape with datasection.baskets for model {model_name}."
        )

    normalized_records: list[NormalizedRecord] = []
    for basket in baskets:
        topic_name = type(basket).__name__
        if not is_dataclass(basket):
            continue
        bid = getattr(basket, "bid", None)
        for basket_field in fields(basket):
            if basket_field.name == "bid":
                continue
            records = getattr(basket, basket_field.name, None)
            if not records:
                continue
            for record in records:
                if not is_dataclass(record):
                    continue
                record_model_name = _record_model_name(record, default=model_name)
                normalized_records.append(_normalized_record(record_model_name, topic_name, record, bid=bid))
    return normalized_records


_XTF_24_NAMESPACE_PREFIX = "http://www.interlis.ch/xtf/2.4/"


def _record_model_name(record: Any, *, default: str) -> str:
    """Resolve the model a record's class actually belongs to.

    A basket can carry records whose class is declared in a different (base)
    model than the basket's own model -- topic extensions share one basket
    with their base topic, so a class inherited unchanged by the extending
    topic still transfers through it. The generated dataclass's own
    ``Meta.namespace`` already reflects the class's true origin model (see
    ``ili2py.interfaces.interlis.interlis_24.generator``), so prefer that over
    the basket's/transfer's model name -- otherwise the record is labeled
    under the wrong model and never matches the base model's binding.
    """
    meta = getattr(type(record), "Meta", None)
    namespace = getattr(meta, "namespace", None) if meta else None
    if isinstance(namespace, str) and namespace.startswith(_XTF_24_NAMESPACE_PREFIX):
        model_name = namespace[len(_XTF_24_NAMESPACE_PREFIX) :]
        if model_name:
            return model_name
    return default


def _normalize_transfer_v23(model_name: str, datasection: Any) -> list[NormalizedRecord]:
    """Normalize transfers shaped like INTERLIS 2.3 topic fields."""
    if not is_dataclass(datasection):
        raise UnsupportedTransferShapeError(
            f"Expected INTERLIS 2.3 transfer shape with dataclass DATASECTION for model {model_name}."
        )

    if any(field.name == "baskets" for field in fields(datasection)):
        raise UnsupportedTransferShapeError(
            f"Got INTERLIS 2.4-like transfer while INTERLIS 2.3 was requested for model {model_name}."
        )

    normalized_records: list[NormalizedRecord] = []
    datasection_bid = getattr(datasection, "bid", None)
    for topic_field in fields(datasection):
        if topic_field.name == "bid":
            continue
        topic = getattr(datasection, topic_field.name, None)
        if topic is None or not is_dataclass(topic):
            continue
        topic_name = type(topic).__name__
        bid = getattr(topic, "bid", None) or datasection_bid
        for class_field in fields(topic):
            if class_field.name == "bid":
                continue
            records = getattr(topic, class_field.name, None)
            if not records:
                continue
            record_items = records if isinstance(records, list) else [records]
            for record in record_items:
                if not is_dataclass(record):
                    continue
                normalized_records.append(_normalized_record(model_name, topic_name, record, bid=bid))
    return normalized_records


def _coerce_interlis_version(value: InterlisVersion | str) -> InterlisVersion:
    if isinstance(value, InterlisVersion):
        return value
    try:
        return InterlisVersion(value)
    except ValueError as exc:
        allowed = ", ".join(v.value for v in InterlisVersion)
        raise ValueError(f"Unsupported interlis_version '{value}'. Allowed: {allowed}") from exc


def _detect_interlis_version(datasection: Any) -> InterlisVersion:
    """Infer transfer shape from ``datasection`` structure."""
    baskets = getattr(datasection, "baskets", None)
    if isinstance(baskets, list):
        return InterlisVersion.V24

    if is_dataclass(datasection):
        ds_fields = {f.name for f in fields(datasection)}
        if "baskets" in ds_fields:
            return InterlisVersion.V24
        if any(name != "bid" for name in ds_fields):
            return InterlisVersion.V23

    raise UnsupportedTransferShapeError(
        "Could not detect INTERLIS transfer shape from datasection."
    )


def _normalized_record(
    model_name: str, topic_name: str, record: Any, *, bid: str | None = None
) -> NormalizedRecord:
    return {
        "model_name": model_name,
        "topic_name": topic_name,
        "class_name": type(record).__name__,
        "tid": getattr(record, "tid", None),
        "bid": bid,
        "attributes": _scalar_attributes(record),
        "references": _reference_map(record),
        "geometries": _geometry_map(record),
        "children": _child_record_map(record),
    }


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

    normalized = _normalize_geometry_node(geometry_node)
    if normalized:
        return normalized
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


def _normalize_geometry_node(node: AnyElement) -> NormalizedGeometry | None:
    """Normalize one geometry node (or wrapper) into GeoJSON-like structure."""
    node_name = _local_name(node.qname)
    if node_name == "coord":
        point = _coord_to_position(node)
        if point:
            return {"type": "Point", "coordinates": point}
    elif node_name == "polyline":
        line = _polyline_to_coordinates(node)
        if line:
            return {"type": "LineString", "coordinates": line}
    elif node_name == "surface":
        polygon = _surface_to_coordinates(node)
        if polygon:
            return {"type": "Polygon", "coordinates": polygon}

    direct_children = _direct_geometry_children(node)
    if not direct_children:
        geometry_node = _find_geometry_node(node)
        if geometry_node is None or geometry_node is node:
            return None
        return _normalize_geometry_node(geometry_node)

    direct_kinds = [_local_name(child.qname) for child in direct_children]
    if all(kind == "coord" for kind in direct_kinds):
        points = [point for point in (_coord_to_position(child) for child in direct_children) if point]
        if len(points) == 1:
            return {"type": "Point", "coordinates": points[0]}
        if len(points) > 1:
            return {"type": "MultiPoint", "coordinates": points}
        return None

    if all(kind == "polyline" for kind in direct_kinds):
        lines = [line for line in (_polyline_to_coordinates(child) for child in direct_children) if line]
        if len(lines) == 1:
            return {"type": "LineString", "coordinates": lines[0]}
        if len(lines) > 1:
            return {"type": "MultiLineString", "coordinates": lines}
        return None

    if all(kind == "surface" for kind in direct_kinds):
        polygons = [polygon for polygon in (_surface_to_coordinates(child) for child in direct_children) if polygon]
        if len(polygons) == 1:
            return {"type": "Polygon", "coordinates": polygons[0]}
        if len(polygons) > 1:
            return {"type": "MultiPolygon", "coordinates": polygons}
        return None

    # Keep descending before giving up on curved content at this level.
    # This avoids missing polygon/surface content nested below wrappers.
    if any(kind in {"arc", "curve", "circularstring", "compoundcurve"} for kind in direct_kinds):
        geometry_node = _find_geometry_node(node)
        if geometry_node is None or geometry_node is node:
            return None
        return _normalize_geometry_node(geometry_node)

    geometry_node = _find_geometry_node(node)
    if geometry_node is None or geometry_node is node:
        return None
    return _normalize_geometry_node(geometry_node)


def _direct_geometry_children(node: AnyElement) -> list[AnyElement]:
    return [child for child in getattr(node, "children", []) or [] if isinstance(child, AnyElement)]


def _polyline_to_coordinates(polyline: AnyElement) -> list[Any]:
    """Flatten a polyline into a list of vertices.

    Each entry is either a plain point ``[x, y(, z)]`` (a straight vertex) or
    an arc marker ``{"arc_via": [x, y(, z)], "point": [x, y(, z)]}`` meaning
    "the segment from the previous vertex to `point` is a circular arc
    passing through `arc_via`". This preserves arc/straight segment identity
    so it can be losslessly reconstructed on write (see
    `ili2py.runtime.denormalized`), unlike the flat point list this used to
    produce.
    """
    coordinates: list[Any] = []
    for child in getattr(polyline, "children", []) or []:
        if not isinstance(child, AnyElement):
            continue
        local_name = _local_name(child.qname)
        if local_name == "coord":
            point = _coord_to_position(child)
            if point:
                _append_vertex_if_new(coordinates, point)
        elif local_name == "arc":
            midpoint = _arc_midpoint_to_position(child)
            endpoint = _arc_endpoint_to_position(child)
            if midpoint and endpoint:
                _append_vertex_if_new(coordinates, {"arc_via": midpoint, "point": endpoint})
    return coordinates


def _vertex_position(vertex: Any) -> list[NormalizedScalar]:
    if isinstance(vertex, dict):
        return vertex["point"]
    return vertex


def _append_vertex_if_new(coordinates: list[Any], vertex: Any) -> None:
    if coordinates and _vertex_position(coordinates[-1]) == _vertex_position(vertex):
        return
    coordinates.append(vertex)


def _arc_midpoint_to_position(arc: AnyElement) -> list[NormalizedScalar]:
    a1 = _child_text(arc, "a1")
    a2 = _child_text(arc, "a2")
    a3 = _child_text(arc, "a3")

    if a1 is None or a2 is None:
        return []

    pos: list[NormalizedScalar] = [_parse_number(a1), _parse_number(a2)]
    if a3 is not None:
        pos.append(_parse_number(a3))
    return pos


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