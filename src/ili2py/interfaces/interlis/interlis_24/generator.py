from dataclasses import dataclass, field, make_dataclass
from typing import Any, List, Optional

from ili2py.interfaces.interlis.common_generator import ModelDataGeneratorBase
from ili2py.interfaces.interlis.interlis_24 import Transfer, namespace_map


class DataClassGenerator(ModelDataGeneratorBase):

    def generate(self, model_name: str):
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
                record_fields = self._record_fields(
                    model_data,
                    getattr(class_item, "tid", None),
                    tid_name="tid",
                    tid_namespace=namespace_map["ili"],
                    xml_namespace=model_namespace,
                )
                record_type = make_dataclass(
                    class_item.name,
                    record_fields,
                    namespace={"Meta": type("Meta", (), {"namespace": model_namespace, "name": class_item.name})},
                    kw_only=True,
                )
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
            datasection: data_section_type = field(
                metadata={"name": "datasection", "type": "Element", "namespace": namespace_map["ili"]}
            )

        return XtfTransfer24
