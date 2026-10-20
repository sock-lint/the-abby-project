"""Explicitly prepare a private Voyager policy draft; never activate its rules."""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.reading_voyager import prepare_reading_voyager


class Command(BaseCommand):
    help = "Prepare and preview the private Reading Voyager milestone/56-day draft; never simulate or publish."

    def add_arguments(self, parser):
        parser.add_argument("--actor-id", required=True, type=int,
                            help="Exact active staff-parent account ID that will privately own this draft.")

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(pk=options["actor_id"])
        except get_user_model().DoesNotExist as error:
            raise CommandError("The explicit draft actor was not found.") from error
        try:
            result = prepare_reading_voyager(actor)
        except ContentPackError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
