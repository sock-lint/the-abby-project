import logging
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.rpg.constants import TriggerType

logger = logging.getLogger(__name__)

# Damage values per trigger type (for boss fights).
#
# CREATION_LOGGED is intentionally absent: child-authored creations do not
# deal boss damage. QUEST_COMPLETE and PERFECT_DAY are also absent: they fire as
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
    # Journal entries deal modest damage — matches habit logs. The service
    # gates on first-of-day so repeat entries don't stack.
    TriggerType.JOURNAL_ENTRY: 5,
    # Reading Adventure fires only once per family-local day after ten
    # cumulative minutes; saved legacy quests keep their trigger matching.
    TriggerType.READING_LOGGED: 5,
    # Movement sessions deal flat damage per session, not duration-scaled,
    # so the boss damage stays proportional to *commitment to show up*
    # rather than rewarding marathon entries that already win at the XP
    # layer. The service caps the reward path at 3 sessions per local day.
    TriggerType.MOVEMENT_SESSION: 8,
    # Expedition returns deal modest damage — same scale as habit_log.
    # Sending a mount out is a low-effort daily action; we want it to
    # contribute toward boss quests so the loops feel connected, but
    # not so much that mount-spamming becomes the dominant strategy.
    TriggerType.EXPEDITION_RETURNED: 5,
}

# Rage shield balance (boss quests only). Idle days climb the shield;
# active days decay it. Asymmetric on purpose — climb is gentler than
# decay so a child returning from a multi-day absence can claw back
# faster than they fell behind. With CLIMB=15 / DECAY=25, a 4-day
# absence (+60) clears in roughly 2.5 active days. Cap stays at 100.
RAGE_SHIELD_CLIMB_STEP = 15
RAGE_SHIELD_DECAY_STEP = 25
RAGE_SHIELD_CAP = 100

# Back-compat alias — some external content/tests may still import the
# original name. Points at the climb step (the "growth" direction).
RAGE_SHIELD_STEP = RAGE_SHIELD_CLIMB_STEP


class QuestService:
    """Manages quest lifecycle: start, progress, completion, expiration."""

    @staticmethod
    def _campaign_belongs_to_participants(quest, users):
        """Stop old invalid starts before they can credit a foreign promise."""
        from django.contrib.auth import get_user_model

        family_ids = {member.family_id for member in users}
        if len(family_ids) != 1 or None in family_ids:
            return False
        definition = quest.definition
        if definition.is_system or definition.created_by_id is None:
            # Existing orphaned promises predate this gate. Preserve those
            # saved rewards without making them startable public definitions.
            return True
        return get_user_model().objects.filter(
            pk=definition.created_by_id, family_id=next(iter(family_ids)),
        ).exists()

    @staticmethod
    def _lock_participants(quest_id):
        """Lock all award users in one stable order before campaign rows.

        Co-op progress from source transactions waits until their commit in
        the game loop, so no acting-child award lock precedes this ordering.
        Participants are fixed when a campaign is created.
        """
        from django.contrib.auth import get_user_model
        from apps.quests.models import QuestParticipant

        user_ids = QuestParticipant.objects.filter(quest_id=quest_id).values_list("user_id", flat=True)
        return list(
            get_user_model().objects.select_for_update(no_key=True)
            .filter(pk__in=user_ids).order_by("pk")
        )

    @staticmethod
    @transaction.atomic
    def start_quest(user, definition_id, use_scroll_item_id=None):
        """Start a quest for a user. Optionally consumes a quest scroll from inventory.

        Returns the new Quest, or raises ValueError.
        """
        from apps.quests.models import ChallengeGoal, QuestDefinition, Quest, QuestParticipant
        from apps.quests.queries import definitions_visible_to, equivalent_definition_ids
        from django.contrib.auth import get_user_model

        # Serialize this legacy compatibility path with automatic enrollment.
        user = get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        try:
            definition = definitions_visible_to(user).get(pk=definition_id)
        except QuestDefinition.DoesNotExist:
            raise ValueError("Quest not found")
        from .availability import definition_is_available
        if not definition_is_available(definition):
            raise ValueError("This challenge needs companion artwork that is not currently available.")
        if definition.is_cooperative:
            raise ValueError("Ask a parent to assign this shared challenge to at least two children.")
        if (definition.trigger_filter or {}).get("distinct_active_days") is True:
            raise ValueError("This challenge counts active days automatically. Pin it to follow your progress.")
        from .reference_locks import admit_definition_choices, admit_definition_identity
        admit_definition_choices(definition)
        admit_definition_identity(definition)
        from .progress_sources import require_current_progress_source
        require_current_progress_source(definition)
        definition_ids = equivalent_definition_ids(definition)
        if ChallengeGoal.objects.filter(user=user, catalog_definition_id__in=definition_ids).exists():
            raise ValueError("This challenge progresses automatically. Pin it to follow your progress.")
        if definition.duration_days is None:
            raise ValueError("This challenge progresses automatically with no deadline. Pin it to follow your progress.")

        # Check no active quest
        if Quest.objects.filter(
            participants__user=user, status=Quest.Status.ACTIVE,
        ).exists():
            raise ValueError("You already have an active quest")

        if not definition.is_repeatable and Quest.objects.filter(
            definition_id__in=definition_ids, participants__user=user, status=Quest.Status.COMPLETED,
        ).exists():
            raise ValueError("You have already completed this quest")

        from .milestone_eligibility import has_milestone_gate, milestone_eligibility
        if has_milestone_gate(definition):
            if Quest.objects.filter(definition=definition, participants__user=user).exists():
                raise ValueError("This one-time challenge already has an accepted window.")
            eligibility = milestone_eligibility(user, definition)
            if not eligibility["unlocked"]:
                raise ValueError(" ".join(eligibility["locked_reasons"]))
            raise ValueError("This challenge progresses automatically. Your next Reading Adventure opens its window.")

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
        from apps.quests.reward_items import snapshot_reward_items
        quest = Quest.objects.create(
            definition=definition,
            start_date=now,
            end_date=now + timedelta(days=definition.duration_days),
            reward_items_snapshot=snapshot_reward_items(definition),
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
        from apps.quests.models import ChallengeGoal, QuestDefinition, Quest, QuestParticipant
        from apps.quests.queries import definitions_visible_to, equivalent_definition_ids
        from django.contrib.auth import get_user_model

        users = list(users)
        if not users:
            raise ValueError("start_co_op_quest needs at least one user")
        if len({u.pk for u in users}) != len(users):
            raise ValueError("Duplicate user in co-op quest assignment")
        users = [
            get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
            for user in sorted(users, key=lambda member: member.pk)
        ]
        if len({user.family_id for user in users}) != 1 or users[0].family_id is None:
            raise ValueError("Co-op participants must belong to the same family")
        try:
            definition = definitions_visible_to(users[0]).get(pk=definition_id)
        except QuestDefinition.DoesNotExist:
            raise ValueError("Quest not found")
        from .availability import definition_is_available
        if not definition_is_available(definition):
            raise ValueError("This challenge needs companion artwork that is not currently available.")
        if (definition.trigger_filter or {}).get("distinct_active_days") is True:
            raise ValueError("This challenge counts active days automatically. Pin it to follow your progress.")
        from .reference_locks import admit_definition_choices, admit_definition_identity
        admit_definition_choices(definition)
        admit_definition_identity(definition)
        from .progress_sources import require_current_progress_source
        require_current_progress_source(definition)
        definition_ids = equivalent_definition_ids(definition)
        personal_goals = ChallengeGoal.objects.filter(user__in=users, catalog_definition_id__in=definition_ids)
        if definition.is_cooperative:
            if len(users) < 2:
                raise ValueError("A shared challenge needs at least two children.")
            if any(user.role != "child" for user in users):
                raise ValueError("Shared challenge participants must be children.")
            # Accepted personal promises can still finish after their end,
            # when an earlier accepted fact is repaired. A one-time promise
            # therefore cannot be reassigned for a second full reward.
            now = timezone.now()
            if not definition.is_repeatable and personal_goals.exists():
                raise ValueError("A participant already has an accepted individual version of this one-time challenge. Its original promise is preserved and cannot be reassigned as a shared reward.")
            if personal_goals.filter(
                Q(occurrences__ends_at__gt=now) | Q(occurrences__isnull=True, ends_at__gt=now),
            ).exists():
                raise ValueError("A saved individual challenge window is still open. Wait for it to expire before this shared assignment.")
        elif personal_goals.exists():
            raise ValueError("These challenges already progress automatically; a second campaign cannot be started.")
        if definition.duration_days is None:
            raise ValueError("This challenge progresses automatically with no deadline for each child.")

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

        if not definition.is_repeatable and Quest.objects.filter(
            definition_id__in=definition_ids, participants__user__in=users, status=Quest.Status.COMPLETED,
        ).exists():
            raise ValueError("A participant has already completed this quest")

        from .milestone_eligibility import has_milestone_gate, milestone_eligibility
        if has_milestone_gate(definition):
            if Quest.objects.filter(definition=definition, participants__user__in=users).exists():
                raise ValueError("A participant already accepted this one-time challenge.")
            for participant in users:
                eligibility = milestone_eligibility(participant, definition)
                if not eligibility["unlocked"]:
                    raise ValueError("Every participant must qualify: " + " ".join(eligibility["locked_reasons"]))
            raise ValueError("This challenge progresses automatically. Each child's next Reading Adventure opens their window.")

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
        from apps.quests.reward_items import snapshot_reward_items
        quest = Quest.objects.create(
            definition=definition,
            start_date=now,
            end_date=now + timedelta(days=definition.duration_days),
            reward_items_snapshot=snapshot_reward_items(definition),
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
    def record_progress(user, trigger_type, context=None, *, quest_id=None, category_context=None):
        """Record quest progress from a completed task.

        Returns dict with: quest_id, quest_name, damage_dealt, new_progress, completed (bool), rewards (if completed).
        Returns None if no active quest, the trigger doesn't match its filter,
        or the trigger is ineligible for boss damage.
        """
        from apps.quests.models import Quest, QuestParticipant

        if context is None:
            context = {}

        # Discover membership without campaign locks, then establish the same
        # user-first ordering used by every award path. Re-read the campaign
        # under its lock: another participant may have finished while waiting.
        membership = QuestParticipant.objects.filter(
            user=user, quest__status=Quest.Status.ACTIVE,
        )
        if quest_id is not None:
            # Deferred source work belongs to the campaign observed before
            # commit, even if a new campaign has since been assigned.
            membership = membership.filter(quest_id=quest_id)
        quest_id = membership.values_list("quest_id", flat=True).first()
        if quest_id is None:
            return None
        users = QuestService._lock_participants(quest_id)
        quest = Quest.objects.select_for_update(of=("self",)).select_related("definition").get(pk=quest_id)
        if quest.status != Quest.Status.ACTIVE:
            return None
        if not QuestService._campaign_belongs_to_participants(quest, users):
            return None
        try:
            participant = QuestParticipant.objects.select_for_update().get(user=user, quest=quest)
        except QuestParticipant.DoesNotExist:
            return None

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
        if trigger_filter.get("skill_category_id"):
            from .activity import resolve_category_context
            from .category_matching import matches_category
            if category_context is None:
                category_context = resolve_category_context(user, trigger_type, context)
            if not matches_category(category_context, trigger_filter["skill_category_id"]):
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
            base_damage = TRIGGER_DAMAGE.get(trigger_type, 0)
            # Excluded triggers must not record boss activity, refresh rage
            # timestamps or finish a campaign already at its target.
            if base_damage <= 0:
                return None
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
        """Complete once and atomically pay the full promise to every member.

        The response retains the finishing child's reward shape. Persisted
        completion, awards, items and recipient notifications commit together;
        a late failure leaves the campaign active and fully retryable.
        """
        from apps.quests.models import Quest

        users = QuestService._lock_participants(quest.pk)
        quest = Quest.objects.select_for_update(of=("self",)).select_related("definition").get(pk=quest.pk)
        if quest.status != Quest.Status.ACTIVE:
            return None
        if not any(member.pk == user.pk for member in users):
            raise ValueError("You are not a participant in this quest")
        if not QuestService._campaign_belongs_to_participants(quest, users):
            raise ValueError("Quest not found")
        if quest.reward_items_snapshot is None:
            from apps.quests.reward_items import snapshot_reward_items
            quest.reward_items_snapshot = snapshot_reward_items(quest.definition, available_only=False)
        quest.status = Quest.Status.COMPLETED
        quest.save(update_fields=["status", "updated_at", "reward_items_snapshot"])
        finishing_rewards = None
        for member in users:
            rewards = QuestService._award_quest_rewards(quest, member)
            if member.pk == user.pk:
                finishing_rewards = rewards
        return finishing_rewards

    @staticmethod
    def _award_quest_rewards(quest, user):
        """Pay one participant while the campaign and user locks are held."""
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        from apps.rpg.inventory import grant_item
        from apps.notifications.services import notify

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
            # Audit H8: quest completion moves quest counters + meta, plus
            # coin (quest reward already paid) and skill_xp (untagged
            # quest case where AwardService isn't reached).
            BadgeService.evaluate_badges(
                user, scopes={"quest", "coin", "skill_xp", "badges"},
            )

        # Award item rewards. Eggs auto-salvage to coins when the player
        # already mounts the matching species — quests like Dragon Slayer
        # (rewards Wolf Egg + Dragon Egg) would otherwise stack dead eggs
        # in the inventory of a kid who's already evolved both lifecycles.
        # Salvage value = item.coin_value × quantity, mirroring the
        # cosmetic-dupe rule in DropService.
        from apps.quests.reward_items import accepted_reward_items, egg_reward_is_duplicate, reward_item_details
        accepted_items = accepted_reward_items(quest)
        for reward_item in accepted_items:
            item = reward_item.item
            details = {"item_id": item.pk, **reward_item_details(
                item, snapshot=getattr(reward_item, "reward_snapshot", None),
            ), "quantity": reward_item.quantity}
            is_owned_egg = egg_reward_is_duplicate(user, item, (row.item for row in accepted_items))
            if is_owned_egg and item.coin_value > 0:
                salvage = item.coin_value * reward_item.quantity
                CoinService.award_coins(
                    user, salvage, CoinLedger.Reason.ADJUSTMENT,
                    description=f"Quest egg salvage: {item.display_name}",
                )
                rewards["coins"] += salvage
                rewards["items"].append({
                    **details,
                    "salvaged_to_coins": salvage,
                })
                continue
            grant_item(user, item, reward_item.quantity)
            rewards["items"].append(details)

        # Completion and every recipient's payout share the campaign/user
        # locks. Its status guard makes this extra roll one-time, including
        # co-op members who did not land the finishing hit.
        from apps.rpg.services import DropService
        DropService.award_accomplishment(user, TriggerType.QUEST_COMPLETE)
        from apps.chronicle.recognition import safe_record_firsts
        safe_record_firsts(user, TriggerType.QUEST_COMPLETE)

        notify(
            user,
            title=f"Challenge complete: {definition.name}!",
            message=f"Earned {rewards['coins']} coins and {rewards['xp']} XP!",
            notification_type="badge_earned",
            link="/quests",
        )

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="quest",
            event_type="quest.complete",
            summary=f"Challenge complete: {definition.name}",
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

        - Idle day (no participant progress): rage climbs by
          RAGE_SHIELD_CLIMB_STEP, capped at RAGE_SHIELD_CAP. The cap
          prevents an absent user's quest from spiraling into unwinnable
          territory.
        - Active day (any participant made progress): rage decays by
          RAGE_SHIELD_DECAY_STEP toward 0. Decay is faster than climb so
          coming back after an absence isn't punished proportionally to
          the absence — preserves the gentle-nudge doctrine.

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

            prior = quest.rage_shield
            if not had_progress and quest.rage_shield < RAGE_SHIELD_CAP:
                quest.rage_shield = min(
                    quest.rage_shield + RAGE_SHIELD_CLIMB_STEP,
                    RAGE_SHIELD_CAP,
                )
                quest.save(update_fields=["rage_shield", "updated_at"])
                raged += 1
                QuestService._log_rage_event(
                    quest, prior, direction="up",
                )
            elif had_progress and quest.rage_shield > 0:
                quest.rage_shield = max(
                    quest.rage_shield - RAGE_SHIELD_DECAY_STEP, 0,
                )
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
                            f"+{RAGE_SHIELD_CLIMB_STEP}"
                            if direction == "up"
                            else f"-{RAGE_SHIELD_DECAY_STEP}"
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
    """Compatibility for saved daily challenges and older clients.

    New clients use the automatic daily bonus. These methods share its
    user lock and paid markers so an old client cannot pay it twice.
    """

    @staticmethod
    @transaction.atomic
    def get_or_create_today(user):
        """Return today's challenge for the user, creating one if missing.

        Retained for ``GET /api/challenges/daily/`` on older clients.
        """
        from apps.quests.models import DailyBonus, DailyChallenge
        from django.contrib.auth import get_user_model
        from apps.quests.daily_bonus import paid_legacy_bonus

        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        from apps.quests.activity import household_timezone
        today = timezone.localdate(timezone.now(), timezone=household_timezone(user))
        existing = DailyChallenge.objects.filter(user=user, date=today).first()
        if existing:
            return existing

        template = random.choice(DAILY_CHALLENGE_TEMPLATES)
        paid_bonus = (DailyBonus.objects.filter(user=user, date=today, awarded_at__isnull=False).first()
                      or paid_legacy_bonus(user, today))
        return DailyChallenge.objects.create(
            user=user,
            challenge_type=template["type"],
            target_value=template["target"],
            coin_reward=0 if paid_bonus else template["coins"],
            xp_reward=0 if paid_bonus else template["xp"],
            current_progress=template["target"] if paid_bonus else 0,
            completed_at=paid_bonus.completed_at if paid_bonus else None,
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

        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        from apps.quests.activity import household_timezone
        today = timezone.localdate(timezone.now(), timezone=household_timezone(user))
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
        from apps.quests.models import DailyBonus, DailyChallenge

        from django.contrib.auth import get_user_model
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)

        from apps.quests.activity import household_timezone
        from apps.quests.daily_bonus import paid_legacy_bonus
        today = timezone.localdate(timezone.now(), timezone=household_timezone(user))
        if (DailyBonus.objects.filter(user=user, date=today, awarded_at__isnull=False).exists()
                or paid_legacy_bonus(user, today)):
            return {"already_claimed": True, "coins": 0, "xp": 0}
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
            coin_reason="daily_challenge",
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
