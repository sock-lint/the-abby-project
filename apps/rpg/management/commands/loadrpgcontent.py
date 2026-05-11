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

        # Post-load: backfill the journal cover for every active user.
        # The 2026-05 cover unification turned the 6 base covers into
        # cosmetic_theme items — every existing user needs ownership of
        # cover-hyrule (the free baseline) + the cover matching their
        # pre-unification ``User.theme`` so their selection survives the
        # upgrade. Idempotent via ``UserInventory.get_or_create`` — safe
        # to run on every deploy. No-op when ``namespace`` is set (third-
        # party packs don't ship the base covers).
        if not dry_run and not namespace:
            self._grant_starter_covers()

        self.stdout.write(self.style.SUCCESS("Content pack load complete."))

    # Map legacy User.theme values (summer/winter/spring/autumn) to the
    # modern palette slugs that frontend/src/themes.js + the cover-* items
    # both use. Mirrors LEGACY_THEME_ALIASES in themes.js.
    _LEGACY_THEME_ALIASES = {
        "summer": "sunlit",
        "winter": "snowquill",
        "spring": "verdant",
        "autumn": "harvest",
    }
    _VALID_THEME_SLUGS = {
        "hyrule", "vigil", "sunlit", "snowquill", "verdant", "harvest",
    }

    def _grant_starter_covers(self) -> None:
        """Backfill journal cover ownership for every active user.

        On every loadrpgcontent run:
        - Grant ``cover-hyrule`` (the always-free baseline).
        - Resolve their current ``User.theme`` (legacy aliases supported)
          and grant the matching cover too, so a kid who was using Vigil
          pre-unification doesn't lose access.
        - Equip the resolved cover if no theme is currently equipped.

        Idempotent via ``UserInventory.get_or_create`` — safe to run on
        every deploy. The first run after the 2026-05 unification
        materializes the inventory rows; subsequent runs are no-ops.
        """
        from django.contrib.auth import get_user_model
        from apps.rpg.models import (
            CharacterProfile, ItemDefinition, UserInventory,
        )

        User = get_user_model()

        covers_by_theme: dict[str, ItemDefinition] = {}
        for theme in self._VALID_THEME_SLUGS:
            try:
                covers_by_theme[theme] = ItemDefinition.objects.get(
                    slug=f"cover-{theme}",
                )
            except ItemDefinition.DoesNotExist:
                # If the YAML didn't include this cover (e.g. partial pack
                # in a test fixture) we skip silently — covers_by_theme
                # just has fewer entries.
                continue

        hyrule = covers_by_theme.get("hyrule")
        if hyrule is None:
            self.stdout.write(self.style.WARNING(
                "  cover-hyrule not in this pack — skipping starter-cover backfill",
            ))
            return

        granted = 0
        for user in User.objects.filter(is_active=True).iterator():
            # Resolve current theme to a modern slug.
            resolved = self._LEGACY_THEME_ALIASES.get(user.theme, user.theme)
            if resolved not in self._VALID_THEME_SLUGS:
                resolved = "hyrule"
            current_cover = covers_by_theme.get(resolved, hyrule)

            # Always grant Hyrule.
            _, hyrule_created = UserInventory.objects.get_or_create(
                user=user, item=hyrule, defaults={"quantity": 1},
            )
            # Grant the resolved cover too (skip dupe if it's Hyrule).
            current_created = False
            if current_cover.pk != hyrule.pk:
                _, current_created = UserInventory.objects.get_or_create(
                    user=user, item=current_cover, defaults={"quantity": 1},
                )

            # Equip the resolved cover if nothing is currently equipped.
            profile, _ = CharacterProfile.objects.get_or_create(user=user)
            if profile.active_theme_id is None:
                profile.active_theme = current_cover
                profile.save(update_fields=["active_theme", "updated_at"])

            # Normalize User.theme to the modern slug so the frontend
            # bootstrap stops depending on LEGACY_THEME_ALIASES.
            if user.theme != resolved:
                user.theme = resolved
                user.save(update_fields=["theme"])

            if hyrule_created or current_created:
                granted += 1

        self.stdout.write(f"  starter covers ensured for {granted} users")
