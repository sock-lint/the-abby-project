from datetime import datetime, timedelta
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.movement.models import MovementType
from apps.quests.goals import (
    create_goal, ingest_activity, list_goals, set_pin, void_activity,
)
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal,
    ChallengeOccurrence, ChallengePin, Quest, QuestDefinition, QuestParticipant, QuestSkillTag,
)
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class _GoalFixture:
    def setUp(self):
        self.family = make_family("Goal household", parents=[{"username": "goalparent"}],
                                  children=[{"username": "goalchild"}, {"username": "goalsibling"}])
        self.parent, self.child = self.family.parents[0], self.family.children[0]
        category = SkillCategory.objects.create(name="Goal physical")
        self.skill = Skill.objects.create(name="Running", category=category)
        self.running = MovementType.objects.create(name="Run", slug="run-goal")
        self.cycling = MovementType.objects.create(name="Cycle", slug="cycle-goal")
        self.now = timezone.now()
        ChallengeEnrollment.objects.create(user=self.child, starts_at=self.now - timedelta(days=1), timezone_name="America/Phoenix")

    def definition(self, name="Move often", target=2, **overrides):
        definition = QuestDefinition.objects.create(
            name=name, description="Two recorded sessions", quest_type=overrides.pop("quest_type", "collection"),
            target_value=target, duration_days=7, is_system=True, coin_reward=5, xp_reward=10,
            trigger_filter={"allowed_triggers": ["movement_session"]}, **overrides,
        )
        QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
        return definition

    def fact(self, source_id, *, at=None, trigger="movement_session", distance=None, minutes=20, movement_type=None):
        context = {"movement_type_id": (movement_type or self.running).pk, "duration_minutes": minutes}
        if distance is not None:
            context["distance_meters"] = distance
        return ingest_activity(self.child, "movement_session", source_id, trigger,
                               occurred_at=at or timezone.now(), context=context)

    def goal(self, **overrides):
        data = {"name": "Run two miles", "metric": "distance", "target": Decimal(2), "unit": "mi",
                "trigger_type": "movement_session", "movement_type_id": self.running.pk,
                "period": "this_week", "repeat_weekly": True, "coin_reward": 7, "xp_reward": 15,
                "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}
        data.update(overrides)
        return create_goal(self.parent, self.child, data)

class AutomaticGoalsTests(_GoalFixture, TestCase):
    def test_idle_child_first_real_activity_gets_fresh_catalog_window(self):
        from apps.movement.services import MovementSessionService
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=timezone.now() - timedelta(days=30))
        definition = self.definition(target=1)
        session = MovementSessionService.log_session(self.child, movement_type=self.running, duration_minutes=20)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))
        self.assertEqual(occurrence.starts_at, session.created_at)
        self.assertEqual(occurrence.ends_at, session.created_at + timedelta(days=7))

    def test_idle_child_first_list_starts_fresh_once_and_never_restarts_expired_window(self):
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=timezone.now() - timedelta(days=30))
        self.definition()
        offered = timezone.now()
        with patch("django.utils.timezone.now", return_value=offered):
            payload = list_goals(self.child)
        occurrence = ChallengeOccurrence.objects.get()
        self.assertEqual((payload["results"][0]["status"], occurrence.starts_at), ("active", offered))
        ends_at = occurrence.ends_at
        set_pin(self.child, payload["results"][0]["id"])
        with patch("django.utils.timezone.now", return_value=offered + timedelta(days=30)):
            self.assertEqual(list_goals(self.child)["results"][0]["status"], "expired")
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.starts_at, occurrence.ends_at), (offered, ends_at))
        self.assertEqual(ChallengeOccurrence.objects.count(), 1)
        self.assertFalse(CoinLedger.objects.exists())

    def test_catalog_added_later_has_own_fresh_window_without_rewriting_paid_history(self):
        first_day = datetime(2026, 10, 1, 18, tzinfo=ZoneInfo("UTC"))
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=first_day)
        with patch("django.utils.timezone.now", return_value=first_day):
            original_definition = self.definition("Original catalog", target=1)
            self.fact("original", at=first_day)
        original = ChallengeOccurrence.objects.get(goal__catalog_definition=original_definition)
        saved = (original.starts_at, original.ends_at, original.reward_receipt, original.awarded_at)
        later = first_day + timedelta(days=30)
        with patch("django.utils.timezone.now", return_value=later):
            added = self.definition("New catalog", target=1)
            self.fact("new-content", at=later)
        new_occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=added)
        self.assertEqual((new_occurrence.progress, new_occurrence.status), (1, "completed"))
        self.assertEqual((new_occurrence.starts_at, new_occurrence.ends_at), (later, later + timedelta(days=7)))
        original.refresh_from_db()
        self.assertEqual((original.starts_at, original.ends_at, original.reward_receipt, original.awarded_at), saved)

    def test_new_child_first_real_saved_activity_counts_without_enrollment_or_get(self):
        from apps.movement.services import MovementSessionService
        ChallengeEnrollment.objects.filter(user=self.child).delete()
        definition = self.definition(target=1)
        source = MovementSessionService.log_session(self.child, movement_type=self.running, duration_minutes=20)
        self.assertEqual(ChallengeEnrollment.objects.get(user=self.child).starts_at, source.created_at)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((occurrence.starts_at, occurrence.progress, occurrence.status),
                         (source.created_at, 1, "completed"))

    def test_pending_source_survives_get_before_retry_with_original_window(self):
        definition = self.definition(target=1)
        accepted_at = timezone.now()
        with patch("django.utils.timezone.now", return_value=accepted_at):
            with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("pending")):
                with self.assertRaises(RuntimeError):
                    self.fact("pending", at=accepted_at)
        self.assertFalse(ChallengeGoal.objects.exists())
        with patch("django.utils.timezone.now", return_value=accepted_at + timedelta(days=1)):
            list_goals(self.child)
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
            self.assertEqual(occurrence.starts_at, accepted_at)
            self.fact("pending", at=accepted_at)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.starts_at, occurrence.progress, occurrence.status),
                         (accepted_at, 1, "completed"))
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="adjustment").count(), 1)

    def test_new_child_failed_first_real_save_then_get_keeps_accepted_cutover(self):
        from apps.movement.services import MovementSessionService
        from apps.quests.activity import retry_pending_activity
        ChallengeEnrollment.objects.filter(user=self.child).delete()
        definition = self.definition(target=1)
        accepted_at = timezone.now()
        with patch("django.utils.timezone.now", return_value=accepted_at):
            with self.assertLogs("apps.quests.activity", level="ERROR"):
                with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("pending")):
                    source = MovementSessionService.log_session(self.child, movement_type=self.running, duration_minutes=20)
        self.assertFalse(ChallengeEnrollment.objects.filter(user=self.child).exists())
        with patch("django.utils.timezone.now", return_value=accepted_at + timedelta(days=1)):
            list_goals(self.child)
            self.assertEqual(ChallengeEnrollment.objects.get(user=self.child).starts_at, source.created_at)
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
            self.assertEqual((occurrence.starts_at, occurrence.progress), (source.created_at, 0))
            self.assertEqual(retry_pending_activity(self.child), 1)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.starts_at, occurrence.progress, occurrence.status),
                         (source.created_at, 1, "completed"))

    def test_pending_sources_before_cutover_or_definition_cannot_anchor_or_credit_new_content(self):
        offered = datetime(2026, 10, 15, 18, tzinfo=ZoneInfo("UTC"))
        cutover = offered - timedelta(days=10)
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=cutover)
        for name, at in (("pre-feature", cutover - timedelta(seconds=1)),
                         ("pre-content", offered - timedelta(seconds=1))):
            ChallengeActivity.objects.create(user=self.child, source_type="movement_session", source_id=name,
                                             trigger_type="movement_session", occurred_at=at, occurred_on=at.date())
        with patch("django.utils.timezone.now", return_value=offered):
            definition = self.definition(target=1)
            list_goals(self.child)
            self.fact("pre-feature", at=cutover - timedelta(seconds=1))
            self.fact("pre-content", at=offered - timedelta(seconds=1))
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
            self.assertEqual((occurrence.starts_at, occurrence.progress), (offered, 0))
            self.fact("new-content", at=offered)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))

    def test_old_badge_unlock_gets_fresh_window_without_pre_unlock_or_processed_history(self):
        offered = datetime(2026, 10, 15, 18, tzinfo=ZoneInfo("UTC"))
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=offered - timedelta(days=90))
        with patch("django.utils.timezone.now", return_value=offered - timedelta(days=60)):
            badge = Badge.objects.create(name="Old catalog unlock", criteria_type="chore_completions")
            definition = self.definition(target=1, required_badge=badge)
        with patch("django.utils.timezone.now", return_value=offered - timedelta(days=30)):
            UserBadge.objects.create(user=self.child, badge=badge)
        for name, days_ago, processed in (("before-unlock", 40, None), ("already-processed", 20, offered)):
            at = offered - timedelta(days=days_ago)
            ChallengeActivity.objects.create(user=self.child, source_type="movement_session", source_id=name,
                                             trigger_type="movement_session", occurred_at=at, occurred_on=at.date(),
                                             processed_at=processed)
        with patch("django.utils.timezone.now", return_value=offered):
            list_goals(self.child)
            self.fact("before-unlock", at=offered - timedelta(days=40))
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
            self.assertEqual((occurrence.starts_at, occurrence.progress), (offered, 0))
            self.fact("after-unlock", at=offered)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.status), (1, "completed"))

    def test_over_limit_pending_plan_cannot_anchor_or_progress_catalog_window(self):
        offered = datetime(2026, 10, 15, 18, tzinfo=ZoneInfo("UTC"))
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=offered - timedelta(days=30))
        with patch("django.utils.timezone.now", return_value=offered - timedelta(days=20)):
            definition = QuestDefinition.objects.create(
                name="Pending capped plans", quest_type="collection", target_value=1, duration_days=7,
                is_system=True, trigger_filter={"allowed_triggers": ["homework_created"]},
            )
        old_at = offered - timedelta(days=15)
        ChallengeActivity.objects.create(user=self.child, source_type="homework_created", source_id="over-limit",
                                         trigger_type="homework_created", occurred_at=old_at, occurred_on=old_at.date(),
                                         context={"catalog_eligible": False})
        with patch("django.utils.timezone.now", return_value=offered):
            list_goals(self.child)
            occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
            self.assertEqual((occurrence.starts_at, occurrence.progress), (offered, 0))
            ingest_activity(self.child, "homework_created", "over-limit", "homework_created", occurred_at=old_at)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.starts_at, occurrence.progress, occurrence.status), (offered, 0, "active"))

    def test_repeatable_legacy_handoff_respects_original_deadline(self):
        offered = timezone.now()
        definition = self.definition(is_repeatable=True)
        deadline = offered + timedelta(days=3)
        legacy = Quest.objects.create(definition=definition, end_date=deadline, current_progress=1, rage_shield=15)
        QuestParticipant.objects.create(user=self.child, quest=legacy, contribution=1)
        list_goals(self.child)
        goal = ChallengeGoal.objects.get(catalog_definition=definition)
        self.assertEqual((goal.starts_at, goal.ends_at), (deadline, deadline + timedelta(days=7)))
        self.fact("too-early", at=offered)
        self.assertFalse(ChallengeOccurrence.objects.exists())
        with patch("django.utils.timezone.now", return_value=deadline):
            self.fact("handoff", at=deadline)
        occurrence = ChallengeOccurrence.objects.get(goal=goal)
        self.assertEqual((occurrence.starts_at, occurrence.progress), (deadline, 1))
        legacy.refresh_from_db()
        self.assertEqual((legacy.current_progress, legacy.rage_shield, legacy.end_date), (1, 15, deadline))

    def test_boss_what_counts_omits_actions_that_deal_no_damage(self):
        definition = self.definition(quest_type="boss")
        definition.trigger_filter = {}
        definition.save(update_fields=["trigger_filter"])
        payload = list_goals(self.child)["results"][0]
        self.assertEqual(payload["metric"], "damage")
        self.assertNotIn("logged creations", payload["what_counts"])
        self.assertIn("approved homework", payload["what_counts"])
        self.assertIn("planned homework (first per day)", payload["what_counts"])
        self.assertIn("positive habit taps", payload["what_counts"])

    def test_reward_preview_and_payout_keep_accepted_snapshot_after_support_retirement(self):
        from apps.pets.models import PetSpecies
        from apps.quests.models import QuestRewardItem
        from apps.rpg.models import ItemDefinition, UserInventory
        species = PetSpecies.objects.create(slug="preview-wolf", name="Synthetic Wolf", sprite_key="preview-wolf")
        egg = ItemDefinition.objects.create(slug="preview-wolf-egg", name="Synthetic Wolf Egg", item_type="egg", pet_species=species)
        definition = self.definition()
        QuestRewardItem.objects.create(quest_definition=definition, item=egg)
        policy = {"schema_version": 1, "potion_slugs": ["base"], "disabled_item_types": [],
                  "pets": [{"species_slug": "preview-wolf", "sprite_key": "preview-wolf", "potion_slugs": ["base"]}]}
        with self.settings(RPG_ASSET_SUPPORT_POLICY=policy):
            first = list_goals(self.child)["results"][0]
        occurrence = ChallengeOccurrence.objects.get()
        snapshot = occurrence.snapshot
        self.assertEqual(first["rewards"]["items"][0]["item_name"], egg.name)
        self.assertEqual(snapshot["items"][0]["item_id"], egg.pk)
        # The default registry no longer offers the synthetic wolf, while the
        # accepted window keeps the preview and exact original item promise.
        expected_item = {**first["rewards"]["items"][0], "item_catalog_available": False}
        self.assertEqual(list_goals(self.child)["results"][0]["rewards"]["items"], [expected_item])
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, snapshot)
        self.fact("first")
        self.fact("second")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.reward_receipt, {"coins": 5, "xp": 10, "items": [expected_item]})
        self.fact("third")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 1)
    def test_approval_after_cutoff_counts_catalog_and_keeps_performed_week(self):
        from apps.chores.models import Chore, ChoreCompletion
        from apps.chores.services import ChoreService
        boundary = datetime(2026, 10, 14, 18, tzinfo=ZoneInfo("UTC"))
        performed_at = boundary - timedelta(days=2)
        performed_day = performed_at.astimezone(ZoneInfo("America/Phoenix")).date()
        ChallengeEnrollment.objects.filter(user=self.child).update(starts_at=boundary)
        with patch("django.utils.timezone.now", return_value=boundary):
            # Definition creation is an eligibility cutoff too. Keep it on
            # the fixture clock so a later real test run cannot skip approval.
            definition = QuestDefinition.objects.create(
                name="Fresh approvals", description="An approved chore", is_system=True,
                quest_type="collection", target_value=1, duration_days=7, coin_reward=5,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            list_goals(self.child)
            parent_goal = self.goal(name="This week's chores", metric="count", target=Decimal(2), unit="actions",
                                    trigger_type="chore_complete", movement_type_id=None, repeat_weekly=False,
                                    coin_reward=0, xp_reward=0, skill_tags=[])
            chore = Chore.objects.create(title="Dishes", family=self.family.family, created_by=self.parent,
                                         reward_amount=0, coin_reward=0)
            completion = ChoreCompletion.objects.create(
                chore=chore, user=self.child, completed_date=performed_day,
                reward_amount_snapshot=0, coin_reward_snapshot=0,
            )
        ChoreCompletion.objects.filter(pk=completion.pk).update(created_at=performed_at)
        with patch("django.utils.timezone.now", return_value=boundary + timedelta(hours=1)):
            ChoreService.approve_completion(completion, self.parent)
        completion.refresh_from_db()
        fact = ChallengeActivity.objects.get(user=self.child, source_type="chore_complete")
        self.assertEqual(fact.occurred_at, completion.decided_at)
        self.assertEqual(fact.occurred_on, performed_day)
        catalog = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertEqual((catalog.progress, catalog.status), (1, "completed"))
        parent_goal.refresh_from_db()
        self.assertEqual((parent_goal.progress, parent_goal.status), (1, "active"))

    def test_persisted_private_journal_fact_and_receipt_never_copy_content(self):
        from apps.chronicle.models import ChronicleEntry
        from apps.quests.activity import record_activity, resolve_activity
        private_title, private_body = "PRIVATE TITLE SENTINEL", "PRIVATE BODY SENTINEL"
        QuestDefinition.objects.create(name="Journal progress", description="Two entries", is_system=True,
                                       quest_type="collection", target_value=2, duration_days=7,
                                       trigger_filter={"allowed_triggers": ["journal_entry"]})
        entry = ChronicleEntry.objects.create(
            user=self.child, kind="journal", occurred_on=timezone.localdate(), chapter_year=2026,
            title=private_title, summary=private_body, metadata={"body": private_body}, is_private=True,
        )
        self.assertIsNone(resolve_activity(self.parent, "journal_entry", {"entry_id": entry.pk}))
        self.assertIsNone(resolve_activity(self.family.children[1], "journal_entry", {"entry_id": entry.pk}))
        record_activity(self.child, "journal_entry", {"entry_id": entry.pk, "body": private_body})
        fact = ChallengeActivity.objects.get(user=self.child, source_type="journal_entry")
        self.assertEqual(ChallengeOccurrence.objects.get().progress, 1)
        public_context = json.dumps(fact.context)
        public_list = json.dumps(list_goals(self.child))
        for secret in (private_title, private_body):
            self.assertNotIn(secret, public_context)
            self.assertNotIn(secret, public_list)
    def test_weekly_pin_follows_same_goal_without_replaying_rewards(self):
        first = self.goal()
        original_id = f"goal:{first.pk}"
        set_pin(self.child, original_id)
        self.fact("first-week", distance="3218.688")
        with patch("apps.quests.goals.timezone.now", return_value=first.ends_at + timedelta(hours=1)):
            payload = list_goals(self.child)
        successor = ChallengeOccurrence.objects.get(goal=first.goal, starts_at=first.ends_at)
        self.assertEqual(payload["pin"], f"goal:{successor.pk}")
        self.assertEqual((successor.status, successor.progress), ("active", 0))
        self.assertEqual(ChallengePin.objects.get(user=self.child).occurrence_id, successor.pk)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        # An offline unpin of the previous window clears the same ongoing goal.
        self.assertEqual(set_pin(self.child, original_id, clear=True), {"pin": None})
    def test_parent_read_enrolls_own_catalog_without_awarding_or_enrolling_other_members(self):
        definition = self.definition()
        payload = list_goals(self.parent)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["progress"], "0")
        self.assertTrue(ChallengeGoal.objects.filter(user=self.parent, catalog_definition=definition).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.parent).exists())
        self.assertFalse(ChallengeGoal.objects.filter(user=self.family.children[1]).exists())
    def test_locked_skill_does_not_invent_xp_in_paid_receipt(self):
        self.skill.is_locked_by_default = True
        self.skill.save(update_fields=["is_locked_by_default"])
        self.definition(target=1)
        self.fact("complete")
        self.assertEqual(ChallengeOccurrence.objects.get().reward_receipt["xp"], 0)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 0)
    def test_account_deletion_removes_owned_goal_facts_and_contributions(self):
        self.definition()
        self.fact("first")
        self.child.delete()
        self.assertFalse(ChallengeActivity.objects.exists())
        self.assertFalse(ChallengeContribution.objects.exists())
    def test_first_new_activity_counts_before_any_screen_is_opened(self):
        ChallengeEnrollment.objects.filter(user=self.child).delete()
        self.definition()
        self.fact("first")
        self.assertEqual(ChallengeOccurrence.objects.get().progress, 1)

    def test_catalog_snapshot_and_boss_target_do_not_change_with_template_or_idle_time(self):
        definition = self.definition(quest_type="boss", target=16)
        self.fact("first")
        definition.target_value, definition.coin_reward = 800, 900
        definition.save()
        self.fact("second")
        occurrence = ChallengeOccurrence.objects.get()
        self.assertEqual((occurrence.status, occurrence.snapshot["target"]), ("completed", "16.000"))
        self.assertEqual(occurrence.reward_receipt["coins"], 5)

    def test_unsupported_reward_only_catalog_rule_is_not_presented_as_new_goal(self):
        QuestDefinition.objects.create(name="Perfect Arc", description="Ten Perfect Days", is_system=True,
                                       quest_type="collection", target_value=10, trigger_filter={"allowed_triggers": ["perfect_day"]})
        self.assertEqual(list_goals(self.child)["results"], [])

    def test_all_matching_catalog_goals_progress_independently_of_pin_and_pay_once(self):
        self.definition()
        self.definition("Another matching goal")
        rows = list_goals(self.child)["results"]
        set_pin(self.child, rows[0]["id"])
        self.fact("one")
        result = self.fact("two")
        self.assertEqual(len(result["goals"]), 2)
        self.assertTrue(all(receipt["completed"] for receipt in result["goals"]))
        self.assertEqual(sum(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 20)
        replay = self.fact("two")
        self.assertEqual(replay["goals"], [])
        set_pin(self.child, rows[0]["id"], clear=True)
        list_goals(self.child)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 2)
        self.assertEqual(ChallengeContribution.objects.count(), 4)

    def test_two_partial_distances_sum_only_matching_running_and_window(self):
        occurrence = self.goal()
        self.fact("cycle", distance="4000", movement_type=self.cycling)
        self.fact("missing")
        self.fact("run-one", distance="1207.008")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, Decimal("0.75"))
        self.fact("prior-week", at=occurrence.starts_at - timedelta(seconds=1), distance="4000")
        self.fact("run-two", distance="2011.680")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, Decimal(2))
        self.assertEqual(occurrence.status, "completed")
        self.assertEqual(occurrence.reward_receipt["coins"], 7)
        self.assertEqual(occurrence.reward_receipt["xp"], 15)

    def test_next_family_week_has_distinct_occurrence_and_one_payout(self):
        self.family.family.timezone = "America/New_York"
        self.family.family.save(update_fields=["timezone"])
        self.child.family = self.family.family
        with patch("apps.quests.goals.timezone.now", return_value=datetime(2026, 10, 28, 12, tzinfo=ZoneInfo("UTC"))):
            occurrence = self.goal()
        self.assertEqual(occurrence.starts_at.astimezone(ZoneInfo("America/New_York")).weekday(), 0)
        self.fact("weekone", at=occurrence.starts_at + timedelta(days=1), distance="3218.688")
        self.fact("weektwo", at=occurrence.ends_at, distance="3218.688")
        occurrences = list(ChallengeOccurrence.objects.filter(goal=occurrence.goal).order_by("starts_at"))
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(occurrences[1].starts_at, occurrence.ends_at)
        self.assertEqual(occurrences[1].ends_at.astimezone(ZoneInfo("America/New_York")).hour, 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 2)

    def test_explicit_midweek_goal_counts_prior_recorded_facts_but_catalog_does_not_backfill(self):
        self.fact("earlier", distance="1207.008")
        occurrence = self.goal()
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, Decimal("0.75"))
        self.definition()
        list_goals(self.child)
        catalog = ChallengeOccurrence.objects.get(goal__catalog_definition__isnull=False)
        self.assertEqual(catalog.progress, 0)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_void_removes_only_unpaid_contributions_and_never_rearms_paid_goal(self):
        self.definition()
        self.fact("first")
        occurrence = ChallengeOccurrence.objects.get()
        void_activity(self.child, "movement_session", "first")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.progress, 0)
        self.fact("second")
        self.fact("third")
        void_activity(self.child, "movement_session", "third")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, "completed")
        self.fact("fourth")
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_failed_payout_rolls_back_progress_and_keeps_durable_fact_retryable(self):
        self.definition(target=1)
        with patch("apps.achievements.services.AwardService.grant", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                self.fact("retry")
        activity = ChallengeActivity.objects.get()
        self.assertIsNone(activity.processed_at)
        self.assertFalse(ChallengeContribution.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        result = self.fact("retry")
        self.assertTrue(result["goals"][0]["completed"])
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_legacy_active_is_pinned_preserved_and_not_duplicated(self):
        definition = self.definition()
        legacy = Quest.objects.create(definition=definition, end_date=self.now + timedelta(days=3), current_progress=1, rage_shield=15)
        QuestParticipant.objects.create(user=self.child, quest=legacy, contribution=1)
        result = list_goals(self.child)
        self.assertEqual(result["pin"], f"legacy:{legacy.pk}")
        self.assertEqual(len(result["results"]), 1)
        self.fact("new")
        self.assertFalse(ChallengeOccurrence.objects.exists())
        legacy.refresh_from_db()
        self.assertEqual((legacy.current_progress, legacy.rage_shield, legacy.status), (1, 15, "active"))

    def test_legacy_completed_nonrepeatable_is_never_awarded_again(self):
        definition = self.definition(target=1)
        legacy = Quest.objects.create(definition=definition, status="completed", end_date=self.now, current_progress=1)
        QuestParticipant.objects.create(user=self.child, quest=legacy, contribution=1)
        self.fact("new")
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_badge_gate_requires_actual_earned_badge(self):
        badge = Badge.objects.create(name="Gate", criteria_type="chore_completions", criteria_value={"count": 2})
        self.definition(required_badge=badge)
        self.fact("before")
        self.assertFalse(ChallengeGoal.objects.exists())
        UserBadge.objects.create(user=self.child, badge=badge)
        self.fact("after", at=timezone.now() + timedelta(seconds=1))
        self.assertEqual(ChallengeOccurrence.objects.get().progress, 1)

    def test_context_keeps_no_private_journal_content(self):
        result = ingest_activity(self.child, "journal_entry", "entry", "journal_entry", context={"notes": "private", "body": "private", "skill_tags": []})
        self.assertEqual(result["activity"].context, {"skill_tags": []})


class GoalApiTests(_GoalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.payload = {"user_id": self.child.pk, "name": "Run two miles", "metric": "distance", "target": "2",
                        "unit": "mi", "trigger_type": "movement_session", "movement_type_id": self.running.pk,
                        "period": "this_week", "repeat_weekly": True, "coin_reward": 7, "xp_reward": 15,
                        "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}

    def test_parent_creates_and_child_pins_without_rewards(self):
        response = self.client.post("/api/challenges/goals/", self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["target"], "2")
        self.assertEqual(response.data["action"]["movement_type_id"], self.running.pk)
        self.client.force_authenticate(self.child)
        goal_id = response.data["id"]
        self.assertEqual(self.client.post(f"/api/challenges/{goal_id}/pin/").data, {"pin": goal_id})
        listed = self.client.get("/api/challenges/")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["pin"], goal_id)
        self.assertFalse(CoinLedger.objects.exists())
        self.assertEqual(self.client.delete(f"/api/challenges/{goal_id}/pin/").data, {"pin": None})

    def test_goal_response_keeps_period_and_real_recorded_completion_timestamp(self):
        created = self.client.post("/api/challenges/goals/", self.payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data["completed_at"])
        occurrence = ChallengeOccurrence.objects.get(pk=created.data["id"].split(":")[1])
        starts_at, ends_at = occurrence.starts_at, occurrence.ends_at
        recorded_at = ends_at + timedelta(days=1)
        performed_at = ends_at - timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=recorded_at):
            self.fact("late-approved-run", at=performed_at, distance="3218.688")
            # Completion recognition and reward delivery are separate stored
            # timestamps; the new field must not alias the reward receipt.
            awarded_at = recorded_at + timedelta(hours=1)
            ChallengeOccurrence.objects.filter(pk=occurrence.pk).update(awarded_at=awarded_at)
            response = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        saved = next(row for row in response.data["results"] if row["id"] == created.data["id"])
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["starts_at"], starts_at.isoformat())
        self.assertEqual(saved["ends_at"], ends_at.isoformat())
        self.assertEqual(saved["completed_at"], recorded_at.isoformat())
        self.assertEqual(saved["reward_receipt"]["awarded_at"], awarded_at.isoformat())
        receipt = next(row for row in response.data["recent_receipts"] if row["id"] == saved["id"])
        self.assertEqual(receipt["completed_at"], recorded_at.isoformat())

    def test_missed_week_remains_history_and_next_cycle_keeps_saved_zone_across_dst(self):
        family = self.family.family
        family.timezone = "America/New_York"
        family.save(update_fields=["timezone"])
        self.child.family = family
        offered_at = datetime(2026, 10, 28, 16, 15, tzinfo=ZoneInfo("UTC"))
        with patch("django.utils.timezone.now", return_value=offered_at):
            occurrence = self.goal()
        self.assertEqual(occurrence.starts_at, datetime(2026, 10, 26, 4, tzinfo=ZoneInfo("UTC")))
        self.assertEqual(occurrence.ends_at, datetime(2026, 11, 2, 5, tzinfo=ZoneInfo("UTC")))

        # Updating today's household zone must not change an accepted goal's
        # weekly clock or erase the prior, incomplete period.
        family.timezone = "Pacific/Auckland"
        family.save(update_fields=["timezone"])
        with patch("django.utils.timezone.now", return_value=occurrence.ends_at):
            response = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        rows = sorted(response.data["results"], key=lambda row: row["starts_at"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "expired")
        self.assertEqual(rows[0]["progress"], "0")
        self.assertIsNone(rows[0]["completed_at"])
        self.assertEqual(rows[1]["status"], "active")
        self.assertEqual(datetime.fromisoformat(rows[1]["starts_at"]), occurrence.ends_at)
        self.assertEqual(rows[1]["ends_at"], datetime(2026, 11, 9, 5, tzinfo=ZoneInfo("UTC")).isoformat())
        self.assertTrue(all(row["timezone"] == "America/New_York" for row in rows))
        self.assertTrue(all(row["completed_at"] is None for row in rows))
        self.assertEqual(response.data["recent_receipts"], [])
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_rolling_catalog_cycle_keeps_saved_wall_clock_across_dst_and_zone_change(self):
        ChallengeEnrollment.objects.filter(user=self.child).update(timezone_name="America/New_York")
        definition = self.definition(is_repeatable=True)
        offered_at = datetime(2026, 10, 28, 16, 15, tzinfo=ZoneInfo("UTC"))
        with patch("django.utils.timezone.now", return_value=offered_at):
            first = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        original = first.data["results"][0]
        self.assertEqual(original["ends_at"], datetime(2026, 11, 4, 17, 15, tzinfo=ZoneInfo("UTC")).isoformat())

        family = self.family.family
        family.timezone = "Pacific/Auckland"
        family.save(update_fields=["timezone"])
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 4, 17, 15, tzinfo=ZoneInfo("UTC"))):
            response = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        rows = sorted(response.data["results"], key=lambda row: row["starts_at"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "expired")
        self.assertEqual(rows[1]["starts_at"], original["ends_at"])
        self.assertEqual(rows[1]["ends_at"], datetime(2026, 11, 11, 17, 15, tzinfo=ZoneInfo("UTC")).isoformat())
        self.assertTrue(all(row["timezone"] == "America/New_York" for row in rows))
        self.assertTrue(all(row["completed_at"] is None for row in rows))
        self.assertEqual(ChallengeOccurrence.objects.filter(goal__catalog_definition=definition).count(), 2)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_legacy_completed_goal_has_no_invented_completion_timestamp(self):
        definition = self.definition()
        legacy = Quest.objects.create(
            definition=definition, status="completed", end_date=self.now, current_progress=2,
        )
        QuestParticipant.objects.create(user=self.child, quest=legacy, contribution=2)
        response = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        saved = next(row for row in response.data["results"] if row["id"] == f"legacy:{legacy.pk}")
        self.assertIsNone(saved["completed_at"])

    def test_cross_family_children_unknown_children_and_pin_targets_are_indistinguishable(self):
        outsider = make_family("Other goals", children=[{"username": "goaloutsider"}]).children[0]
        payload = {**self.payload, "user_id": outsider.pk}
        foreign = self.client.post("/api/challenges/goals/", payload, format="json")
        missing = self.client.post("/api/challenges/goals/", {**payload, "user_id": 999999}, format="json")
        self.assertEqual((foreign.status_code, foreign.data), (missing.status_code, missing.data))
        self.assertEqual(foreign.status_code, 404)
        own = self.client.post("/api/challenges/goals/", self.payload, format="json")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post(f"/api/challenges/{own.data['id']}/pin/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/challenges/?user_id={self.child.pk}").status_code, 404)

    def test_child_cannot_author_goals(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.post("/api/challenges/goals/", self.payload, format="json").status_code, 403)

    def test_invalid_metric_activity_tags_and_windows_leave_no_goal(self):
        variants = [
            {"trigger_type": "chore_complete"}, {"unit": "minutes"},
            {"metric": "count", "unit": "actions", "target": "0.5"},
            {"skill_tags": []}, {"period": "custom"},
            {"period": "from_today", "repeat_weekly": True},
            {"coop_user_ids": [self.child.pk, self.family.children[1].pk]},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                response = self.client.post("/api/challenges/goals/", {**self.payload, **variant}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_parent_request_retry_preserves_one_paid_goal_and_rejects_changed_details(self):
        self.fact("existing-run", distance="3218.688")
        payload = {**self.payload, "request_id": str(uuid4())}
        first = self.client.post("/api/challenges/goals/", payload, format="json")
        second = self.client.post("/api/challenges/goals/", payload, format="json")
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        conflict = self.client.post("/api/challenges/goals/", {**payload, "target": "1"}, format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_future_custom_goal_is_visible_immediately_without_payout(self):
        today = timezone.localdate()
        payload = {**self.payload, "period": "custom", "repeat_weekly": False,
                   "start_date": str(today + timedelta(days=2)), "end_date": str(today + timedelta(days=8))}
        created = self.client.post("/api/challenges/goals/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], "upcoming")
        listed = self.client.get(f"/api/challenges/?user_id={self.child.pk}")
        self.assertIn(created.data["id"], [row["id"] for row in listed.data["results"]])
        self.assertFalse(CoinLedger.objects.exists())
