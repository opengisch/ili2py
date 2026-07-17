from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from ili2django.runtime import Ili2PyBridge


class FakeField:
    def __init__(
        self,
        name: str,
        oid: str,
        internal_type: str,
        *,
        related_model: type[object] | None = None,
    ) -> None:
        self.name = name
        self._ili2django = {"oid": oid}
        self._internal_type = internal_type
        self.related_model = related_model
        self.remote_field = SimpleNamespace(model=related_model) if related_model else None

    def get_internal_type(self) -> str:
        return self._internal_type


class FakeMeta:
    def __init__(self, fields: list[FakeField]) -> None:
        self._fields = fields

    def get_fields(self) -> list[FakeField]:
        return list(self._fields)


class MemoryRouter:
    def __init__(self, models: list[type[object]]) -> None:
        self._models = models
        self.rows: dict[type[object], dict[str, dict[str, object]]] = {model: {} for model in models}

    def iter_models(self) -> list[type[object]]:
        return list(self._models)

    def upsert(self, model: type[object], tid: str, values: dict[str, object]) -> None:
        row = dict(self.rows[model].get(tid, {}))
        row.update(values)
        row["tid"] = tid
        self.rows[model][tid] = row

    def set_reference(
        self,
        model: type[object],
        source_tid: str,
        field_name: str,
        target_model: type[object],
        target_tid: str,
    ) -> None:
        self.rows[model][source_tid][field_name] = self.rows[target_model][target_tid]


class MemoryProvider:
    def __init__(self, objects_by_model: dict[type[object], list[object]], *, basket_id: str) -> None:
        self._objects_by_model = objects_by_model
        self._basket_id = basket_id

    def iter_models(self) -> list[type[object]]:
        return list(self._objects_by_model)

    def iter_objects(self, model: type[object]) -> list[object]:
        return list(self._objects_by_model[model])

    def basket_id(self, _model: type[object], _obj: object) -> str:
        return self._basket_id


def test_bridge_exports_and_imports_supported_subset_round_trip(tmp_path):
    class Parent:
        __ili2django__ = {"oid": "DemoModel.Main.Parent", "qname": "demo.Parent"}

    Parent._meta = FakeMeta(
        [
            FakeField("from_field", "DemoModel.Main.Parent.From", "CharField"),
            FakeField("number", "DemoModel.Main.Parent.Number", "IntegerField"),
        ]
    )

    class Child:
        __ili2django__ = {"oid": "DemoModel.Main.Child", "qname": "demo.Child"}

    Child._meta = FakeMeta(
        [
            FakeField("name", "DemoModel.Main.Child.Name", "CharField"),
            FakeField("count", "DemoModel.Main.Child.Count", "IntegerField"),
            FakeField("active", "DemoModel.Main.Child.Active", "BooleanField"),
            FakeField(
                "parent",
                "DemoModel.Main.Link_Child_Parent.Parent",
                "ForeignKey",
                related_model=Parent,
            ),
        ]
    )

    @dataclass
    class ParentRow:
        tid: str
        from_field: str
        number: int

    @dataclass
    class ChildRow:
        tid: str
        name: str
        count: int
        active: bool
        parent: ParentRow

    parent = ParentRow(tid="p1", from_field="north", number=7)
    child = ChildRow(tid="c1", name="child", count=3, active=True, parent=parent)

    bridge = Ili2PyBridge()
    provider = MemoryProvider({Parent: [parent], Child: [child]}, basket_id="demo-basket")
    xtf_path = tmp_path / "demo.xtf"

    bridge.export_xtf(str(xtf_path), queryset_provider=provider)

    xml = xtf_path.read_text(encoding="utf-8")
    assert "<From>north</From>" in xml
    assert '<DemoModel.Main.Main' not in xml
    assert 'REF="p1"' in xml
    assert "demo-basket" in xml

    router = MemoryRouter([Parent, Child])
    imported_counts = bridge.import_xtf(str(xtf_path), django_router=router)

    assert imported_counts == {
        "DemoModel.Main.Parent": 1,
        "DemoModel.Main.Child": 1,
    }

    assert router.rows[Parent]["p1"]["from_field"] == "north"
    assert router.rows[Parent]["p1"]["number"] == 7
    assert router.rows[Child]["c1"]["name"] == "child"
    assert router.rows[Child]["c1"]["count"] == 3
    assert router.rows[Child]["c1"]["active"] is True
    assert router.rows[Child]["c1"]["parent"]["tid"] == "p1"


def test_bridge_extracts_multilingual_translations_from_secondary_imd():
    bridge = Ili2PyBridge()

    translation_metamodel = SimpleNamespace(
        datasection=SimpleNamespace(
            ModelTranslation=[
                SimpleNamespace(
                    translation=[
                        SimpleNamespace(
                            language="de",
                            translations=[
                                SimpleNamespace(
                                    metranslation=SimpleNamespace(
                                        of=SimpleNamespace(ref="DemoModel.Main.Parent"),
                                        translated_name="Eltern",
                                    )
                                ),
                                SimpleNamespace(
                                    metranslation=SimpleNamespace(
                                        of=SimpleNamespace(ref="DemoModel.Main.Child"),
                                        translated_name="Kind",
                                    )
                                ),
                            ],
                        ),
                        SimpleNamespace(
                            language="fr",
                            translations=[
                                SimpleNamespace(
                                    metranslation=SimpleNamespace(
                                        of=SimpleNamespace(ref="DemoModel.Main.Parent"),
                                        translated_name="Parent",
                                    )
                                )
                            ],
                        ),
                    ]
                )
            ]
        )
    )

    translations = bridge._extract_imd_translations(translation_metamodel)
    bridge._merge_imd_translations(translations)

    assert bridge.get_translation_label("DemoModel.Main.Parent", "de") == "Eltern"
    assert bridge.get_translation_label("DemoModel.Main.Parent", "fr") == "Parent"
    assert bridge.get_translation_label("DemoModel.Main.Child", "de") == "Kind"
    assert bridge.get_translation_label("DemoModel.Main.Child", "fr") is None
    assert bridge.get_export_label("DemoModel.Main.Parent", "Parent") == "Parent"


def _normalized_xml_structure(xml_path: Path) -> tuple[object, ...]:
    root = ET.parse(xml_path).getroot()

    def normalize(node: ET.Element) -> tuple[object, ...]:
        attrs = tuple(sorted((str(k), str(v).strip()) for k, v in node.attrib.items()))
        text = (node.text or "").strip() or None
        children = [normalize(child) for child in list(node)]
        children.sort(key=repr)
        return node.tag, attrs, text, tuple(children)

    return normalize(root)


def test_kgk_round_trip_xtf_semantic_equality(tmp_path):
    if sys.version_info >= (3, 14):
        # Current IMD reader stack (xsdata integration) is unstable on Python 3.14
        # for this model set; runtime tests are executed on 3.13 in this repository.
        pytest.skip("KGK IMD generation is currently expected to run on Python 3.13 in this repo")

    project_dir = tmp_path / "kgk_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    generated_dir = project_dir / "generated_apps"
    generated_dir.mkdir(parents=True, exist_ok=True)

    test_root = Path(__file__).resolve().parent
    imd_path = test_root / "local_data" / "models" / "KGK_V1_0" / "KGK_Alles_V1_0.imd"
    input_xtf = test_root / "local_data" / "DMAVTYM_Alles_V1_1.xtf"
    output_xtf = project_dir / "round_trip.xtf"

    script = textwrap.dedent(
        """from pathlib import Path
import os
import sys
import types

from ili2django.generator import generate_django_models
from ili2django.runtime import Ili2PyBridge

project_dir = Path(sys.argv[1])
generated_dir = Path(sys.argv[2])
imd_path = Path(sys.argv[3])
input_xtf = Path(sys.argv[4])
output_xtf = Path(sys.argv[5])

result = generate_django_models(
    imd_path=str(imd_path),
    output_root=str(generated_dir),
    library_name="interface",
    app_prefix="ili",
    srid=2056,
)
if not result.created_files:
    raise RuntimeError("No files generated for KGK model")

app_names = sorted(
    child.name for child in generated_dir.iterdir() if child.is_dir() and (child / "apps.py").exists()
)
if not app_names:
    raise RuntimeError("No Django apps discovered after generation")

settings_file = project_dir / "test_settings.py"
settings_file.write_text(
    "\\n".join(
        [
            "SECRET_KEY = 'kgk-test'",
            "INSTALLED_APPS = ['django.contrib.contenttypes', "
            + ", ".join(repr(name) for name in app_names)
            + "]",
            "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': "
            + repr(str(project_dir / "db.sqlite3"))
            + "}}",
            "DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'",
        ]
    ),
    encoding="utf-8",
)

from django.db import models as dj_models

gis_models = types.ModuleType("django.contrib.gis.db.models")

class GeometryField(dj_models.TextField):
    def __init__(self, *args, srid=None, **kwargs):
        self.srid = srid
        super().__init__(*args, **kwargs)

class PointField(GeometryField):
    pass

class MultiPointField(GeometryField):
    pass

class LineStringField(GeometryField):
    pass

class MultiLineStringField(GeometryField):
    pass

class PolygonField(GeometryField):
    pass

class MultiPolygonField(GeometryField):
    pass

class CircularStringField(GeometryField):
    pass

class CompoundCurveField(GeometryField):
    pass

class CurvePolygonField(GeometryField):
    pass

class MultiCurveField(GeometryField):
    pass

class MultiSurfaceField(GeometryField):
    pass

gis_models.Model = dj_models.Model
gis_models.CharField = dj_models.CharField
gis_models.IntegerField = dj_models.IntegerField
gis_models.FloatField = dj_models.FloatField
gis_models.BooleanField = dj_models.BooleanField
gis_models.BinaryField = dj_models.BinaryField
gis_models.TextField = dj_models.TextField
gis_models.JSONField = dj_models.JSONField
gis_models.ForeignKey = dj_models.ForeignKey
gis_models.PROTECT = dj_models.PROTECT
gis_models.GeometryField = GeometryField
gis_models.PointField = PointField
gis_models.MultiPointField = MultiPointField
gis_models.LineStringField = LineStringField
gis_models.MultiLineStringField = MultiLineStringField
gis_models.PolygonField = PolygonField
gis_models.MultiPolygonField = MultiPolygonField
gis_models.CircularStringField = CircularStringField
gis_models.CompoundCurveField = CompoundCurveField
gis_models.CurvePolygonField = CurvePolygonField
gis_models.MultiCurveField = MultiCurveField
gis_models.MultiSurfaceField = MultiSurfaceField

gis_db = types.ModuleType("django.contrib.gis.db")
gis_db.models = gis_models

gis_pkg = types.ModuleType("django.contrib.gis")
gis_pkg.db = gis_db

sys.modules["django.contrib.gis"] = gis_pkg
sys.modules["django.contrib.gis.db"] = gis_db
sys.modules["django.contrib.gis.db.models"] = gis_models

sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(generated_dir))
os.environ["DJANGO_SETTINGS_MODULE"] = "test_settings"

import django
from django.core.management import call_command

django.setup()
call_command("migrate", run_syncdb=True, verbosity=0)

bridge = Ili2PyBridge()
bridge.read_imd(str(imd_path))
bridge.import_xtf(str(input_xtf))
bridge.export_xtf(str(output_xtf))
"""
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(project_dir),
            str(generated_dir),
            str(imd_path),
            str(input_xtf),
            str(output_xtf),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        "Subprocess round-trip failed\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert output_xtf.exists(), "Round-trip export file was not produced"

    assert _normalized_xml_structure(input_xtf) == _normalized_xml_structure(output_xtf)