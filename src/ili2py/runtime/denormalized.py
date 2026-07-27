"""Build parsed-transfer-shaped dataclass trees from normalized records.

The reverse of `ili2py.runtime.normalized.normalize_transfers`: given a
loaded IMD metamodel and a list of `NormalizedRecord` dicts (the exact shape
`normalize_transfers` produces), reconstruct dataclass instances that can be
serialized back to XTF via xsdata's `XmlSerializer`.

Scope: scalar attributes, single references, bag/multivalue children
(recursively -- e.g. Objektnummer containing Textposition), and simple
(non-multi) Point/LineString/Polygon geometries built from already-flattened
coordinate lists. Note that arc/curve segments are *already* lost by the
time a record reaches `NormalizedRecord` -- `normalize_transfers` flattens
them into plain point lists on read (see `_polyline_to_coordinates` in
`normalized.py`) -- so there is no separate "curve support" to add here:
reconstructing a plain polyline/ring from that same flattened coordinate
list is a faithful round-trip of the normalized form, even though the
original XTF used `<arc>` elements.

Not yet supported (raises rather than silently producing wrong XTF):
- MultiPoint/MultiLineString/MultiPolygon geometries.
- `RawGeometry` fallback entries (geometry that `normalize_transfers` itself
  couldn't interpret). Deliberately out of scope for now, not just
  unimplemented -- see the ili2py roadmap discussion.
"""

from __future__ import annotations

import dataclasses
import typing
from collections import defaultdict
from typing import Any

from xsdata.formats.dataclass.models.generics import AnyElement

from ili2py.interfaces.interlis.interlis_24 import HeaderSection, Model, Models
from ili2py.interfaces.interlis.interlis_24.generator import (
    DataClassGenerator,
    _GeometryElement24,
    _RefElement24,
)
from ili2py.runtime.normalized import NormalizedRecord

GEOMETRY_NAMESPACE = "http://www.interlis.ch/geometry/1.0"

_SUPPORTED_GEOMETRY_TYPES = {"Point", "LineString", "Polygon"}


class UnsupportedRecordDataError(ValueError):
    """Raised when a record can't be faithfully rebuilt with the current v1 support."""


def build_transfers(
    metamodel: Any, records: list[NormalizedRecord], *, sender: str = "ili2py"
) -> dict[str, Any]:
    """Group records by model_name and build one transfer object per model."""
    by_model: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_model[record["model_name"]].append(record)

    return {
        model_name: build_transfer(metamodel, model_name, model_records, sender=sender)
        for model_name, model_records in by_model.items()
    }


def build_transfer(
    metamodel: Any,
    model_name: str,
    records: list[NormalizedRecord],
    *,
    sender: str = "ili2py",
) -> Any:
    """Build one parsed-transfer-shaped object for `model_name` from `records`.

    Only records with `record["model_name"] == model_name` are used.
    """
    generator = DataClassGenerator(metamodel)
    transfer_cls = generator.generate(model_name)
    basket_choices = generator._basket_choices_for_model(model_name)

    records_by_topic_class: dict[str, dict[str, list[NormalizedRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    bid_by_topic: dict[str, str | None] = {}
    for record in records:
        if record.get("model_name") != model_name:
            continue

        topic_name = record["topic_name"]
        records_by_topic_class[topic_name][record["class_name"]].append(record)
        bid = record.get("bid")
        if bid:
            bid_by_topic[topic_name] = bid

    baskets: list[Any] = []
    for choice in basket_choices:
        topic_name = choice["name"]
        class_records = records_by_topic_class.get(topic_name)
        if not class_records:
            continue

        basket_cls = choice["type"]
        basket_kwargs: dict[str, Any] = {"bid": bid_by_topic.get(topic_name)}
        for class_name, class_record_list in class_records.items():
            record_cls = _field_class(basket_cls, class_name.lower())
            basket_kwargs[class_name.lower()] = [
                _build_record(record_cls, record) for record in class_record_list
            ]

        baskets.append(basket_cls(**basket_kwargs))

    datasection_field = next(
        f for f in dataclasses.fields(transfer_cls) if f.name == "datasection"
    )
    data_section_type = datasection_field.type

    header_section = HeaderSection(
        models=Models(elements=[Model(model=model_name)]), sender=sender
    )
    return transfer_cls(
        headersection=header_section,
        datasection=data_section_type(baskets=baskets),
    )


def _field_class(cls: type[Any], attr_name: str) -> type[Any]:
    """Extract the real class behind a dataclass field's annotation.

    Handles the three shapes used here: `List[X]` (basket -> record, and
    wrapper -> child record), `Optional[X]` (record -> wrapper, when the
    bag is optional), and a bare `X` (record -> wrapper, when mandatory).
    """
    for cls_field in dataclasses.fields(cls):
        if cls_field.name != attr_name:
            continue

        args = typing.get_args(cls_field.type)
        if not args:
            return cls_field.type

        for arg in args:
            if arg is not type(None):
                return arg

        return cls_field.type

    raise LookupError(f"No field named {attr_name!r} on {cls.__name__}.")


def _build_record(record_cls: type[Any], record: NormalizedRecord) -> Any:
    kwargs: dict[str, Any] = {"tid": record.get("tid")}
    kwargs.update(record.get("attributes") or {})

    for name, ref in (record.get("references") or {}).items():
        kwargs[name] = _RefElement24(ref=ref)

    for name, geometry in (record.get("geometries") or {}).items():
        kwargs[name] = _build_geometry_element(geometry, record=record, field_name=name)

    for name, child_records in (record.get("children") or {}).items():
        wrapper_cls = _field_class(record_cls, name)
        child_cls = _field_class(wrapper_cls, "items")
        kwargs[name] = wrapper_cls(
            items=[_build_record(child_cls, child) for child in child_records]
        )

    return record_cls(**kwargs)


def _build_geometry_element(
    geometry: dict[str, Any], *, record: NormalizedRecord, field_name: str
) -> _GeometryElement24:
    geometry_type = geometry.get("type")
    if geometry_type not in _SUPPORTED_GEOMETRY_TYPES:
        raise UnsupportedRecordDataError(
            f"Record {record.get('tid')!r} ({record.get('class_name')}) has a "
            f"{geometry_type!r} geometry on {field_name!r}, which build_transfer "
            "doesn't support yet (only Point/LineString/Polygon)."
        )

    if geometry_type == "Point":
        node = _coord_element(geometry["coordinates"])
    elif geometry_type == "LineString":
        node = _polyline_element(geometry["coordinates"])
    else:
        node = _surface_element(geometry["coordinates"])

    return _GeometryElement24(content=[node])


def _qn(local_name: str) -> str:
    return f"{{{GEOMETRY_NAMESPACE}}}{local_name}"


def _coord_element(point: list[Any]) -> AnyElement:
    children = [
        AnyElement(qname=_qn("c1"), text=str(point[0])),
        AnyElement(qname=_qn("c2"), text=str(point[1])),
    ]
    if len(point) > 2 and point[2] is not None:
        children.append(AnyElement(qname=_qn("c3"), text=str(point[2])))

    return AnyElement(qname=_qn("coord"), children=children)


def _polyline_element(coordinates: list[list[Any]]) -> AnyElement:
    return AnyElement(
        qname=_qn("polyline"),
        children=[_coord_element(point) for point in coordinates],
    )


def _surface_element(rings: list[list[list[Any]]]) -> AnyElement:
    children: list[AnyElement] = []
    if rings:
        children.append(
            AnyElement(qname=_qn("exterior"), children=[_polyline_element(rings[0])])
        )
        for ring in rings[1:]:
            children.append(
                AnyElement(qname=_qn("interior"), children=[_polyline_element(ring)])
            )

    return AnyElement(qname=_qn("surface"), children=children)
