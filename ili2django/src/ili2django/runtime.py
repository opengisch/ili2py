"""Runtime bridge for optionally delegating IMD/XTF tasks to ili2py."""

from __future__ import annotations

from dataclasses import dataclass, field, make_dataclass
from datetime import date, datetime, time
from decimal import Decimal
import keyword
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from ili2py.mappers.helpers import Index
from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


ILI23_NAMESPACE = "http://www.interlis.ch/INTERLIS2.3"


@dataclass(frozen=True)
class _XtfFlavor:
    transfer_namespace: str
    transfer_name: str
    header_name: str
    data_name: str
    models_name: str
    model_name: str
    bid_attr_name: str
    tid_attr_name: str
    attr_namespace: str | None
    model_namespaces: dict[str, str] = field(default_factory=dict)

    def model_namespace(self, model_name: str) -> str:
        return self.model_namespaces.get(model_name, self.transfer_namespace)


XTF_FLAVOR_23 = _XtfFlavor(
    transfer_namespace=ILI23_NAMESPACE,
    transfer_name="TRANSFER",
    header_name="HEADERSECTION",
    data_name="DATASECTION",
    models_name="MODELS",
    model_name="MODEL",
    bid_attr_name="BID",
    tid_attr_name="TID",
    attr_namespace=None,
)


@dataclass(kw_only=True)
class _RefElement:
    class Meta:
        namespace = ILI23_NAMESPACE

    ref: str | None = field(default=None, metadata={"name": "REF", "type": "Attribute"})


@dataclass(kw_only=True)
class _HeaderModel:
    class Meta:
        namespace = ILI23_NAMESPACE

    name: str | None = field(default=None, metadata={"name": "NAME", "type": "Attribute"})
    version: str | None = field(default=None, metadata={"name": "VERSION", "type": "Attribute"})
    uri: str | None = field(default=None, metadata={"name": "URI", "type": "Attribute"})


@dataclass(kw_only=True)
class _HeaderModels:
    class Meta:
        namespace = ILI23_NAMESPACE

    choice: list[_HeaderModel] = field(
        default_factory=list,
        metadata={
            "type": "Elements",
            "choices": ({"name": "MODEL", "type": _HeaderModel, "namespace": ILI23_NAMESPACE},),
        },
    )


@dataclass(kw_only=True)
class _HeaderSection:
    class Meta:
        namespace = ILI23_NAMESPACE

    models: _HeaderModels = field(
        metadata={"name": "MODELS", "type": "Element", "namespace": ILI23_NAMESPACE}
    )
    sender: str | None = field(default=None, metadata={"name": "SENDER", "type": "Attribute"})
    version: str | None = field(default="2.3", metadata={"name": "VERSION", "type": "Attribute"})


@dataclass
class _MetaFieldSpec:
    django_name: str
    xml_name: str
    py_name: str
    kind: str
    python_type: type[Any]
    related_model: type[Any] | None = None


@dataclass
class _GeometryFieldSpec:
    django_name: str
    xml_name: str
    srid: int | None
    geom_type: str | None


@dataclass
class _ModelSpec:
    model: type[Any]
    model_name: str
    topic_name: str
    class_name: str
    record_type: type[Any]
    record_attr: str
    fields: list[_MetaFieldSpec]


@dataclass
class _TopicSpec:
    model_name: str
    topic_name: str
    basket_xml_name: str
    basket_type: type[Any]
    model_specs: list[_ModelSpec]


@dataclass
class _Schema:
    transfer_type: type[Any]
    datasection_type: type[Any]
    topics: list[_TopicSpec]
    topic_by_type: dict[type[Any], _TopicSpec]


class _RouterAdapter:
    def iter_models(self) -> list[type[Any]]:
        raise NotImplementedError

    def upsert(self, model: type[Any], tid: str, values: dict[str, Any]) -> None:
        raise NotImplementedError

    def set_reference(
        self,
        model: type[Any],
        source_tid: str,
        field_name: str,
        target_model: type[Any],
        target_tid: str,
    ) -> None:
        raise NotImplementedError


class _DjangoRouterAdapter(_RouterAdapter):
    def __init__(self) -> None:
        from django.apps import apps

        self._apps = apps

    def iter_models(self) -> list[type[Any]]:
        return list(self._apps.get_models())

    def upsert(self, model: type[Any], tid: str, values: dict[str, Any]) -> None:
        defaults = dict(values)
        defaults["tid"] = tid
        model.objects.update_or_create(tid=tid, defaults=defaults)

    def set_reference(
        self,
        model: type[Any],
        source_tid: str,
        field_name: str,
        target_model: type[Any],
        target_tid: str,
    ) -> None:
        source = model.objects.get(tid=source_tid)
        target = target_model.objects.get(tid=target_tid)
        setattr(source, field_name, target)
        source.save(update_fields=[field_name])


class _CustomRouterAdapter(_RouterAdapter):
    def __init__(self, router: Any) -> None:
        self._router = router

    def iter_models(self) -> list[type[Any]]:
        return list(self._router.iter_models())

    def upsert(self, model: type[Any], tid: str, values: dict[str, Any]) -> None:
        self._router.upsert(model, tid, values)

    def set_reference(
        self,
        model: type[Any],
        source_tid: str,
        field_name: str,
        target_model: type[Any],
        target_tid: str,
    ) -> None:
        self._router.set_reference(model, source_tid, field_name, target_model, target_tid)


class Ili2PyBridge:
    """Thin runtime adapter with a Pythonic API surface for generated projects."""

    def __init__(self, *, sender: str = "ili2django", xtf_version: str = "2.3") -> None:
        self.sender = sender
        self.xtf_version = xtf_version
        self._metamodel: Any | None = None
        self._index: Any | None = None
        self._imd_models: dict[str, dict[str, str | None]] = {}
        self._imd_translations: dict[str, dict[str, str]] = {}
        self._last_import_diagnostics: dict[str, str | int | None] = {
            "mode": None,
            "reason": None,
            "baskets_seen": 0,
            "records_seen": 0,
            "records_imported": 0,
            "upsert_errors": 0,
            "reference_errors": 0,
        }

    def get_last_import_diagnostics(self) -> dict[str, str | int | None]:
        """Return diagnostics for the most recent `import_xtf` call."""

        return dict(self._last_import_diagnostics)

    def read_imd(
        self,
        imd_path: str,
        *,
        translation_imd_paths: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """Read IMD and return minimal structured objects for runtime usage."""

        metamodel = Imd16Reader().read(imd_path)
        index = Index(metamodel.datasection)
        self._metamodel = metamodel
        self._index = index
        self._imd_models = self._extract_imd_model_metadata(metamodel)
        self._imd_translations = {}

        if translation_imd_paths:
            if isinstance(translation_imd_paths, str):
                translation_paths = [translation_imd_paths]
            else:
                translation_paths = list(translation_imd_paths)
            for translation_path in translation_paths:
                translation_metamodel = Imd16Reader().read(translation_path)
                self._merge_imd_translations(self._extract_imd_translations(translation_metamodel))

        return {
            "metamodel": metamodel,
            "index": index,
            "translations": self._imd_translations,
        }

    def get_translation_label(self, ref: str, language: str, default: str | None = None) -> str | None:
        """Resolve a translated label for non-export contexts (UI, docs, diagnostics)."""

        translations = self._imd_translations.get(ref, {})
        return translations.get(language, default)

    def get_export_label(self, _ref: str, base_label: str) -> str:
        """Return the base label used for XTF export.

        Export intentionally ignores translation overlays because extended models
        and translation models are complementary concerns.
        """

        return base_label

    def import_xtf(
        self,
        xtf_path: str,
        *,
        django_router: Any | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        """Import XTF into Django domain objects.

        Import/export use xsdata for XML parsing/serialization and build the XTF
        schema dynamically from `@interlis_model` and `ili_field` metadata.
        Geometry and other unsupported field types are skipped rather than parsed manually.
        """

        path = Path(xtf_path)
        if not path.exists():
            raise FileNotFoundError(f"XTF file not found: {xtf_path}")

        self._last_import_diagnostics = {
            "mode": "started",
            "reason": None,
            "continue_on_error": continue_on_error,
            "baskets_seen": 0,
            "records_seen": 0,
            "records_imported": 0,
            "upsert_errors": 0,
            "reference_errors": 0,
            "missing_geometry_values": 0,
            "missing_geometry_fields": [],
        }

        router = self._router_adapter(django_router)
        flavor = self._detect_xtf_flavor(path)
        schema = self._build_schema(router.iter_models(), flavor=flavor)
        geometry_specs = self._geometry_specs_for_schema(schema)
        geometry_values = self._extract_geometry_values(path, geometry_specs)
        parser = XmlParser(config=ParserConfig(fail_on_unknown_properties=False))
        try:
            transfer = parser.parse(str(path), schema.transfer_type)
            self._last_import_diagnostics["mode"] = "structured"
        except Exception as exc:
            self._last_import_diagnostics["mode"] = "parse_failed"
            self._last_import_diagnostics["reason"] = f"{type(exc).__name__}: {exc}"
            raise

        pending_refs: list[tuple[type[Any], str, str, type[Any], str]] = []
        imported_counts: dict[str, int] = {}
        datasection = getattr(transfer, "datasection", None)
        if datasection is None:
            self._last_import_diagnostics["mode"] = "empty_datasection"
            self._last_import_diagnostics["reason"] = "no DATASECTION found"
            return imported_counts

        for basket in getattr(datasection, "baskets", []):
            self._last_import_diagnostics["baskets_seen"] = int(self._last_import_diagnostics["baskets_seen"] or 0) + 1
            topic = schema.topic_by_type.get(type(basket))
            if topic is None:
                continue
            for model_spec in topic.model_specs:
                for record in getattr(basket, model_spec.record_attr, []):
                    self._last_import_diagnostics["records_seen"] = int(self._last_import_diagnostics["records_seen"] or 0) + 1
                    tid = getattr(record, "tid", None)
                    if not tid:
                        continue
                    scalar_values: dict[str, Any] = {}
                    for field_spec in model_spec.fields:
                        raw_value = getattr(record, field_spec.py_name, None)
                        if raw_value is None:
                            continue
                        if field_spec.kind == "ref":
                            ref_tid = getattr(raw_value, "ref", None)
                            if ref_tid:
                                pending_refs.append(
                                    (
                                        model_spec.model,
                                        tid,
                                        field_spec.django_name,
                                        field_spec.related_model,
                                        ref_tid,
                                    )
                                )
                            continue
                        scalar_values[field_spec.django_name] = raw_value
                    for geometry_spec in geometry_specs.get(model_spec.model, []):
                        geometry_value = geometry_values.get((tid, geometry_spec.xml_name))
                        if geometry_value is not None:
                            scalar_values[geometry_spec.django_name] = geometry_value
                            continue
                        self._last_import_diagnostics["missing_geometry_values"] = int(
                            self._last_import_diagnostics["missing_geometry_values"] or 0
                        ) + 1
                        missing_geometry_fields = self._last_import_diagnostics.setdefault(
                            "missing_geometry_fields", []
                        )
                        if len(missing_geometry_fields) < 25:
                            missing_geometry_fields.append(
                                {
                                    "tid": tid,
                                    "model": model_spec.model_name,
                                    "topic": model_spec.topic_name,
                                    "class": model_spec.class_name,
                                    "field": geometry_spec.django_name,
                                    "xml_name": geometry_spec.xml_name,
                                }
                            )
                    try:
                        router.upsert(model_spec.model, tid, scalar_values)
                    except Exception as exc:
                        self._last_import_diagnostics["upsert_errors"] = int(
                            self._last_import_diagnostics["upsert_errors"] or 0
                        ) + 1
                        error_reason = (
                            "upsert error "
                            f"({type(exc).__name__}) for "
                            f"{model_spec.model_name}.{model_spec.topic_name}.{model_spec.class_name} "
                            f"tid={tid}: {exc}"
                        )
                        if not self._last_import_diagnostics.get("reason"):
                            self._last_import_diagnostics["reason"] = error_reason
                        if continue_on_error:
                            continue
                        self._last_import_diagnostics["mode"] = "failed_fast"
                        raise
                    class_ref = f"{model_spec.model_name}.{model_spec.topic_name}.{model_spec.class_name}"
                    imported_counts[class_ref] = imported_counts.get(class_ref, 0) + 1
                    self._last_import_diagnostics["records_imported"] = int(
                        self._last_import_diagnostics["records_imported"] or 0
                    ) + 1

        for model, source_tid, field_name, target_model, target_tid in pending_refs:
            if target_model is None:
                continue
            try:
                router.set_reference(model, source_tid, field_name, target_model, target_tid)
            except Exception as exc:
                self._last_import_diagnostics["reference_errors"] = int(
                    self._last_import_diagnostics["reference_errors"] or 0
                ) + 1
                error_reason = (
                    "reference error "
                    f"({type(exc).__name__}) for {model.__name__} "
                    f"tid={source_tid} field={field_name} target_tid={target_tid}: {exc}"
                )
                if not self._last_import_diagnostics.get("reason"):
                    self._last_import_diagnostics["reason"] = error_reason
                if continue_on_error:
                    continue
                self._last_import_diagnostics["mode"] = "failed_fast"
                raise

        if not imported_counts:
            upsert_errors = int(self._last_import_diagnostics.get("upsert_errors") or 0)
            reference_errors = int(self._last_import_diagnostics.get("reference_errors") or 0)
            if upsert_errors or reference_errors:
                self._last_import_diagnostics["mode"] = "partial_failures"
                if not self._last_import_diagnostics.get("reason"):
                    self._last_import_diagnostics["reason"] = (
                        f"rows failed during import (upsert_errors={upsert_errors}, reference_errors={reference_errors})"
                    )
            else:
                self._last_import_diagnostics["mode"] = "no_matching_records"
                self._last_import_diagnostics["reason"] = (
                    "no records matched generated model/topic/class metadata"
                )
        else:
            self._last_import_diagnostics["mode"] = "structured"

        return imported_counts

    def export_xtf(self, xtf_path: str, *, queryset_provider: Any | None = None) -> None:
        """Export Django domain objects into XTF.

        Export always uses base-language values. Translation overlays are kept
        for lookup/UI usage and are intentionally not applied during serialization.
        Geometry and unsupported field types are omitted unless a richer schema generator exists.
        """

        target = Path(xtf_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        models = self._provider_models(queryset_provider)
        schema = self._build_schema(models)
        baskets_by_key: dict[tuple[str, str, str], Any] = {}

        for topic in schema.topics:
            for model_spec in topic.model_specs:
                for obj in self._iter_objects(queryset_provider, model_spec.model):
                    basket_id = self._basket_id(queryset_provider, model_spec, obj)
                    basket_key = (model_spec.model_name, model_spec.topic_name, basket_id)
                    basket = baskets_by_key.get(basket_key)
                    if basket is None:
                        basket = topic.basket_type(bid=basket_id)
                        baskets_by_key[basket_key] = basket

                    record_kwargs: dict[str, Any] = {"tid": getattr(obj, "tid", None)}
                    for field_spec in model_spec.fields:
                        value = getattr(obj, field_spec.django_name, None)
                        if value is None:
                            continue
                        if field_spec.kind == "ref":
                            ref_tid = getattr(value, "tid", None)
                            if ref_tid is None and isinstance(value, str):
                                ref_tid = value
                            if ref_tid is not None:
                                record_kwargs[field_spec.py_name] = _RefElement(ref=str(ref_tid))
                            continue
                        record_kwargs[field_spec.py_name] = value

                    getattr(basket, model_spec.record_attr).append(model_spec.record_type(**record_kwargs))

        model_names = sorted({topic.model_name for topic in schema.topics})
        header_models = _HeaderModels(
            choice=[
                _HeaderModel(
                    name=model_name,
                    version=self._imd_models.get(model_name, {}).get("version"),
                    uri=self._imd_models.get(model_name, {}).get("uri"),
                )
                for model_name in model_names
            ]
        )
        transfer = schema.transfer_type(
            headersection=_HeaderSection(models=header_models, sender=self.sender, version=self.xtf_version),
            datasection=schema.datasection_type(baskets=list(baskets_by_key.values())),
        )
        serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))
        xml = serializer.render(transfer, ns_map={None: ILI23_NAMESPACE})
        target.write_text(xml, encoding="utf-8")

    def _extract_imd_model_metadata(self, metamodel: Any) -> dict[str, dict[str, str | None]]:
        model_info: dict[str, dict[str, str | None]] = {}
        for model_data in getattr(getattr(metamodel, "datasection", None), "ModelData", []):
            for element in getattr(model_data, "choice", []):
                if type(element).__name__ != "Model":
                    continue
                model_info[element.name] = {
                    "version": getattr(element, "model_version", None),
                    "uri": getattr(element, "uri", None),
                }
                break
        return model_info

    def _extract_imd_translations(self, metamodel: Any) -> dict[str, dict[str, str]]:
        translation_info: dict[str, dict[str, str]] = {}
        for model_translation in getattr(getattr(metamodel, "datasection", None), "ModelTranslation", []):
            for translation in getattr(model_translation, "translation", []):
                language = getattr(translation, "language", None)
                if not language:
                    continue
                for translated_entry in getattr(translation, "translations", []):
                    metranslation = getattr(translated_entry, "metranslation", None)
                    if metranslation is None:
                        continue
                    ref = getattr(getattr(metranslation, "of", None), "ref", None)
                    translated_name = getattr(metranslation, "translated_name", None)
                    if not ref or not translated_name:
                        continue
                    translation_info.setdefault(ref, {})[language] = translated_name
        return translation_info

    def _merge_imd_translations(self, translation_info: dict[str, dict[str, str]]) -> None:
        for ref, language_map in translation_info.items():
            self._imd_translations.setdefault(ref, {}).update(language_map)

    def _router_adapter(self, django_router: Any | None) -> _RouterAdapter:
        if django_router is None:
            return _DjangoRouterAdapter()
        if hasattr(django_router, "iter_models") and hasattr(django_router, "upsert") and hasattr(
            django_router, "set_reference"
        ):
            return _CustomRouterAdapter(django_router)
        raise TypeError(
            "django_router must provide iter_models(), upsert(), and set_reference(), or be omitted."
        )

    def _provider_models(self, queryset_provider: Any | None) -> list[type[Any]]:
        if queryset_provider is not None and hasattr(queryset_provider, "iter_models"):
            return list(queryset_provider.iter_models())
        return _DjangoRouterAdapter().iter_models()

    def _iter_objects(self, queryset_provider: Any | None, model: type[Any]) -> list[Any]:
        if queryset_provider is not None:
            if hasattr(queryset_provider, "iter_objects"):
                return list(queryset_provider.iter_objects(model))
            if callable(queryset_provider):
                return list(queryset_provider(model))
        return list(model.objects.all())

    def _basket_id(self, queryset_provider: Any | None, model_spec: _ModelSpec, obj: Any) -> str:
        if queryset_provider is not None:
            if hasattr(queryset_provider, "basket_id"):
                return str(queryset_provider.basket_id(model_spec.model, obj))
            if hasattr(queryset_provider, "get_bid"):
                return str(queryset_provider.get_bid(model_spec.model, obj))
        return f"{model_spec.model_name}.{model_spec.topic_name}"

    def _build_schema(self, models: list[type[Any]], *, flavor: _XtfFlavor = XTF_FLAVOR_23) -> _Schema:
        grouped: dict[tuple[str, str], list[_ModelSpec]] = {}

        for model in models:
            model_meta = getattr(model, "__ili2django__", None)
            if not model_meta:
                continue
            oid = model_meta.get("oid")
            if not isinstance(oid, str) or oid.count(".") < 2:
                continue
            model_name, topic_name, class_name = oid.split(".", 2)
            model_namespace = flavor.model_namespace(model_name)
            field_specs = self._field_specs(model)
            record_type = self._record_type(
                model_name,
                topic_name,
                class_name,
                field_specs,
                flavor=flavor,
                model_namespace=model_namespace,
            )
            model_spec = _ModelSpec(
                model=model,
                model_name=model_name,
                topic_name=topic_name,
                class_name=class_name,
                record_type=record_type,
                record_attr=_safe_name(getattr(model, "__name__", class_name).lower()),
                fields=field_specs,
            )
            grouped.setdefault((model_name, topic_name), []).append(model_spec)

        topic_specs: list[_TopicSpec] = []
        topic_choices: list[dict[str, Any]] = []
        topic_by_type: dict[type[Any], _TopicSpec] = {}
        for (model_name, topic_name), model_specs in sorted(grouped.items()):
            model_namespace = flavor.model_namespace(model_name)
            basket_type = self._basket_type(
                model_name,
                topic_name,
                model_specs,
                flavor=flavor,
                model_namespace=model_namespace,
            )
            basket_xml_name = topic_name if flavor.transfer_name == "transfer" else f"{model_name}.{topic_name}"
            topic_spec = _TopicSpec(
                model_name=model_name,
                topic_name=topic_name,
                basket_xml_name=basket_xml_name,
                basket_type=basket_type,
                model_specs=model_specs,
            )
            topic_specs.append(topic_spec)
            topic_by_type[basket_type] = topic_spec
            topic_choices.append(
                {
                    "name": topic_spec.basket_xml_name,
                    "type": basket_type,
                    "namespace": model_namespace,
                }
            )

        if flavor.transfer_name == XTF_FLAVOR_23.transfer_name and flavor.transfer_namespace == XTF_FLAVOR_23.transfer_namespace:
            header_section_type = _HeaderSection
        else:
            header_section_type = self._header_section_type(flavor)
        datasection_type = make_dataclass(
            "DataSection",
            [
                (
                    "baskets",
                    list[Any],
                    field(default_factory=list, metadata={"type": "Elements", "choices": tuple(topic_choices)}),
                )
            ],
            namespace={
                "Meta": type("Meta", (), {"namespace": flavor.transfer_namespace, "name": flavor.data_name})
            },
            kw_only=True,
        )
        transfer_type = make_dataclass(
            "Transfer",
            [
                (
                    "headersection",
                    header_section_type,
                    field(
                        metadata={
                            "name": flavor.header_name,
                            "type": "Element",
                            "namespace": flavor.transfer_namespace,
                        }
                    ),
                ),
                (
                    "datasection",
                    datasection_type,
                    field(
                        metadata={
                            "name": flavor.data_name,
                            "type": "Element",
                            "namespace": flavor.transfer_namespace,
                        }
                    ),
                ),
            ],
            namespace={
                "Meta": type(
                    "Meta",
                    (),
                    {"namespace": flavor.transfer_namespace, "name": flavor.transfer_name},
                )
            },
            kw_only=True,
        )
        return _Schema(
            transfer_type=transfer_type,
            datasection_type=datasection_type,
            topics=topic_specs,
            topic_by_type=topic_by_type,
        )

    def _header_section_type(self, flavor: _XtfFlavor) -> type[Any]:
        model_entry_type = make_dataclass(
            "HeaderModelEntry",
            [("value", str | None, field(default=None, metadata={"type": "Text"}))],
            namespace={
                "Meta": type(
                    "Meta",
                    (),
                    {"namespace": flavor.transfer_namespace, "name": flavor.model_name},
                )
            },
            kw_only=True,
        )
        models_type = make_dataclass(
            "HeaderModels",
            [
                (
                    "choice",
                    list[model_entry_type],
                    field(
                        default_factory=list,
                        metadata={
                            "type": "Elements",
                            "choices": (
                                {
                                    "name": flavor.model_name,
                                    "type": model_entry_type,
                                    "namespace": flavor.transfer_namespace,
                                },
                            ),
                        },
                    ),
                )
            ],
            namespace={"Meta": type("Meta", (), {"namespace": flavor.transfer_namespace})},
            kw_only=True,
        )
        return make_dataclass(
            "HeaderSection",
            [
                (
                    "models",
                    models_type,
                    field(
                        metadata={
                            "name": flavor.models_name,
                            "type": "Element",
                            "namespace": flavor.transfer_namespace,
                        }
                    ),
                ),
                (
                    "wildcard",
                    list[object],
                    field(default_factory=list, metadata={"type": "Wildcard", "namespace": "##any"}),
                ),
            ],
            namespace={
                "Meta": type(
                    "Meta",
                    (),
                    {"namespace": flavor.transfer_namespace, "name": flavor.header_name},
                )
            },
            kw_only=True,
        )

    def _detect_xtf_flavor(self, xtf_path: Path) -> _XtfFlavor:
        namespace_map: dict[str, str] = {}
        root_tag: str | None = None
        for event, data in ET.iterparse(str(xtf_path), events=("start", "start-ns")):
            if event == "start-ns":
                prefix, uri = data
                namespace_map[prefix or ""] = uri
            elif event == "start":
                root_tag = str(data.tag)
                break

        if root_tag is None:
            return XTF_FLAVOR_23

        root_namespace, root_name = _split_tag(root_tag)
        if root_namespace and "/xtf/2.4/" in root_namespace and root_name.lower() == "transfer":
            model_namespaces = {
                prefix: uri
                for prefix, uri in namespace_map.items()
                if prefix and uri.startswith("http://www.interlis.ch/xtf/2.4/") and prefix not in {"ili", "geom", "xsi"}
            }
            return _XtfFlavor(
                transfer_namespace=root_namespace,
                transfer_name="transfer",
                header_name="headersection",
                data_name="datasection",
                models_name="models",
                model_name="model",
                bid_attr_name="bid",
                tid_attr_name="tid",
                attr_namespace=root_namespace,
                model_namespaces=model_namespaces,
            )

        return XTF_FLAVOR_23

    def _basket_type(
        self,
        model_name: str,
        topic_name: str,
        model_specs: list[_ModelSpec],
        *,
        flavor: _XtfFlavor,
        model_namespace: str,
    ) -> type[Any]:
        bid_metadata: dict[str, Any] = {"name": flavor.bid_attr_name, "type": "Attribute"}
        if flavor.attr_namespace:
            bid_metadata["namespace"] = flavor.attr_namespace
        basket_fields: list[tuple[str, Any, Any]] = [
            ("bid", str | None, field(default=None, metadata=bid_metadata))
        ]
        for model_spec in model_specs:
            record_element_name = (
                model_spec.class_name
                if flavor.transfer_name == "transfer"
                else f"{model_name}.{topic_name}.{model_spec.class_name}"
            )
            basket_fields.append(
                (
                    model_spec.record_attr,
                    list[model_spec.record_type],
                    field(
                        default_factory=list,
                        metadata={
                            "name": record_element_name,
                            "type": "Element",
                            "namespace": model_namespace,
                        },
                    ),
                )
            )
        return make_dataclass(
            f"{_safe_name(model_name)}_{_safe_name(topic_name)}Basket",
            basket_fields,
            namespace={"Meta": type("Meta", (), {"namespace": model_namespace})},
            kw_only=True,
        )

    def _record_type(
        self,
        model_name: str,
        topic_name: str,
        class_name: str,
        field_specs: list[_MetaFieldSpec],
        *,
        flavor: _XtfFlavor,
        model_namespace: str,
    ) -> type[Any]:
        tid_metadata: dict[str, Any] = {"name": flavor.tid_attr_name, "type": "Attribute"}
        if flavor.attr_namespace:
            tid_metadata["namespace"] = flavor.attr_namespace
        record_fields: list[tuple[str, Any, Any]] = [
            ("tid", str | None, field(default=None, metadata=tid_metadata))
        ]
        for field_spec in field_specs:
            field_type: Any = field_spec.python_type | None
            if field_spec.kind == "ref":
                field_type = _RefElement | None
            record_fields.append(
                (
                    field_spec.py_name,
                    field_type,
                    field(
                        default=None,
                        metadata={
                            "name": field_spec.xml_name,
                            "type": "Element",
                            "namespace": model_namespace,
                        },
                    ),
                )
            )
        record_meta: dict[str, Any] = {"namespace": model_namespace}
        if flavor.transfer_name == "transfer":
            record_meta["name"] = class_name
        return make_dataclass(
            f"{_safe_name(model_name)}_{_safe_name(topic_name)}_{_safe_name(class_name)}Record",
            record_fields,
            namespace={"Meta": type("Meta", (), record_meta)},
            kw_only=True,
        )

    def _field_specs(self, model: type[Any]) -> list[_MetaFieldSpec]:
        specs: list[_MetaFieldSpec] = []
        for field_obj in self._iter_model_fields(model):
            field_meta = getattr(field_obj, "_ili2django", None)
            if not field_meta:
                continue
            xml_name = str(field_meta.get("oid", "")).split(".")[-1]
            django_name = getattr(field_obj, "name", None)
            if not xml_name or not django_name:
                continue
            # TID is represented as a dedicated transfer attribute and must not
            # be duplicated as a regular element field in record dataclasses.
            if django_name == "tid" or xml_name.lower() == "tid":
                continue
            kind, python_type, related_model = self._field_kind(field_obj)
            if kind == "unsupported":
                continue
            specs.append(
                _MetaFieldSpec(
                    django_name=django_name,
                    xml_name=xml_name,
                    py_name=_safe_name(xml_name.lower()),
                    kind=kind,
                    python_type=python_type,
                    related_model=related_model,
                )
            )
        return specs

    def _geometry_specs_for_schema(self, schema: _Schema) -> dict[type[Any], list[_GeometryFieldSpec]]:
        specs_by_model: dict[type[Any], list[_GeometryFieldSpec]] = {}
        seen_models: set[type[Any]] = set()
        for topic in schema.topics:
            for model_spec in topic.model_specs:
                if model_spec.model in seen_models:
                    continue
                seen_models.add(model_spec.model)
                specs = self._geometry_field_specs(model_spec.model)
                if specs:
                    specs_by_model[model_spec.model] = specs
        return specs_by_model

    def _geometry_field_specs(self, model: type[Any]) -> list[_GeometryFieldSpec]:
        specs: list[_GeometryFieldSpec] = []
        for field_obj in self._iter_model_fields(model):
            field_meta = getattr(field_obj, "_ili2django", None)
            if not field_meta:
                continue
            xml_name = str(field_meta.get("oid", "")).split(".")[-1]
            django_name = getattr(field_obj, "name", None)
            if not xml_name or not django_name:
                continue
            if not self._is_geometry_field(field_obj):
                continue
            srid = getattr(field_obj, "srid", None)
            if not isinstance(srid, int):
                srid = None
            geom_type = getattr(field_obj, "geom_type", None)
            if geom_type is not None:
                geom_type = str(geom_type)
            specs.append(
                _GeometryFieldSpec(
                    django_name=django_name,
                    xml_name=xml_name,
                    srid=srid,
                    geom_type=geom_type,
                )
            )
        return specs

    def _is_geometry_field(self, field_obj: Any) -> bool:
        internal_type = None
        if hasattr(field_obj, "get_internal_type"):
            try:
                internal_type = field_obj.get_internal_type()
            except Exception:
                internal_type = None
        if internal_type is None:
            internal_type = type(field_obj).__name__
        geometry_types = {
            "GeometryField",
            "PointField",
            "LineStringField",
            "PolygonField",
            "MultiPointField",
            "MultiLineStringField",
            "MultiPolygonField",
            "GeometryCollectionField",
            "CircularStringField",
            "CompoundCurveField",
            "CurvePolygonField",
            "MultiCurveField",
            "MultiSurfaceField",
        }
        return str(internal_type) in geometry_types

    def _extract_geometry_values(
        self,
        xtf_path: Path,
        specs_by_model: dict[type[Any], list[_GeometryFieldSpec]],
    ) -> dict[tuple[str, str], Any]:
        specs: list[_GeometryFieldSpec] = []
        for model_specs in specs_by_model.values():
            specs.extend(model_specs)
        if not specs:
            return {}

        target_names = {spec.xml_name for spec in specs}
        spec_by_xml_name: dict[str, _GeometryFieldSpec] = {}
        for spec in specs:
            spec_by_xml_name.setdefault(spec.xml_name, spec)

        values: dict[tuple[str, str], Any] = {}
        root = ET.parse(str(xtf_path)).getroot()
        for element in root.iter():
            tid = self._extract_tid(element)
            if not tid:
                continue
            for child in list(element):
                _, child_name = _split_tag(str(child.tag))
                if child_name not in target_names:
                    continue
                geometry_spec = spec_by_xml_name.get(child_name)
                if geometry_spec is None:
                    continue
                geometry_value = self._parse_geometry_element(child, geometry_spec)
                if geometry_value is None:
                    continue
                values[(tid, child_name)] = geometry_value
        return values

    def _extract_tid(self, element: ET.Element) -> str | None:
        for attr_name, attr_value in element.attrib.items():
            _, local_name = _split_tag(str(attr_name))
            if local_name.lower() == "tid":
                value = str(attr_value).strip()
                return value or None
        return None

    def _parse_geometry_element(
        self,
        geometry_element: ET.Element,
        geometry_spec: _GeometryFieldSpec,
    ) -> Any | None:
        try:
            from django.contrib.gis.geos import LinearRing, Polygon
        except Exception:
            return None

        surface = None
        for element in geometry_element.iter():
            _, name = _split_tag(str(element.tag))
            if name == "surface":
                surface = element
                break
        if surface is None:
            return None

        exterior = None
        for element in surface:
            _, name = _split_tag(str(element.tag))
            if name == "exterior":
                exterior = element
                break
        if exterior is None:
            return None

        polyline = None
        for element in exterior:
            _, name = _split_tag(str(element.tag))
            if name == "polyline":
                polyline = element
                break
        if polyline is None:
            return None

        coords: list[tuple[float, float]] = []
        for coord in polyline:
            _, coord_name = _split_tag(str(coord.tag))
            if coord_name != "coord":
                continue
            c1 = None
            c2 = None
            for axis in coord:
                _, axis_name = _split_tag(str(axis.tag))
                if axis_name == "c1" and axis.text is not None:
                    c1 = float(axis.text)
                elif axis_name == "c2" and axis.text is not None:
                    c2 = float(axis.text)
            if c1 is None or c2 is None:
                continue
            coords.append((c1, c2))

        if len(coords) < 3:
            return None
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        try:
            ring = LinearRing(coords)
            polygon = Polygon(ring)
        except Exception:
            return None

        polygon_wkt = polygon.wkt
        linear_ring_text = polygon_wkt.removeprefix("POLYGON((").removesuffix("))")

        geom_type = (geometry_spec.geom_type or "").upper()
        if "CURVEPOLYGON" in geom_type:
            wkt_body = f"CURVEPOLYGON(({linear_ring_text}))"
        elif "MULTIPOLYGON" in geom_type or "MULTISURFACE" in geom_type:
            wkt_body = f"MULTIPOLYGON((({linear_ring_text})))"
        else:
            wkt_body = polygon_wkt

        if geometry_spec.srid is not None:
            return f"SRID={geometry_spec.srid};{wkt_body}"
        return wkt_body

    def _iter_model_fields(self, model: type[Any]) -> list[Any]:
        meta = getattr(model, "_meta", None)
        if meta is None:
            return []
        if hasattr(meta, "get_fields"):
            return [field_obj for field_obj in meta.get_fields() if getattr(field_obj, "name", None)]
        return list(getattr(meta, "fields", []))

    def _field_kind(self, field_obj: Any) -> tuple[str, type[Any], type[Any] | None]:
        internal_type = None
        if hasattr(field_obj, "get_internal_type"):
            try:
                internal_type = field_obj.get_internal_type()
            except Exception:
                internal_type = None
        if internal_type is None:
            internal_type = type(field_obj).__name__

        related_model = getattr(field_obj, "related_model", None)
        if related_model is None:
            remote_field = getattr(field_obj, "remote_field", None)
            related_model = getattr(remote_field, "model", None)
        if related_model is not None:
            return "ref", str, related_model

        mapping: dict[str, type[Any]] = {
            "CharField": str,
            "TextField": str,
            "SlugField": str,
            "UUIDField": str,
            "IntegerField": int,
            "BigIntegerField": int,
            "SmallIntegerField": int,
            "PositiveIntegerField": int,
            "PositiveSmallIntegerField": int,
            "FloatField": float,
            "DecimalField": Decimal,
            "BooleanField": bool,
            "NullBooleanField": bool,
            "DateField": date,
            "DateTimeField": datetime,
            "TimeField": time,
        }
        python_type = mapping.get(internal_type)
        if python_type is None:
            return "unsupported", str, None
        return "scalar", python_type, None


def _safe_name(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)
    if not token:
        return "value"
    if token[0].isdigit():
        token = f"x_{token}"
    if keyword.iskeyword(token):
        token = f"{token}_field"
    return token


def _split_tag(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{") and "}" in tag:
        namespace, name = tag[1:].split("}", 1)
        return namespace, name
    return None, tag
