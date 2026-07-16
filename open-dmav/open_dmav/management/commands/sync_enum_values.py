"""Synchronize generated enum value-list tables with model metadata."""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection, models, transaction


@dataclass
class SyncStats:
    model_count: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0


def _is_generated_enum_model(model: type[models.Model]) -> bool:
    return hasattr(model, "__ili2django_values__")


def _enum_models() -> list[type[models.Model]]:
    result: list[type[models.Model]] = []
    for model in apps.get_models():
        if not model._meta.app_label.startswith("odmav_"):
            continue
        if model._meta.abstract:
            continue
        if _is_generated_enum_model(model):
            result.append(model)
    return result


def _label_from_code(code: str) -> str:
    return code.split(".")[-1]


class Command(BaseCommand):
    help = "Populate/update generated enum value-list rows from __ili2django_values__."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Delete enum rows not present in generated __ili2django_values__ metadata.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        prune = bool(options["prune"])
        dry_run = bool(options["dry_run"])
        existing_tables = set(connection.introspection.table_names())

        stats = SyncStats()
        for model in _enum_models():
            if model._meta.db_table not in existing_tables:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {model._meta.label}: table {model._meta.db_table} does not exist yet."
                    )
                )
                continue
            stats.model_count += 1
            values: list[str] = list(getattr(model, "__ili2django_values__", []))
            is_tree = bool(getattr(model, "__ili2django_tree__", False))
            seen_codes: set[str] = set()
            node_cache: dict[str, models.Model] = {}

            for order, code in enumerate(values):
                defaults: dict[str, object] = {
                    "label": _label_from_code(code),
                    "order": order,
                }
                if is_tree and any(field.name == "parent" for field in model._meta.get_fields()):
                    parent_code = ".".join(code.split(".")[:-1])
                    parent = None
                    if parent_code:
                        parent = node_cache.get(parent_code)
                        if parent is None:
                            parent = model.objects.filter(code=parent_code).first()
                    defaults["parent"] = parent

                seen_codes.add(code)

                if dry_run:
                    exists = model.objects.filter(code=code).exists()
                    if exists:
                        stats.updated += 1
                    else:
                        stats.created += 1
                    continue

                obj, created = model.objects.update_or_create(code=code, defaults=defaults)
                node_cache[code] = obj
                if created:
                    stats.created += 1
                else:
                    stats.updated += 1

            if prune:
                qs = model.objects.exclude(code__in=seen_codes)
                deleted_count = qs.count()
                if deleted_count and not dry_run:
                    qs.delete()
                stats.deleted += deleted_count

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Synced enum value-lists "
                f"(models={stats.model_count}, created={stats.created}, "
                f"updated={stats.updated}, deleted={stats.deleted}, dry_run={dry_run})."
            )
        )
