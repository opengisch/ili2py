from dataclasses import dataclass, field, make_dataclass
from typing import List

from ili2py.interfaces.interlis.common_generator import ModelDataGeneratorBase
from ili2py.interfaces.interlis.interlis_23 import TRANSFER


class DataClassGenerator(ModelDataGeneratorBase):

    def generate(self, model_name: str):
        """
        This is a factory method which produces dataclasses at runtime `make_dataclass`. The
        construction plan of the dataclasses is derived from the tree of dataclass objects
        which has to be created to be first.

        TODO: currently this makes no big sense since we usually want to read all models which can be
            in an XTF.

        Args:
            model_name: The name of the desired model name which the XTF is constructed from.

        Returns: The tree of dataclasses representing the structure of the XTF. This can be used to generate
            readers out of it.
        """
        model_data = self.find_model_by_name(model_name)
        topic_fields = []
        model_element = self._model_element(model_data)
        model_tid = getattr(model_element, "tid", None)
        for topic_item in self._topic_elements(model_data, model_tid):
            class_fields = [("bid", str, field(metadata={"name": "BID", "type": "Attribute"}))]
            for class_item in self._class_elements(model_data, getattr(topic_item, "tid", None)):
                attr_or_param_fields = self._record_fields(
                    model_data,
                    getattr(class_item, "tid", None),
                    tid_name="TID",
                    tid_namespace=None,
                    xml_namespace=None,
                )

                class_fields.append(
                    (
                        class_item.name.lower(),
                        List[make_dataclass(class_item.name, attr_or_param_fields)],
                        field(
                            default=None,
                            metadata={
                                "name": class_item.tid,
                                "type": "Element",
                                "default": None,
                            },
                        ),
                    )
                )
            topic_fields.append(
                (
                    topic_item.name.lower(),
                    make_dataclass(topic_item.name, class_fields),
                    field(metadata={"name": topic_item.tid, "type": "Element", "default": None}),
                )
            )

        @dataclass
        class XtfTransfer(TRANSFER):
            DATASECTION: make_dataclass("DATASECTION", fields=topic_fields)

        return XtfTransfer
