from decimal import Decimal
from dataclasses import field, make_dataclass
from typing import Any, List, Optional

from ili2py.interfaces.interlis.interlis_24.ilismeta16 import ImdTransfer
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.model_data import (
    ModelDataType,
)


class ModelDataGeneratorBase:

    def _python_type_for_num_type(self, type_item):
        numeric_bounds = [getattr(type_item, "min", None), getattr(type_item, "max", None)]
        for bound in numeric_bounds:
            if bound is None:
                continue
            bound_str = str(bound)
            if any(token in bound_str.lower() for token in (".", "e")):
                return Decimal
        return int

    def __init__(self, meta_model: ImdTransfer):
        self.meta_model = meta_model

    def _model_baskets(self):
        return getattr(getattr(self.meta_model, "datasection", None), "ModelData", [])

    def _basket_elements(self, basket):
        return getattr(basket, "choice", [])

    def _elements_of_type(self, basket, type_name: str):
        return [element for element in self._basket_elements(basket) if type(element).__name__ == type_name]

    def _model_element(self, basket):
        for element in self._basket_elements(basket):
            if type(element).__name__ == "Model":
                return element
        raise LookupError("No Model element found in basket.")

    def _ref_value(self, value):
        if value is None:
            return None
        ref = getattr(value, "ref", None)
        if ref is not None:
            return ref
        nested = getattr(value, "attr_or_param_type", None)
        if nested is not None:
            return getattr(nested, "ref", None)
        return None

    def _topic_elements(self, basket, model_tid: str):
        return [
            element
            for element in self._elements_of_type(basket, "SubModel")
            if getattr(getattr(element, "element_in_package", None), "ref", None) == model_tid
        ]

    def _class_elements(self, basket, topic_tid: str):
        return [
            element
            for element in self._elements_of_type(basket, "Class")
            if getattr(getattr(element, "element_in_package", None), "ref", None) == topic_tid
            and getattr(element, "kind", None) == "Class"
        ]

    def _attributes_for_class(self, basket, class_tid: str):
        return [
            element
            for element in self._elements_of_type(basket, "AttrOrParam")
            if getattr(getattr(element, "attr_parent", None), "ref", None) == class_tid
        ]

    def _types_by_tid(self, basket, type_name: str):
        return {getattr(element, "tid", None): element for element in self._elements_of_type(basket, type_name)}

    def _classes_by_tid(self, basket):
        return {getattr(element, "tid", None): element for element in self._elements_of_type(basket, "Class")}

    def _ordered_attribute_refs(self, basket, class_tid: str):
        refs: list[tuple[int, str]] = []
        for transfer_element in self._elements_of_type(basket, "TransferElement"):
            if getattr(getattr(transfer_element, "transfer_class", None), "ref", None) != class_tid:
                continue
            transfer_target = getattr(transfer_element, "transfer_element", None)
            ref = getattr(transfer_target, "ref", None)
            order_pos = getattr(transfer_target, "order_pos", None)
            try:
                order = int(order_pos)
            except (TypeError, ValueError):
                order = len(refs) + 1
            if ref:
                refs.append((order, ref))
        refs.sort(key=lambda item: item[0])
        return [ref for _, ref in refs]

    def _ordered_attributes(self, basket, class_tid: str):
        attr_by_tid = {
            getattr(attr, "tid", None): attr
            for attr in self._attributes_for_class(basket, class_tid)
        }
        ordered_attr_refs = self._ordered_attribute_refs(basket, class_tid)
        ordered_attrs = [attr_by_tid[ref] for ref in ordered_attr_refs if ref in attr_by_tid]
        if not ordered_attrs:
            ordered_attrs = list(attr_by_tid.values())
        return ordered_attrs

    def _attribute_field_specs(self, basket, class_tid: str):
        text_types = self._types_by_tid(basket, "TextType")
        num_types = self._types_by_tid(basket, "NumType")
        multi_value_types = self._types_by_tid(basket, "MultiValue")
        field_specs = []
        for attr_or_param_item in self._ordered_attributes(basket, class_tid):
            type_ref = self._ref_value(getattr(attr_or_param_item, "type_value", None))
            type_item = text_types.get(type_ref) or num_types.get(type_ref) or multi_value_types.get(type_ref)
            if type_item is None:
                continue
            mandatory = bool(getattr(type_item, "mandatory", False))
            attr_name = getattr(attr_or_param_item, "name", "").lower()
            xml_name = getattr(attr_or_param_item, "name", None)
            if not attr_name or not xml_name:
                continue
            type_name = type(type_item).__name__
            if type_name == "TextType":
                field_specs.append(("scalar", attr_name, xml_name, str, mandatory, type_item))
                continue
            if type_name == "NumType":
                python_type: Any = self._python_type_for_num_type(type_item)
                field_specs.append(("scalar", attr_name, xml_name, python_type, mandatory, type_item))
                continue
            if type_name == "MultiValue":
                field_specs.append(("multivalue", attr_name, xml_name, None, mandatory, type_item))
        return field_specs

    def find_model_by_name(self, model_name: str) -> ModelDataType:
        for model_data in self._model_baskets():
            for element in self._basket_elements(model_data):
                if type(element).__name__ != "Model":
                    continue
                if model_name == getattr(element, "name", None):
                    return model_data
        raise LookupError(f"No model with name {model_name} could be found.")

    def _record_fields(
        self,
        basket: ModelDataType,
        class_tid: str,
        *,
        tid_name: str,
        tid_namespace: str | None,
        xml_namespace: str | None,
    ):
        tid_metadata = {"name": tid_name, "type": "Attribute"}
        if tid_namespace is not None:
            tid_metadata["namespace"] = tid_namespace
        attr_or_param_fields: list[tuple[str, Any, Any]] = [
            ("tid", Optional[str], field(default=None, metadata=tid_metadata))
        ]
        for field_kind, attr_name, xml_name, python_type, mandatory, _type_item in self._attribute_field_specs(basket, class_tid):
            if field_kind != "scalar":
                continue
            metadata = {"name": xml_name, "type": "Element", "required": mandatory}
            if xml_namespace is not None:
                metadata["namespace"] = xml_namespace
            field_def = field(metadata=metadata) if mandatory else field(default=None, metadata=metadata)
            field_tuple = (attr_name, python_type if mandatory else Optional[python_type], field_def)
            if mandatory:
                attr_or_param_fields.insert(0, field_tuple)
            else:
                attr_or_param_fields.append(field_tuple)
        return attr_or_param_fields
