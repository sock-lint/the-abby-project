"""Validate the affirmations YAML.

There's no DB-side authoring of the affirmation pool — the YAML IS the source
of truth, parsed lazily on first request via ``WellbeingService._load_affirmations``.
This command exists so seed flows can fail loud when the file is malformed
(rather than discovering it at first user request) and so contributors have
a single command to run after editing the YAML.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.wellbeing.services import (
    AFFIRMATIONS_PATH,
    WellbeingContentError,
    _load_affirmations,
)


class Command(BaseCommand):
    help = "Validate content/wellbeing/affirmations.yaml and report the loaded entry count."

    def handle(self, *args, **options):
        # Bypass the lru_cache so re-runs after edits pick up the file fresh.
        _load_affirmations.cache_clear()
        try:
            entries = _load_affirmations()
        except WellbeingContentError as exc:
            # Chain the original exception so the underlying YAML/parse
            # error is visible in the traceback during debugging instead
            # of being swallowed by ``CommandError``.
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(entries)} affirmation(s) from {AFFIRMATIONS_PATH}"
        ))
