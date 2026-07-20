"""Runtime bridge for optionally delegating IMD/XTF tasks to ili2py."""

from __future__ import annotations

from typing import Any

from .importer import DjangoImporter


def _build_backend(*, sender: str, xtf_version: str) -> Any:
    from .backend import Ili2PyBackend

    return Ili2PyBackend(sender=sender, xtf_version=xtf_version)


class Ili2PyBridge:
    """Runtime facade with explicit importer/backend composition.

    The concrete import/export implementation lives in a backend module while
    this facade keeps a stable API and testable orchestration.
    """

    def __init__(self, *, sender: str = "ili2django", xtf_version: str = "2.3") -> None:
        self._backend = _build_backend(sender=sender, xtf_version=xtf_version)
        self._django_importer = DjangoImporter()

    def get_last_import_diagnostics(self) -> dict[str, str | int | None]:
        return self._backend.get_last_import_diagnostics()

    def read_imd(
        self,
        imd_path: str,
        *,
        translation_imd_paths: str | list[str] | None = None,
    ) -> dict[str, Any]:
        return self._backend.read_imd(
            imd_path,
            translation_imd_paths=translation_imd_paths,
        )

    def get_translation_label(
        self,
        ref: str,
        language: str,
        default: str | None = None,
    ) -> str | None:
        return self._backend.get_translation_label(ref, language, default)

    def get_export_label(self, ref: str, base_label: str) -> str:
        return self._backend.get_export_label(ref, base_label)

    def import_xtf(
        self,
        xtf_path: str,
        *,
        django_router: Any | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        return self._django_importer.import_xtf(
            self._backend,
            xtf_path,
            django_router=django_router,
            continue_on_error=continue_on_error,
        )

    def load_xtf(self, xtf_path: str) -> None:
        self._backend.load_xtf(xtf_path)

    def export_xtf(self, xtf_path: str, *, queryset_provider: Any | None = None) -> None:
        self._backend.export_xtf(xtf_path, queryset_provider=queryset_provider)


__all__ = ["Ili2PyBridge"]
