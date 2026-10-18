from dataclasses import dataclass, field

from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.abstract_element import (
    MetaAttributeElement,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.constraints import (
    SimpleConstraint,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.extendable_me import (  # noqa: E501
    AttrOrParam,
    DataUnit,
    EnumNode,
    Unit,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.domain_type.class_related_type.class_related_type import (  # noqa: E501
    ClassRefType,
    ObjectType,
    ReferenceType,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.domain_type.class_related_type.role import (  # noqa: E501
    Role,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.domain_type.domain_type import (  # noqa: E501
    AxisSpec,
    BlackboxType,
    BooleanType,
    CoordType,
    EnumType,
    FormattedType,
    LineType,
    MultiValue,
    NumType,
    TextType,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.type_class import (  # noqa: E501
    BaseClass,
    Class,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.line_form import (
    LineForm,
    LinesForm,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.package.package import (
    Model,
    SubModel,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.shared import imd_namespace_map


@dataclass
class ModelDataType:
    bid: str = field(metadata={"type": "Attribute", "namespace": imd_namespace_map["ili"]})
    Model: "Model" = field(metadata={"namespace": imd_namespace_map["IlisMeta16"]})
    # TODO: Keep an eye on requested list length (as of meta model docs list of sub_model has
    #  to be at least 1)
    SubModel: list["SubModel"] = field(default_factory=list)
    DataUnit: list["DataUnit"] | None = None
    MetaAttribute: list[MetaAttributeElement] | None = field(default_factory=list)
    consistency: str | None = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": imd_namespace_map["ili"],
        },
    )
    Class: list["Class"] | None = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    AttrOrParam: list["AttrOrParam"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    TextType: list["TextType"] | None = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    EnumNode: list["EnumNode"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    EnumType: list["EnumType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    NumType: list["NumType"] | None = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    AxisSpec: list["AxisSpec"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    CoordType: list["CoordType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    BaseClass: list["BaseClass"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    ObjectType: list["ObjectType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    ClassRefType: list["ClassRefType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    MultiValue: list["MultiValue"] | None = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    BooleanType: list["BooleanType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    FormattedType: list["FormattedType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    LinesForm: list["LinesForm"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    LineType: list["LineType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    LineForm: list["LineForm"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    Role: list["Role"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    SimpleConstraint: list["SimpleConstraint"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    ReferenceType: list["ReferenceType"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    BlackboxType: list["BlackboxType"] | None = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    Unit: list["Unit"] = field(
        default_factory=list, metadata={"namespace": imd_namespace_map["IlisMeta16"]}
    )
    # TODO: Add Views
