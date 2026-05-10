"""WellbeingService — daily affirmation roll + gratitude submit.

Mirrors the shape of ``DailyChallengeService.get_or_create_today`` (idempotent)
so the surface plugs into the existing ``GET /today/`` poll pattern.

Affirmation pool is a static YAML file under ``content/wellbeing/``. The roll
is deterministic per ``(user_id, date)`` via a hash — refreshes on the same
day return the same affirmation so the kid doesn't slot-machine the prompt.
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


AFFIRMATIONS_PATH = settings.BASE_DIR / "content" / "wellbeing" / "affirmations.yaml"

# Per-line constraints. The kid is writing a one-liner gratitude jot; we
# don't want a 1k-char essay sitting in the JSON column. The journal
# captures the longer-form work and is locked after midnight; this is
# the soft daily counterpart that stays editable all day.
MAX_LINES = 3
MAX_LINE_CHARS = 200

# First-of-day coin trickle. Small on purpose — the gratitude act is the
# reward; the coin is recognition, not motivation. Tunable as a constant
# because this is a game-design balance choice, not a deploy-time setting.
GRATITUDE_FIRST_OF_DAY_COINS = 2


class WellbeingError(ValueError):
    """Surface-level service errors — line-length, line-count, etc."""


class WellbeingContentError(RuntimeError):
    """Raised when the affirmations YAML is missing or malformed."""


@lru_cache(maxsize=1)
def _load_affirmations() -> list[dict[str, Any]]:
    """Parse the affirmations YAML once per process.

    Cleared by tests via ``_load_affirmations.cache_clear()`` when the
    file is replaced or mocked.
    """
    path: Path = AFFIRMATIONS_PATH
    if not path.exists():
        raise WellbeingContentError(
            f"Affirmations file not found at {path}. Run "
            f"`python manage.py loadwellbeingcontent` or check the seed."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise WellbeingContentError(f"{path}: invalid YAML — {exc}") from exc

    entries = raw.get("affirmations")
    if not isinstance(entries, list) or not entries:
        raise WellbeingContentError(
            f"{path}: affirmations must be a non-empty list"
        )

    seen: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise WellbeingContentError(f"affirmation #{index + 1} must be a mapping")
        slug = entry.get("slug")
        text = entry.get("text")
        if not isinstance(slug, str) or not slug:
            raise WellbeingContentError(f"affirmation #{index + 1} missing slug")
        if not isinstance(text, str) or not text.strip():
            raise WellbeingContentError(f"{slug}: text must be a non-empty string")
        if slug in seen:
            raise WellbeingContentError(f"duplicate affirmation slug: {slug}")
        seen.add(slug)
        parsed.append({"slug": slug, "text": text.strip(), "tone": entry.get("tone", "")})
    return parsed


def _resolve_affirmation(slug: str) -> dict[str, Any] | None:
    """Look up an affirmation by slug. Returns ``None`` if missing."""
    for entry in _load_affirmations():
        if entry["slug"] == slug:
            return entry
    return None


def _roll_affirmation_slug(user_id: int, day) -> str:
    """Deterministic per-(user, day) pick.

    Uses SHA-1 of ``"{user_id}:{ordinal}"`` modulo the pool size so the
    same pair always yields the same slug. Stable across restarts and
    across multiple GET calls in a day.
    """
    pool = _load_affirmations()
    digest = hashlib.sha1(f"{user_id}:{day.toordinal()}".encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(pool)
    return pool[index]["slug"]


def _serialize_entry(entry, *, today_marker=None) -> dict[str, Any]:
    """Shape the wellbeing-today response for the frontend card."""
    affirmation = _resolve_affirmation(entry.affirmation_slug)
    if affirmation is None:
        # Authored slug went missing between writes (YAML edit). Fall back
        # to a re-roll for display purposes — the row stays put for audit.
        affirmation = {"slug": entry.affirmation_slug, "text": "", "tone": ""}

    return {
        "id": entry.pk,
        "date": entry.date.isoformat(),
        "is_today": today_marker is not None and entry.date == today_marker,
        "affirmation": {
            "slug": affirmation["slug"],
            "text": affirmation["text"],
            "tone": affirmation.get("tone") or "",
        },
        "gratitude_lines": list(entry.gratitude_lines or []),
        "gratitude_paid": entry.coin_paid_at is not None,
        "max_lines": MAX_LINES,
        "max_line_chars": MAX_LINE_CHARS,
        "coin_reward": GRATITUDE_FIRST_OF_DAY_COINS,
    }


class WellbeingService:
    """Lifecycle for ``DailyWellbeingEntry`` rows."""

    @staticmethod
    @transaction.atomic
    def get_or_create_today(user):
        """Idempotent — creates today's row on first call, returns it on later calls."""
        from apps.wellbeing.models import DailyWellbeingEntry

        today = timezone.localdate()
        # select_for_update keeps two concurrent first-mounts from racing
        # the unique constraint; mirrors DailyChallengeService.
        entry, _created = DailyWellbeingEntry.objects.select_for_update().get_or_create(
            user=user, date=today,
            defaults={"affirmation_slug": _roll_affirmation_slug(user.pk, today)},
        )
        return entry

    @staticmethod
    @transaction.atomic
    def submit_gratitude(user, lines):
        """Persist 1-3 gratitude lines for today.

        First-of-day submit pays a small coin trickle. Subsequent edits
        same-day are free (no XP, no double-pay). Raises ``WellbeingError``
        on validation failures (too many lines, too long, all empty).
        """
        if not isinstance(lines, list):
            raise WellbeingError("gratitude lines must be a list of strings")

        cleaned: list[str] = []
        for raw in lines:
            if not isinstance(raw, str):
                raise WellbeingError("each gratitude line must be a string")
            text = raw.strip()
            if not text:
                continue
            if len(text) > MAX_LINE_CHARS:
                raise WellbeingError(
                    f"gratitude line too long — max {MAX_LINE_CHARS} chars"
                )
            cleaned.append(text)

        if not cleaned:
            raise WellbeingError("write at least one gratitude line")
        if len(cleaned) > MAX_LINES:
            raise WellbeingError(
                f"too many gratitude lines — max {MAX_LINES} per day"
            )

        entry = WellbeingService.get_or_create_today(user)
        already_paid = entry.coin_paid_at is not None
        entry.gratitude_lines = cleaned
        update_fields = ["gratitude_lines", "updated_at"]

        coin_awarded = 0
        if not already_paid:
            from apps.rewards.models import CoinLedger
            from apps.rewards.services import CoinService
            try:
                ledger = CoinService.award_coins(
                    user, GRATITUDE_FIRST_OF_DAY_COINS,
                    CoinLedger.Reason.ADJUSTMENT,
                    description="Gratitude — first of day",
                )
                if ledger is not None:
                    coin_awarded = int(ledger.amount)
                    entry.coin_paid_at = timezone.now()
                    update_fields.append("coin_paid_at")
            except Exception:
                # Coin award failure must never lose the gratitude write.
                logger.exception("Gratitude coin payout failed")

        entry.save(update_fields=update_fields)
        return {
            "entry": entry,
            "coin_awarded": coin_awarded,
            "freshly_paid": coin_awarded > 0,
        }

    @staticmethod
    def serialize_today(entry):
        """Public helper for the view — wraps ``_serialize_entry`` with today's marker."""
        return _serialize_entry(entry, today_marker=timezone.localdate())
