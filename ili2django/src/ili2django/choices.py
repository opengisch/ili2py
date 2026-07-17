"""TextChoices-like helpers for INTERLIS enum/value-list data."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, cast


_IDENTIFIER_RE = re.compile(r"[^0-9A-Za-z]+")


class IliChoice(str):
    """Single value-list entry with INTERLIS metadata."""

    label: Any
    order: int
    parent: str | None
    ref: str | None

    def __new__(
        cls,
        code: str,
        label: Any,
        order: int = 0,
        parent: str | None = None,
        ref: str | None = None,
    ) -> IliChoice:
        obj = str.__new__(cls, code)
        obj.label = label
        obj.order = order
        obj.parent = parent
        obj.ref = ref
        return obj


class _classproperty(property):
    def __get__(self, _obj: object, owner: type[object]) -> Any:
        return self.fget(owner)


class IliChoicesMeta(type):
    def __new__(
        mcls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
    ) -> IliChoicesMeta:
        cls = cast(IliChoicesMeta, super().__new__(mcls, name, bases, namespace))

        members: dict[str, IliChoice] = {}
        for base in bases:
            base_members = getattr(base, "_members", None)
            if isinstance(base_members, dict):
                members.update(base_members)

        for key, value in namespace.items():
            if isinstance(value, IliChoice):
                members[key] = value

        cls._members = members
        cls._by_code = {str(choice): choice for choice in members.values()}
        return cls

    def __iter__(cls):
        return iter(cls._members.values())

    def __len__(cls) -> int:
        return len(cls._members)


class IliChoices(metaclass=IliChoicesMeta):
    """TextChoices-like base class for INTERLIS value-list declarations."""

    _members: dict[str, IliChoice]
    _by_code: dict[str, IliChoice]

    @_classproperty
    def choices(cls) -> list[tuple[str, Any]]:
        return [(str(member), member.label) for member in cls._members.values()]

    @_classproperty
    def values(cls) -> list[str]:
        return [str(member) for member in cls._members.values()]

    @_classproperty
    def labels(cls) -> list[str]:
        return [member.label for member in cls._members.values()]

    @_classproperty
    def names(cls) -> list[str]:
        return list(cls._members.keys())

    @classmethod
    def ordered(cls) -> list[IliChoice]:
        return sorted(cls._members.values(), key=lambda member: (member.order, str(member)))

    @classmethod
    def roots(cls) -> list[IliChoice]:
        return [member for member in cls._members.values() if member.parent is None]

    @classmethod
    def children_of(cls, code: str) -> list[IliChoice]:
        return [member for member in cls._members.values() if member.parent == code]

    @classmethod
    def get(cls, code: str) -> IliChoice | None:
        return cls._by_code.get(code)


def as_form_choices(ili_choices: type[IliChoices], *, ordered: bool = False) -> list[tuple[str, Any]]:
    """Build ``(value, label)`` tuples for Django form fields."""

    members = ili_choices.ordered() if ordered else list(ili_choices)
    return [(str(member), member.label) for member in members]


def as_admin_lookups(ili_choices: type[IliChoices], *, ordered: bool = False) -> list[tuple[str, Any]]:
    """Build admin lookup tuples usable in ``SimpleListFilter.lookups``."""

    return as_form_choices(ili_choices, ordered=ordered)


def build_ili_choices(
    name: str,
    entries: Iterable[Mapping[str, Any]],
) -> type[IliChoices]:
    """Build an ``IliChoices`` subclass from value-list rows.

    Required entry keys:
    - ``code``
    - ``label``

    Optional entry keys:
    - ``order``
    - ``parent``
    - ``ref``
    """

    members: dict[str, IliChoice] = {}
    used_names: set[str] = set()

    for entry in entries:
        code = str(entry["code"])
        label = entry["label"]
        order = int(entry.get("order", 0))
        parent = entry.get("parent")
        if parent is not None:
            parent = str(parent)
        ref = entry.get("ref")
        if ref is not None:
            ref = str(ref)

        member_name = _member_name_from_code(code, used_names)
        members[member_name] = IliChoice(code, label, order, parent, ref)

    if not members:
        raise ValueError("build_ili_choices requires at least one entry")

    namespace: dict[str, Any] = {"__module__": __name__}
    namespace.update(members)
    return cast(type[IliChoices], IliChoicesMeta(name, (IliChoices,), namespace))


def _member_name_from_code(code: str, used_names: set[str]) -> str:
    candidate = _IDENTIFIER_RE.sub("_", code).strip("_").upper()
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
