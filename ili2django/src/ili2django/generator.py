"""Django model generator based on ili2py IMD parsing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import keyword
import re
from pathlib import Path

from ili2py.mappers.helpers import Index
from ili2py.readers.interlis_24.ilismeta16.xsdata import Imd16Reader
from ili2py.writers.py.python_structure import Library


@dataclass(frozen=True)
class _ClassRef:
    app_label: str
    model_name: str
    abstract: bool


@dataclass(frozen=True)
class _EnumRef:
    model_name: str
    enum_identifier: str
    enum_name: str
    values: list[str]
    tree: bool


@dataclass(frozen=True)
class GenerationResult:
    output_root: Path
    created_files: list[Path]


def _snake(value: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "_", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value.lower() or "value"


def _pascal(value: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", value)
    words = [p for p in parts if p]
    return "".join(word[:1].upper() + word[1:] for word in words) or "Model"


def _field_name(value: str) -> str:
    name = _snake(value)
    if keyword.iskeyword(name):
        return f"{name}_field"
    return name


def _choice_member_name(code: str, used_names: set[str]) -> str:
    candidate = _snake(code).upper()
    if not candidate:
        candidate = "VALUE"
    if candidate[:1].isdigit():
        candidate = f"V_{candidate}"

    unique = candidate
    suffix = 2
    while unique in used_names:
        unique = f"{candidate}_{suffix}"
        suffix += 1

    used_names.add(unique)
    return unique


def _db_table_name(app_label: str, model_name: str) -> str:
    """Generate PostgreSQL-safe db_table names with deterministic hash fallback."""

    base_name = f"{app_label.lower()}__{_snake(model_name)}"
    if len(base_name) <= 63:
        return base_name

    digest = hashlib.sha1(base_name.encode("utf-8")).hexdigest()[:10]
    prefix = base_name[: 63 - len(digest) - 1]
    return f"{prefix}_{digest}"


def _resolve_fk(ref_tid: str, class_map: dict[str, _ClassRef]) -> str | None:
    ref = class_map.get(ref_tid)
    if not ref or ref.abstract:
        return None
    return f"{ref.app_label}.{ref.model_name}"


def _build_model_name_map(classes: list) -> dict[str, str]:
    """Build deterministic, app-local unique Django model names."""

    base_names = {cls.identifier: _pascal(cls.name) for cls in classes}
    base_counts = Counter(base_names.values())
    used_names: set[str] = set()
    model_names: dict[str, str] = {}

    for cls in classes:
        base_name = base_names[cls.identifier]
        if base_counts[base_name] == 1:
            candidate = base_name
        else:
            scope = cls.identifier.split(".")[-2] if "." in cls.identifier else "Model"
            candidate = f"{_pascal(scope)}{base_name}"

        unique = candidate
        counter = 2
        while unique in used_names:
            unique = f"{candidate}{counter}"
            counter += 1

        used_names.add(unique)
        model_names[cls.identifier] = unique

    return model_names


def _is_many(restrictions: dict) -> bool:
    multiplicity = restrictions.get("multiplicity")
    if not multiplicity:
        return False
    max_value = multiplicity.get("max")
    if max_value in (None, "*"):
        return True
    if isinstance(max_value, int) and max_value > 1:
        return True
    return False


def _nullable(restrictions: dict) -> bool:
    multiplicity = restrictions.get("multiplicity")
    if isinstance(multiplicity, dict):
        min_value = multiplicity.get("min")
        if min_value is not None:
            if isinstance(min_value, int):
                return min_value == 0
            if isinstance(min_value, str) and min_value.isdigit():
                return int(min_value) == 0

    return not bool(restrictions.get("mandatory", False))


def _module_name_from_class_identifier(identifier: str) -> str | None:
    parts = identifier.split(".")
    if len(parts) < 2:
        return None
    return parts[-2]


def _collect_enum_refs(
    modules: list,
    classes: list,
    class_model_names: dict[str, str],
) -> tuple[dict[tuple[str, str], _EnumRef], dict[str, _EnumRef]]:
    """Collect enum definitions and resolution maps for global and local enums."""

    used_model_names = set(class_model_names.values())
    by_module_and_name: dict[tuple[str, str], _EnumRef] = {}
    by_attribute_id: dict[str, _EnumRef] = {}

    def unique_model_name(base: str) -> str:
        candidate = f"{_pascal(base)}Value"
        unique = candidate
        counter = 2
        while unique in used_model_names:
            unique = f"{candidate}{counter}"
            counter += 1
        used_model_names.add(unique)
        return unique

    for module in modules:
        for enumeration in module.enumerations:
            by_module_and_name[(module.name, enumeration.name)] = _EnumRef(
                model_name=unique_model_name(enumeration.name),
                enum_identifier=enumeration.identifier,
                enum_name=enumeration.name,
                values=list(enumeration.values or []),
                tree=bool(getattr(enumeration, "tree", False)),
            )

    for cls in classes:
        for attribute in getattr(cls, "attributes", []):
            local_enum = getattr(attribute, "enumeration", None)
            if local_enum is None:
                continue
            enum_name = local_enum.name or f"{cls.name}{attribute.name}Enum"
            by_attribute_id[attribute.identifier] = _EnumRef(
                model_name=unique_model_name(enum_name),
                enum_identifier=local_enum.identifier,
                enum_name=enum_name,
                values=list(local_enum.values or []),
                tree=bool(getattr(local_enum, "tree", False)),
            )

    return by_module_and_name, by_attribute_id


def _enum_target(
    attribute,
    owner_class,
    global_enum_map: dict[tuple[str, str], _EnumRef],
    local_enum_map: dict[str, _EnumRef],
    app_label: str,
) -> str | None:
    local_enum = local_enum_map.get(attribute.identifier)
    if local_enum:
        return f"{app_label}.{local_enum.model_name}"

    first_type = attribute.types[0] if attribute.types else None
    if not first_type:
        return None

    module_name = _module_name_from_class_identifier(owner_class.identifier)
    if not module_name:
        return None

    global_enum = global_enum_map.get((module_name, first_type))
    if not global_enum:
        return None

    return f"{app_label}.{global_enum.model_name}"


def _prefers_curved(attr_obj) -> bool:
    line_type = getattr(attr_obj, "line_type", None)
    return bool(line_type and getattr(line_type, "arcs", False))


def _geom_type_from_flags(attr_obj, prefer_curved: bool = False) -> str | None:
    is_multi = bool(getattr(attr_obj, "geometric_multi", False))

    if getattr(attr_obj, "geometric_is_polygon_like", False):
        if prefer_curved:
            return "MultiSurfaceField" if is_multi else "CurvePolygonField"
        return "MultiPolygonField" if is_multi else "PolygonField"

    if getattr(attr_obj, "geometric_is_line_like", False):
        if prefer_curved:
            return "MultiCurveField" if is_multi else "CompoundCurveField"
        return "MultiLineStringField" if is_multi else "LineStringField"

    if getattr(attr_obj, "geometric_is_point_like", False):
        return "MultiPointField" if is_multi else "PointField"

    return None


def _field_expression(
    attribute,
    class_map: dict[str, _ClassRef],
    srid: int,
    enum_fk_target: str | None = None,
    geometric_override: str | None = None,
) -> str:
    restrictions = attribute.type_restrictions or {}
    nullable = _nullable(restrictions)
    null_kw = f"null={str(nullable)}, blank={str(nullable)}"

    if enum_fk_target:
        return (
            f"models.ForeignKey('{enum_fk_target}', on_delete=models.PROTECT, "
            f"related_name='+', {null_kw})"
        )

    if getattr(attribute, "geometric", False):
        def _geom_constructor(field_name: str, fallback: str | None = None) -> str:
            if fallback:
                return f'getattr(models, "{field_name}", models.{fallback})'
            return f"models.{field_name}"

        if geometric_override:
            if ":" in geometric_override:
                field_name, fallback = geometric_override.split(":", 1)
                return f"{_geom_constructor(field_name, fallback)}(srid={srid}, {null_kw})"
            return f"{_geom_constructor(geometric_override)}(srid={srid}, {null_kw})"

        geom_type = None
        struct_class = getattr(attribute, "type_related_type_class", None)
        if struct_class and getattr(struct_class, "attributes", None):
            geometric_subattrs = [
                sub_attr
                for sub_attr in struct_class.attributes
                if getattr(sub_attr, "geometric", False)
            ]
            preferred_subattrs = [
                sub_attr
                for sub_attr in geometric_subattrs
                if str(getattr(sub_attr, "name", "")).lower() in {"geometrie", "geometry", "geom"}
            ]
            for sub_attr in preferred_subattrs or geometric_subattrs:
                geom_type = _geom_type_from_flags(
                    sub_attr,
                    prefer_curved=_prefers_curved(sub_attr),
                )
                if geom_type:
                    break

        if not geom_type:
            geom_type = _geom_type_from_flags(
                attribute,
                prefer_curved=_prefers_curved(attribute),
            ) or "GeometryField"

        return f"models.{geom_type}(srid={srid}, {null_kw})"

    if _is_many(restrictions):
        return f"models.JSONField(default=list, {null_kw})"

    first_type = attribute.types[0] if attribute.types else "str"

    if first_type == "Ref":
        if attribute.reference_targets:
            target = _resolve_fk(attribute.reference_targets[0], class_map)
            if target:
                return (
                    f"models.ForeignKey('{target}', on_delete=models.PROTECT, "
                    f"related_name='+', {null_kw})"
                )
        return f"models.CharField(max_length=255, {null_kw})"

    if first_type == "str":
        max_length = restrictions.get("max_length", 255)
        return f"models.CharField(max_length={max_length}, {null_kw})"
    if first_type == "int":
        return f"models.IntegerField({null_kw})"
    if first_type == "float":
        return f"models.FloatField({null_kw})"
    if first_type == "bool":
        if nullable:
            return "models.BooleanField(null=True, blank=True, default=None)"
        return "models.BooleanField(default=False)"

    if first_type in {"BinBlBoxType", "XmlBlBoxType"}:
        return f"models.BinaryField({null_kw})"

    return f"models.TextField({null_kw})"


def _render_models_py(
    app_label: str,
    modules: list,
    classes: list,
    class_model_names: dict[str, str],
    class_map: dict[str, _ClassRef],
    srid: int,
) -> str:
    global_enum_map, local_enum_map = _collect_enum_refs(
        modules=modules,
        classes=classes,
        class_model_names=class_model_names,
    )
    enum_models = list(global_enum_map.values()) + list(local_enum_map.values())

    def _promote_to_multi(kind: str) -> str:
        if kind == "PointField":
            return "MultiPointField"
        if kind == "LineStringField":
            return "MultiLineStringField"
        if kind == "PolygonField":
            return "MultiPolygonField"
        if kind == "CompoundCurveField":
            return "MultiCurveField"
        if kind == "CurvePolygonField":
            return "MultiSurfaceField"
        return kind

    def _geometry_kind_from_class(class_obj) -> str | None:
        geometric_attrs = [
            attr
            for attr in getattr(class_obj, "attributes", [])
            if getattr(attr, "geometric", False)
        ]
        if not geometric_attrs:
            return None

        preferred = [
            attr
            for attr in geometric_attrs
            if str(getattr(attr, "name", "")).lower() in {"geometrie", "geometry", "geom"}
        ]

        for attr in preferred or geometric_attrs:
            kind = _geom_type_from_flags(
                attr,
                prefer_curved=_prefers_curved(attr),
            )
            if kind:
                return kind
        return None

    class_geometry_kind_by_name: dict[str, str | None] = {}
    for class_obj in classes:
        kind = _geometry_kind_from_class(class_obj)
        if not kind:
            continue
        existing = class_geometry_kind_by_name.get(class_obj.name)
        if existing and existing != kind:
            class_geometry_kind_by_name[class_obj.name] = None
        else:
            class_geometry_kind_by_name[class_obj.name] = kind

    curved_geometry_map: dict[str, str] = {
        "circularstring": "CircularStringField:LineStringField",
        "compoundcurve": "CompoundCurveField:MultiLineStringField",
        "curvepolygon": "CurvePolygonField:PolygonField",
        "multicurve": "MultiCurveField:MultiLineStringField",
        "multisurface": "MultiSurfaceField:MultiPolygonField",
    }

    def _normalize_curved_type_token(type_name: str) -> str:
        token = str(type_name).split(".")[-1].strip().lower().replace("_", "")
        for suffix in ("zm", "z", "m"):
            if token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    def _geometry_override_from_curved_types(attribute) -> str | None:
        candidate_types = list(getattr(attribute, "types", []) or [])

        struct_class = getattr(attribute, "type_related_type_class", None)
        if struct_class and getattr(struct_class, "attributes", None):
            struct_content = struct_class.attributes[0]
            candidate_types.extend(getattr(struct_content, "types", []) or [])

        for type_name in candidate_types:
            token = _normalize_curved_type_token(type_name)
            override = curved_geometry_map.get(token)
            if override:
                return override
        return None

    def _geometry_override_from_struct(attribute) -> str | None:
        struct_class = getattr(attribute, "type_related_type_class", None)
        if not struct_class or not getattr(struct_class, "attributes", None):
            return None

        # MultiValue attributes are represented by a HOP class with one
        # struct_content attribute that references the actual base structure.
        struct_content = struct_class.attributes[0]
        if not getattr(struct_content, "types", None):
            return None

        base_structure_name = struct_content.types[0]
        base_kind = class_geometry_kind_by_name.get(base_structure_name)
        if not base_kind:
            return None

        if getattr(attribute, "geometric_multi", False):
            return _promote_to_multi(base_kind)
        return base_kind

    lines = [
        '"""Generated by ili2django. Do not edit manually."""',
        "",
        "from django.contrib.gis.db import models",
        "from django.utils.translation import gettext_lazy as _",
        "",
        "from ili2django.choices import IliChoice, IliChoices",
        "from ili2django.decorators import ili_field, interlis_model",
        "",
    ]

    for enum_ref in enum_models:
        qname = f"{app_label}.{enum_ref.enum_name}"
        lines.append(
            f"@interlis_model(oid='{enum_ref.enum_identifier}', qname='{qname}')"
        )
        lines.append(f"class {enum_ref.model_name}(models.Model):")
        lines.append(
            "    code = ili_field(models.CharField(max_length=255, unique=True), "
            f"oid='{enum_ref.enum_identifier}.code', qname='{qname}.code')"
        )
        lines.append(
            "    label = ili_field(models.CharField(max_length=255), "
            f"oid='{enum_ref.enum_identifier}.label', qname='{qname}.label')"
        )
        if enum_ref.tree:
            lines.append(
                "    parent = models.ForeignKey('self', on_delete=models.PROTECT, "
                "related_name='children', null=True, blank=True)"
            )
        lines.append("    order = models.IntegerField(default=0)")
        lines.append(f"    __ili2django_values__ = {enum_ref.values!r}")
        lines.append(f"    __ili2django_tree__ = {enum_ref.tree!r}")
        lines.append("")
        lines.append("    def __str__(self) -> str:")
        lines.append("        return self.label or self.code")
        lines.append("")
        lines.append("    class Meta:")
        lines.append(
            f"        db_table = '{_db_table_name(app_label, enum_ref.model_name)}'"
        )
        lines.append("")
        lines.append(f"class {enum_ref.model_name}Choices(IliChoices):")
        if not enum_ref.values:
            lines.append("    pass")
        else:
            used_choice_names: set[str] = set()
            for order, code in enumerate(enum_ref.values):
                label = code.split(".")[-1]
                member_name = _choice_member_name(code, used_choice_names)
                if enum_ref.tree:
                    parent_code = ".".join(code.split(".")[:-1]) or None
                    lines.append(
                        f"    {member_name} = IliChoice({code!r}, _({label!r}), order={order}, parent={parent_code!r})"
                    )
                else:
                    lines.append(
                        f"    {member_name} = IliChoice({code!r}, _({label!r}), order={order})"
                    )
        lines.append("")

    for cls in classes:
        model_name = class_model_names.get(cls.identifier, _pascal(cls.name))
        qname = f"{app_label}.{cls.name}"
        lines.append(f"@interlis_model(oid='{cls.identifier}', qname='{qname}')")
        lines.append(f"class {model_name}(models.Model):")

        if getattr(cls, "oid", None):
            lines.append(
                "    tid = ili_field(models.CharField(max_length=255, unique=True), "
                f"oid='{cls.oid.identifier}', qname='{qname}.tid')"
            )

        if not cls.attributes:
            lines.append("    pass")
        else:
            for attribute in cls.attributes:
                attr_name = _field_name(attribute.name)
                enum_fk_target = _enum_target(
                    attribute=attribute,
                    owner_class=cls,
                    global_enum_map=global_enum_map,
                    local_enum_map=local_enum_map,
                    app_label=app_label,
                )
                field_expr = _field_expression(
                    attribute,
                    class_map,
                    srid,
                    enum_fk_target=enum_fk_target,
                    geometric_override=(
                        _geometry_override_from_curved_types(attribute)
                        or _geometry_override_from_struct(attribute)
                    ),
                )
                field_qname = f"{qname}.{attribute.name}"
                lines.append(
                    f"    {attr_name} = ili_field({field_expr}, "
                    f"oid='{attribute.identifier}', qname='{field_qname}')"
                )

        lines.append("")
        lines.append("    class Meta:")
        if cls.abstract:
            lines.append("        abstract = True")
        lines.append(f"        db_table = '{_db_table_name(app_label, model_name)}'")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_init_py() -> str:
    return "from .models_generated import *\n"


def generate_django_models(
    imd_path: str,
    output_root: str,
    library_name: str,
    app_prefix: str,
    srid: int = 2056,
    bootstrap: bool = False,
) -> GenerationResult:
    """Generate Django model modules from an IMD file."""

    metamodel = Imd16Reader().read(imd_path)
    index = Index(metamodel.datasection)
    library = Library.from_imd(metamodel.datasection.ModelData, index, library_name)

    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)

    class_map: dict[str, _ClassRef] = {}
    for package in library.packages:
        app_label = _snake(f"{app_prefix}_{package.name}")
        package_classes = []
        for module in package.modules:
            package_classes.extend(module.classes)

        package_model_names = _build_model_name_map(package_classes)
        for cls in package_classes:
            class_map[cls.identifier] = _ClassRef(
                app_label=app_label,
                model_name=package_model_names.get(cls.identifier, _pascal(cls.name)),
                abstract=bool(getattr(cls, "abstract", False)),
            )

    created_files: list[Path] = []

    for package in library.packages:
        app_label = _snake(f"{app_prefix}_{package.name}")
        app_dir = out / app_label
        app_dir.mkdir(parents=True, exist_ok=True)

        classes = []
        for module in package.modules:
            classes.extend(module.classes)
        class_model_names = _build_model_name_map(classes)

        (app_dir / "models_generated.py").write_text(
            _render_models_py(
                app_label=app_label,
                modules=package.modules,
                classes=classes,
                class_model_names=class_model_names,
                class_map=class_map,
                srid=srid,
            ),
            encoding="utf-8",
        )
        created_files.append(app_dir / "models_generated.py")

        if bootstrap:
            (app_dir / "apps.py").write_text(
                "\n".join(
                    [
                        "from django.apps import AppConfig",
                        "",
                        f"class {_pascal(app_label)}Config(AppConfig):",
                        f"    name = '{app_label}'",
                        f"    label = '{app_label}'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            created_files.append(app_dir / "apps.py")

            (app_dir / "models.py").write_text(
                _render_init_py(),
                encoding="utf-8",
            )
            created_files.append(app_dir / "models.py")

            (app_dir / "__init__.py").write_text("", encoding="utf-8")
            created_files.append(app_dir / "__init__.py")

    return GenerationResult(output_root=out, created_files=created_files)
