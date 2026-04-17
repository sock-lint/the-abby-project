import logging
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

        quest.save(update_fields=["current_progress", "updated_at"])
        participant.save(update_fields=["contribution", "updated_at"])

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

        # Award XP (AwardService.grant already runs BadgeService.evaluate_badges
        # internally when xp > 0, so the QUEST_COMPLETED criterion picks up).
        if definition.xp_reward > 0:
            from apps.achievements.services import AwardService
            AwardService.grant(user, xp=definition.xp_reward)
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

        logger.info("User %s completed quest: %s", user.username, definition.name)
        return rewards

    @staticmethod
    def expire_quests():
        """Expire all active quests past their end_date. Called by Celery task."""
        from apps.quests.models import Quest

        expired = Quest.objects.filter(
            status=Quest.Status.ACTIVE,
            end_date__lt=timezone.now(),
        ).update(status=Quest.Status.EXPIRED)

        return expired

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

        raged = 0
        decayed = 0
        for quest in active_bosses:
            had_progress = quest.participants.filter(
                updated_at__date=today,
            ).exists()

            if not had_progress and quest.rage_shield < RAGE_SHIELD_CAP:
                quest.rage_shield = min(
                    quest.rage_shield + RAGE_SHIELD_STEP, RAGE_SHIELD_CAP,
                )
                quest.save(update_fields=["rage_shield", "updated_at"])
                raged += 1
            elif had_progress and quest.rage_shield > 0:
                quest.rage_shield = max(quest.rage_shield - RAGE_SHIELD_STEP, 0)
                quest.save(update_fields=["rage_shield", "updated_at"])
                decayed += 1

        return {"raged": raged, "decayed": decayed}

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
