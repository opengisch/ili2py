"""ili2django package."""

from .choices import IliChoices, as_admin_lookups, as_form_choices, build_ili_choices

__all__ = [
	"__version__",
	"IliChoices",
	"build_ili_choices",
	"as_form_choices",
	"as_admin_lookups",
]
__version__ = "0.1.0"
