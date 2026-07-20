import io
from pathlib import Path
from typing import IO, AnyStr
import xml.etree.ElementTree as ET

from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.parsers.config import ParserConfig

from ili2py.interfaces.interlis.interlis_24 import Transfer
from ili2py.interfaces.interlis.interlis_24.generator import DataClassGenerator
from ili2py.interfaces.interlis.interlis_24.ilismeta16 import ImdTransfer
from ili2py.readers.common.xtf import model_names_from_transfer


class Reader:

    def __init__(
        self,
        meta_model: ImdTransfer,
        fail_on_unknown_properties: bool = False,
        namespace_map: dict | None = None,
    ):
        self.parser = XmlParser()
        self.parser.config = ParserConfig()
        self.parser.config.fail_on_unknown_properties = fail_on_unknown_properties
        self.namespace_map = namespace_map or {}
        self.parser.ns_map = self.namespace_map
        self.meta_model = meta_model

    def read(self, input_xtf: str | IO[AnyStr]):
        pre_xtf = self.parser.parse(input_xtf, Transfer)
        canonical_input = self._canonicalized_input(input_xtf)
        xtf_data = {}
        generator = DataClassGenerator(self.meta_model)
        for model_name in model_names_from_transfer(pre_xtf):
            generated_dataclasses = generator.generate(model_name)
            xtf_data[model_name] = self.parser.parse(io.BytesIO(canonical_input), generated_dataclasses)
        return xtf_data

    def _canonicalized_input(self, input_xtf: str | IO[AnyStr]) -> bytes:
        if isinstance(input_xtf, str):
            raw_bytes = Path(input_xtf).read_bytes()
        else:
            stream = input_xtf
            position = None
            if hasattr(stream, "tell"):
                try:
                    position = stream.tell()
                except Exception:
                    position = None
            raw_bytes = stream.read()
            if isinstance(raw_bytes, str):
                raw_bytes = raw_bytes.encode("utf-8")
            if position is not None and hasattr(stream, "seek"):
                try:
                    stream.seek(position)
                except Exception:
                    pass

        try:
            root = ET.fromstring(raw_bytes)
        except Exception:
            return raw_bytes

        updated = False
        for elem in root.iter():
            tag = str(elem.tag)
            if not tag.startswith("{") or "}" not in tag:
                continue
            namespace, local = tag[1:].split("}", 1)
            if "/xtf/2.4/" not in namespace:
                continue
            if "." not in local:
                continue
            elem.tag = f"{{{namespace}}}{local.rsplit('.', 1)[-1]}"
            updated = True

        if not updated:
            return raw_bytes
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
