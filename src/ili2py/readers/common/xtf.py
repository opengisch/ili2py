from pathlib import Path
from typing import IO, AnyStr
import xml.etree.ElementTree as ET

from ili2py.interfaces.interlis.interlis_23 import TRANSFER
from ili2py.interfaces.interlis.interlis_24 import Transfer as TRANSFER_24


def detect_transfer_type(input_xtf: str | IO[AnyStr]):
    xtf_path = input_xtf if isinstance(input_xtf, str) else getattr(input_xtf, "name", None)
    if not xtf_path:
        return TRANSFER

    path = Path(xtf_path)
    if not path.exists():
        return TRANSFER

    try:
        root = ET.parse(path).getroot()
    except Exception:
        return TRANSFER

    tag = str(root.tag)
    if tag.startswith("{") and "}" in tag:
        namespace, name = tag[1:].split("}", 1)
        if namespace == "http://www.interlis.ch/xtf/2.4/INTERLIS" and name == "transfer":
            return TRANSFER_24
    return TRANSFER


def model_names_from_transfer(transfer):
    headersection = getattr(transfer, "HEADERSECTION", None)
    if headersection is not None:
        return [model.NAME for model in headersection.MODELS]

    headersection = getattr(transfer, "headersection", None)
    if headersection is None:
        return []
    models = getattr(headersection, "models", None)
    if models is None:
        return []
    return [model.model for model in getattr(models, "elements", [])]
