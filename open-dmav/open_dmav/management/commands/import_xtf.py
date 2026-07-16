"""Import INTERLIS transfer data (XTF) into generated Django models."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Import an XTF file into generated Django models via ili2django runtime bridge."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "xtf",
            help="Path to the source XTF transfer file.",
        )
        parser.add_argument(
            "--imd",
            help="Optional path to IMD model metadata used to preload runtime model labels.",
        )
        parser.add_argument(
            "--translation-imd",
            action="append",
            default=[],
            help="Optional translation IMD path (repeatable).",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        xtf_path = Path(options["xtf"]).expanduser().resolve()
        imd = options.get("imd")
        translation_imds = options.get("translation_imd") or []

        if not xtf_path.exists():
            raise CommandError(f"XTF file not found: {xtf_path}")

        if imd:
            imd_path = Path(imd).expanduser().resolve()
            if not imd_path.exists():
                raise CommandError(f"IMD file not found: {imd_path}")
            imd = str(imd_path)

        resolved_translation_imds: list[str] = []
        for translation_imd in translation_imds:
            translation_path = Path(translation_imd).expanduser().resolve()
            if not translation_path.exists():
                raise CommandError(f"Translation IMD file not found: {translation_path}")
            resolved_translation_imds.append(str(translation_path))

        try:
            from ili2django.runtime import Ili2PyBridge
        except Exception as exc:
            raise CommandError(
                "Unable to import ili2django runtime bridge. "
                "Install/ship ili2django + ili2py runtime dependencies."
            ) from exc

        bridge = Ili2PyBridge()
        if imd:
            bridge.read_imd(
                imd,
                translation_imd_paths=resolved_translation_imds or None,
            )

        bridge.import_xtf(str(xtf_path))
        self.stdout.write(self.style.SUCCESS(f"Imported XTF: {xtf_path}"))
