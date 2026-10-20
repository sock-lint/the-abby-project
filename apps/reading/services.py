"""Server-owned reading progress and once-daily RPG rewards."""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.achievements.models import Skill
from apps.achievements.services import AwardService
from apps.notifications.services import defer_push_until_commit
from apps.quests.activity import household_timezone
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.services import GameLoopService

from .models import ReadingDailyReward, ReadingRewardCredit


class ReadingRewardService:
    TARGET_MINUTES = 10
    BASE_XP = 15
    BASE_COINS = 5
    SKILL_NAME = "Reading Comprehension"

    @classmethod
    @transaction.atomic
    def credit_new_session(cls, user, session):
        """Credit one genuinely new, present-day session under the owner lock.

        Call only immediately after insertion, never for a replay or PATCH.
        Progress remains separate from mutable session history. The caller's
        transaction also contains the inserted session, so a payout failure
        leaves the same request eligible for an ordinary retry.
        """
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if session.user_id != user.pk:
            return
        credit, created = ReadingRewardCredit.objects.get_or_create(
            user=user, client_request_id=session.client_request_id,
            defaults={"day": session.occurred_on, "minutes": 0},
        )
        # Even a zero-minute, historical or over-cap request keeps its original
        # classification after deletion. Retrying tomorrow cannot turn it into
        # a fresh reward opportunity.
        if not created:
            return
        day = timezone.localdate(timezone=household_timezone(user))
        if session.occurred_on != day or session.duration_minutes <= 0:
            return
        daily, _ = ReadingDailyReward.objects.select_for_update().get_or_create(user=user, day=day)
        if daily.awarded_at is not None:
            return
        added_minutes = min(cls.TARGET_MINUTES - daily.minutes_credited, session.duration_minutes)
        credit.minutes = added_minutes
        credit.save(update_fields=["minutes"])
        daily.minutes_credited += added_minutes
        if daily.minutes_credited < cls.TARGET_MINUTES:
            daily.save(update_fields=["minutes_credited", "updated_at"])
            return

        skill = Skill.objects.filter(name=cls.SKILL_NAME, category__name="Language Arts").first()
        tags = [SimpleNamespace(skill=skill, xp_weight=1)] if skill is not None else []
        # Observe only entries created by this direct reading award. Badge,
        # check-in and drop Coins have their own reasons and receipts.
        prior_coin_id = CoinLedger.objects.filter(user=user, reason=CoinLedger.Reason.READING).aggregate(
            last_id=Max("pk"),
        )["last_id"] or 0
        with defer_push_until_commit():
            award = AwardService.grant(
                user, xp_tags=tags, xp=cls.BASE_XP, xp_source_label="Reading adventure",
                coins=cls.BASE_COINS, coin_reason=CoinLedger.Reason.READING,
                coin_description="Daily reading adventure", badge_scopes={"skill_xp", "coin", "badges"},
            )
            daily.xp_awarded = award["xp_awarded"]
            daily.coins_awarded = CoinLedger.objects.filter(
                user=user, reason=CoinLedger.Reason.READING, pk__gt=prior_coin_id,
            ).aggregate(total=Sum("amount", default=0))["total"]
            daily.source_session = session
            daily.awarded_at = timezone.now()
            daily.save(update_fields=[
                "minutes_credited", "xp_awarded", "coins_awarded", "source_session", "awarded_at", "updated_at",
            ])
            # Only this genuinely new, accepted daily receipt may capture a
            # prospective milestone offer. Replays and repair jobs cannot
            # infer when a previously observed skill level was reached.
            from apps.quests.activity import freeze_milestone_eligibility
            freeze_milestone_eligibility(user, TriggerType.READING_LOGGED,
                                         {"reading_reward_id": daily.pk})
            # Other task flows tolerate a failed optional step. This reward is
            # one transaction; pushes must not escape a later strict rollback.
            GameLoopService.on_task_completed(
                user, TriggerType.READING_LOGGED,
                {"session_id": session.pk, "reading_reward_id": daily.pk}, strict=True,
            )

    @classmethod
    def daily_payload(cls, user, *, day=None):
        """Read current progress without creating a receipt or awarding."""
        if day is None:
            day = timezone.localdate(timezone=household_timezone(user))
        daily = ReadingDailyReward.objects.filter(user=user, day=day).first()
        minutes = daily.minutes_credited if daily else 0
        return {
            "day": day.isoformat(), "target_minutes": cls.TARGET_MINUTES,
            "minutes_credited": minutes, "remaining_minutes": max(0, cls.TARGET_MINUTES - minutes),
            "earned": bool(daily and daily.awarded_at), "base_xp": cls.BASE_XP, "base_coins": cls.BASE_COINS,
            "xp_awarded": daily.xp_awarded if daily else 0, "coins_awarded": daily.coins_awarded if daily else 0,
            "skill_name": cls.SKILL_NAME,
        }
