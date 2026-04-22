"""One-shot cleanup of RPG catalog cruft predating YAML-authored content.

The content loader (``loadrpgcontent``) is upsert-only — it can't remove
rows that used to be seeded from Python and were never migrated into
``content/rpg/initial/*.yaml``. This command deletes the specific orphan
rows identified during the 2026-04-21 catalog review, plus any smoke-test
quests left behind by MCP integration checks.

Run after a YAML-authoring restructure whenever duplicate categories,
duplicate badges, or dev-only quest rows need to disappear.

Usage::

    docker compose exec django python manage.py cleanup_rpg_catalog
    docker compose exec django python manage.py cleanup_rpg_catalog --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


# Legacy skill categories superseded by the YAML-authored taxonomy.
# Their skills (and all SkillProgress / ProjectSkillTag / MilestoneSkillTag
# rows referencing those skills) cascade-delete. Safe to run when the app
# has no user data — otherwise retire via admin instead.
LEGACY_SKILL_CATEGORIES = [
    "Electronics & Circuits",  # superseded by "Electronics"
    "STEM Fundamentals",       # overlaps with "Science" + "Life Skills"
]

# Duplicate badges — same criterion as a sibling, different display name
# and XP. YAML keeps the canonical version; these go.
DUPLICATE_BADGES = [
    "Clocked In",         # dup of "First Clock-In"
    "First Spark",        # dup of "First Project"
    "Ten Hour Club",      # dup of "10-Hour Club" (same criterion, different XP)
    "Centurion",          # dup of "Century Worker"
    "Project Machine",    # dup of "Perfect 10"
    "Skill Unlocked",     # dup of "Level Up"
    "Week Warrior",       # dup of "Streak Week"
    "Shutterbug",         # dup of "Documentarian"
    "Renaissance Maker",  # "Universal Genius" covers it
    "Speed Runner",       # renamed to "Speedrunner" with a real fast_project criterion
    # 2026-04-22 review: identical criterion to Master Craftsman (legendary).
    # Both fired on reach-L5-any-skill so kids earned both at once — retired
    # the epic so the legendary is the single capstone moment.
    "Mastery",
]

# Retired quests — removed from YAML in the 2026-04-22 review because they
# duplicated a repeatable sibling. The loader is upsert-only; it can't remove
# rows whose YAML entry was deleted, so this list cleans up prod.
RETIRED_QUESTS = [
    "Chore Champion",          # overlaps with Pantry Patroller (repeatable, same 7d loop)
    "Spring Bloom Collector",  # Spring Planting has a real trigger_filter — cleaner replacement
]


def cleanup(*, dry_run: bool = False) -> dict[str, int]:
    """Delete orphan rows. Returns a count dict."""
    from apps.achievements.models import Badge, SkillCategory
    from apps.quests.models import QuestDefinition

    counts = {
        "skill_categories": 0,
        "skills_cascaded": 0,
        "badges": 0,
        "quests": 0,
        "retired_quests": 0,
    }

    with transaction.atomic():
        sid = transaction.savepoint()
        try:
            # 1. Legacy skill categories (+ their skills via CASCADE)
            cat_qs = SkillCategory.objects.filter(name__in=LEGACY_SKILL_CATEGORIES)
            # Count cascaded skills before deleting the categories.
            from apps.achievements.models import Skill
            counts["skills_cascaded"] = Skill.objects.filter(
                category__in=cat_qs,
            ).count()
            counts["skill_categories"] = cat_qs.count()
            cat_qs.delete()

            # 2. Duplicate badges
            badge_qs = Badge.objects.filter(name__in=DUPLICATE_BADGES)
            counts["badges"] = badge_qs.count()
            badge_qs.delete()

            # 3. Smoke-test quests (any QuestDefinition whose name starts
            # with "MCP-SmokeTest-" — the MCP test harness uses that prefix).
            quest_qs = QuestDefinition.objects.filter(
                name__startswith="MCP-SmokeTest-",
            )
            counts["quests"] = quest_qs.count()
            quest_qs.delete()

            # 4. Retired quests — named YAML removals that the upsert loader
            # can't clean up on its own.
            retired_qs = QuestDefinition.objects.filter(name__in=RETIRED_QUESTS)
            counts["retired_quests"] = retired_qs.count()
            retired_qs.delete()

            if dry_run:
                transaction.savepoint_rollback(sid)
            else:
                transaction.savepoint_commit(sid)
        except Exception:
            transaction.savepoint_rollback(sid)
            raise

    return counts


class Command(BaseCommand):
    help = "Delete legacy skill categories, duplicate badges, and smoke-test quests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts without deleting.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        counts = cleanup(dry_run=dry_run)
        mode = "[dry-run] would delete" if dry_run else "deleted"
        self.stdout.write(
            f"{mode}: {counts['skill_categories']} skill categories "
            f"(+{counts['skills_cascaded']} skills cascaded), "
            f"{counts['badges']} badges, "
            f"{counts['quests']} smoke-test quests, "
            f"{counts['retired_quests']} retired quests"
        )
