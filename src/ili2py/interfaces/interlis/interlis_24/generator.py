from dataclasses import dataclass, field, make_dataclass
from typing import Any, List, Optional

from ili2py.interfaces.interlis.common_generator import ModelDataGeneratorBase
from ili2py.interfaces.interlis.interlis_24 import Transfer, namespace_map


@dataclass(kw_only=True)
class _RefElement24:
    class Meta:
        namespace = namespace_map["ili"]

    ref: str | None = field(default=None, metadata={"name": "ref", "type": "Attribute", "namespace": namespace_map["ili"]})


@dataclass(kw_only=True)
class _GeometryElement24:
    content: list[object] = field(default_factory=list, metadata={"type": "Wildcard", "namespace": "##any"})


class DataClassGenerator(ModelDataGeneratorBase):
    """Generate xsdata-compatible dataclasses for INTERLIS 2.4 XTF payloads."""

    def __init__(self, meta_model):
        super().__init__(meta_model)
        self._structure_cache: dict[tuple[str, str], type[Any]] = {}
        self._class_context_cache: dict[str, tuple[Any, Any] | None] = {}

    def _class_context(self, class_tid: str):
        if class_tid in self._class_context_cache:
            return self._class_context_cache[class_tid]

        for model_data in self._model_baskets():
            class_item = self._classes_by_tid(model_data).get(class_tid)
            if class_item is not None:
                ctx = (model_data, class_item)
                self._class_context_cache[class_tid] = ctx
                return ctx

        self._class_context_cache[class_tid] = None
        return None

    def _namespace_for_tid(self, class_tid: str) -> str:
        model_name = class_tid.split(".", 1)[0]
        return f"http://www.interlis.ch/xtf/2.4/{model_name}"

    def _structure_record_type(self, model_data, class_tid: str, model_namespace: str):
        """Create or reuse a dataclass for one class/structure tid.

        The generated record type includes scalar/reference/geometry fields and
        recursively materialized multivalue wrapper types.
        """
        cache_key = (class_tid, model_namespace)
        cached = self._structure_cache.get(cache_key)
        if cached is not None:
            return cached

        class_ctx = self._class_context(class_tid)
        if class_ctx is None:
            raise LookupError(f"No class with tid {class_tid} could be found.")
        class_model_data, class_item = class_ctx

        record_fields = self._record_fields(
            class_model_data,
            class_tid,
            tid_name="tid",
            tid_namespace=namespace_map["ili"],
            xml_namespace=model_namespace,
            ref_python_type=_RefElement24,
            geometry_python_type=_GeometryElement24,
        )

        for field_kind, attr_name, xml_name, _python_type, mandatory, type_item in self._attribute_field_specs(class_model_data, class_tid):
            if field_kind != "multivalue":
                continue
            base_ref = getattr(getattr(type_item, "base_type", None), "ref", None)
            if not base_ref:
                continue
            if self._class_context(base_ref) is None:
                continue
            child_namespace = self._namespace_for_tid(base_ref)
            child_type = self._structure_record_type(class_model_data, base_ref, child_namespace)
            wrapper_type = make_dataclass(
                f"{class_item.name}_{xml_name}Wrapper",
                [
                    (
                        "items",
                        List[child_type],
                        field(
                            default_factory=list,
                            metadata={
                                "type": "Elements",
                                "choices": (
                                    {
                                        "name": child_type.__name__,
                                        "type": child_type,
                                        "namespace": child_namespace,
                                    },
                                ),
                            },
                        ),
                    )
                ],
                namespace={"Meta": type("Meta", (), {"namespace": model_namespace})},
                kw_only=True,
            )
            metadata = {"name": xml_name, "type": "Element", "namespace": model_namespace, "required": mandatory}
            field_def = field(metadata=metadata) if mandatory else field(default=None, metadata=metadata)
            field_tuple = (attr_name, wrapper_type if mandatory else Optional[wrapper_type], field_def)
            if mandatory:
                record_fields.insert(0, field_tuple)
            else:
                record_fields.append(field_tuple)

        record_type = make_dataclass(
            class_item.name,
            record_fields,
            namespace={"Meta": type("Meta", (), {"namespace": model_namespace, "name": class_item.name})},
            kw_only=True,
        )
        self._structure_cache[cache_key] = record_type
        return record_type

    def _basket_choices_for_model(self, model_name: str) -> list[dict[str, Any]]:
        model_data = self.find_model_by_name(model_name)
        model_element = self._model_element(model_data)
        model_tid = getattr(model_element, "tid", None)
        if model_tid is None:
            raise LookupError(f"Model {model_name} has no tid.")

        model_namespace = f"http://www.interlis.ch/xtf/2.4/{model_name}"
        basket_choices: list[dict[str, Any]] = []

        for topic_item in self._topic_elements(model_data, model_tid):
            basket_fields: list[tuple[str, Any, Any]] = [
                (
                    "bid",
                    Optional[str],
                    field(
                        default=None,
                        metadata={
                            "name": "bid",
                            "type": "Attribute",
                            "namespace": namespace_map["ili"],
                        },
                    ),
                )
            ]

            for class_item in self._class_elements(model_data, getattr(topic_item, "tid", None)):
                record_type = self._structure_record_type(model_data, getattr(class_item, "tid", None), model_namespace)
                basket_fields.append(
                    (
                        class_item.name.lower(),
                        List[record_type],
                        field(
                            default_factory=list,
                            metadata={
                                "name": class_item.name,
                                "type": "Element",
                                "namespace": model_namespace,
                            },
                        ),
                    )
                )

            basket_type = make_dataclass(
                topic_item.name,
                basket_fields,
                namespace={"Meta": type("Meta", (), {"namespace": model_namespace, "name": topic_item.name})},
                kw_only=True,
            )
            basket_choices.append({"name": topic_item.name, "type": basket_type, "namespace": model_namespace})

        return basket_choices

    def _build_transfer_type(self, basket_choices: list[dict[str, Any]]):
        data_section_type = make_dataclass(
            "DataSection",
            [
                (
                    "baskets",
                    List[Any],
                    field(default_factory=list, metadata={"type": "Elements", "choices": tuple(basket_choices)}),
                )
            ],
            namespace={"Meta": type("Meta", (), {"namespace": namespace_map["ili"], "name": "datasection"})},
            kw_only=True,
        )

        @dataclass(kw_only=True)
        class XtfTransfer24(Transfer):
            class Meta:
                name = "transfer"
                namespace = namespace_map["ili"]

            datasection: data_section_type = field(
                metadata={"name": "datasection", "type": "Element", "namespace": namespace_map["ili"]}
            )

        return XtfTransfer24

    def generate(self, model_name: str):
        """Build a dynamic Transfer subclass tailored to one model name."""
        return self._build_transfer_type(self._basket_choices_for_model(model_name))

    def generate_many(self, model_names: list[str]):
        """Build a Transfer subclass covering baskets for multiple models."""
        basket_choices: list[dict[str, Any]] = []
        for model_name in model_names:
            basket_choices.extend(self._basket_choices_for_model(model_name))
        return self._build_transfer_type(basket_choices)
