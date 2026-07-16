from types import SimpleNamespace
import sys
import types

from ili2django.decorators import ensure_curve_field_aliases
from ili2django.generator import _field_expression


def _geom_attr() -> SimpleNamespace:
    return SimpleNamespace(
        type_restrictions={},
        geometric=True,
        geometric_multi=False,
        geometric_is_point_like=False,
        geometric_is_line_like=True,
        geometric_is_polygon_like=False,
        type_related_type_class=None,
        types=["LineString"],
        reference_targets=[],
    )


def test_field_expression_curve_polygon_with_fallback_constructor():
    expr = _field_expression(
        _geom_attr(),
        class_map={},
        srid=2056,
        geometric_override="CurvePolygonField:PolygonField",
    )

    assert expr == 'getattr(models, "CurvePolygonField", models.PolygonField)(srid=2056, null=True, blank=True)'


def test_field_expression_multicurve_with_fallback_constructor():
    expr = _field_expression(
        _geom_attr(),
        class_map={},
        srid=2056,
        geometric_override="MultiCurveField:MultiLineStringField",
    )

    assert expr == 'getattr(models, "MultiCurveField", models.MultiLineStringField)(srid=2056, null=True, blank=True)'


def test_ensure_curve_field_aliases_maps_missing_fields(monkeypatch):
    fake_models = types.ModuleType("django.contrib.gis.db.models")

    class LineStringField:
        pass

    class MultiLineStringField:
        pass

    class PolygonField:
        pass

    class MultiPolygonField:
        pass

    fake_models.LineStringField = LineStringField
    fake_models.MultiLineStringField = MultiLineStringField
    fake_models.PolygonField = PolygonField
    fake_models.MultiPolygonField = MultiPolygonField

    fake_db = types.ModuleType("django.contrib.gis.db")
    fake_db.models = fake_models

    fake_gis = types.ModuleType("django.contrib.gis")
    fake_gis.db = fake_db

    fake_contrib = types.ModuleType("django.contrib")
    fake_contrib.gis = fake_gis

    fake_django = types.ModuleType("django")
    fake_django.contrib = fake_contrib

    monkeypatch.setitem(sys.modules, "django", fake_django)
    monkeypatch.setitem(sys.modules, "django.contrib", fake_contrib)
    monkeypatch.setitem(sys.modules, "django.contrib.gis", fake_gis)
    monkeypatch.setitem(sys.modules, "django.contrib.gis.db", fake_db)
    monkeypatch.setitem(sys.modules, "django.contrib.gis.db.models", fake_models)

    ensure_curve_field_aliases()

    assert fake_models.CircularStringField is LineStringField
    assert fake_models.CompoundCurveField is MultiLineStringField
    assert fake_models.CurvePolygonField is PolygonField
    assert fake_models.MultiCurveField is MultiLineStringField
    assert fake_models.MultiSurfaceField is MultiPolygonField
