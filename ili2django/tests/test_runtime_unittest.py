from __future__ import annotations

import unittest
from unittest.mock import patch

from ili2django.importer import DjangoImporter
from ili2django.runtime import Ili2PyBridge


class _FakeBackend:
    def __init__(self) -> None:
        self.last_import_call: dict[str, object] | None = None
        self.last_export_call: dict[str, object] | None = None

    def import_xtf(
        self,
        xtf_path: str,
        *,
        django_router=None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        self.last_import_call = {
            "xtf_path": xtf_path,
            "django_router": django_router,
            "continue_on_error": continue_on_error,
        }
        return {"Model.Topic.Class": 7}

    def export_xtf(self, xtf_path: str, *, queryset_provider=None) -> None:
        self.last_export_call = {
            "xtf_path": xtf_path,
            "queryset_provider": queryset_provider,
        }

    def read_imd(self, imd_path: str, *, translation_imd_paths=None) -> dict[str, object]:
        return {
            "imd_path": imd_path,
            "translation_imd_paths": translation_imd_paths,
        }

    def get_translation_label(self, ref: str, language: str, default: str | None = None) -> str | None:
        if ref == "known.ref" and language == "de":
            return "Beispiel"
        return default

    def get_export_label(self, _ref: str, base_label: str) -> str:
        return base_label

    def get_last_import_diagnostics(self) -> dict[str, str | int | None]:
        return {"mode": "structured", "records_imported": 7}


class _FakeImporter:
    def __init__(self) -> None:
        self.last_call: dict[str, object] | None = None

    def import_xtf(
        self,
        backend,
        xtf_path: str,
        *,
        django_router=None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        self.last_call = {
            "backend": backend,
            "xtf_path": xtf_path,
            "django_router": django_router,
            "continue_on_error": continue_on_error,
        }
        return backend.import_xtf(
            xtf_path,
            django_router=django_router,
            continue_on_error=continue_on_error,
        )


class RuntimeTests(unittest.TestCase):
    def test_runtime_routes_import_through_importer(self) -> None:
        fake_backend = _FakeBackend()
        fake_importer = _FakeImporter()

        with patch("ili2django.runtime._build_backend", return_value=fake_backend):
            bridge = Ili2PyBridge()
            bridge._django_importer = fake_importer
            result = bridge.import_xtf("/tmp/source.xtf", continue_on_error=True)

        self.assertEqual({"Model.Topic.Class": 7}, result)
        self.assertIsNotNone(fake_importer.last_call)
        self.assertIs(fake_backend, fake_importer.last_call["backend"])
        self.assertEqual("/tmp/source.xtf", fake_importer.last_call["xtf_path"])
        self.assertTrue(fake_importer.last_call["continue_on_error"])

    def test_runtime_delegates_non_import_methods_to_backend(self) -> None:
        fake_backend = _FakeBackend()

        with patch("ili2django.runtime._build_backend", return_value=fake_backend):
            bridge = Ili2PyBridge()
            imd = bridge.read_imd("/tmp/model.imd", translation_imd_paths=["/tmp/tr.imd"])
            label = bridge.get_translation_label("known.ref", "de")
            fallback = bridge.get_translation_label("unknown", "de", default="x")
            export_label = bridge.get_export_label("known.ref", "Base")
            diagnostics = bridge.get_last_import_diagnostics()
            bridge.export_xtf("/tmp/out.xtf", queryset_provider="provider")

        self.assertEqual("/tmp/model.imd", imd["imd_path"])
        self.assertEqual(["/tmp/tr.imd"], imd["translation_imd_paths"])
        self.assertEqual("Beispiel", label)
        self.assertEqual("x", fallback)
        self.assertEqual("Base", export_label)
        self.assertEqual("structured", diagnostics["mode"])
        self.assertIsNotNone(fake_backend.last_export_call)
        self.assertEqual("/tmp/out.xtf", fake_backend.last_export_call["xtf_path"])


class ImporterTests(unittest.TestCase):
    def test_django_importer_delegates_to_backend(self) -> None:
        importer = DjangoImporter()
        backend = _FakeBackend()

        result = importer.import_xtf(
            backend,
            "/tmp/data.xtf",
            django_router="router",
            continue_on_error=True,
        )

        self.assertEqual({"Model.Topic.Class": 7}, result)
        self.assertIsNotNone(backend.last_import_call)
        self.assertEqual("/tmp/data.xtf", backend.last_import_call["xtf_path"])
        self.assertEqual("router", backend.last_import_call["django_router"])
        self.assertTrue(backend.last_import_call["continue_on_error"])


if __name__ == "__main__":
    unittest.main()
