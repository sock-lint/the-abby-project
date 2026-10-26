"""Two reviewed future policies never rewrite an accepted challenge promise."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as datetime_timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml

from django.conf import settings
from django.db import transaction
from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory
from apps.quests import reconciliation
from apps.quests.goals import _occurrence, _occurrence_window, ingest_activity
from apps.quests.models import (
    ChallengeContribution, ChallengeGoal, ChallengeOccurrence, ChallengePin, Quest, QuestDefinition,
    QuestParticipant, QuestRewardItem, QuestSkillTag,
)
from apps.quests.queries import active_system_definitions
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPackError
from apps.rpg.models import ContentPackPublication, ItemDefinition, UserInventory
from config.tests.factories import make_family


OLD_COMEBACK_DESCRIPTION = (
    "Rebuild momentum with 3 positive habit taps during this seven-day challenge. "
    "Available even without a streak reset."
)


def make_policy_pair(actor, name):
    """Real bundled fields/links, synthetic identities, legacy owner provenance.

    Shared with actual MCP transport tests so they exercise the same supported
    pair rather than a weaker invented policy with omitted tags or rewards.
    """
    directory = Path(settings.BASE_DIR) / "content/rpg/initial"
    entry = next(row for row in yaml.safe_load((directory / "quests.yaml").read_text())["quests"]
                 if row["name"] == name)
    canonical_values = {key: deepcopy(value) for key, value in entry.items()
                        if key not in {"reward_items", "skill_tags"}}
    source_values = {**deepcopy(canonical_values), "trigger_filter": {"allowed_triggers": ["habit_log"]},
                     "coin_reward": 10 if name == "Daily Rituals" else 40}
    if name == "Comeback Kid":
        source_values["description"] = OLD_COMEBACK_DESCRIPTION
    source = QuestDefinition.objects.create(**source_values, created_by=actor)
    canonical = QuestDefinition.objects.create(**canonical_values)
    items = {row["slug"]: row for row in yaml.safe_load((directory / "items.yaml").read_text())["items"]}
    for definition, rewards in ((source, [{"slug": "pouch-small", "quantity": 1}] if name == "Daily Rituals"
                                 else entry["reward_items"]), (canonical, entry["reward_items"])):
        for reward in rewards:
            row = deepcopy(items[reward["slug"]])
            slug = row.pop("slug")
            item, _ = ItemDefinition.objects.get_or_create(slug=slug, defaults=row)
            QuestRewardItem.objects.create(quest_definition=definition, item=item, quantity=reward["quantity"])
        for tag in entry["skill_tags"]:
            category_name, skill_name = tag["skill"].split("::", 1)
            category, _ = SkillCategory.objects.get_or_create(name=category_name)
            skill, _ = Skill.objects.get_or_create(category=category, name=skill_name)
            QuestSkillTag.objects.create(quest_definition=definition, skill=skill, xp_weight=tag["weight"])
    return source, canonical


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PolicyReconciliationTests(TestCase):
    anchor = datetime(2026, 10, 1, 12, tzinfo=datetime_timezone.utc)

    def setUp(self):
        own = make_family("Policy authors", parents=[{"username": "policy-author", "is_staff": True}],
                          children=[{"username": "policy-child"}])
        self.actor, self.child = own.parents[0], own.children[0]
        own.family.timezone = "UTC"
        own.family.save(update_fields=["timezone"])
        self.now = self.anchor + timedelta(days=20)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        drops = patch("apps.rpg.services.DropService.award_accomplishment", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def preview(self, source, canonical, request_id=None):
        return reconciliation.preview_reconciliation(self.actor, source.pk, canonical.pk, request_id or uuid4())

    def publish(self, preview, *, policy=True):
        options = {"acknowledge_policy_transition": True} if policy else {}
        return reconciliation.publish_reconciliation(self.actor, preview["preview_id"],
                                                       preview["content_digest"], **options)

    def goal(self, definition, *, start=None, opened=True):
        start = start or self.anchor
        if definition.created_at > start:
            QuestDefinition.objects.filter(pk=definition.pk).update(created_at=start-timedelta(days=1))
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, is_catalog=True, catalog_definition=definition,
            name=definition.name, description=definition.description, metric="count", target=definition.target_value,
            unit="active days" if definition.trigger_filter.get("distinct_active_days") else "actions",
            trigger_filter=deepcopy(definition.trigger_filter), timezone_name=self.child.family.timezone,
            starts_at=start, ends_at=start + timedelta(days=definition.duration_days),
            repeat_days=definition.duration_days, coin_reward=definition.coin_reward, xp_reward=definition.xp_reward,
            skill_tags=[{"skill_id": row.skill_id, "xp_weight": row.xp_weight} for row in definition.skill_tags.all()],
            reward_items=[{"item_id": row.item_id, "quantity": row.quantity} for row in definition.reward_items.all()],
        )
        if opened:
            _occurrence(goal, start)
        return goal

    def fact(self, key, at):
        return ingest_activity(self.child, "policy-reconciliation-test", key, "habit_log", occurred_at=at)

    def amounts(self):
        return list(CoinLedger.objects.filter(user=self.child).order_by("pk").values_list("amount", flat=True))

    def test_daily_rituals_policy_preview_reports_the_exact_reviewed_transition(self):
        source, canonical = make_policy_pair(self.actor, "Daily Rituals")
        preview = self.preview(source, canonical)
        self.assertTrue(preview["requires_policy_acknowledgement"])
        self.assertFalse(preview["requires_cooperative_acknowledgement"])
        self.assertEqual({row["field"] for row in preview["differences"]},
                         {"coin_reward", "trigger_filter", "reward_items"})
        self.assertEqual((preview["source_definition"]["coin_reward"],
                          preview["canonical_definition"]["coin_reward"]), (10, 2))
        source.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)

    def test_comeback_policy_preview_reports_distinct_days_and_old_new_coin_promises(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        preview = self.preview(source, canonical)
        self.assertTrue(preview["requires_policy_acknowledgement"])
        self.assertEqual({row["field"] for row in preview["differences"]},
                         {"description", "coin_reward", "trigger_filter"})
        self.assertEqual((preview["source_definition"]["coin_reward"],
                          preview["canonical_definition"]["coin_reward"]), (40, 10))
        self.assertEqual(preview["canonical_definition"]["trigger_filter"], {
            "allowed_triggers": ["habit_log"], "reward_policy_version": 2, "distinct_active_days": True,
        })
        self.assertEqual(preview["source_definition"]["reward_items"],
                         preview["canonical_definition"]["reward_items"])

    def test_policy_acknowledgement_is_strict_required_and_required_again_on_replay(self):
        source, canonical = make_policy_pair(self.actor, "Daily Rituals")
        preview = self.preview(source, canonical)
        for value in (False, None, 1, "true"):
            with self.subTest(value=value):
                with self.assertRaises(ContentPackError):
                    reconciliation.publish_reconciliation(self.actor, preview["preview_id"], preview["content_digest"],
                                                           acknowledge_policy_transition=value)
                source.refresh_from_db()
                self.assertIsNone(source.superseded_by_id)
        published = self.publish(preview)
        self.assertTrue(published["acknowledged_policy_transition"])
        self.assertFalse(published["acknowledged_cooperative_transition"])
        with self.assertRaises(ContentPackError):
            reconciliation.publish_reconciliation(self.actor, preview["preview_id"], preview["content_digest"])
        self.assertEqual(self.publish(preview), published)
        self.assertEqual(self.amounts(), [])
        self.assertFalse(UserInventory.objects.exists())

    def test_policy_receipt_recovery_is_immutable_and_catalog_drift_still_requires_new_review(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        request_id = uuid4()
        preview = self.preview(source, canonical, request_id)
        published = self.publish(preview)
        QuestDefinition.objects.filter(pk=canonical.pk).update(description="A later editorial revision")
        self.assertEqual(self.preview(source, canonical, request_id), preview)
        self.assertEqual(reconciliation.get_reconciliation(self.actor, preview["preview_id"]), published)
        self.assertEqual(self.publish(preview), published)
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_existing_window_progress_contributions_pin_legacy_and_provenance_remain_exact(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        goal = self.goal(source)
        accepted = goal.occurrences.get()
        self.fact("accepted-first", self.anchor + timedelta(hours=1))
        pin, _ = ChallengePin.objects.update_or_create(user=self.child,
                                                      defaults={"occurrence": accepted, "legacy_quest": None})
        legacy = Quest.objects.create(definition=source, start_date=self.anchor, end_date=goal.ends_at,
                                      current_progress=1, reward_items_snapshot=None)
        QuestParticipant.objects.create(quest=legacy, user=self.child, contribution=1)
        goal_before = ChallengeGoal.objects.filter(pk=goal.pk).values().get()
        window_before = ChallengeOccurrence.objects.filter(pk=accepted.pk).values().get()
        legacy_before = Quest.objects.filter(pk=legacy.pk).values().get()
        source_before = QuestDefinition.objects.filter(pk=source.pk).values().get()
        canonical_before = QuestDefinition.objects.filter(pk=canonical.pk).values().get()
        contributions = list(ChallengeContribution.objects.values())
        self.publish(self.preview(source, canonical))
        self.assertEqual(ChallengeGoal.objects.filter(pk=goal.pk).values().get(),
                         {**goal_before, "catalog_definition_id": canonical.pk})
        self.assertEqual(QuestDefinition.objects.filter(pk=source.pk).values().get(),
                         {**source_before, "superseded_by_id": canonical.pk})
        self.assertEqual(QuestDefinition.objects.filter(pk=canonical.pk).values().get(), canonical_before)
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=accepted.pk).values().get(), window_before)
        self.assertEqual(Quest.objects.filter(pk=legacy.pk).values().get(), legacy_before)
        self.assertEqual(list(ChallengeContribution.objects.values()), contributions)
        pin.refresh_from_db()
        self.assertEqual(pin.occurrence_id, accepted.pk)
        self.assertEqual(self.amounts(), [])
        goal.refresh_from_db()
        future = _occurrence(goal, accepted.ends_at + timedelta(hours=1))
        self.assertEqual((future.snapshot["coins"], future.snapshot["filter"].get("distinct_active_days")), (10, True))
        self.assertEqual((future.starts_at, future.ends_at), (accepted.ends_at, accepted.ends_at+timedelta(days=7)))
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=accepted.pk).values().get(), window_before)

    def test_daily_rituals_pays_old_pouch_once_then_future_cycle_has_two_coins_and_no_pouch(self):
        source, canonical = make_policy_pair(self.actor, "Daily Rituals")
        goal = self.goal(source)
        accepted = goal.occurrences.get()
        saved = deepcopy(accepted.snapshot)
        self.publish(self.preview(source, canonical))
        for index in range(3):
            self.fact(f"old-daily-{index}", self.anchor + timedelta(hours=1))
        accepted.refresh_from_db()
        self.assertEqual((accepted.snapshot, accepted.reward_receipt["coins"]), (saved, 10))
        pouch = ItemDefinition.objects.get(slug="pouch-small")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)
        for index in range(3):
            self.fact(f"next-daily-{index}", accepted.ends_at + timedelta(hours=1))
        future = goal.occurrences.get(starts_at=accepted.ends_at)
        self.assertEqual((future.snapshot["coins"], future.snapshot["items"], future.reward_receipt["coins"]),
                         (2, [], 2))
        self.fact("next-daily-2", accepted.ends_at + timedelta(hours=1))
        self.assertEqual(self.amounts(), [10, 2])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=pouch).quantity, 1)

    def test_comeback_old_three_taps_pay_forty_but_future_three_days_pay_ten(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        goal = self.goal(source)
        accepted = goal.occurrences.get()
        saved = deepcopy(accepted.snapshot)
        self.publish(self.preview(source, canonical))
        for index in range(3):
            self.fact(f"old-comeback-{index}", self.anchor + timedelta(hours=1))
        accepted.refresh_from_db()
        self.assertEqual((accepted.snapshot, accepted.reward_receipt["coins"]), (saved, 40))
        start = accepted.ends_at
        for index in range(3):
            self.fact(f"same-day-{index}", start + timedelta(hours=1))
        future = goal.occurrences.get(starts_at=start)
        self.assertEqual((future.progress, future.status, future.snapshot["unit"]), (1, "active", "active days"))
        self.assertEqual(self.amounts(), [40])
        self.fact("second-day", start + timedelta(days=1, hours=1))
        self.fact("third-day", start + timedelta(days=2, hours=1))
        future.refresh_from_db()
        self.assertEqual((future.progress, future.reward_receipt["coins"]), (3, 10))
        self.assertEqual(self.amounts(), [40, 10])
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="streak-freeze").quantity, 2)

    def test_unopened_policy_cycle_zero_is_saved_even_when_ended_without_paying_on_publish(self):
        source, canonical = make_policy_pair(self.actor, "Daily Rituals")
        goal = self.goal(source, opened=False)
        self.publish(self.preview(source, canonical))
        window = goal.occurrences.get()
        self.assertEqual((window.starts_at, window.ends_at, window.snapshot["coins"]),
                         (self.anchor, goal.ends_at, 10))
        self.assertEqual(window.snapshot["filter"], {"allowed_triggers": ["habit_log"]})
        self.assertEqual(len(window.snapshot["items"]), 1)
        self.assertIsNone(window.awarded_at)
        self.assertEqual(window.progress, 0)
        self.assertEqual(self.amounts(), [])
        self.assertFalse(UserInventory.objects.exists())

    def test_policy_overlap_retains_old_cycle_zero_and_no_future_alias_cycle(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        old = self.goal(source, opened=False)
        other = self.goal(canonical, start=self.now, opened=False)
        old_before = ChallengeGoal.objects.filter(pk=old.pk).values().get()
        other_before = ChallengeGoal.objects.filter(pk=other.pk).values().get()
        self.publish(self.preview(source, canonical))
        self.assertEqual(ChallengeGoal.objects.filter(pk=old.pk).values().get(), old_before)
        self.assertEqual(ChallengeGoal.objects.filter(pk=other.pk).values().get(), other_before)
        self.assertEqual(old.occurrences.get().snapshot["coins"], 40)
        self.assertFalse(other.occurrences.exists())
        for index in range(3):
            self.fact(f"old-overlap-{index}", self.anchor + timedelta(hours=1))
        self.assertEqual(self.amounts(), [40])
        self.assertIsNone(_occurrence(old, self.now + timedelta(days=1)))
        self.assertEqual(list(active_system_definitions().values_list("pk", flat=True)), [canonical.pk])

    def test_unopened_repeated_hour_cycle_zero_keeps_old_policy_with_pre_anchor_history(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        self.child.family.timezone = "America/Denver"
        self.child.family.save(update_fields=["timezone"])
        anchor = datetime(2026, 11, 1, 7, 30, tzinfo=ZoneInfo("UTC"))
        old = self.goal(source, start=anchor, opened=False)
        self.goal(canonical, start=anchor+timedelta(days=30), opened=False)
        ChallengeOccurrence.objects.create(goal=old, starts_at=anchor-timedelta(days=7), ends_at=anchor,
                                           snapshot={"coins": 40, "filter": deepcopy(source.trigger_filter)})
        visit = anchor + timedelta(minutes=40)  # Second-pass 01:10 after first-pass 01:30.
        with patch("django.utils.timezone.now", return_value=visit):
            self.publish(self.preview(source, canonical))
            for index in range(3):
                self.fact(f"repeated-hour-{index}", visit)
        accepted = old.occurrences.get(starts_at=anchor)
        expected_start, expected_end = _occurrence_window(old, anchor)
        self.assertEqual((accepted.starts_at, accepted.ends_at),
                         (expected_start.astimezone(datetime_timezone.utc), expected_end.astimezone(datetime_timezone.utc)))
        self.assertEqual((accepted.snapshot["coins"], accepted.snapshot["filter"], accepted.reward_receipt["coins"]),
                         (40, source.trigger_filter, 40))
        self.assertEqual(self.amounts(), [40])

    def test_only_the_finite_reviewed_policy_values_and_matching_other_fields_are_allowed(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        cases = [
            ("coins", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(coin_reward=11)),
            ("target", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(target_value=4)),
            ("cadence", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(duration_days=8)),
            ("xp", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(xp_reward=61)),
            ("description", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(description="Arbitrary new promise")),
            ("name", lambda: QuestDefinition.objects.filter(pk__in=[source.pk, canonical.pk]).update(name="Unreviewed policy")),
            ("activity", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(trigger_filter={
                "allowed_triggers": ["chore_complete"], "reward_policy_version": 2, "distinct_active_days": True})),
            ("distinct-days", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(trigger_filter={
                "allowed_triggers": ["habit_log"], "reward_policy_version": 2})),
            ("private-filter", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(trigger_filter={
                "allowed_triggers": ["habit_log"], "reward_policy_version": 2, "distinct_active_days": True,
                "project_id": 123})),
            ("tag", lambda: QuestSkillTag.objects.filter(quest_definition=canonical).update(xp_weight=9)),
            ("reward", lambda: QuestRewardItem.objects.filter(quest_definition=canonical).update(quantity=2)),
            ("nonrepeatable", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(is_repeatable=False)),
            ("cooperative", lambda: QuestDefinition.objects.filter(pk=canonical.pk).update(is_cooperative=True)),
        ]
        for label, mutate in cases:
            with self.subTest(label=label), transaction.atomic():
                mutate()
                with self.assertRaises(ContentPackError):
                    self.preview(source, canonical)
                self.assertFalse(ContentPackPublication.objects.exists())
                transaction.set_rollback(True)

    def test_daily_transition_requires_exact_original_pouch_and_empty_new_reward(self):
        source, canonical = make_policy_pair(self.actor, "Daily Rituals")
        for value in (0, 2):
            with self.subTest(quantity=value), transaction.atomic():
                QuestRewardItem.objects.filter(quest_definition=source).update(quantity=value)
                with self.assertRaises(ContentPackError):
                    self.preview(source, canonical)
                transaction.set_rollback(True)
        with transaction.atomic():
            QuestRewardItem.objects.filter(quest_definition=source).delete()
            with self.assertRaises(ContentPackError):
                self.preview(source, canonical)
            transaction.set_rollback(True)
        item = ItemDefinition.objects.get(slug="pouch-small")
        QuestRewardItem.objects.create(quest_definition=canonical, item=item, quantity=1)
        with self.assertRaises(ContentPackError):
            self.preview(source, canonical)

    def test_changed_plan_after_preview_cannot_publish_partial_alias_or_new_windows(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        old = self.goal(source, opened=False)
        preview = self.preview(source, canonical)
        QuestDefinition.objects.filter(pk=canonical.pk).update(coin_reward=11)
        with self.assertRaises(ContentPackError):
            self.publish(preview)
        source.refresh_from_db()
        self.assertIsNone(source.superseded_by_id)
        self.assertFalse(old.occurrences.exists())
        self.assertEqual(self.amounts(), [])

    def test_unopened_repeat_cycle_zero_survives_overlap_and_pre_anchor_history(self):
        source, canonical = make_policy_pair(self.actor, "Comeback Kid")
        # An equivalent v1 control isolates the existing preservation hole from
        # the new v2-admission gate, so this test fails independently on base.
        canonical.trigger_filter = deepcopy(source.trigger_filter)
        canonical.description, canonical.coin_reward = source.description, source.coin_reward
        canonical.save(update_fields=["trigger_filter", "description", "coin_reward"])
        old = self.goal(source, opened=False)
        other = self.goal(canonical, start=self.now, opened=False)
        historical = ChallengeOccurrence.objects.create(
            goal=old, starts_at=self.anchor-timedelta(days=7), ends_at=self.anchor,
            snapshot={"coins": 40, "filter": deepcopy(source.trigger_filter)},
        )
        history_before = ChallengeOccurrence.objects.filter(pk=historical.pk).values().get()
        self.publish(self.preview(source, canonical), policy=False)
        accepted = old.occurrences.filter(starts_at=self.anchor).first()
        self.assertIsNotNone(accepted, "An accepted repeating cycle zero must remain completable after alias retirement")
        self.assertEqual((accepted.ends_at, accepted.snapshot["coins"], accepted.snapshot["filter"]),
                         (old.ends_at, 40, source.trigger_filter))
        old.refresh_from_db()
        self.assertEqual(old.catalog_definition_id, source.pk)
        self.assertEqual(ChallengeOccurrence.objects.filter(pk=historical.pk).values().get(), history_before)
        self.assertIsNone(_occurrence(old, self.now))
        self.assertFalse(other.occurrences.exists(), "Publication must not open unrelated or future cycles")
