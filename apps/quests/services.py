import logging
import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.rpg.constants import TriggerType

logger = logging.getLogger(__name__)

# Damage values per trigger type (for boss fights).
#
# QUEST_COMPLETE and PERFECT_DAY are intentionally absent: they fire as
# *rewards* for existing work, not new effort — so they don't count as
# damage against a separate boss quest. If a future design wants them to
# cross-count, add them here explicitly.
TRIGGER_DAMAGE = {
    TriggerType.CLOCK_OUT: 10,  # per hour
    TriggerType.CHORE_COMPLETE: 15,
    TriggerType.HOMEWORK_COMPLETE: 25,
    TriggerType.HOMEWORK_CREATED: 5,
    TriggerType.MILESTONE_COMPLETE: 50,
    TriggerType.BADGE_EARNED: 30,
    TriggerType.PROJECT_COMPLETE: 75,
    TriggerType.HABIT_LOG: 5,
    # Savings goal completion is a one-shot event per goal; the flat 100
    # matches its rarity. Collection-type quests (Hoard Builder) don't use
    # this — they count 1 per qualifying trigger regardless.
    TriggerType.SAVINGS_GOAL_COMPLETE: 100,
}

# Rage shield balance (boss quests only). Idle day climbs, active day decays.
# Cap matches the original per-day step of 20 so the cliff is 5 idle days.
RAGE_SHIELD_STEP = 20
RAGE_SHIELD_CAP = 100


class QuestService:
    """Manages quest lifecycle: start, progress, completion, expiration."""

    @staticmethod
    @transaction.atomic
    def start_quest(user, definition_id, use_scroll_item_id=None):
        """Start a quest for a user. Optionally consumes a quest scroll from inventory.

        Returns the new Quest, or raises ValueError.
        """
        from apps.quests.models import QuestDefinition, Quest, QuestParticipant

        # Check no active quest
        if Quest.objects.filter(
            participants__user=user, status=Quest.Status.ACTIVE,
        ).exists():
            raise ValueError("You already have an active quest")

        try:
            definition = QuestDefinition.objects.get(pk=definition_id)
        except QuestDefinition.DoesNotExist:
            raise ValueError("Quest not found")

        # Check badge requirement
        if definition.required_badge:
            from apps.achievements.models import UserBadge
            if not UserBadge.objects.filter(user=user, badge=definition.required_badge).exists():
                raise ValueError(f"You need the '{definition.required_badge.name}' badge to start this quest")

        # Consume scroll if provided
        if use_scroll_item_id:
            from apps.rpg.models import ItemDefinition, UserInventory
            try:
                scroll_inv = UserInventory.objects.select_for_update().get(
                    user=user, item_id=use_scroll_item_id, quantity__gte=1,
                )
            except UserInventory.DoesNotExist:
                raise ValueError("You don't have that quest scroll")
            if scroll_inv.item.item_type != ItemDefinition.ItemType.QUEST_SCROLL:
                raise ValueError("That item is not a quest scroll")
            scroll_inv.quantity -= 1
            if scroll_inv.quantity == 0:
                scroll_inv.delete()
            else:
                scroll_inv.save(update_fields=["quantity", "updated_at"])

        now = timezone.now()
        quest = Quest.objects.create(
            definition=definition,
            start_date=now,
            end_date=now + timedelta(days=definition.duration_days),
        )
        QuestParticipant.objects.create(quest=quest, user=user)

        logger.info("User %s started quest: %s", user.username, definition.name)
        return quest

    @staticmethod
    @transaction.atomic
    def start_co_op_quest(definition_id, users):
        """Start one shared Quest with multiple participants.

        Each user gets a ``QuestParticipant`` row tied to the same ``Quest``
        so damage/contribution pools together toward the target. Same
        one-active-quest-per-user invariant as ``start_quest`` — any user
        already on an active quest causes the whole call to fail rather
        than partially-assign.

        Caller responsibility: verify parent auth. Returns the created
        Quest. Raises ``ValueError`` on invalid input.
        """
        from apps.quests.models import QuestDefinition, Quest, QuestParticipant

        users = list(users)
        if not users:
            raise ValueError("start_co_op_quest needs at least one user")
        if len({u.pk for u in users}) != len(users):
            raise ValueError("Duplicate user in co-op quest assignment")

        # Pre-flight: no participant may already have an active quest.
        # Doing this as one SQL query keeps the check atomic.
        conflicting = Quest.objects.filter(
            participants__user__in=users, status=Quest.Status.ACTIVE,
        ).values_list("participants__user__username", flat=True)
        if conflicting:
            raise ValueError(
                "Users already on active quests: "
                + ", ".join(sorted(set(conflicting)))
            )

        try:
            definition = QuestDefinition.objects.get(pk=definition_id)
        except QuestDefinition.DoesNotExist:
            raise ValueError("Quest not found")

        # Badge gate applies to every participant — don't start if any
        # participant can't satisfy it.
        if definition.required_badge:
            from apps.achievements.models import UserBadge
            gated = set(
                u.pk for u in users
                if not UserBadge.objects.filter(
                    user=u, badge=definition.required_badge,
                ).exists()
            )
            if gated:
                raise ValueError(
                    f"Not every participant has the '{definition.required_badge.name}' badge "
                    f"({len(gated)} missing)"
                )

        now = timezone.now()
        quest = Quest.objects.create(
            definition=definition,
            start_date=now,
            end_date=now + timedelta(days=definition.duration_days),
        )
        for u in users:
            QuestParticipant.objects.create(quest=quest, user=u)

        logger.info(
            "Co-op quest started: %s with %d participants",
            definition.name, len(users),
        )
        return quest

    @staticmethod
    @transaction.atomic
    def record_progress(user, trigger_type, context=None):
        """Record quest progress from a completed task.

        Returns dict with: quest_id, quest_name, damage_dealt, new_progress, completed (bool), rewards (if completed).
        Returns None if no active quest or trigger doesn't match filter.
        """
        from apps.quests.models import Quest, QuestParticipant

        if context is None:
            context = {}

        # Find user's active quest
        try:
            participant = QuestParticipant.objects.select_for_update().select_related(
                "quest", "quest__definition",
            ).get(user=user, quest__status=Quest.Status.ACTIVE)
        except QuestParticipant.DoesNotExist:
            return None

        quest = participant.quest
        definition = quest.definition

        # Check if quest is expired
        if quest.is_expired:
            quest.status = Quest.Status.EXPIRED
            quest.save(update_fields=["status", "updated_at"])
            return None

        # Check trigger filter
        trigger_filter = definition.trigger_filter or {}
        allowed_triggers = trigger_filter.get("allowed_triggers")
        if allowed_triggers and trigger_type not in allowed_triggers:
            return None

        # Check project filter
        if trigger_filter.get("project_id") and context.get("project_id") != trigger_filter["project_id"]:
            return None

        # Check skill category filter
        if trigger_filter.get("skill_category_id") and context.get("skill_category_id") != trigger_filter["skill_category_id"]:
            return None

        # Check chore filter
        if trigger_filter.get("chore_ids") and context.get("chore_id") not in trigger_filter["chore_ids"]:
            return None

        # Check timeliness filter (homework on-time submissions, etc.)
        if trigger_filter.get("on_time") and not context.get("on_time"):
            return None

        # Check savings-goal filter. When set, only the named goal's completion
        # counts — lets Hoard Builder be assigned against a specific goal.
        if trigger_filter.get("savings_goal_id") and (
            context.get("savings_goal_id") != trigger_filter["savings_goal_id"]
        ):
            return None

        # Calculate damage/progress
        if definition.quest_type == "boss":
            base_damage = TRIGGER_DAMAGE.get(trigger_type, 10)
            # Scale by hours for clock_out
            if trigger_type == TriggerType.CLOCK_OUT and "hours" in context:
                damage = int(base_damage * context["hours"])
            else:
                damage = base_damage
        else:
            # Collection quest: each qualifying trigger = 1 item collected
            damage = 1

        # Apply damage
        quest.current_progress += damage
        participant.contribution += damage

        prior_progress = quest.current_progress - damage
        quest.save(update_fields=["current_progress", "updated_at"])
        participant.save(update_fields=["contribution", "updated_at"])

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="quest",
            event_type="quest.progress",
            summary=f"Quest progress: {definition.name} +{damage}",
            subject=user,
            target=quest,
            breakdown=[
                {"label": "trigger", "value": str(trigger_type), "op": "note"},
                {"label": "damage", "value": damage, "op": "+"},
                {"label": "progress",
                 "value": f"{prior_progress} → {quest.current_progress}/{quest.effective_target}",
                 "op": "note"},
            ],
            extras={
                "quest_id": quest.pk,
                "quest_name": definition.name,
                "trigger_type": str(trigger_type),
                "damage_dealt": damage,
                "prior_progress": prior_progress,
                "new_progress": quest.current_progress,
                "target": quest.effective_target,
            },
        )

        # Check completion
        completed = False
        rewards = None
        if quest.current_progress >= quest.effective_target:
            completed = True
            rewards = QuestService._complete_quest(quest, user)

        return {
            "quest_id": quest.pk,
            "quest_name": definition.name,
            "damage_dealt": damage,
            "new_progress": quest.current_progress,
            "target": quest.effective_target,
            "completed": completed,
            "rewards": rewards,
        }

    @staticmethod
    @transaction.atomic
    def _complete_quest(quest, user):
        """Mark quest as completed and award rewards."""
        from apps.quests.models import Quest
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        from apps.rpg.models import UserInventory
        from apps.notifications.services import notify

        quest.status = Quest.Status.COMPLETED
        quest.save(update_fields=["status", "updated_at"])

        rewards = {"coins": 0, "xp": 0, "items": []}
        definition = quest.definition

        # Award coins
        if definition.coin_reward > 0:
            CoinService.award_coins(
                user, definition.coin_reward, CoinLedger.Reason.ADJUSTMENT,
                description=f"Quest complete: {definition.name}",
            )
            rewards["coins"] = definition.coin_reward

        # Award XP — tag-distributed across QuestSkillTag rows when any
        # exist. Quests without tags still award coins + items + trigger
        # BadgeService.evaluate_badges (so QUEST_COMPLETED fires) but
        # skip the skill-tree credit. Parents authoring custom quests
        # should attach tags; every system quest in quests.yaml ships
        # with a ``skill_tags:`` block.
        if definition.xp_reward > 0:
            from apps.achievements.services import AwardService
            AwardService.grant(
                user,
                xp_tags=definition.skill_tags.select_related("skill"),
                xp=definition.xp_reward,
                xp_source_label=f"Quest: {definition.name}",
            )
            rewards["xp"] = definition.xp_reward
        else:
            # Quests with xp_reward == 0 still need badge evaluation so the
            # QUEST_COMPLETED criterion fires. AwardService is the usual
            # doorway; when it isn't called, evaluate directly.
            from apps.achievements.services import BadgeService
            BadgeService.evaluate_badges(user)

        # Award item rewards
        for reward_item in definition.reward_items.select_related("item").all():
            inv, created = UserInventory.objects.get_or_create(
                user=user, item=reward_item.item,
                defaults={"quantity": reward_item.quantity},
            )
            if not created:
                inv.quantity += reward_item.quantity
                inv.save(update_fields=["quantity", "updated_at"])
            rewards["items"].append({
                "item_name": reward_item.item.name,
                "item_icon": reward_item.item.icon,
                "quantity": reward_item.quantity,
            })

        notify(
            user,
            title=f"Quest complete: {definition.name}!",
            message=f"Earned {rewards['coins']} coins and {rewards['xp']} XP!",
            notification_type="badge_earned",
            link="/quests",
        )

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="quest",
            event_type="quest.complete",
            summary=f"Quest complete: {definition.name}",
            subject=user,
            target=quest,
            coins_delta=int(rewards["coins"]) or None,
            xp_delta=int(rewards["xp"]) or None,
            breakdown=[
                {"label": "coins", "value": rewards["coins"], "op": "note"},
                {"label": "xp", "value": rewards["xp"], "op": "note"},
                {"label": "items",
                 "value": ", ".join(i["item_name"] for i in rewards["items"]) or "—",
                 "op": "note"},
            ],
            extras={
                "quest_id": quest.pk,
                "quest_name": definition.name,
                "coin_reward": rewards["coins"],
                "xp_reward": rewards["xp"],
                "item_rewards": rewards["items"],
            },
        )

        logger.info("User %s completed quest: %s", user.username, definition.name)
        return rewards

    @staticmethod
    def expire_quests():
        """Expire all active quests past their end_date. Called by Celery task."""
        from apps.quests.models import Quest

        to_expire = list(
            Quest.objects.filter(
                status=Quest.Status.ACTIVE,
                end_date__lt=timezone.now(),
            ).select_related("definition").prefetch_related("participants__user")
        )
        if not to_expire:
            return 0

        ids = [q.pk for q in to_expire]
        Quest.objects.filter(pk__in=ids).update(status=Quest.Status.EXPIRED)

        from apps.activity.services import ActivityLogService
        for quest in to_expire:
            for participant in quest.participants.all():
                ActivityLogService.record(
                    category="system",
                    event_type="system.quest_expire",
                    summary=f"Quest expired: {quest.definition.name}",
                    actor=None,
                    subject=participant.user,
                    target=quest,
                    extras={
                        "quest_id": quest.pk,
                        "quest_name": quest.definition.name,
                        "progress": quest.current_progress,
                        "target": quest.effective_target,
                    },
                )

        return len(to_expire)

    @staticmethod
    def apply_boss_rage():
        """Tick rage shield on every active boss quest.

        Called by nightly Celery task.

        - Idle day (no participant progress): rage climbs by RAGE_SHIELD_STEP,
          capped at RAGE_SHIELD_CAP. The cap prevents an absent user's quest
          from spiraling into unwinnable territory.
        - Active day (any participant made progress): rage decays by
          RAGE_SHIELD_STEP toward 0. This preserves the "catch up when you're
          back" signal while staying consistent with the project's
          gentle-nudge doctrine.

        Returns a dict with ``raged`` and ``decayed`` counts.
        """
        from apps.quests.models import Quest

        today = timezone.localdate()
        active_bosses = Quest.objects.filter(
            status=Quest.Status.ACTIVE,
            definition__quest_type="boss",
        )

        from apps.activity.services import ActivityLogService

        raged = 0
        decayed = 0
        for quest in active_bosses:
            had_progress = quest.participants.filter(
                updated_at__date=today,
            ).exists()

            prior = quest.rage_shield
            if not had_progress and quest.rage_shield < RAGE_SHIELD_CAP:
                quest.rage_shield = min(
                    quest.rage_shield + RAGE_SHIELD_STEP, RAGE_SHIELD_CAP,
                )
                quest.save(update_fields=["rage_shield", "updated_at"])
                raged += 1
                QuestService._log_rage_event(
                    quest, prior, direction="up",
                )
            elif had_progress and quest.rage_shield > 0:
                quest.rage_shield = max(quest.rage_shield - RAGE_SHIELD_STEP, 0)
                quest.save(update_fields=["rage_shield", "updated_at"])
                decayed += 1
                QuestService._log_rage_event(
                    quest, prior, direction="down",
                )

        return {"raged": raged, "decayed": decayed}

    @staticmethod
    def _log_rage_event(quest, prior, direction):
        from apps.activity.services import ActivityLogService

        for participant in quest.participants.select_related("user").all():
            ActivityLogService.record(
                category="system",
                event_type="system.rage_shield_tick",
                summary=(
                    f"{quest.definition.name}: rage "
                    f"{prior} → {quest.rage_shield}"
                    + (" (idle day)" if direction == "up" else " (active day)")
                ),
                actor=None,
                subject=participant.user,
                target=quest,
                breakdown=[
                    {"label": "prior", "value": prior, "op": "+"},
                    {
                        "label": "step",
                        "value": (
                            f"+{RAGE_SHIELD_STEP}"
                            if direction == "up"
                            else f"-{RAGE_SHIELD_STEP}"
                        ),
                        "op": "=",
                    },
                    {"label": "now", "value": quest.rage_shield, "op": "note"},
                ],
                extras={
                    "quest_id": quest.pk,
                    "direction": direction,
                    "prior": prior,
                    "new": quest.rage_shield,
                },
            )

    @staticmethod
    def get_active_quest(user):
        """Get the user's current active quest, or None."""
        from apps.quests.models import Quest, QuestParticipant

        try:
            participant = QuestParticipant.objects.select_related(
                "quest", "quest__definition",
            ).get(user=user, quest__status=Quest.Status.ACTIVE)
            return participant.quest
        except QuestParticipant.DoesNotExist:
            return None


# Trigger → DailyChallenge.ChallengeType progress increment map. Quantity
# reflects the user-visible unit; clock_out quantizes by floor(minutes/60)
# so half-hour sessions don't prematurely complete a 1-hour challenge.
DAILY_CHALLENGE_TRIGGER_MAP = {
    "clock_out": "clock_hour",
    "chore_complete": "chores",
    "habit_log": "habits",
    "homework_complete": "homework",
    "milestone_complete": "milestone",
}

# Curated daily-challenge templates the rotation task picks from. Each is
# tuned so ~10 minutes of focused engagement will satisfy it — the slot is
# supposed to feel like a small, friendly nudge, not a grind.
DAILY_CHALLENGE_TEMPLATES = [
    {"type": "clock_hour", "target": 1, "coins": 15, "xp": 25},
    {"type": "chores", "target": 2, "coins": 10, "xp": 20},
    {"type": "habits", "target": 2, "coins": 10, "xp": 20},
    {"type": "homework", "target": 1, "coins": 15, "xp": 30},
    {"type": "milestone", "target": 1, "coins": 20, "xp": 40},
]


class DailyChallengeService:
    """Create, advance, and reward once-per-day micro-challenges.

    Separate from QuestService by design — a Daily Challenge is always one
    active slot per user per day, shares no lifecycle state with Quest, and
    rotates automatically at 00:30 local (see ``rotate_daily_challenges_task``
    in apps/quests/tasks.py).
    """

    @staticmethod
    @transaction.atomic
    def get_or_create_today(user):
        """Return today's challenge for the user, creating one if missing.

        Called from the Celery rotation task for every active child, and
        opportunistically from ``GET /api/challenges/daily/`` so a user who
        logs in mid-day before the rotation fires still sees a challenge.
        """
        from apps.quests.models import DailyChallenge

        today = timezone.localdate()
        existing = DailyChallenge.objects.filter(user=user, date=today).first()
        if existing:
            return existing

        template = random.choice(DAILY_CHALLENGE_TEMPLATES)
        return DailyChallenge.objects.create(
            user=user,
            challenge_type=template["type"],
            target_value=template["target"],
            coin_reward=template["coins"],
            xp_reward=template["xp"],
            date=today,
        )

    @staticmethod
    @transaction.atomic
    def record_progress(user, trigger_type, context=None):
        """Bump today's challenge if the trigger matches the challenge type.

        Returns a tuple of ``(challenge_or_None, newly_completed_bool)``.
        Called from ``GameLoopService.on_task_completed`` alongside regular
        quest progress. Safe to call with any trigger_type — it returns
        ``(None, False)`` when the trigger doesn't map to a daily type.
        """
        from apps.quests.models import DailyChallenge

        if context is None:
            context = {}
        mapped = DAILY_CHALLENGE_TRIGGER_MAP.get(str(trigger_type))
        if mapped is None:
            return (None, False)

        today = timezone.localdate()
        try:
            challenge = DailyChallenge.objects.select_for_update().get(
                user=user, date=today,
            )
        except DailyChallenge.DoesNotExist:
            return (None, False)
        if challenge.challenge_type != mapped:
            return (challenge, False)
        if challenge.is_complete:
            return (challenge, False)

        # clock_out increments by hours worked, not by "1 clock-out event".
        increment = 1
        if mapped == "clock_hour":
            minutes = int(context.get("duration_minutes", 0))
            increment = max(0, minutes // 60)
        if increment <= 0:
            return (challenge, False)

        prior_complete = challenge.is_complete
        challenge.current_progress = min(
            challenge.target_value, challenge.current_progress + increment,
        )
        newly_complete = challenge.is_complete and not prior_complete
        if newly_complete:
            challenge.completed_at = timezone.now()
        challenge.save(update_fields=[
            "current_progress", "completed_at", "updated_at",
        ])
        return (challenge, newly_complete)

    @staticmethod
    @transaction.atomic
    def claim_reward(user):
        """Pay out a completed daily challenge's coin + XP reward once.

        Idempotent — a second claim after the first no-ops and returns the
        already-awarded state. Returns a dict describing the payout.
        """
        from apps.achievements.services import AwardService
        from apps.quests.models import DailyChallenge

        today = timezone.localdate()
        try:
            challenge = DailyChallenge.objects.select_for_update().get(
                user=user, date=today,
            )
        except DailyChallenge.DoesNotExist:
            raise ValueError("No daily challenge today")
        if not challenge.is_complete:
            raise ValueError("Complete the challenge before claiming")
        if challenge.completed_at is None:
            challenge.completed_at = timezone.now()
            challenge.save(update_fields=["completed_at"])

        # Award is idempotent on the claim boundary — a second call sees
        # coin_reward=0 via the marker below and skips the award. We set
        # reward values to 0 after the first claim.
        if challenge.coin_reward == 0 and challenge.xp_reward == 0:
            return {
                "already_claimed": True,
                "coins": 0,
                "xp": 0,
            }

        coins = challenge.coin_reward
        xp = challenge.xp_reward
        AwardService.grant(
            user,
            coins=coins,
            coin_reason="adjustment",
            xp=xp,
            xp_source_label="Daily Challenge",
        )
        challenge.coin_reward = 0
        challenge.xp_reward = 0
        challenge.save(update_fields=["coin_reward", "xp_reward"])
        return {
            "already_claimed": False,
            "coins": coins,
            "xp": xp,
        }
