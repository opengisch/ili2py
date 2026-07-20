"""Django importer entrypoint.

This module provides a small adapter seam so runtime orchestration can be
tested independently from the concrete backend implementation.
"""

from __future__ import annotations

from typing import Any, Protocol


class ImportBackend(Protocol):
    def import_xtf(
        self,
        xtf_path: str,
        *,
        django_router: Any | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]: ...


class DjangoImporter:
    """Adapter that executes the configured import backend."""

    def import_xtf(
        self,
        backend: ImportBackend,
        xtf_path: str,
        *,
        django_router: Any | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        return backend.import_xtf(
            xtf_path,
            django_router=django_router,
            continue_on_error=continue_on_error,
        )
