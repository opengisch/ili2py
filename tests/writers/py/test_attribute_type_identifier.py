import os

import pytest

from ili2py.mappers.helpers import Index
from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.writers.py.python_structure import Library

KGK = "models/KGK_Alles_V1_0.imd"
BODENBEDECKUNG = "DMAV_Bodenbedeckung_V1_1.Bodenbedeckung.Bodenbedeckung"


@pytest.fixture(scope="module")
def packages(resource_path_root):
    metamodel = Imd16Reader().read(os.path.join(resource_path_root, KGK))
    library = Library.from_imd(
        metamodel.datasection.ModelData, Index(metamodel.datasection), "kgk"
    )
    return {package.name: package for package in library.packages}


def attribute_of(packages, class_identifier, attribute_name):
    """The attribute of a class, on the model level or in a topic."""
    classes = [
        cls
        for package in packages.values()
        for module in [package, *package.modules]
        for cls in module.classes
    ]
    (cls,) = [cls for cls in classes if cls.identifier == class_identifier]
    (attribute,) = [attribute for attribute in cls.attributes if attribute.name == attribute_name]
    return attribute


@pytest.mark.parametrize(
    "class_identifier, attribute_name, types, type_identifier",
    [
        # a topic class taking a domain of its model, outside the topic
        (
            "KGKCGC_FPDS2_V1_1.FPDS2.FixpunktVersion",
            "HoeheZuv",
            ["KGKCGC_FPDS2_V1_1Zuverlaessigkeit"],
            "KGKCGC_FPDS2_V1_1.Zuverlaessigkeit",
        ),
        # a structure taking a domain of another model
        (
            "DMAVTYM_Grafik_V1_0.Textposition",
            "HReferenzpunkt",
            ["INTERLISHALIGNMENT"],
            "INTERLIS.HALIGNMENT",
        ),
        # a class taking a domain of its topic
        (
            BODENBEDECKUNG,
            "Bodenbedeckungsart",
            ["Bodenbedeckungsart"],
            "DMAV_Bodenbedeckung_V1_1.Bodenbedeckung.Bodenbedeckungsart",
        ),
    ],
)
def test_attribute_keeps_the_identifier_of_its_domain(
    packages, class_identifier, attribute_name, types, type_identifier
):
    attribute = attribute_of(packages, class_identifier, attribute_name)

    assert attribute.types == types
    assert attribute.type_identifier == type_identifier
    # the identifier of the enumeration of the domain
    assert type_identifier in {
        enumeration.identifier
        for package in packages.values()
        for module in [package, *package.modules]
        for enumeration in module.enumerations
    }


def test_attribute_of_a_type_of_its_own_keeps_the_tid_of_that_type(packages):
    attribute = attribute_of(packages, BODENBEDECKUNG, "Qualitaetsstandard")

    assert attribute.type_identifier == f"{BODENBEDECKUNG}.Qualitaetsstandard.TYPE"


def test_role_has_no_type_identifier(packages):
    assert attribute_of(packages, BODENBEDECKUNG, "Entstehung").type_identifier is None
