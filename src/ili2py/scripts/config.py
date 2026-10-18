from dataclasses import dataclass, field


@dataclass
class ModelSet[T]:
    """An IMD with its XTF files and the model names which are drawn in the diagrams."""

    imd: str
    model_names: T
    xtf: list[str] = field(default_factory=list)


@dataclass
class DiagramConfig:
    """The arguments passed to `uml_diagram` for one diagram."""

    flavour: str
    direction: str
    postfix: str
    linetype: str | None = None
    multiplier: int = 2
