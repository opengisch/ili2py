from dataclasses import dataclass, field

from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.expression.expression import (  # noqa: E501
    CompoundExpr,
    UnaryExpr,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.model_data.extendable_me.type.expression.factor.factor import (  # noqa: E501
    Constant,
    UnitFunction,
    UnitRef,
)
from ili2py.interfaces.interlis.interlis_24.ilismeta16.shared import imd_namespace_map


@dataclass
class ConstantElement:
    Constant: "Constant" = field(
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        }
    )


@dataclass
class UnaryExprElement:
    UnaryExpr: "UnaryExpr" = field(
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        }
    )


@dataclass
class UnitRefElement:
    UnitRef: "UnitRef" = field(
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        }
    )


@dataclass
class CompoundExprElement:
    CompoundExpr: "CompoundExpr | None" = field(
        default=None,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )
    UnaryExpression: "UnaryExpr | None" = field(
        default=None,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )


@dataclass
class UnitFunctionElement:
    UnitFunction: "UnitFunction" = field(
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        }
    )


@dataclass
class MultiplicityElement:
    # TODO: *Optional* seems to be wrong regarding to ilismeta model
    Min: int | None = field(
        default=None,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )
    Max: int | None = field(
        default=None,
        metadata={
            "namespace": imd_namespace_map["IlisMeta16"],
        },
    )
