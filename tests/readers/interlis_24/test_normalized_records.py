from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime import InterlisVersion, normalize_transfer, normalize_transfers
from ili2py.runtime.normalized import UnsupportedTransferShapeError


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def dmav_imd_path(repo_root: Path) -> Path:
    return repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"


@pytest.fixture(scope="module")
def dmav_xtf_path(repo_root: Path) -> Path:
    return repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"


@pytest.fixture(scope="module")
def dmav_transfers(dmav_imd_path: Path, dmav_xtf_path: Path) -> dict[str, object]:
    meta_model = Imd16Reader().read(str(dmav_imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    return reader.read(str(dmav_xtf_path))


@pytest.fixture(scope="module")
def dmav_normalized_records(dmav_transfers: dict[str, object]) -> list[dict[str, object]]:
    return normalize_transfers(dmav_transfers)


def _raw_xtf_record_has_arc(xtf_path: Path, record_tid: str) -> bool:
    root = ET.parse(str(xtf_path)).getroot()
    tid_attr = "{http://www.interlis.ch/xtf/2.4/INTERLIS}tid"

    for element in root.iter():
        if element.attrib.get(tid_attr) != record_tid:
            continue
        return any(_local_name(descendant.tag) == "arc" for descendant in element.iter())
    return False


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def test_normalize_transfers_returns_builtin_record_shapes_for_dmav_xtf(
    dmav_normalized_records: list[dict[str, object]],
):
    normalized_records = dmav_normalized_records

    assert normalized_records

    lokalisation = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_Gebaeudeadressen_V1_1"
        and record["class_name"] == "Lokalisation"
    )
    assert lokalisation["topic_name"] == "Gebaeudeadressen"
    assert lokalisation["tid"] == "d9e6497d-443e-4ab2-a762-53aa6b4611ec"
    assert lokalisation["attributes"]["lokalisationnummer"] == "1193"
    assert lokalisation["references"] == {"entstehung": "646cd7be-f2a7-48d0-9523-0bf58c63b280"}
    assert lokalisation["geometries"] == {}
    assert "lokalisationname" in lokalisation["children"]
    assert lokalisation["children"]["lokalisationname"][0]["class_name"] == "Lokalisationsname"
    assert lokalisation["children"]["lokalisationname"][0]["attributes"]["name"]
    assert lokalisation["children"]["lokalisationname"][0]["attributes"]["sprache"] == "fr"

    gemeindegrenze = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_HoheitsgrenzenAV_V1_0"
        and record["class_name"] == "Gemeindegrenze"
        and record["tid"] == "97ec42fd-6405-47d9-b85c-fe5b1c46fe6f"
    )
    assert gemeindegrenze["references"] == {
        "entstehung": "8756dab9-f626-4454-9e2c-513f084329b6",
        "gemeinde": "e0480e97-b39a-49d6-be73-d440aa31eae7",
    }

    toleranzstufe = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_Toleranzstufen_V1_1"
        and record["class_name"] == "Toleranzstufe"
    )
    assert toleranzstufe["attributes"]["nbident"] == "BE0200000115"
    assert "geometrie" not in toleranzstufe["attributes"]
    assert toleranzstufe["geometries"]["geometrie"]["type"] == "Polygon"
    assert len(toleranzstufe["geometries"]["geometrie"]["coordinates"]) >= 1
    assert len(toleranzstufe["geometries"]["geometrie"]["coordinates"][0]) >= 3


def test_normalize_transfers_covers_point_multi_point_and_arc_geometry_shapes_for_dmav_xtf(
    dmav_xtf_path: Path,
    dmav_normalized_records: list[dict[str, object]],
):
    normalized_records = dmav_normalized_records

    point_record = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_Gebaeudeadressen_V1_1"
        and record["class_name"] == "Gebaeudeeingang"
    )
    assert point_record["geometries"]["geometrie"]["type"] == "Point"
    assert len(point_record["geometries"]["geometrie"]["coordinates"]) == 2

    multi_point_record = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_HoheitsgrenzenAV_V1_0"
        and record["class_name"] == "Bezirksgrenzabschnitt"
    )
    assert multi_point_record["geometries"]["geometrie"]["type"] == "LineString"
    assert len(multi_point_record["geometries"]["geometrie"]["coordinates"]) >= 2

    arc_record = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_Toleranzstufen_V1_1"
        and record["class_name"] == "Toleranzstufe"
        and record["tid"] == "3d51371a-1c54-4395-8720-81edf71e72c7"
    )
    assert arc_record["geometries"]["geometrie"]["type"] == "Polygon"
    assert _raw_xtf_record_has_arc(dmav_xtf_path, arc_record["tid"])

    bodenbedeckung_arc_heavy = next(
        record
        for record in normalized_records
        if record["model_name"] == "DMAV_Bodenbedeckung_V1_1"
        and record["class_name"] == "Bodenbedeckung"
        and record["tid"] == "6167d67a-2e45-45ce-8983-7269534f1a36"
    )
    assert _raw_xtf_record_has_arc(dmav_xtf_path, bodenbedeckung_arc_heavy["tid"])
    assert bodenbedeckung_arc_heavy["geometries"]["geometrie"]["type"] == "Polygon"
    assert len(bodenbedeckung_arc_heavy["geometries"]["geometrie"]["coordinates"]) >= 1
    assert len(bodenbedeckung_arc_heavy["geometries"]["geometrie"]["coordinates"][0]) >= 3
    arc_ring = bodenbedeckung_arc_heavy["geometries"]["geometrie"]["coordinates"][0]
    assert any(isinstance(vertex, dict) and "arc_via" in vertex for vertex in arc_ring)


def test_normalize_transfers_accepts_explicit_v24_version_parameter(
    dmav_transfers: dict[str, object],
):
    transfers = dmav_transfers

    auto_records = normalize_transfers(transfers)
    explicit_records = normalize_transfers(transfers, interlis_version=InterlisVersion.V24)

    assert explicit_records == auto_records


def test_normalize_transfer_raises_for_v23_request_on_v24_transfer(
    dmav_transfers: dict[str, object],
):
    transfers = dmav_transfers
    model_name, transfer = next(iter(transfers.items()))

    with pytest.raises(UnsupportedTransferShapeError):
        normalize_transfer(model_name, transfer, interlis_version=InterlisVersion.V23)


def test_normalize_transfer_parses_synthetic_v23_transfer_with_explicit_v23():
    @dataclass
    class Record23:
        tid: str | None = None
        name: str | None = None

    @dataclass
    class Topic23:
        bid: str = "basket-1"
        records: list[Record23] | None = None

    @dataclass
    class DataSection23:
        topic: Topic23 | None = None

    @dataclass
    class Transfer23:
        DATASECTION: DataSection23 | None = None

    transfer = Transfer23(
        DATASECTION=DataSection23(
            topic=Topic23(records=[Record23(tid="r-1", name="Alice")])
        )
    )

    normalized_records = normalize_transfer(
        "Model23",
        transfer,
        interlis_version=InterlisVersion.V23,
    )

    assert len(normalized_records) == 1
    assert normalized_records[0]["model_name"] == "Model23"
    assert normalized_records[0]["topic_name"] == "Topic23"
    assert normalized_records[0]["class_name"] == "Record23"
    assert normalized_records[0]["tid"] == "r-1"
    assert normalized_records[0]["attributes"]["name"] == "Alice"