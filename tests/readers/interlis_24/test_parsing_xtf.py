from pathlib import Path
import tempfile
import warnings

from xsdata.exceptions import ConverterWarning
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader
from ili2py.runtime.normalized import normalize_transfer


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