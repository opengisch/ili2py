import tempfile
from pathlib import Path

import pytest

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime.denormalized import UnsupportedRecordDataError, build_transfer
from ili2py.runtime.normalized import normalize_transfers
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def bodenbedeckung_imd_path(repo_root: Path) -> Path:
    return (
        repo_root.parent
        / "ili2django"
        / "tests"
        / "fixtures"
        / "bodenbedeckung_textposition"
        / "minimal_bodenbedeckung_textposition.imd"
    )


@pytest.fixture(scope="module")
def bodenbedeckung_xtf_path(repo_root: Path) -> Path:
    return (
        repo_root.parent
        / "ili2django"
        / "tests"
        / "fixtures"
        / "bodenbedeckung_textposition"
        / "minimal_bodenbedeckung_textposition.xtf"
    )


@pytest.fixture(scope="module")
def bodenbedeckung_metamodel(bodenbedeckung_imd_path: Path):
    return Imd16Reader().read(str(bodenbedeckung_imd_path))


@pytest.fixture(scope="module")
def bodenbedeckung_records(bodenbedeckung_metamodel, bodenbedeckung_xtf_path: Path):
    reader = Reader(bodenbedeckung_metamodel, fail_on_unknown_properties=False)
    transfers = reader.read(str(bodenbedeckung_xtf_path))
    return normalize_transfers(transfers)


def _assert_records_match(record, source):
    assert record["class_name"] == source["class_name"]
    assert record["attributes"] == source["attributes"]
    assert record["references"] == source["references"]
    assert record["geometries"] == source["geometries"]

    assert set(record["children"]) == set(source["children"])
    for key, source_children in source["children"].items():
        rebuilt_children = record["children"][key]
        assert len(rebuilt_children) == len(source_children)
        # Nested bag records (e.g. Objektnummer, Textposition) have no tid
        # of their own in this fixture, so match them positionally -- list
        # order is preserved end-to-end (parse -> normalize -> build ->
        # serialize -> re-parse -> re-normalize).
        for rebuilt_child, source_child in zip(rebuilt_children, source_children):
            _assert_records_match(rebuilt_child, source_child)


def test_build_transfer_round_trips_scalars_references_geometry_and_bag_children(
    bodenbedeckung_metamodel, bodenbedeckung_records
):
    transfer = build_transfer(
        bodenbedeckung_metamodel, "DMAV_Bodenbedeckung_V1_1", bodenbedeckung_records
    )

    serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))
    xml_text = serializer.render(transfer)

    with tempfile.TemporaryDirectory() as tmpdir:
        rebuilt_xtf_path = Path(tmpdir) / "rebuilt.xtf"
        rebuilt_xtf_path.write_text(xml_text, encoding="utf-8")

        reread_reader = Reader(bodenbedeckung_metamodel, fail_on_unknown_properties=False)
        reparsed_transfers = reread_reader.read(str(rebuilt_xtf_path))

    reparsed_records = normalize_transfers(reparsed_transfers)

    assert len(reparsed_records) == len(bodenbedeckung_records)
    original_by_tid = {r["tid"]: r for r in bodenbedeckung_records}
    for record in reparsed_records:
        source = original_by_tid[record["tid"]]
        assert record["topic_name"] == source["topic_name"]
        _assert_records_match(record, source)

    # This fixture's ring genuinely contains arcs -- confirm the round trip
    # preserved arc identity rather than just replaying flattened points.
    geometry = bodenbedeckung_records[0]["geometries"]["geometrie"]
    ring = geometry["coordinates"][0]
    assert any(isinstance(vertex, dict) and "arc_via" in vertex for vertex in ring)


def _round_trip(metamodel, model_name: str, records):
    transfer = build_transfer(metamodel, model_name, records)

    serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))
    xml_text = serializer.render(transfer)

    with tempfile.TemporaryDirectory() as tmpdir:
        rebuilt_xtf_path = Path(tmpdir) / "rebuilt.xtf"
        rebuilt_xtf_path.write_text(xml_text, encoding="utf-8")

        reread_reader = Reader(metamodel, fail_on_unknown_properties=False)
        reparsed_transfers = reread_reader.read(str(rebuilt_xtf_path))

    return normalize_transfers(reparsed_transfers)


def test_build_transfer_round_trips_multi_polygon(
    bodenbedeckung_metamodel, bodenbedeckung_records
):
    record = dict(bodenbedeckung_records[0])
    record["geometries"] = {
        "geometrie": {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                [[[10, 10], [11, 10], [11, 11], [10, 10]]],
            ],
        }
    }

    reparsed_records = _round_trip(
        bodenbedeckung_metamodel, "DMAV_Bodenbedeckung_V1_1", [record]
    )

    assert len(reparsed_records) == 1
    assert reparsed_records[0]["geometries"] == record["geometries"]


def test_build_transfer_rejects_raw_geometry(bodenbedeckung_metamodel, bodenbedeckung_records):
    record = dict(bodenbedeckung_records[0])
    record["geometries"] = {"geometrie": {"type": "RawGeometry", "xml": {"qname": "x"}}}

    with pytest.raises(UnsupportedRecordDataError):
        build_transfer(bodenbedeckung_metamodel, "DMAV_Bodenbedeckung_V1_1", [record])


@pytest.fixture(scope="module")
def dmav_metamodel(repo_root: Path):
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    return Imd16Reader().read(str(imd_path))


@pytest.fixture(scope="module")
def rohrleitungen_multipolyline_records(repo_root: Path, dmav_metamodel):
    xtf_path = (
        repo_root.parent
        / "ili2django"
        / "tests"
        / "fixtures"
        / "rohrleitungen_multipolyline"
        / "multipolyline_leitungsobjekt.xtf"
    )
    reader = Reader(dmav_metamodel, fail_on_unknown_properties=False)
    transfers = reader.read(str(xtf_path))
    return normalize_transfers(transfers)


def test_build_transfer_round_trips_real_multipolyline_geometry(
    dmav_metamodel, rohrleitungen_multipolyline_records
):
    """`geom:multipolyline` is a real container tag used in production DMAV data
    (see data/DMAVTYM_Alles_V1_1.xtf) for MultiLineString-valued attributes nested
    inside bag children -- round-trip it end to end on the real record.
    """
    leitungsobjekt = rohrleitungen_multipolyline_records[0]
    source_flaechenelement = leitungsobjekt["children"]["flaechenelement"][0]
    source_sichtbar = source_flaechenelement["geometries"]["sichtbar"]
    assert source_sichtbar["type"] == "MultiLineString"

    reparsed_records = _round_trip(
        dmav_metamodel, "DMAV_Rohrleitungen_V1_1", rohrleitungen_multipolyline_records
    )

    assert len(reparsed_records) == 1
    rebuilt_flaechenelement = reparsed_records[0]["children"]["flaechenelement"][0]
    rebuilt_sichtbar = rebuilt_flaechenelement["geometries"]["sichtbar"]
    assert rebuilt_sichtbar == source_sichtbar
