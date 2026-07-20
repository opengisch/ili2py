from pathlib import Path

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime import normalize_transfers


def test_normalize_transfers_returns_builtin_record_shapes_for_dmav_xtf():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    transfers = reader.read(str(xtf_path))

    normalized_records = normalize_transfers(transfers)

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
    assert "sprache" not in lokalisation["children"]["lokalisationname"][0]["attributes"]

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