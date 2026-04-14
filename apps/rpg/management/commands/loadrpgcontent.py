"""Load an RPG content pack (YAML directory) into the catalog.

Examples::

    python manage.py loadrpgcontent
        Loads content/rpg/initial/ (the seed pack).

    python manage.py loadrpgcontent --pack content/rpg/packs/dragons --namespace dragons-
        Loads a third-party pack with every slug prefixed ``dragons-``.

    python manage.py loadrpgcontent --dry-run
        Parses + runs upserts inside a rolled-back transaction to preview
        changes. Exits non-zero on validation errors.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.rpg.content.loader import ContentPack, ContentPackError


DEFAULT_PACK = "content/rpg/initial"


class Command(BaseCommand):
    help = "Load an RPG content pack (YAML) into the catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pack",
            default=None,
            help=f"Pack directory (default: {DEFAULT_PACK}).",
        )
        parser.add_argument(
            "--namespace",
            default="",
            help="Prefix every slug with this string (use for third-party packs).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse + load inside a rolled-back transaction. No changes persist.",
        )

    def handle(self, *args, **options):
        pack_arg = options["pack"] or DEFAULT_PACK
        pack_path = Path(pack_arg)
        if not pack_path.is_absolute():
            pack_path = Path(settings.BASE_DIR) / pack_path
        if not pack_path.is_dir():
            raise CommandError(f"Pack directory not found: {pack_path}")

        namespace = options["namespace"]
        dry_run = options["dry_run"]

        self.stdout.write(
            f"Loading pack: {pack_path}"
            + (f" (namespace={namespace!r})" if namespace else "")
            + (" [dry-run]" if dry_run else "")
        )

        try:
            pack = ContentPack(pack_path, namespace=namespace)
            pack.load(stdout=self.stdout, dry_run=dry_run)
        except ContentPackError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Content pack load complete."))
