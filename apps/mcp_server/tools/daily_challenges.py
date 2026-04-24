"""Daily Challenge MCP tools.

A DailyChallenge is a once-per-day micro-quest separate from the regular
quest slot. Templates are a small enum, not a CRUD'able catalog. The
``rotate_daily_challenges_task`` Celery beat (00:30 local) creates today's
row for every active child, but ``get_daily_challenge`` is idempotent and
will create on demand if a child checks in before rotation runs.
"""
from __future__ import annotations

from typing import Any

from apps.quests.services import DailyChallengeService

from ..context import get_current_user, resolve_target_user
from ..errors import safe_tool
from ..schemas import ClaimDailyChallengeIn, GetDailyChallengeIn
from ..server import tool
from ..shapes import daily_challenge_to_dict


@tool()
@safe_tool
def get_daily_challenge(params: GetDailyChallengeIn) -> dict[str, Any]:
    """Return today's DailyChallenge for the user, creating one if missing."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    challenge = DailyChallengeService.get_or_create_today(target)
    return daily_challenge_to_dict(challenge)


@tool()
@safe_tool
def claim_daily_challenge(params: ClaimDailyChallengeIn) -> dict[str, Any]:
    """Claim today's reward (idempotent — second claim returns already_claimed=True)."""
    user = get_current_user()
    target = resolve_target_user(user, params.user_id)
    return DailyChallengeService.claim_reward(target)
