"""Static Lorebook catalog + per-user discovery state.

The Lorebook is intentionally content-authored, not model-authored: mechanics
copy lives in ``content/lorebook/entries.yaml`` so parent and kid surfaces share
one source of truth without a new CRUD surface.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml
from django.conf import settings


LOREBOOK_PATH = settings.BASE_DIR / "content" / "lorebook" / "entries.yaml"

EXPECTED_ENTRY_SLUGS = {
    "duties",
    "rituals",
    "study",
    "journal",
    "creations",
    "ventures",
    "skills",
    "badges",
    "chronicle",
    "quests",
    "pets",
    "mounts",
    "drops",
    "streaks",
    "coins",
    "money",
    "cosmetics",
}

REQUIRED_FIELDS = {"slug", "title", "chapter", "kid_voice", "mechanics", "trial_template", "trial"}

TRIAL_TEMPLATES = frozenset({
    "tap_and_reward",
    "scribe",
    "observe",
    "choice",
    "drag_to_target",
    "sequence",
})


class LorebookCatalogError(ValueError):
    """Raised when the static Lorebook YAML is malformed."""


@lru_cache(maxsize=1)
def load_lorebook_catalog() -> list[dict[str, Any]]:
    """Parse and validate the YAML-authored Lorebook catalog."""

    try:
        raw = yaml.safe_load(LOREBOOK_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - covered by PyYAML
        raise LorebookCatalogError(f"{LOREBOOK_PATH}: invalid YAML — {exc}") from exc

    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise LorebookCatalogError("content/lorebook/entries.yaml must contain entries: []")

    seen: set[str] = set()
    catalog: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise LorebookCatalogError(f"entry #{index + 1} must be a mapping")
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise LorebookCatalogError(
                f"entry #{index + 1} missing required field(s): {', '.join(sorted(missing))}"
            )
        slug = entry["slug"]
        if not isinstance(slug, str) or not slug:
            raise LorebookCatalogError(f"entry #{index + 1} has invalid slug")
        if slug in seen:
            raise LorebookCatalogError(f"duplicate Lorebook slug: {slug}")
        seen.add(slug)

        mechanics = entry.get("mechanics")
        if not isinstance(mechanics, list) or not all(isinstance(x, str) for x in mechanics):
            raise LorebookCatalogError(f"{slug}: mechanics must be a list of strings")

        economy = entry.get("economy") or {}
        if not isinstance(economy, dict):
            raise LorebookCatalogError(f"{slug}: economy must be a mapping")

        template = entry.get("trial_template")
        if template not in TRIAL_TEMPLATES:
            raise LorebookCatalogError(
                f"{slug}: trial_template must be one of {sorted(TRIAL_TEMPLATES)}, got {template!r}"
            )

        trial = entry.get("trial")
        if not isinstance(trial, dict):
            raise LorebookCatalogError(f"{slug}: trial must be a mapping")
        for key in ("prompt", "payoff"):
            value = trial.get(key)
            if not isinstance(value, str) or not value.strip():
                raise LorebookCatalogError(f"{slug}: trial.{key} must be a non-empty string")

        catalog.append(dict(entry))

    return catalog


def _all_unlocked(catalog: list[dict[str, Any]], reason: str) -> dict[str, dict[str, Any]]:
    return {entry["slug"]: {"unlocked": True, "reason": reason} for entry in catalog}


def compute_lorebook_unlocks(user) -> dict[str, dict[str, Any]]:
    """Return ``{slug: {unlocked, reason}}`` for the current user.

    Parents see the full reference immediately. Children unlock entries from
    existing first-encounter data; no new per-entry model is required.
    """

    catalog = load_lorebook_catalog()
    if getattr(user, "role", None) == "parent":
        return _all_unlocked(catalog, "parent_reference")

    unlocks = {entry["slug"]: {"unlocked": False, "reason": ""} for entry in catalog}

    def mark(slug: str, condition: bool, reason: str) -> None:
        if slug in unlocks and condition:
            unlocks[slug] = {"unlocked": True, "reason": reason}

    from apps.achievements.models import SkillProgress, UserBadge
    from apps.chores.models import ChoreCompletion
    from apps.chronicle.models import ChronicleEntry
    from apps.creations.models import Creation
    from apps.habits.models import HabitLog
    from apps.homework.models import HomeworkAssignment, HomeworkSubmission
    from apps.payments.models import PaymentLedger
    from apps.pets.models import UserMount, UserPet
    from apps.projects.models import Project
    from apps.quests.models import QuestParticipant
    from apps.rewards.models import CoinLedger
    from apps.rpg.models import CharacterProfile, DropLog
    from apps.timecards.models import TimeEntry

    mark(
        "duties",
        ChoreCompletion.objects.filter(
            user=user, status=ChoreCompletion.Status.APPROVED
        ).exists(),
        "first_approved_duty",
    )
    mark(
        "rituals",
        HabitLog.objects.filter(user=user, direction=1).exists(),
        "first_positive_ritual",
    )
    mark(
        "study",
        HomeworkAssignment.objects.filter(assigned_to=user).exists()
        or HomeworkSubmission.objects.filter(user=user).exists(),
        "first_study_record",
    )
    mark(
        "journal",
        ChronicleEntry.objects.filter(user=user, kind=ChronicleEntry.Kind.JOURNAL).exists(),
        "first_journal_entry",
    )
    mark("creations", Creation.objects.filter(user=user).exists(), "first_creation")
    mark(
        "ventures",
        Project.objects.filter(assigned_to=user).exists()
        or TimeEntry.objects.filter(user=user).exists(),
        "first_venture",
    )
    mark(
        "skills",
        SkillProgress.objects.filter(user=user, xp_points__gt=0).exists(),
        "first_skill_xp",
    )
    mark("badges", UserBadge.objects.filter(user=user).exists(), "first_badge")
    mark("drops", DropLog.objects.filter(user=user).exists(), "first_drop")
    mark("pets", UserPet.objects.filter(user=user).exists(), "first_pet")
    mark("mounts", UserMount.objects.filter(user=user).exists(), "first_mount")
    mark(
        "streaks",
        CharacterProfile.objects.filter(user=user, login_streak__gte=2).exists(),
        "streak_two_days",
    )
    mark("coins", CoinLedger.objects.filter(user=user).exists(), "first_coin_ledger")
    mark("money", PaymentLedger.objects.filter(user=user).exists(), "first_money_ledger")
    mark("quests", QuestParticipant.objects.filter(user=user).exists(), "first_quest")

    profile = CharacterProfile.objects.filter(user=user).first()
    mark(
        "cosmetics",
        bool(
            profile
            and (
                profile.active_frame_id
                or profile.active_title_id
                or profile.active_theme_id
                or profile.active_pet_accessory_id
                or profile.active_trophy_badge_id
            )
        ),
        "first_cosmetic_equipped",
    )
    mark(
        "chronicle",
        ChronicleEntry.objects.filter(user=user)
        .exclude(kind__in=[ChronicleEntry.Kind.JOURNAL, ChronicleEntry.Kind.CREATION])
        .exists(),
        "first_chronicle_entry",
    )

    return unlocks


def _trained_state(user, slug: str) -> bool:
    """True when the child has completed (or, for parents, is exempt from) the trial."""

    if getattr(user, "role", None) == "parent":
        return True
    flags = getattr(user, "lorebook_flags", {}) or {}
    return bool(flags.get(f"{slug}_trained"))


def serialize_lorebook(user) -> dict[str, Any]:
    catalog = load_lorebook_catalog()
    unlocks = compute_lorebook_unlocks(user)
    serialized = []
    unlocked_count = 0
    trained_count = 0

    for entry in catalog:
        state = unlocks.get(entry["slug"], {"unlocked": False, "reason": ""})
        unlocked = bool(state.get("unlocked"))
        trained = _trained_state(user, entry["slug"])
        if unlocked:
            unlocked_count += 1
        if trained:
            trained_count += 1
        serialized.append(
            {
                **entry,
                "unlocked": unlocked,
                "unlocked_reason": state.get("reason", ""),
                "trained": trained,
            }
        )

    return {
        "entries": serialized,
        "counts": {
            "unlocked": unlocked_count,
            "trained": trained_count,
            "total": len(serialized),
        },
    }


def newly_unlocked_entries(user) -> list[str]:
    """Slugs that are unlocked but have not been acknowledged by this user."""

    if getattr(user, "role", None) == "parent":
        return []
    flags = getattr(user, "lorebook_flags", {}) or {}
    unlocks = compute_lorebook_unlocks(user)
    return [
        slug
        for slug, state in unlocks.items()
        if state.get("unlocked") and not flags.get(f"{slug}_seen")
    ]
