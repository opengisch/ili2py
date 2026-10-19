import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def ilivalidator_jar() -> Path:
    """
    Provides the ilivalidator jar, `make test-e2e` sets it via ILIVALIDATOR_JAR. The tests are
    skipped if the jar or java is missing.

    Returns:
        The path of the ilivalidator jar.
    """
    jar = os.environ.get("ILIVALIDATOR_JAR")
    if not jar or not Path(jar).is_file():
        pytest.skip("ILIVALIDATOR_JAR not set or missing, run `make test-e2e`")
    if shutil.which("java") is None:
        pytest.skip("java not found")
    return Path(jar)
