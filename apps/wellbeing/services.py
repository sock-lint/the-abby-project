"""Daily affirmations, shared writing Coins, and legacy note compatibility.

Mirrors the shape of ``DailyChallengeService.get_or_create_today`` (idempotent)
so the surface plugs into the existing ``GET /today/`` poll pattern.

The bundled affirmation pool has reviewed database copy/selection overlays. The roll
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
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


AFFIRMATIONS_PATH = settings.BASE_DIR / "content" / "wellbeing" / "affirmations.yaml"

# Short-note limits remain for earlier clients. New Today captures use the
# ordinary journal, whose body can hold both short and longer reflections.
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
def _load_affirmation_source() -> list[dict[str, Any]]:
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


def _load_affirmations(*, include_retired=False) -> list[dict[str, Any]]:
    from apps.rpg.content.editorial import apply_editorial_overrides
    return apply_editorial_overrides("affirmations", _load_affirmation_source(), include_retired=include_retired)


_load_affirmations.cache_clear = _load_affirmation_source.cache_clear


def _resolve_affirmation(slug: str) -> dict[str, Any] | None:
    """Look up an affirmation by slug. Returns ``None`` if missing."""
    for entry in _load_affirmations(include_retired=True):
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
        # Authored slug went missing between writes (YAML edit). The row
        # stays put for audit, but a blank card would degrade UX, so we
        # re-roll a fresh affirmation against the current pool keyed on
        # the same (user, day) the row was stamped for. The slug field
        # in the response reflects what the *user sees*, not the snapshot.
        try:
            fresh_slug = _roll_affirmation_slug(entry.user_id, entry.date)
            fresh = _resolve_affirmation(fresh_slug)
        except WellbeingContentError:
            fresh = None
        if fresh is not None:
            affirmation = fresh
        else:
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
        # Both writing endpoints use author-before-daily-row lock order,
        # including when a daily row does not exist yet.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        entry, _created = DailyWellbeingEntry.objects.select_for_update().get_or_create(
            user=user, date=today,
            defaults={"affirmation_slug": _roll_affirmation_slug(user.pk, today)},
        )
        return entry

    @staticmethod
    @transaction.atomic
    def award_daily_writing_coins(user, day):
        """One verified flat payout per author/day across both clients.

        Commit ledger and sentinel together, or roll both back. A failed
        attempt leaves eligibility intact for a later real save; journal
        UUID replays and journal edits never call this helper again.
        """
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        from apps.wellbeing.models import DailyWellbeingEntry

        get_user_model().objects.select_for_update().get(pk=user.pk)
        receipt = {"coins_awarded": 0, "coin_status": "unavailable"}
        try:
            with transaction.atomic():
                entry, _ = DailyWellbeingEntry.objects.select_for_update().get_or_create(
                    user=user, date=day,
                    defaults={"affirmation_slug": _roll_affirmation_slug(user.pk, day)},
                )
                if entry.coin_paid_at is not None:
                    return {"coins_awarded": 0, "coin_status": "already_received"}
                ledger = CoinService.award_coins(
                    user, GRATITUDE_FIRST_OF_DAY_COINS,
                    CoinLedger.Reason.ADJUSTMENT,
                    description="Journal — first save of day",
                )
                if ledger is not None:
                    entry.coin_paid_at = timezone.now()
                    entry.save(update_fields=["coin_paid_at", "updated_at"])
                    receipt = {"coins_awarded": int(ledger.amount), "coin_status": "awarded"}
        except Exception:
            logger.exception("Daily writing coin payout failed for user %s", user.pk)
        return receipt

    @staticmethod
    def _sync_daily_note(entry):
        """Preserve an older client's writing in its own private history row.

        The source binding avoids collisions with a same-day shared journal.
        Imported short notes do not retroactively trigger XP or game hooks.
        """
        from apps.chronicle.models import ChronicleEntry

        ChronicleEntry.objects.update_or_create(
            daily_note_source=entry,
            defaults={
                "user_id": entry.user_id,
                "kind": ChronicleEntry.Kind.DAILY_NOTE,
                "occurred_on": entry.date,
                "chapter_year": entry.date.year if entry.date.month >= 8 else entry.date.year - 1,
                "title": "Daily note",
                "summary": "\n\n".join(entry.gratitude_lines),
                "is_private": True,
                "metadata": {"reward_receipt": {
                    "status": "unavailable", "xp_awarded": 0, "skills": [],
                    "coins_awarded": 0, "coin_status": "unavailable",
                }},
            },
        )

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
        entry.gratitude_lines = cleaned
        entry.save(update_fields=["gratitude_lines", "updated_at"])
        WellbeingService._sync_daily_note(entry)
        receipt = WellbeingService.award_daily_writing_coins(user, entry.date)
        # The payout helper loads its own locked instance; keep the legacy
        # response's paid flag current without overwriting its sentinel.
        entry.refresh_from_db(fields=["coin_paid_at"])
        coin_awarded = receipt["coins_awarded"]
        return {
            "entry": entry,
            "coin_awarded": coin_awarded,
            "freshly_paid": coin_awarded > 0,
        }

    @staticmethod
    def serialize_today(entry):
        """Public helper for the view — wraps ``_serialize_entry`` with today's marker."""
        return _serialize_entry(entry, today_marker=timezone.localdate())
