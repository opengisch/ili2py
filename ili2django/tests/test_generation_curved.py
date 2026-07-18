from ili2django.generator import _field_expression


def _geom_attr(*, polygon_like: bool = False, multi: bool = False):
    return type(
        "GeomAttr",
        (),
        {
            "type_restrictions": {},
            "geometric": True,
            "geometric_multi": multi,
            "geometric_is_point_like": False,
            "geometric_is_line_like": not polygon_like,
            "geometric_is_polygon_like": polygon_like,
            "type_related_type_class": None,
            "types": ["Geometry"],
            "reference_targets": [],
            "line_type": type("LineType", (), {"arcs": True})(),
        },
    )()


def test_field_expression_curve_polygon_uses_native_field():
    expr = _field_expression(
        _geom_attr(polygon_like=True),
        class_map={},
        srid=2056,
    )

    assert expr == "models.CurvePolygonField(srid=2056, null=True, blank=True)"


def test_field_expression_multicurve_uses_native_field():
    expr = _field_expression(
        _geom_attr(multi=True),
        class_map={},
        srid=2056,
    )

    assert expr == "models.MultiCurveField(srid=2056, null=True, blank=True)"
