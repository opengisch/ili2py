from ili2django.choices import (
    IliChoice,
    IliChoices,
    as_admin_lookups,
    as_form_choices,
    build_ili_choices,
)
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


def test_build_ili_choices_exposes_textchoices_like_accessors() -> None:
    Status = build_ili_choices(
        "Status",
        [
            {"code": "draft", "label": "Draft", "order": 20},
            {"code": "final", "label": "Final", "order": 10},
        ],
    )

    assert issubclass(Status, IliChoices)
    assert Status.values == ["draft", "final"]
    assert Status.labels == ["Draft", "Final"]
    assert Status.choices == [("draft", "Draft"), ("final", "Final")]
    assert [str(member) for member in Status.ordered()] == ["final", "draft"]


def test_build_ili_choices_supports_tree_and_ordering() -> None:
    Coverage = build_ili_choices(
        "Coverage",
        [
            {
                "code": "building",
                "label": "Building",
                "order": 1,
            },
            {
                "code": "residential",
                "label": "Residential",
                "order": 2,
                "parent": "building",
            },
        ],
    )

    assert [str(member) for member in Coverage.roots()] == ["building"]
    assert [str(member) for member in Coverage.children_of("building")] == ["residential"]
    assert as_form_choices(Coverage) == [
        ("building", "Building"),
        ("residential", "Residential"),
    ]
    assert as_admin_lookups(Coverage, ordered=True) == [
        ("building", "Building"),
        ("residential", "Residential"),
    ]


def test_build_ili_choices_normalizes_member_names_and_deduplicates() -> None:
    Mixed = build_ili_choices(
        "Mixed",
        [
            {"code": "in-force", "label": "In force"},
            {"code": "in force", "label": "In force duplicate name"},
            {"code": "123", "label": "Numeric"},
        ],
    )

    assert isinstance(Mixed.IN_FORCE, IliChoice)
    assert str(Mixed.IN_FORCE) == "in-force"
    assert str(Mixed.IN_FORCE_2) == "in force"
    assert str(Mixed.V_123) == "123"


def test_inline_ili_choices_subclass_works_without_builder() -> None:
    class CountryCodeEnumValueChoices(IliChoices):
        CH = IliChoice("CH", _("CH"), order=0)
        FL = IliChoice("FL", _("FL"), order=1)

    assert CountryCodeEnumValueChoices.values == ["CH", "FL"]
    assert isinstance(CountryCodeEnumValueChoices.choices[0][1], Promise)
    assert isinstance(as_form_choices(CountryCodeEnumValueChoices)[1][1], Promise)
