from pathlib import Path
import warnings

from xsdata.exceptions import ConverterWarning

from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.readers.interlis_24.xtf.xsdata import Reader


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