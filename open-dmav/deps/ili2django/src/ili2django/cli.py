"""Command line interface for ili2django."""

from __future__ import annotations

import click

from ili2django.generator import generate_django_models


@click.group(help="Generate Django integration artifacts from INTERLIS IMD.")
def main() -> None:
    pass


@main.command("generate-models", help="Generate Django models from an IMD file.")
@click.option("-i", "--imd", required=True, help="Path to IMD16 file.")
@click.option("-o", "--output", required=True, help="Output directory.")
@click.option(
    "-l",
    "--library-name",
    required=True,
    help="Logical library name passed to ili2py library builder.",
)
@click.option(
    "-a",
    "--app-prefix",
    default="ili",
    show_default=True,
    help="Prefix for generated Django app package names.",
)
@click.option(
    "--srid",
    default=2056,
    show_default=True,
    type=int,
    help="SRID used for generated GeoDjango geometry fields.",
)
def generate_models(
    imd: str, output: str, library_name: str, app_prefix: str, srid: int
) -> None:
    result = generate_django_models(
        imd_path=imd,
        output_root=output,
        library_name=library_name,
        app_prefix=app_prefix,
        srid=srid,
    )
    click.echo(f"Generated {len(result.created_files)} files into {result.output_root}")


if __name__ == "__main__":
    main()
