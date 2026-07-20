from typing import IO, AnyStr

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
        xtf_data = {}
        generator = DataClassGenerator(self.meta_model)
        for model_name in model_names_from_transfer(pre_xtf):
            generated_dataclasses = generator.generate(model_name)
            xtf_data[model_name] = self.parser.parse(input_xtf, generated_dataclasses)
        return xtf_data
