"""ili2django backend built on top of main ili2py parsing/normalization logic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime.normalized import normalize_transfers
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


@dataclass
class _ModelBinding:
    class_ref: str
    model: type[Any]
    fields_by_alias: dict[str, str]
    field_objects: dict[str, Any]
    ref_targets: dict[str, type[Any] | None]


class _DjangoRouterAdapter:
    def __init__(self) -> None:
        from django.apps import apps

        self._apps = apps

    def iter_models(self) -> list[type[Any]]:
        return list(self._apps.get_models())

    def upsert(self, model: type[Any], tid: str, values: dict[str, Any]) -> None:
        defaults = dict(values)
        defaults["tid"] = tid
        model.objects.update_or_create(tid=tid, defaults=defaults)


class _CustomRouterAdapter:
    def __init__(self, router: Any) -> None:
        self._router = router

    def iter_models(self) -> list[type[Any]]:
        return list(self._router.iter_models())

    def upsert(self, model: type[Any], tid: str, values: dict[str, Any]) -> None:
        self._router.upsert(model, tid, values)


class Ili2PyBackend:
    def __init__(self, *, sender: str = "ili2django", xtf_version: str = "2.3") -> None:
        self.sender = sender
        self.xtf_version = xtf_version
        self._metamodel: Any | None = None
        self._imd_translations: dict[str, dict[str, str]] = {}
        self._last_transfers: dict[str, Any] = {}
        self._last_import_diagnostics: dict[str, str | int | None] = {
            "mode": None,
            "reason": None,
            "baskets_seen": 0,
            "records_seen": 0,
            "records_imported": 0,
            "upsert_errors": 0,
            "reference_errors": 0,
            "missing_geometry_values": 0,
            "missing_geometry_fields": [],
        }

    def get_last_import_diagnostics(self) -> dict[str, str | int | None]:
        return dict(self._last_import_diagnostics)

    def read_imd(
        self,
        imd_path: str,
        *,
        translation_imd_paths: str | list[str] | None = None,
    ) -> dict[str, Any]:
        self._metamodel = Imd16Reader().read(imd_path)
        self._imd_translations = {}

        if translation_imd_paths:
            paths = [translation_imd_paths] if isinstance(translation_imd_paths, str) else list(translation_imd_paths)
            for path in paths:
                translation_meta = Imd16Reader().read(path)
                self._merge_imd_translations(self._extract_imd_translations(translation_meta))

        return {
            "metamodel": self._metamodel,
            "translations": self._imd_translations,
        }

    def get_translation_label(self, ref: str, language: str, default: str | None = None) -> str | None:
        return self._imd_translations.get(ref, {}).get(language, default)

    def get_export_label(self, _ref: str, base_label: str) -> str:
        return base_label

    def import_xtf(
        self,
        xtf_path: str,
        *,
        django_router: Any | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        xtf = Path(xtf_path)
        if not xtf.exists():
            raise FileNotFoundError(f"XTF file not found: {xtf_path}")

        self._last_import_diagnostics = {
            "mode": "started",
            "reason": None,
            "baskets_seen": 0,
            "records_seen": 0,
            "records_imported": 0,
            "upsert_errors": 0,
            "reference_errors": 0,
            "missing_geometry_values": 0,
            "missing_geometry_fields": [],
        }

        metamodel = self._resolve_metamodel(xtf)
        reader = Reader(metamodel, fail_on_unknown_properties=False)
        transfers = reader.read(str(xtf))
        self._last_transfers = transfers
        normalized_records = normalize_transfers(transfers)

        router = self._router_adapter(django_router)
        bindings = self._model_bindings(router.iter_models())

        imported_counts: dict[str, int] = {}
        pending_rows: list[tuple[_ModelBinding, str, dict[str, Any], list[tuple[str, type[Any], str]]]] = []

        for record in normalized_records:
            self._last_import_diagnostics["records_seen"] = int(self._last_import_diagnostics["records_seen"] or 0) + 1
            binding = bindings.get((record.get("model_name"), record.get("topic_name"), record.get("class_name")))
            if binding is None:
                continue

            tid = record.get("tid")
            if not tid:
                continue

            values = self._scalar_values(binding, record)
            values.update(self._geometry_values(binding, record, tid=tid))
            values.update(self._child_values(binding, record, tid=tid))
            self._apply_known_model_fallbacks(binding, values)
            pending_refs = self._reference_values(binding, record)

            if pending_refs:
                pending_rows.append((binding, str(tid), values, pending_refs))
                continue

            self._upsert_row(
                router,
                binding=binding,
                tid=str(tid),
                values=values,
                imported_counts=imported_counts,
                continue_on_error=continue_on_error,
            )

        unresolved_rows: list[tuple[_ModelBinding, str, dict[str, Any], list[tuple[str, type[Any], str]]]] = []
        while pending_rows:
            progressed = False
            next_pending: list[tuple[_ModelBinding, str, dict[str, Any], list[tuple[str, type[Any], str]]]] = []
            for binding, tid, values, references in pending_rows:
                resolved_values = dict(values)
                unresolved: list[tuple[str, type[Any], str]] = []
                for field_name, target_model, target_tid in references:
                    target = target_model.objects.filter(tid=target_tid).first()
                    if target is None:
                        unresolved.append((field_name, target_model, target_tid))
                        continue
                    resolved_values[field_name] = target

                if unresolved:
                    next_pending.append((binding, tid, values, unresolved))
                    continue

                self._upsert_row(
                    router,
                    binding=binding,
                    tid=tid,
                    values=resolved_values,
                    imported_counts=imported_counts,
                    continue_on_error=continue_on_error,
                )
                progressed = True

            if not progressed:
                unresolved_rows = next_pending
                break
            pending_rows = next_pending

        if unresolved_rows:
            self._last_import_diagnostics["reference_errors"] = int(
                self._last_import_diagnostics["reference_errors"] or 0
            ) + len(unresolved_rows)
            if not self._last_import_diagnostics.get("reason"):
                sample_binding, sample_tid, _values, sample_refs = unresolved_rows[0]
                unresolved_targets = ", ".join(f"{name}->{target_tid}" for name, _model, target_tid in sample_refs)
                self._last_import_diagnostics["reason"] = (
                    f"unresolved forward references for {sample_binding.class_ref} tid={sample_tid}: {unresolved_targets}"
                )
            if not continue_on_error:
                self._last_import_diagnostics["mode"] = "failed_fast"
                raise RuntimeError(str(self._last_import_diagnostics["reason"]))

        if imported_counts:
            self._last_import_diagnostics["mode"] = "structured"
        else:
            if int(self._last_import_diagnostics.get("upsert_errors") or 0) or int(
                self._last_import_diagnostics.get("reference_errors") or 0
            ):
                self._last_import_diagnostics["mode"] = "partial_failures"
                if not self._last_import_diagnostics.get("reason"):
                    self._last_import_diagnostics["reason"] = "rows failed during import"
            else:
                self._last_import_diagnostics["mode"] = "no_matching_records"
                self._last_import_diagnostics["reason"] = "no records matched generated model/topic/class metadata"

        return imported_counts

    def export_xtf(self, xtf_path: str, *, queryset_provider: Any | None = None) -> None:
        target = Path(xtf_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if queryset_provider is not None:
            raise NotImplementedError("Export from queryset provider is not implemented in the ili2py backend yet.")

        if not self._last_transfers:
            raise RuntimeError("No parsed transfer available. Import an XTF first before exporting.")

        serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))
        if len(self._last_transfers) != 1:
            raise RuntimeError("Export requires exactly one transfer in memory; multi-model export is not implemented yet.")

        transfer = next(iter(self._last_transfers.values()))
        xml = serializer.render(transfer)
        target.write_text(xml, encoding="utf-8")

    def _resolve_metamodel(self, xtf_path: Path) -> Any:
        if self._metamodel is not None:
            return self._metamodel

        stem = xtf_path.stem
        project_root = Path(__file__).resolve().parents[4]
        candidates = [
            xtf_path.with_suffix(".imd"),
            project_root / "models" / f"{stem}.imd",
            project_root / "ili2py" / "tests" / "data" / "models" / f"{stem}.imd",
        ]
        for candidate in candidates:
            if candidate.exists():
                self._metamodel = Imd16Reader().read(str(candidate))
                return self._metamodel

        raise FileNotFoundError(
            "No IMD metamodel loaded. Call read_imd(...) first or place an IMD file alongside the XTF or in models/."
        )

    def _router_adapter(self, django_router: Any | None):
        if django_router is None:
            return _DjangoRouterAdapter()
        if hasattr(django_router, "iter_models") and hasattr(django_router, "upsert"):
            return _CustomRouterAdapter(django_router)
        raise TypeError("django_router must provide at least iter_models() and upsert().")

    def _model_bindings(self, models: list[type[Any]]) -> dict[tuple[str, str, str], _ModelBinding]:
        bindings: dict[tuple[str, str, str], _ModelBinding] = {}
        for model in models:
            meta = getattr(model, "__ili2django__", None)
            oid = getattr(meta, "get", lambda *_: None)("oid") if meta else None
            if not isinstance(oid, str) or oid.count(".") < 2:
                continue
            if not self._model_has_tid(model):
                # TODO: Support importing models without `tid` via model-specific natural keys.
                continue
            model_name, topic_name, class_name = oid.split(".", 2)

            fields_by_alias: dict[str, str] = {}
            field_objects: dict[str, Any] = {}
            ref_targets: dict[str, type[Any] | None] = {}
            for field_obj in model._meta.get_fields():
                field_name = getattr(field_obj, "name", None)
                if not field_name:
                    continue
                field_objects[field_name] = field_obj
                for alias in self._field_aliases(field_obj):
                    fields_by_alias.setdefault(alias, field_name)
                if getattr(field_obj, "related_model", None) is not None:
                    ref_targets[field_name] = getattr(field_obj, "related_model", None)

            bindings[(model_name, topic_name, class_name)] = _ModelBinding(
                class_ref=f"{model_name}.{topic_name}.{class_name}",
                model=model,
                fields_by_alias=fields_by_alias,
                field_objects=field_objects,
                ref_targets=ref_targets,
            )
        return bindings

    def _model_has_tid(self, model: type[Any]) -> bool:
        for field_obj in model._meta.get_fields():
            if getattr(field_obj, "name", None) == "tid":
                return True
        return False

    def _field_aliases(self, field_obj: Any) -> set[str]:
        aliases: set[str] = set()
        name = getattr(field_obj, "name", None)
        if isinstance(name, str):
            aliases.update({name, name.lower(), name.replace("_", "").lower()})

        metadata = getattr(field_obj, "_ili2django", None)
        oid = getattr(metadata, "get", lambda *_: None)("oid") if metadata else None
        if isinstance(oid, str) and "." in oid:
            leaf = oid.rsplit(".", 1)[-1]
            aliases.update({leaf.lower(), self._snake_case(leaf), self._snake_case(leaf).replace("_", "")})
        return aliases

    def _snake_case(self, value: str) -> str:
        chars: list[str] = []
        for index, ch in enumerate(value):
            if ch.isupper() and index > 0 and (not value[index - 1].isupper()):
                chars.append("_")
            chars.append(ch.lower())
        return "".join(chars)

    def _scalar_values(self, binding: _ModelBinding, record: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        attributes = record.get("attributes") or {}
        for raw_name, raw_value in attributes.items():
            django_name = binding.fields_by_alias.get(str(raw_name).lower())
            if not django_name:
                continue
            values[django_name] = self._coerce_scalar(raw_value)
        return values

    def _coerce_scalar(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _geometry_values(self, binding: _ModelBinding, record: dict[str, Any], *, tid: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        geometries = record.get("geometries") or {}
        for raw_name, geometry in geometries.items():
            django_name = binding.fields_by_alias.get(str(raw_name).lower())
            if not django_name:
                continue
            field_obj = binding.field_objects.get(django_name)
            geometry_value = self._to_geometry(geometry, field_obj)
            if geometry_value is None:
                self._last_import_diagnostics["missing_geometry_values"] = int(
                    self._last_import_diagnostics["missing_geometry_values"] or 0
                ) + 1
                missing = self._last_import_diagnostics.setdefault("missing_geometry_fields", [])
                if isinstance(missing, list) and len(missing) < 25:
                    missing.append(
                        {
                            "tid": tid,
                            "class": binding.class_ref,
                            "field": django_name,
                            "xml_name": raw_name,
                        }
                    )
                continue
            values[django_name] = geometry_value
        return values

    def _to_geometry(self, geometry: dict[str, Any], field_obj: Any | None) -> Any | None:
        try:
            from django.contrib.gis.geos import LineString, LinearRing, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
            try:
                from django.contrib.gis.geos import CurvePolygon
            except Exception:
                CurvePolygon = None
        except Exception:
            return None

        geometry_type = str(geometry.get("type") or "")
        coords = geometry.get("coordinates")
        srid = getattr(field_obj, "srid", None)

        try:
            if geometry_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
                g = Point(float(coords[0]), float(coords[1]))
                if self._is_multi_point_field(field_obj):
                    g = MultiPoint([g])
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "MultiPoint" and isinstance(coords, list):
                points = [Point(float(p[0]), float(p[1])) for p in coords if isinstance(p, list) and len(p) >= 2]
                if not points:
                    return None
                g = MultiPoint(points)
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "LineString" and isinstance(coords, list) and len(coords) >= 2:
                g = LineString([(float(p[0]), float(p[1])) for p in coords if isinstance(p, list) and len(p) >= 2])
                if self._is_multi_line_field(field_obj):
                    g = MultiLineString([g])
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "MultiLineString" and isinstance(coords, list):
                lines = [
                    LineString([(float(p[0]), float(p[1])) for p in line if isinstance(p, list) and len(p) >= 2])
                    for line in coords
                    if isinstance(line, list) and len(line) >= 2
                ]
                if not lines:
                    return None
                g = MultiLineString(lines)
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "Polygon" and isinstance(coords, list) and coords:
                rings = [
                    [(float(p[0]), float(p[1])) for p in ring if isinstance(p, list) and len(p) >= 2]
                    for ring in coords
                ]
                rings = [ring for ring in rings if len(ring) >= 3]
                if not rings:
                    return None
                if self._is_curve_polygon_field(field_obj) and CurvePolygon is not None:
                    shell = LinearRing(rings[0])
                    holes = [LinearRing(ring) for ring in rings[1:] if len(ring) >= 4]
                    try:
                        g = CurvePolygon(shell, *holes)
                    except Exception:
                        g = CurvePolygon(shell)
                else:
                    g = Polygon(*rings)
                if self._is_multi_polygon_field(field_obj):
                    g = MultiPolygon([g])
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "MultiPolygon" and isinstance(coords, list):
                polygons = []
                for poly in coords:
                    if not isinstance(poly, list) or not poly:
                        continue
                    rings = [[(float(p[0]), float(p[1])) for p in ring if isinstance(p, list) and len(p) >= 2] for ring in poly]
                    if not rings:
                        continue
                    polygons.append(Polygon(*rings))
                if not polygons:
                    return None
                g = MultiPolygon(polygons)
                if isinstance(srid, int):
                    g.srid = srid
                return g
            if geometry_type == "RawGeometry":
                return self._to_geometry_from_raw(geometry.get("xml"), field_obj)
        except Exception:
            return None

        return None

    def _to_geometry_from_raw(self, raw: Any, field_obj: Any | None) -> Any | None:
        try:
            from django.contrib.gis.geos import LineString, LinearRing, MultiLineString, Point, Polygon
            try:
                from django.contrib.gis.geos import CurvePolygon
            except Exception:
                CurvePolygon = None
        except Exception:
            return None

        points = self._extract_points_from_raw(raw)
        if not points:
            return None

        srid = getattr(field_obj, "srid", None)
        internal_type = ""
        if field_obj is not None and hasattr(field_obj, "get_internal_type"):
            try:
                internal_type = str(field_obj.get_internal_type() or "")
            except Exception:
                internal_type = ""
        itype = internal_type.lower()

        geom = None
        if "polygon" in itype or "curvepolygon" in itype or "surface" in itype:
            if len(points) < 3:
                return None
            if points[0] != points[-1]:
                points.append(points[0])
            if self._is_curve_polygon_field(field_obj) and CurvePolygon is not None:
                ring = LinearRing(points)
                geom = CurvePolygon(ring)
            else:
                geom = Polygon(points)
        elif "multiline" in itype:
            geom = MultiLineString([LineString(points)])
        elif "line" in itype or "curve" in itype:
            if len(points) < 2:
                return None
            geom = LineString(points)
        else:
            geom = Point(points[0][0], points[0][1])

        if isinstance(srid, int):
            geom.srid = srid
        return geom

    def _is_curve_polygon_field(self, field_obj: Any | None) -> bool:
        if field_obj is None or not hasattr(field_obj, "get_internal_type"):
            return False
        try:
            return str(field_obj.get_internal_type() or "").lower() == "curvepolygonfield"
        except Exception:
            return False

    def _is_multi_point_field(self, field_obj: Any | None) -> bool:
        return self._field_internal_type(field_obj) == "multipointfield"

    def _is_multi_line_field(self, field_obj: Any | None) -> bool:
        return self._field_internal_type(field_obj) in {"multilinestringfield", "multicurvefield"}

    def _is_multi_polygon_field(self, field_obj: Any | None) -> bool:
        return self._field_internal_type(field_obj) in {"multipolygonfield", "multisurfacefield"}

    def _is_geometry_field(self, field_obj: Any | None) -> bool:
        return self._field_internal_type(field_obj) in {
            "geometryfield",
            "pointfield",
            "linestringfield",
            "polygonfield",
            "multipointfield",
            "multilinestringfield",
            "multipolygonfield",
            "geometrycollectionfield",
            "circularstringfield",
            "compoundcurvefield",
            "curvepolygonfield",
            "multicurvefield",
            "multisurfacefield",
        }

    def _field_internal_type(self, field_obj: Any | None) -> str:
        if field_obj is None or not hasattr(field_obj, "get_internal_type"):
            return ""
        try:
            return str(field_obj.get_internal_type() or "").lower()
        except Exception:
            return ""

    def _extract_points_from_raw(self, node: Any) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []

        def walk(item: Any) -> None:
            if not isinstance(item, dict):
                return
            qname = str(item.get("qname") or "")
            local = qname.rsplit("}", 1)[-1].lower() if qname else ""
            if local in {"coord", "arc"}:
                pair = self._coord_pair_from_children(item.get("children") or [])
                if pair is not None:
                    points.append(pair)
            for child in item.get("children", []) or []:
                walk(child)

        walk(node)
        return points

    def _coord_pair_from_children(self, children: list[Any]) -> tuple[float, float] | None:
        c1 = None
        c2 = None
        for child in children:
            if not isinstance(child, dict):
                continue
            qname = str(child.get("qname") or "")
            local = qname.rsplit("}", 1)[-1].lower() if qname else ""
            if local not in {"c1", "c2"}:
                continue
            text = child.get("text")
            if text is None:
                continue
            try:
                value = float(text)
            except Exception:
                continue
            if local == "c1":
                c1 = value
            elif local == "c2":
                c2 = value
        if c1 is None or c2 is None:
            return None
        return (c1, c2)

    def _reference_values(self, binding: _ModelBinding, record: dict[str, Any]) -> list[tuple[str, type[Any], str]]:
        refs: list[tuple[str, type[Any], str]] = []
        references = record.get("references") or {}
        for raw_name, target_tid in references.items():
            django_name = binding.fields_by_alias.get(str(raw_name).lower())
            if not django_name:
                continue
            target_model = binding.ref_targets.get(django_name)
            if target_model is None or not target_tid:
                continue
            refs.append((django_name, target_model, str(target_tid)))
        return refs

    def _child_values(self, binding: _ModelBinding, record: dict[str, Any], *, tid: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        children = record.get("children") or {}
        for child_key, child_records in children.items():
            if not isinstance(child_records, list) or not child_records:
                continue

            django_name = binding.fields_by_alias.get(str(child_key).lower())
            if not django_name:
                continue

            field_obj = binding.field_objects.get(django_name)
            if field_obj is None:
                continue

            # Child wrappers often encode a single aggregate geometry value for the parent field.
            geometry_value = None
            for child in child_records:
                if not isinstance(child, dict):
                    continue
                child_geometries = child.get("geometries") or {}
                if not isinstance(child_geometries, dict):
                    continue
                for geometry in child_geometries.values():
                    geometry_value = self._to_geometry(geometry, field_obj)
                    if geometry_value is not None:
                        break
                if geometry_value is not None:
                    break
            if geometry_value is not None:
                values[django_name] = geometry_value
                continue

            # Child wrappers can also encode scalar aggregate values (e.g. LokalisationName).
            if self._is_geometry_field(field_obj):
                continue

            scalar_value = None
            for child in child_records:
                if not isinstance(child, dict):
                    continue
                child_attributes = child.get("attributes") or {}
                if not isinstance(child_attributes, dict):
                    continue
                scalar_value = self._first_non_empty_scalar(child_attributes)
                if scalar_value is not None:
                    break
            if scalar_value is not None:
                values[django_name] = scalar_value

        return values

    def _first_non_empty_scalar(self, attributes: dict[str, Any]) -> Any | None:
        for value in attributes.values():
            if value is None:
                continue
            if isinstance(value, str) and value == "":
                continue
            return self._coerce_scalar(value)
        return None

    def _apply_known_model_fallbacks(self, binding: _ModelBinding, values: dict[str, Any]) -> None:
        if binding.class_ref != "DMAV_Gebaeudeadressen_V1_1.Gebaeudeadressen.Lokalisation":
            return

        if values.get("lokalisation_name") is None and values.get("strassenstueck") is not None:
            # TODO: Remove this once LokalisationName is mapped directly from source wrappers.
            values["lokalisation_name"] = values["strassenstueck"]

    def _upsert_row(
        self,
        router: Any,
        *,
        binding: _ModelBinding,
        tid: str,
        values: dict[str, Any],
        imported_counts: dict[str, int],
        continue_on_error: bool,
    ) -> None:
        try:
            router.upsert(binding.model, tid, values)
        except Exception as exc:
            self._last_import_diagnostics["upsert_errors"] = int(self._last_import_diagnostics["upsert_errors"] or 0) + 1
            if not self._last_import_diagnostics.get("reason"):
                self._last_import_diagnostics["reason"] = f"upsert error ({type(exc).__name__}) for {binding.class_ref} tid={tid}: {exc}"
            if continue_on_error:
                return
            self._last_import_diagnostics["mode"] = "failed_fast"
            raise

        imported_counts[binding.class_ref] = imported_counts.get(binding.class_ref, 0) + 1
        self._last_import_diagnostics["records_imported"] = int(self._last_import_diagnostics["records_imported"] or 0) + 1

    def _extract_imd_translations(self, metamodel: Any) -> dict[str, dict[str, str]]:
        translations: dict[str, dict[str, str]] = {}
        for model_translation in getattr(getattr(metamodel, "datasection", None), "ModelTranslation", []):
            for translation in getattr(model_translation, "translation", []):
                language = getattr(translation, "language", None)
                if not language:
                    continue
                for translated_entry in getattr(translation, "translations", []):
                    metranslation = getattr(translated_entry, "metranslation", None)
                    ref = getattr(getattr(metranslation, "of", None), "ref", None)
                    translated_name = getattr(metranslation, "translated_name", None)
                    if not ref or not translated_name:
                        continue
                    translations.setdefault(ref, {})[language] = translated_name
        return translations

    def _merge_imd_translations(self, incoming: dict[str, dict[str, str]]) -> None:
        for ref, language_map in incoming.items():
            self._imd_translations.setdefault(ref, {}).update(language_map)
