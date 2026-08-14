from pathlib import Path

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader


def test_reader_parses_redefined_attribute_kept_in_origin_model_namespace():
    """Regression test for a class extension (INTERLIS EXTENDS) that redefines
    an inherited attribute's enumeration type.

    `KGK_Einzelobjekte_V1_0.Einzelobjekt` extends `DMAV_Einzelobjekte_V1_1.Einzelobjekt`
    and redefines its `Einzelobjektart` attribute to widen the enumeration. INTERLIS
    keeps such redefined attributes tagged under the XML namespace of the model where
    they were first declared (DMAV_Einzelobjekte_V1_1), not the extending model
    (KGK_Einzelobjekte_V1_0). If the generated dataclass field's namespace metadata
    does not match, xsdata fails to bind the (mandatory) element and parsing raises
    `TypeError: Einzelobjekt.__init__() missing 1 required keyword-only argument:
    'einzelobjektart'`.
    """
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "KGK_Alles_V1_0.imd"
    xtf_path = repo_root.parent / "data" / "KGK_Testdaten_20260608.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["KGK_Einzelobjekte_V1_0"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Einzelobjekte")
    records = getattr(basket, "einzelobjekt", [])

    assert records
    assert all(getattr(record, "einzelobjektart", None) for record in records)


def test_reader_parses_purely_inherited_attribute_not_redeclared_by_subclass():
    """Regression test for a class extension that does not redefine an inherited
    attribute at all.

    `KGK_Grundstuecke_V1_0.SelbstaendigesDauerndesRecht` extends
    `DMAV_Grundstuecke_V1_1.SelbstaendigesDauerndesRecht` and transfers its mandatory
    `Flaechenmass` attribute unchanged: there is no local `AttrOrParam` for it on the
    KGK class, only a `TransferElement` pointing directly at the DMAV attribute's tid.
    If field resolution only looks at attributes declared locally on the class, this
    inherited field is silently dropped from the generated dataclass, so the value is
    never parsed and downstream inserts hit a NOT NULL violation instead.
    """
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "KGK_Alles_V1_0.imd"
    xtf_path = repo_root.parent / "data" / "KGK_Testdaten_20260608.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["KGK_Grundstuecke_V1_0"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Grundstuecke")
    records = getattr(basket, "selbstaendigesdauerndesrecht", [])

    assert records
    assert all(getattr(record, "flaechenmass", None) is not None for record in records)
