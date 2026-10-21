"""One automatic daily bonus, sharing factual inputs with longer goals."""
from datetime import datetime, time, timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .activity import household_timezone
from .models import ChallengeActivity, DailyBonus, DailyChallenge

GOAL = "Complete an approved task or log 10 minutes of work or movement"
TASK_TRIGGERS = {"chore_complete", "homework_complete", "milestone_complete", "project_complete"}
MINUTE_TRIGGERS = {"clock_out", "movement_session"}


def paid_legacy_bonus(user, day):
    zone = household_timezone(user)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    # Old dates used the server timezone. The confirmed completion timestamp
    # also identifies an already paid bonus in a different household zone.
    from django.db.models import Q
    return DailyChallenge.objects.filter(user=user, coin_reward=0, xp_reward=0).filter(
        Q(date=day) | Q(completed_at__gte=start, completed_at__lt=end),
    ).filter(completed_at__isnull=False).first()


def _minutes(user, day):
    zone = household_timezone(user)
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return sum(int(row.context.get("duration_minutes", 0)) for row in ChallengeActivity.objects.filter(
        user=user, occurred_at__gte=start, occurred_at__lt=end,
        voided=False, trigger_type__in=MINUTE_TRIGGERS,
    ))


def _payload(user, day, bonus=None, legacy=None):
    zone = household_timezone(user)
    legacy_paid = bool(legacy and legacy.is_complete and legacy.coin_reward == 0 and legacy.xp_reward == 0)
    return {
        "date": day.isoformat(), "timezone": str(zone), "goal": GOAL,
        "progress_minutes": _minutes(user, day),
        "completed": bool(bonus and bonus.completed_at) or legacy_paid,
        "awarded": bool(bonus and bonus.awarded_at) or legacy_paid,
        "coin_reward": bonus.coin_reward if bonus else (legacy.coin_reward if legacy and not legacy_paid else 10),
        "xp_reward": bonus.xp_reward if bonus else (legacy.xp_reward if legacy and not legacy_paid else 20),
        "coins_awarded": bonus.coins_awarded if bonus else 0,
        "xp_awarded": bonus.xp_awarded if bonus else 0,
        "ends_at": datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).isoformat(),
        # Imported paid markers have no recorded original payout. Preserve
        # that unknown receipt instead of displaying invented zero totals.
        "receipt_id": (f"daily:{bonus.pk}" if bonus and bonus.awarded_at
                       and (bonus.coin_reward or bonus.xp_reward) else None),
    }


def get_daily_bonus_payload(user):
    """Reading the screen never earns or settles a reward."""
    if user.role != "child":
        return None
    day = timezone.localdate(timezone.now(), timezone=household_timezone(user))
    return _payload(user, day, DailyBonus.objects.filter(user=user, date=day).first(),
                    paid_legacy_bonus(user, day) or DailyChallenge.objects.filter(user=user, date=day).first())


@transaction.atomic
def process_daily_bonus(user, activity):
    if activity.voided or user.role != "child":
        return None
    from apps.achievements.models import Skill
    from apps.achievements.services import AwardService
    from apps.rewards.models import CoinLedger

    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    # Daily credit follows the accepted/approval timestamp. The separate
    # performed date (including a weekly chore's Monday bucket) stays intact
    # for parent goal calendars. A retry keeps its original acceptance day.
    day = (activity.occurred_on if activity.trigger_type == "legacy_daily"
           else timezone.localdate(activity.occurred_at, timezone=household_timezone(user)))
    # A completed, unclaimed row is an explicit promise for its own date.
    # Preserve it even when another old row was paid on the same local day
    # (the old client could claim past work late).
    legacy = DailyChallenge.objects.select_for_update().filter(user=user, date=day).first()
    legacy = legacy or paid_legacy_bonus(user, day)
    legacy_paid = bool(legacy and legacy.is_complete and legacy.coin_reward == 0 and legacy.xp_reward == 0)
    qualified = activity.trigger_type in TASK_TRIGGERS or _minutes(user, day) >= 10
    if not qualified and not (legacy and legacy.is_complete):
        return None

    skill_rows = activity.context.get("skill_tags") or []
    if not skill_rows:
        persistence = Skill.objects.filter(category__name="Life Skills", name="Persistence").first()
        skill_rows = [{"skill_id": persistence.pk, "xp_weight": 1}] if persistence else []
    skills = {skill.pk: skill for skill in Skill.objects.filter(pk__in=[row["skill_id"] for row in skill_rows])}
    tags = [SimpleNamespace(skill=skills[row["skill_id"]], xp_weight=row["xp_weight"])
            for row in skill_rows if row["skill_id"] in skills]
    bonus, _ = DailyBonus.objects.get_or_create(user=user, date=day, defaults={
        "timezone_name": str(household_timezone(user)),
        "coin_reward": legacy.coin_reward if legacy else 10,
        "xp_reward": (legacy.xp_reward if legacy else 20) if tags else 0,
    })
    if bonus.awarded_at:
        return None
    now = timezone.now()
    if legacy_paid:
        bonus.completed_at = legacy.completed_at or now
        bonus.awarded_at = bonus.completed_at
        bonus.save(update_fields=["completed_at", "awarded_at"])
        return None

    description = f"Daily bonus #{bonus.pk} ·"
    award = AwardService.grant(user, xp_tags=tags, xp=bonus.xp_reward, xp_source_label=description,
                       coins=bonus.coin_reward, coin_reason="daily_challenge", coin_description=description,
                       badge_scopes={"coin", "skill_xp", "badges"})
    bonus.coins_awarded = sum(CoinLedger.objects.filter(
        user=user, reason="daily_challenge", description__startswith=description,
    ).values_list("amount", flat=True))
    bonus.xp_awarded = award["xp_awarded"]
    bonus.completed_at = now
    bonus.awarded_at = now
    bonus.save(update_fields=["coins_awarded", "xp_awarded", "completed_at", "awarded_at"])
    if legacy:
        legacy.coin_reward = 0
        legacy.xp_reward = 0
        legacy.save(update_fields=["coin_reward", "xp_reward"])
    return _payload(user, day, bonus)


def settle_legacy_bonuses(limit=100):
    """Pay genuinely completed old bonuses once, outside schema migrations."""
    from django.db.models import F, Q
    rows = DailyChallenge.objects.filter(
        current_progress__gte=F("target_value"), user__role="child", user__is_active=True,
    ).filter(Q(coin_reward__gt=0) | Q(xp_reward__gt=0)).select_related("user__family").order_by("pk")[:limit]
    settled = 0
    for legacy in rows:
        # Only dates with an earned legacy row enter this path; no invented
        # historical participation or daily rewards for unfinished work.
        marker = SimpleNamespace(voided=False, trigger_type="legacy_daily", occurred_on=legacy.date,
                                 context={}, user=legacy.user)
        if process_daily_bonus(legacy.user, marker):
            settled += 1
    return settled
