from dataclasses import dataclass, field

from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.abstract_element import (
    AbstractElement,
    DocTextElement,
    MetaAttributeElement,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.references import HasRef, Ref
from ili2py.interfaces.interlis.interlis_24.ilismeta16.shared import imd_namespace_map


@dataclass(kw_only=True)
class MetaElement(HasRef, AbstractElement):
    Name: str = field(
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        }
    )
    tid: str = field(metadata={"type": "Attribute", "namespace": imd_namespace_map["ili"]})
    Documentation: list["MetaElement._Documentation"] | None = field(
        default_factory=list,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )
    MetaAttribute: list[MetaAttributeElement] | None = field(
        default_factory=list,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )
    # use the metadata.name to fetch the element from XML but store it
    #   as `*_ref` instance variable to resolve soft reference to actual object
    ElementInPackage_ref: Ref | None = field(
        default=None,
        metadata={"name": "ElementInPackage"},
    )

    @dataclass
    class _Documentation:
        DocText: DocTextElement = field(
            metadata={
                "name": "DocText",
                "type": "Element",
                "namespace": imd_namespace_map["IlisMeta16"],
            },
        )
