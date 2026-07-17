from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
import types
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.conf import settings
from django.db import models as dj_models

from ili2django.generator import (
    _build_model_name_map,
    _ClassRef,
    _collect_enum_refs,
    _db_table_name,
    _field_expression,
    _field_name,
    _nullable,
    _render_models_py,
    generate_django_models,
)


def _install_gis_stub() -> None:
    if "django.contrib.gis.db.models" in sys.modules:
        return

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


@pytest.fixture(scope="module")
def generated_apps(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[str]]:
    _install_gis_stub()
    output_root = tmp_path_factory.mktemp("generated")
    local_models = Path(__file__).parent / "local_data" / "models"
    imd_paths = [
        local_models / "DMAVTYM_Alles_V1_0" / "DMAVTYM_Alles_V1_0.imd",
        local_models / "DMAVTYM_Tous_V1_0" / "DMAVTYM_Tous_V1_0.imd",
    ]

    app_names: list[str] = []
    for imd_path in imd_paths:
        result = generate_django_models(
            imd_path=str(imd_path),
            output_root=str(output_root),
            library_name="interface",
            app_prefix="ili",
            srid=2056,
            bootstrap=True,
        )
        assert result.created_files

    for child in output_root.iterdir():
        if child.is_dir() and (child / "apps.py").exists():
            app_names.append(child.name)

    assert app_names, "No Django apps were generated"

    sys.path.insert(0, str(output_root))

    if not settings.configured:
        settings.configure(
            SECRET_KEY="ili2django-test-secret",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                *app_names,
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            DEFAULT_AUTO_FIELD="django.db.models.AutoField",
        )

    import django

    if not apps.ready:
        django.setup()

    return output_root, app_names


def test_generated_files_exist(generated_apps: tuple[Path, list[str]]) -> None:
    output_root, app_names = generated_apps
    for app_name in app_names:
        app_path = output_root / app_name
        assert (app_path / "models_generated.py").exists()
        assert (app_path / "models.py").exists()
        assert (app_path / "apps.py").exists()


def test_generate_models_defaults_to_generated_only(tmp_path: Path) -> None:
    imd_path = Path(__file__).parent / "local_data" / "models" / "DMAVTYM_Alles_V1_0" / "DMAVTYM_Alles_V1_0.imd"
    output_root = tmp_path / "generated_only"

    result = generate_django_models(
        imd_path=str(imd_path),
        output_root=str(output_root),
        library_name="interface",
        app_prefix="ili",
        srid=2056,
    )

    assert result.created_files
    assert all(path.name == "models_generated.py" for path in result.created_files)

    for generated_file in result.created_files:
        app_dir = generated_file.parent
        assert generated_file.exists()
        assert not (app_dir / "apps.py").exists()
        assert not (app_dir / "models.py").exists()
        assert not (app_dir / "__init__.py").exists()


def test_generated_models_load_and_carry_metadata(generated_apps: tuple[Path, list[str]]) -> None:
    _, app_names = generated_apps
    gis_models = importlib.import_module("django.contrib.gis.db.models")
    loaded_models = []
    for app_name in app_names:
        module = importlib.import_module(f"{app_name}.models_generated")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, gis_models.Model) and cls.__module__ == module.__name__:
                loaded_models.append(cls)

    assert loaded_models, "No generated Django model classes found"

    tagged_models = [m for m in loaded_models if hasattr(m, "__ili2django__")]
    assert tagged_models, "Generated model metadata decorator was not applied"


def test_geometry_fields_use_expected_srid(generated_apps: tuple[Path, list[str]]) -> None:
    _, app_names = generated_apps
    gis_models = importlib.import_module("django.contrib.gis.db.models")

    geometry_fields = []
    for app_name in app_names:
        module = importlib.import_module(f"{app_name}.models_generated")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not (issubclass(cls, gis_models.Model) and cls.__module__ == module.__name__):
                continue
            for field in cls._meta.get_fields():
                if isinstance(field, gis_models.GeometryField):
                    geometry_fields.append(field)

    if not geometry_fields:
        pytest.skip("No geometry fields generated for the selected DMAVTYM models")

    for field in geometry_fields:
        assert field.srid == 2056


def test_keyword_field_name_does_not_end_with_underscore() -> None:
    assert _field_name("From") == "from_field"


def test_ref_to_abstract_model_falls_back_to_charfield() -> None:
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": True},
        geometric=False,
        types=["Ref"],
        reference_targets=["abstract-target"],
    )
    class_map = {
        "abstract-target": _ClassRef(
            app_label="app",
            model_name="AbstractBase",
            abstract=True,
        )
    }

    expression = _field_expression(attribute, class_map, srid=2056)

    assert expression.startswith("models.CharField(")


def test_duplicate_class_names_get_disambiguated() -> None:
    classes = [
        SimpleNamespace(name="Hierarchy", identifier="Model.TopicOne.Hierarchy"),
        SimpleNamespace(name="Hierarchy", identifier="Model.TopicTwo.Hierarchy"),
        SimpleNamespace(name="City", identifier="Model.TopicOne.City"),
    ]

    model_names = _build_model_name_map(classes)

    assert model_names["Model.TopicOne.Hierarchy"] == "TopicOneHierarchy"
    assert model_names["Model.TopicTwo.Hierarchy"] == "TopicTwoHierarchy"
    assert model_names["Model.TopicOne.City"] == "City"


def test_field_expression_uses_enum_fk_target() -> None:
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": True},
        geometric=False,
        types=["Status"],
        reference_targets=[],
    )

    expression = _field_expression(
        attribute,
        class_map={},
        srid=2056,
        enum_fk_target="app.StatusValue",
    )

    assert expression.startswith("models.ForeignKey('app.StatusValue'")


def test_nullable_prefers_multiplicity_min_over_mandatory() -> None:
    restrictions = {
        "mandatory": True,
        "multiplicity": {"min": 0, "max": 1},
    }

    assert _nullable(restrictions) is True


def test_collect_enum_refs_and_render_models_include_value_lists() -> None:
    enum = SimpleNamespace(
        identifier="Model.Topic.Status",
        name="Status",
        values=["active", "inactive"],
        tree=False,
    )
    attr = SimpleNamespace(
        name="status",
        identifier="Model.Topic.Parcel.status",
        types=["Status"],
        type_restrictions={"mandatory": True},
        geometric=False,
        reference_targets=[],
        enumeration=None,
    )
    cls = SimpleNamespace(
        name="Parcel",
        identifier="Model.Topic.Parcel",
        oid=None,
        attributes=[attr],
        abstract=False,
    )
    module = SimpleNamespace(name="Topic", enumerations=[enum])

    class_model_names = {cls.identifier: "Parcel"}

    global_enum_map, local_enum_map = _collect_enum_refs(
        modules=[module],
        classes=[cls],
        class_model_names=class_model_names,
    )

    assert ("Topic", "Status") in global_enum_map
    assert local_enum_map == {}

    content = _render_models_py(
        app_label="ili_demo",
        modules=[module],
        classes=[cls],
        class_model_names=class_model_names,
        class_map={},
        srid=2056,
    )

    assert "class StatusValue(models.Model):" in content
    assert "from django.utils.translation import gettext_lazy as _" in content
    assert "from ili2django.choices import IliChoice, IliChoices" in content
    assert "__ili2django_values__ = ['active', 'inactive']" in content
    assert "__ili2django_tree__ = False" in content
    assert "class StatusValueChoices(IliChoices):" in content
    assert "ACTIVE = IliChoice('active', _('active'), order=0)" in content
    assert "def __str__(self) -> str:" in content
    assert "models.ForeignKey('ili_demo.StatusValue'" in content


def test_collect_enum_refs_supports_local_attribute_enums() -> None:
    local_enum = SimpleNamespace(
        identifier="Model.Topic.Parcel.status.TYPE",
        name="ParcelStatusEnum",
        values=["draft", "final"],
        tree=False,
    )
    attr = SimpleNamespace(
        name="status",
        identifier="Model.Topic.Parcel.status",
        types=["ParcelStatusEnum"],
        type_restrictions={"mandatory": False},
        geometric=False,
        reference_targets=[],
        enumeration=local_enum,
    )
    cls = SimpleNamespace(
        name="Parcel",
        identifier="Model.Topic.Parcel",
        oid=None,
        attributes=[attr],
        abstract=False,
    )
    module = SimpleNamespace(name="Topic", enumerations=[])

    content = _render_models_py(
        app_label="ili_demo",
        modules=[module],
        classes=[cls],
        class_model_names={cls.identifier: "Parcel"},
        class_map={},
        srid=2056,
    )

    assert "class ParcelStatusEnumValue(models.Model):" in content
    assert "models.ForeignKey('ili_demo.ParcelStatusEnumValue'" in content


def test_db_table_name_short_names_are_unchanged() -> None:
    assert _db_table_name("odmav_coord_sys", "GeoHeight") == "odmav_coord_sys__geo_height"


def test_db_table_name_long_names_get_hashed_suffix() -> None:
    name = _db_table_name(
        "odmav_dmav_dauernde_bodenverschiebungen_v1_0",
        "DauerndeBodenverschiebungMitExtremLangemNamenUndZusatz",
    )

    assert len(name) <= 63
    assert "_" in name


def test_db_table_name_is_deterministic_and_unique_for_similar_prefixes() -> None:
    a = _db_table_name(
        "odmav_dmav_dauernde_bodenverschiebungen_v1_0",
        "DauerndeBodenverschiebungSehrLangerNameAlpha",
    )
    b = _db_table_name(
        "odmav_dmav_dauernde_bodenverschiebungen_v1_0",
        "DauerndeBodenverschiebungSehrLangerNameBeta",
    )

    assert a == _db_table_name(
        "odmav_dmav_dauernde_bodenverschiebungen_v1_0",
        "DauerndeBodenverschiebungSehrLangerNameAlpha",
    )
    assert a != b


def test_field_expression_prefers_nested_geometrie_polygon_for_structure_lists() -> None:
    nested_geometrie = SimpleNamespace(
        name="Geometrie",
        geometric=True,
        geometric_multi=False,
        geometric_is_point_like=False,
        geometric_is_line_like=False,
        geometric_is_polygon_like=True,
    )
    nested_symbolposition = SimpleNamespace(
        name="Symbolposition",
        geometric=True,
        geometric_multi=True,
        geometric_is_point_like=True,
        geometric_is_line_like=False,
        geometric_is_polygon_like=False,
    )
    nested_struct = SimpleNamespace(attributes=[nested_symbolposition, nested_geometrie])
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": False},
        geometric=True,
        geometric_multi=True,
        geometric_is_point_like=True,
        geometric_is_line_like=False,
        geometric_is_polygon_like=True,
        type_related_type_class=nested_struct,
        types=["Any"],
        reference_targets=[],
    )

    expression = _field_expression(attribute, class_map={}, srid=2056)

    assert expression.startswith("models.PolygonField(")


def test_field_expression_uses_nested_geometrie_line_for_structure_lists() -> None:
    nested_geometrie = SimpleNamespace(
        name="Geometrie",
        geometric=True,
        geometric_multi=True,
        geometric_is_point_like=False,
        geometric_is_line_like=True,
        geometric_is_polygon_like=False,
    )
    nested_struct = SimpleNamespace(attributes=[nested_geometrie])
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": False},
        geometric=True,
        geometric_multi=True,
        geometric_is_point_like=True,
        geometric_is_line_like=True,
        geometric_is_polygon_like=False,
        type_related_type_class=nested_struct,
        types=["Any"],
        reference_targets=[],
    )

    expression = _field_expression(attribute, class_map={}, srid=2056)

    assert expression.startswith("models.MultiLineStringField(")


def test_field_expression_prefers_compound_curve_for_arced_lines() -> None:
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": False},
        geometric=True,
        geometric_multi=False,
        geometric_is_point_like=False,
        geometric_is_line_like=True,
        geometric_is_polygon_like=False,
        line_type=SimpleNamespace(arcs=True),
        type_related_type_class=None,
        types=["Any"],
        reference_targets=[],
    )

    expression = _field_expression(attribute, class_map={}, srid=2056)

    assert expression.startswith("models.CompoundCurveField(")


def test_field_expression_prefers_multi_surface_for_arced_multi_polygons() -> None:
    attribute = SimpleNamespace(
        type_restrictions={"mandatory": False},
        geometric=True,
        geometric_multi=True,
        geometric_is_point_like=False,
        geometric_is_line_like=False,
        geometric_is_polygon_like=True,
        line_type=SimpleNamespace(arcs=True),
        type_related_type_class=None,
        types=["Any"],
        reference_targets=[],
    )

    expression = _field_expression(attribute, class_map={}, srid=2056)

    assert expression.startswith("models.MultiSurfaceField(")
