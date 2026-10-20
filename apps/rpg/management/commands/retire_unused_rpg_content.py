"""Preview or apply the owner's exact unused first-party catalog retirement."""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.rpg.retired_catalog import (
    RetiredCatalogCollision, retire_unused_catalog, retire_unused_catalog_explicitly, retirement_summary,
)
from apps.rpg.retirement_resources import RetirementResourceError


class Command(BaseCommand):
    help = "Remove explicitly retired legacy pets, eggs, potions and pet accessories and their unused dependencies."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Execute cleanup under a rolled-back transaction.")
        parser.add_argument("--json", action="store_true", help="Report exact affected catalog and dependent row identities.")

    def handle(self, *args, **options):
        try:
            if options["dry_run"]:
                report = retire_unused_catalog(dry_run=True)
            else:
                report = retire_unused_catalog_explicitly()
        except (RetiredCatalogCollision, RetirementResourceError) as exc:
            raise CommandError(str(exc)) from exc
        if options["json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            mode = "[dry-run] would retire" if options["dry_run"] else "retired"
            self.stdout.write(f"{mode}: {retirement_summary(report)}; "
                              f"{sum(report['deleted'].values())} dependent/catalog rows")
