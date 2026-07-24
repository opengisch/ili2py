from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import warnings

from xsdata.exceptions import ConverterWarning
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime.normalized import normalize_transfer


GEOM_NS = "http://www.interlis.ch/geometry/1.0"


def test_reader_parses_dmav_xtf_without_converter_warnings():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConverterWarning)
        result = reader.read(str(xtf_path))

    converter_warnings = [warning for warning in caught if issubclass(warning.category, ConverterWarning)]

    assert converter_warnings == []
    assert len(result) == 31
    assert "DMAVTYM_Vermarkung_V1_0" in result
    sample = result["DMAVTYM_Vermarkung_V1_0"]
    assert getattr(sample, "datasection", None) is not None


def test_reader_round_trip_preserves_normalized_records_for_dmav_model():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    model_name = "DMAV_HoheitsgrenzenAV_V1_0"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    parsed_transfers = reader.read(str(xtf_path))

    original_transfer = parsed_transfers[model_name]
    original_records = normalize_transfer(model_name, original_transfer)
    assert original_records

    serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))
    xml = serializer.render(original_transfer)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".xtf", encoding="utf-8", delete=False) as tmp:
        tmp.write(xml)
        tmp_path = Path(tmp.name)

    try:
        round_trip_transfers = reader.read(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    round_trip_transfer = round_trip_transfers[model_name]
    round_trip_records = normalize_transfer(model_name, round_trip_transfer)

    assert round_trip_records == original_records


def test_reader_parses_dotted_topic_class_elements_for_bodenbedeckung_model():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["DMAV_Bodenbedeckung_V1_1"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Bodenbedeckung")

    assert len(getattr(basket, "bodenbedeckung", [])) > 0


def test_reader_export_preserves_total_arc_count_for_dmav_xtf():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    serializer = XmlSerializer(config=SerializerConfig(indent="  ", xml_declaration=True))

    source_arc_count = sum(1 for e in ET.parse(str(xtf_path)).getroot().iter() if e.tag == f"{{{GEOM_NS}}}arc")

    exported_arc_count = 0
    for transfer in result.values():
        exported_root = ET.fromstring(serializer.render(transfer))
        exported_arc_count += sum(1 for e in exported_root.iter() if e.tag == f"{{{GEOM_NS}}}arc")

    assert exported_arc_count == source_arc_count


def test_reader_parses_nested_textposition_for_dmav_bodenbedeckung_bags():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["DMAV_Bodenbedeckung_V1_1"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Bodenbedeckung")

    found_objektnummer_textposition = False
    found_objektname_textposition = False

    for record in getattr(basket, "bodenbedeckung", []):
        objektnummer_wrapper = getattr(record, "objektnummer", None)
        for item in getattr(objektnummer_wrapper, "items", []) or []:
            textposition_wrapper = getattr(item, "textposition", None)
            if getattr(textposition_wrapper, "items", None):
                found_objektnummer_textposition = True
                break

        objektname_wrapper = getattr(record, "objektname", None)
        for item in getattr(objektname_wrapper, "items", []) or []:
            textposition_wrapper = getattr(item, "textposition", None)
            if getattr(textposition_wrapper, "items", None):
                found_objektname_textposition = True
                break

        if found_objektnummer_textposition and found_objektname_textposition:
            break

    assert found_objektnummer_textposition
    assert found_objektname_textposition


def test_reader_parses_copied_bodenbedeckung_textposition_fixture():
    repo_root = Path(__file__).resolve().parents[3]
    fixture_dir = repo_root / "tests" / "data" / "fixtures" / "bodenbedeckung_textposition"
    imd_path = fixture_dir / "minimal_bodenbedeckung_textposition.imd"
    xtf_path = fixture_dir / "minimal_bodenbedeckung_textposition.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["DMAV_Bodenbedeckung_V1_1"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Bodenbedeckung")
    record = basket.bodenbedeckung[0]

    objektnummer = record.objektnummer.items[0]
    assert getattr(objektnummer, "textposition", None) is not None
    assert len(objektnummer.textposition.items) == 1


def test_reader_parses_textposition_enum_backed_fields_for_dmav_bodenbedeckung():
    repo_root = Path(__file__).resolve().parents[3]
    imd_path = repo_root / "tests" / "data" / "models" / "DMAVTYM_Alles_V1_1.imd"
    xtf_path = repo_root.parent / "data" / "DMAVTYM_Alles_V1_1.xtf"

    meta_model = Imd16Reader().read(str(imd_path))
    reader = Reader(meta_model, fail_on_unknown_properties=False)
    result = reader.read(str(xtf_path))

    transfer = result["DMAV_Bodenbedeckung_V1_1"]
    basket = next(b for b in transfer.datasection.baskets if type(b).__name__ == "Bodenbedeckung")

    found = False
    for record in getattr(basket, "bodenbedeckung", []):
        objektname_wrapper = getattr(record, "objektname", None)
        for objname_item in getattr(objektname_wrapper, "items", []) or []:
            textposition_wrapper = getattr(objname_item, "textposition", None)
            for textposition_item in getattr(textposition_wrapper, "items", []) or []:
                if getattr(textposition_item, "textgroesse", None) is None:
                    continue
                if getattr(textposition_item, "hreferenzpunkt", None) is None:
                    continue
                if getattr(textposition_item, "vreferenzpunkt", None) is None:
                    continue
                found = True
                break
            if found:
                break
        if found:
            break

    assert found