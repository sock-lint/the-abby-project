"""Mapping from GameLoopService trigger + context to Chronicle first-ever slugs.

Called from GameLoopService._record_chronicle_firsts after quest progress.
The legacy single-slug mapper preserves its source-first priority.
"""
from __future__ import annotations

from typing import Optional

from apps.rpg.constants import TriggerType


def slug_for(trigger_type: str, context: dict) -> Optional[tuple[str, str, str]]:
    """Return (event_slug, title, icon_slug) or None.

    Slugs here must NEVER change after shipping — they key the partial unique
    index and are used for deep-link lookups.
    """
    ctx = context or {}

    if trigger_type == TriggerType.PROJECT_COMPLETE:
        if ctx.get("payment_kind") == "bounty":
            return ("first_bounty_payout", "First bounty payout", "coin-stack")
        return ("first_project_completed", "First project completed", "spark")

    if trigger_type == TriggerType.MILESTONE_COMPLETE:
        return ("first_milestone_bonus", "First milestone bonus", "banner")

    if trigger_type == TriggerType.BADGE_EARNED and ctx.get("rarity") == "legendary":
        return ("first_legendary_badge", "First legendary badge", "legendary-sigil")

    if trigger_type == TriggerType.PERFECT_DAY:
        return ("first_perfect_day", "First perfect day", "sun-crown")

    if trigger_type == TriggerType.QUEST_COMPLETE:
        return ("first_quest_completed", "First quest completed", "quest-seal")

    # Streak milestones come through context["streak"] on any trigger.
    streak = ctx.get("streak")
    if streak in (30, 60, 100):
        return (f"first_streak_{streak}", f"First {streak}-day streak", "streak-flame")

    return None


def slugs_for(trigger_type: str, context: dict) -> list[tuple[str, str, str]]:
    """Return source and streak firsts, retaining the legacy primary result."""
    primary = slug_for(trigger_type, context)
    mapped = [primary] if primary is not None else []
    streak = (context or {}).get("streak")
    if streak in (30, 60, 100):
        streak_first = (
            f"first_streak_{streak}", f"First {streak}-day streak", "streak-flame",
        )
        if streak_first not in mapped:
            mapped.append(streak_first)
    return mapped
