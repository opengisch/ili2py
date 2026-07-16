"""Shared XTF XML core utilities.

This module intentionally stays framework-agnostic so downstream adapters
(e.g. Django) can reuse a single transfer-level XML handling layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class ParsedTransfer:
    """Parsed transfer payload with reusable XML root tree."""

    root: ET.Element


class XtfCore:
    """Minimal transfer XML parser/renderer for shared adapter usage."""

    def parse_transfer(self, xtf_path: str) -> ParsedTransfer:
        path = Path(xtf_path)
        if not path.exists():
            raise FileNotFoundError(f"XTF file not found: {xtf_path}")

        root = ET.parse(path).getroot()
        return ParsedTransfer(root=root)

    def render_transfer(self, transfer: ParsedTransfer, *, xml_declaration: bool = True) -> str:
        return ET.tostring(
            transfer.root,
            encoding="unicode",
            xml_declaration=xml_declaration,
        )
