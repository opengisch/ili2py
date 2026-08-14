from pathlib import Path

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime.normalized import normalize_transfers


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


def test_reader_parses_inherited_role_kept_in_origin_model_namespace():
    """Regression test for an inherited association Role, not just plain attributes.

    `KGK_Grundstuecke_V1_0.SelbstaendigesDauerndesRecht` also inherits the
    `Grundstueck` role of the `DMAV_Grundstuecke_V1_1.GrundstueckSelbstaendigesDauerndesRecht`
    association unchanged. Roles don't carry a `Super` reference the way redefined
    attributes do, so a role pulled in purely through inheritance (via
    `_ordered_field_elements`'s cross-model fallback) must have its namespace derived
    from its own tid rather than defaulting to the extending class's model
    (KGK_Grundstuecke_V1_0); otherwise xsdata never binds the reference and the
    mandatory foreign key ends up NULL at the database layer.
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
    assert all(getattr(record, "grundstueck", None) is not None for record in records)
    assert all(getattr(record.grundstueck, "ref", None) for record in records)


def test_reader_parses_classes_inherited_into_a_shared_basket_from_a_base_topic():
    """Regression test for classes that belong only to a base topic, not the
    extending topic, but still transfer through the extending topic's basket.

    A topic extension (`KGK_Grundstuecke_V1_0.Grundstuecke` extends
    `DMAV_Grundstuecke_V1_1.Grundstuecke`) shares ONE basket with its base topic:
    the XTF nests both the extending topic's own classes (e.g.
    SelbstaendigesDauerndesRecht, redefined by KGK) and the base topic's classes
    that KGK doesn't touch at all (Liegenschaft, Grundstueck, Grenzpunkt, ...)
    as children of a single basket element tagged with the extending topic's
    namespace. Which classes belong to a basket is defined by `AllowedInBasket`
    metadata, not by which topic a class is declared in. If basket generation
    only enumerates classes declared locally in the topic, base-topic classes
    are missing entirely from the generated dataclass, so xsdata silently drops
    every such record instead of raising -- e.g. plain `Grundstueck` and
    `Liegenschaft` records disappear, along with everything that references
    them, cascading into unresolved-forward-reference failures downstream.
    """
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "KGK_Alles_V1_0.imd"
    xtf_path = repo_root.parent / "data" / "KGK_Testdaten_20260608.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["KGK_Grundstuecke_V1_0"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Grundstuecke")

    grundstueck_records = getattr(basket, "grundstueck", [])
    liegenschaft_records = getattr(basket, "liegenschaft", [])

    assert grundstueck_records
    assert liegenschaft_records
    assert all(getattr(record, "tid", None) for record in grundstueck_records)
    assert all(getattr(record, "tid", None) for record in liegenschaft_records)


def test_normalize_labels_inherited_basket_records_under_their_true_origin_model():
    """Regression test: normalization must label a record with the model its
    class actually belongs to, not the model of the basket/transfer it was
    parsed under.

    `KGK_Grundstuecke_V1_0.Grundstuecke`'s basket carries `Grundstueck` and
    `Liegenschaft` records that are declared only in `DMAV_Grundstuecke_V1_1`
    (see the shared-basket regression test above). ili2django's model bindings
    are keyed by a class's true origin (model_name, topic_name, class_name),
    e.g. `DMAV_Grundstuecke_V1_1.Grundstuecke.Grundstueck` -- if normalization
    always stamped every record from this basket with the transfer's own model
    name (`KGK_Grundstuecke_V1_0`), such records would never match their
    binding, get silently skipped as "no matching binding", and any reference
    pointing at them would then fail to resolve.
    """
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "KGK_Alles_V1_0.imd"
    xtf_path = repo_root.parent / "data" / "KGK_Testdaten_20260608.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    transfers = reader.read(str(xtf_path))
    records = normalize_transfers(transfers)

    def model_names_for(class_name: str) -> set[str]:
        return {r["model_name"] for r in records if r["class_name"] == class_name}

    assert model_names_for("Grundstueck") == {"DMAV_Grundstuecke_V1_1"}
    assert model_names_for("Liegenschaft") == {"DMAV_Grundstuecke_V1_1"}
    assert model_names_for("SelbstaendigesDauerndesRecht") == {"KGK_Grundstuecke_V1_0"}
    assert model_names_for("Einzelobjekt") == {"KGK_Einzelobjekte_V1_0"}
