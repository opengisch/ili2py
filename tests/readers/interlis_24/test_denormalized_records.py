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


def test_build_transfer_rejects_multi_geometry(
    bodenbedeckung_metamodel, bodenbedeckung_records
):
    record = dict(bodenbedeckung_records[0])
    record["geometries"] = {
        "geometrie": {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 1]]]]}
    }

    with pytest.raises(UnsupportedRecordDataError):
        build_transfer(bodenbedeckung_metamodel, "DMAV_Bodenbedeckung_V1_1", [record])
