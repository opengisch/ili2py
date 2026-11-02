import zipfile
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "data"
DMAV = DATA / "models" / "DMAVTYM_Alles_V1_1"


@pytest.fixture(scope="session")
def dmav_imd_path() -> Path:
    return DMAV / "DMAVTYM_Alles_V1_1.imd"


@pytest.fixture(scope="session")
def dmav_xtf_path(tmp_path_factory) -> Path:
    """The DMAV 1.1 sample transfer, out of the archive that ships it."""
    with zipfile.ZipFile(DMAV / "DMAV_Version_1_1.zip") as archive:
        return Path(archive.extract("DMAVTYM_Alles_V1_1.xtf", tmp_path_factory.mktemp("dmav")))


@pytest.fixture(scope="session")
def kgk_imd_path() -> Path:
    return DATA / "models" / "KGK_Alles_V1_0.imd"


@pytest.fixture(scope="session")
def kgk_xtf_path() -> Path:
    return DATA / "fixtures" / "kgk_extensions" / "kgk_extensions.xtf"
