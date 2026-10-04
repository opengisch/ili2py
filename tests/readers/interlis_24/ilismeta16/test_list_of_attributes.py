import dataclasses
import os
import xml.etree.ElementTree as ET
from collections import Counter

import pytest

from ili2py.mappers.helpers import Index
from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.writers.py.python_structure import Class

IMD_NAMESPACE = "{http://www.interlis.ch/xtf/2.4/IlisMeta16}"

# The LIST OF and BAG OF attributes of IlisMeta16 whose elements are structures
LIST_OF_ATTRIBUTES = (
    "Documentation",
    "Derivates",
    "FormationParameter",
    "SubExpressions",
    "PathEls",
    "Cases",
    "ObjectClasses",
    "Arguments",
    "UniqueDef",
    "Assignments",
    "Rule",
    "TranslatedDoc",
    "Translations",
)


# The classes in which an existence constraint requires the value (INTERLIS 2.4), which the
# binding does not have
UNMAPPED_ATTRIBUTES = ("RequiredIn",)


def count_in_imd(imd_path: str) -> Counter:
    """Count the elements of each LIST OF attribute in the XML of an IMD."""
    counts = Counter()

    def visit(element):
        attribute = element.tag.removeprefix(IMD_NAMESPACE)
        if attribute in UNMAPPED_ATTRIBUTES:
            return
        if attribute in LIST_OF_ATTRIBUTES:
            counts[attribute] += len(element)
        for child in element:
            visit(child)

    visit(ET.parse(imd_path).getroot())
    return counts


def count_parsed(node, counts: Counter | None = None) -> Counter:
    """Count the elements of each LIST OF attribute in the parsed IMD."""
    counts = Counter() if counts is None else counts
    if isinstance(node, list):
        for item in node:
            count_parsed(item, counts)
    elif dataclasses.is_dataclass(node):
        for field in dataclasses.fields(node):
            value = getattr(node, field.name)
            attribute = field.metadata.get("name")
            if attribute in LIST_OF_ATTRIBUTES:
                for wrapper in value if isinstance(value, list) else [value]:
                    for elements_field in dataclasses.fields(wrapper):
                        elements = getattr(wrapper, elements_field.name)
                        if isinstance(elements, list):
                            counts[attribute] += len(elements)
                        elif elements is not None:
                            counts[attribute] += 1
            count_parsed(value, counts)
    return counts


@pytest.mark.parametrize(
    "imd_path",
    [
        "ilismeta16/IlisMeta16.imd",
        "models/KGK_Alles_V1_0.imd",
        "models/DMAVTYM_Alles_V1_1.imd",
        "models/SIA405_Abwasser_3D_2015_2_d-20211020/SIA405_Abwasser_3D_2015_2_d-20211020.imd",
        "models/ili2c/Constraints.imd",
    ],
)
def test_list_of_attributes_keep_all_their_elements(resource_path_root, imd_path):
    path = os.path.join(resource_path_root, imd_path)

    assert count_parsed(Imd16Reader().read(path)) == count_in_imd(path)


def test_path_keeps_all_its_elements(resource_path_root):
    metamodel = Imd16Reader().read(os.path.join(resource_path_root, "models/KGK_Alles_V1_0.imd"))
    view = Index(metamodel.datasection).index[
        "DMAV_Grundstuecke_V1_1.Grundstuecke.Liegenschaft_Gueltig"
    ]

    # DEFINED(Liegenschaft->Grundstueck->Entstehung) AND ...
    where = Class.translate_expression(view.where.choice).choice
    defined = where.sub_expressions[0].choice.sub_expressions[0].choice
    path_els = defined.sub_expression.choice.path_els
    assert [(path_el.kind, path_el.ref) for path_el in path_els] == [
        ("ViewBase", "DMAV_Grundstuecke_V1_1.Grundstuecke.Liegenschaft_Gueltig.Liegenschaft"),
        ("Role", "DMAV_Grundstuecke_V1_1.Grundstuecke.GrundstueckLiegenschaft.Grundstueck"),
        ("Role", "DMAV_Grundstuecke_V1_1.Grundstuecke.Entstehung_Grundstueck.Entstehung"),
    ]


def test_unique_constraint_keeps_all_its_attributes(resource_path_root):
    metamodel = Imd16Reader().read(os.path.join(resource_path_root, "models/KGK_Alles_V1_0.imd"))
    index = Index(metamodel.datasection)

    # UNIQUE NBIdent, Identifikator;
    (constraint,) = Class.translate_unique_constraint(
        ["DMAV_HoheitsgrenzenAV_V1_0.HoheitsgrenzenAV.HHGNachfuehrung.CH030101"], index
    )
    assert [factor["path_els"][-1]["ref"] for factor in constraint["unique_def"]] == [
        "DMAV_HoheitsgrenzenAV_V1_0.HoheitsgrenzenAV.HHGNachfuehrung.NBIdent",
        "DMAV_HoheitsgrenzenAV_V1_0.HoheitsgrenzenAV.HHGNachfuehrung.Identifikator",
    ]
