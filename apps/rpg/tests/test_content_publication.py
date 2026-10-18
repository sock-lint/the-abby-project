"""Reviewed publication exercises real loader behavior with disposable data."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Event
from unittest import skipUnless
from django.db import connection, transaction
from django.test import TransactionTestCase

from datetime import timedelta
import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone
import yaml

from config.tests.factories import make_family
from apps.accounts.models import User
from apps.achievements.models import Badge, Skill, SkillCategory
from apps.quests.models import Quest, QuestDefinition, QuestRewardItem
from apps.rewards.models import Reward
from apps.rpg.models import ContentPackEntry, ContentPackPublication, ItemDefinition, UserInventory
from apps.rpg.content.loader import ContentPackError
from apps.rpg.content.publication import preview_content_pack, publish_content_pack


class ContentPublicationTests(TestCase):
    def setUp(self):
        self.family = make_family("Publisher").family
        self.actor = User.objects.create_user(username="publisher", role="parent", is_staff=True, family=self.family)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def write(self, filename, value):
        (self.path / filename).write_text(yaml.safe_dump(value))

    def items(self):
        self.write("items.yaml", {"items": [{"slug": "token", "name": "A token", "description": "Synthetic", "item_type": "food", "icon": "x", "coin_value": 3}]})

    def preview(self):
        return preview_content_pack(self.path, "test-pack", self.actor)

    def publish(self, plan):
        return publish_content_pack(self.path, "test-pack", self.actor, plan["preview_id"], plan["content_digest"])

    def test_exact_preview_rolls_back_then_publishes_once_and_keeps_receipt(self):
        self.items()
        plan = self.preview()
        self.assertFalse(ItemDefinition.objects.filter(slug="test-pack-token").exists())
        self.assertTrue(any(c["action"] == "create" for c in plan["changes"]))
        result = self.publish(plan)
        item = ItemDefinition.objects.get(slug="test-pack-token")
        self.assertTrue(result["published_at"])
        self.assertEqual(self.publish(plan), result)
        self.assertEqual(ContentPackEntry.objects.get(object_id=item.pk, model_label="rpg.itemdefinition").pack, "test-pack")
        self.assertEqual(ContentPackPublication.objects.count(), 1)

    def test_stale_source_or_catalog_state_rejected_without_writes(self):
        self.items()
        plan = self.preview()
        self.write("items.yaml", {"items": []})
        with self.assertRaisesMessage(ContentPackError, "source changed"):
            self.publish(plan)
        self.assertFalse(ItemDefinition.objects.filter(slug="test-pack-token").exists())
        self.items()
        plan = self.preview()
        ItemDefinition.objects.create(slug="concurrent", name="Concurrent", item_type="food")
        with self.assertRaisesMessage(ContentPackError, "state changed"):
            self.publish(plan)

    def test_stable_quest_id_rename_and_reward_removal_keep_owned_item(self):
        self.items()
        def quest(name, rewards):
            self.write("quests.yaml", {"quests": [{"id": "weekly", "name": name, "description": "Synthetic", "quest_type": "collection", "target_value": 2, "reward_items": rewards}]})
        quest("Original", [{"slug": "token", "quantity": 2}])
        self.publish(self.preview())
        original = QuestDefinition.objects.get(name="Original")
        item = ItemDefinition.objects.get(slug="test-pack-token")
        UserInventory.objects.create(user=self.actor, item=item, quantity=2)
        accepted = Quest.objects.create(definition=original, end_date=timezone.now() + timedelta(days=7))
        promised_row = original.reward_items.get()
        quest("Renamed", [])
        plan = self.preview()
        self.assertTrue(any(c["action"] == "remove" and "questrewarditem" in c["object"] for c in plan["changes"]))
        accepted.refresh_from_db()
        self.assertIsNone(accepted.reward_items_snapshot)
        self.publish(plan)
        accepted.refresh_from_db()
        snapshot = accepted.reward_items_snapshot
        self.assertEqual([{key: row[key] for key in ("id", "item_id", "quantity")} for row in snapshot],
                         [{"id": promised_row.pk, "item_id": item.pk, "quantity": 2}])
        self.assertEqual(snapshot[0]["item_name"], item.display_name)
        self.assertEqual(QuestDefinition.objects.get(name="Renamed").pk, original.pk)
        self.assertFalse(QuestRewardItem.objects.filter(quest_definition=original).exists())
        self.assertEqual(UserInventory.objects.get(user=self.actor, item=item).quantity, 2)

    def test_global_name_collision_cannot_adopt_unowned_quest(self):
        QuestDefinition.objects.create(name="Existing", description="Original", quest_type="collection", target_value=5)
        self.write("quests.yaml", {"quests": [{"id": "new", "name": "Existing", "description": "Changed", "quest_type": "collection", "target_value": 1}]})
        with self.assertRaisesMessage(ContentPackError, "Unowned"):
            self.preview()
        self.assertEqual(QuestDefinition.objects.get(name="Existing").target_value, 5)

    def test_shop_destination_is_explicit_actor_family_and_removed_offer_retires(self):
        self.write("rewards.yaml", {"rewards": [{"id": "outing", "name": "Outing", "description": "Synthetic", "cost_coins": 30}]})
        self.publish(self.preview())
        reward = Reward.objects.get(name="Outing")
        self.assertEqual(reward.family, self.family)
        self.write("rewards.yaml", {"rewards": []})
        plan = self.preview()
        self.assertEqual(plan["stats"]["retired"], {"shop_offer": 1})
        self.publish(plan)
        reward.refresh_from_db()
        self.assertFalse(reward.is_active)

    def test_invalid_filter_criteria_and_negative_reward_never_publish(self):
        for value in ({"allowed_trigger": ["chore_complete"]}, {"allowed_triggers": ["unknown"]}):
            self.write("quests.yaml", {"quests": [{"name": "Bad", "quest_type": "collection", "target_value": 1, "trigger_filter": value}]})
            with self.assertRaises(ContentPackError):
                self.preview()
        (self.path / "quests.yaml").unlink()
        self.write("badges.yaml", {"badges": [{"name": "Bad", "criteria_type": "projects_completed", "criteria_value": {"cout": 2}}]})
        with self.assertRaisesMessage(ContentPackError, "criteria_value"):
            self.preview()
        self.assertFalse(Badge.objects.filter(name="Bad").exists())
        self.assertFalse(ContentPackPublication.objects.exists())

    def test_expired_or_other_actor_preview_refused(self):
        self.items()
        plan = self.preview()
        ContentPackPublication.objects.filter(pk=plan["preview_id"]).update(expires_at=timezone.now())
        with self.assertRaisesMessage(ContentPackError, "expired"):
            self.publish(plan)
        other = User.objects.create_user(username="other-publisher", role="parent", is_staff=True, family=self.family)
        with self.assertRaisesMessage(ContentPackError, "not found"):
            publish_content_pack(self.path, "test-pack", other, plan["preview_id"], plan["content_digest"])

    def test_strict_numeric_boolean_unknown_fields_and_duplicate_ids(self):
        invalid = [
            {"coin_reward": -1}, {"target_value": 0}, {"duration_days": 366},
            {"is_repeatable": "false"}, {"is_system": False}, {"coin_rewad": 10},
            {"reward_items": [{"slug": "missing", "quantity": 0}]},
        ]
        for extra in invalid:
            with self.subTest(extra=extra):
                self.write("quests.yaml", {"quests": [{"id": "one", "name": "Invalid", "description": "Synthetic", "quest_type": "collection", "target_value": 1, **extra}]})
                with self.assertRaises(ContentPackError):
                    self.preview()
        self.write("quests.yaml", {"quests": [{"id": "duplicate", "name": name, "quest_type": "collection", "target_value": 1} for name in ("One", "Two")]})
        with self.assertRaisesMessage(ContentPackError, "Duplicate"):
            self.preview()

    def test_active_legacy_quest_rules_rewards_and_skill_destinations_cannot_be_rewritten(self):
        category = SkillCategory.objects.create(name="Synthetic category")
        first = Skill.objects.create(name="First synthetic skill", category=category)
        second = Skill.objects.create(name="Second synthetic skill", category=category)
        original = {"id": "accepted", "name": "Accepted", "description": "Synthetic", "quest_type": "collection",
                    "target_value": 2, "coin_reward": 50, "xp_reward": 40, "duration_days": 7,
                    "trigger_filter": {"allowed_triggers": ["chore_complete"]}, "skill_tags": [first.name]}
        self.write("quests.yaml", {"quests": [original]})
        self.publish(self.preview())
        definition = QuestDefinition.objects.get(name="Accepted")
        accepted = Quest.objects.create(definition=definition, end_date=timezone.now() + timedelta(days=7), reward_items_snapshot=[])
        for changes in ({"coin_reward": 1}, {"xp_reward": 1}, {"target_value": 10}, {"quest_type": "boss"},
                        {"duration_days": 14}, {"trigger_filter": {}}, {"skill_tags": []}, {"skill_tags": [second.name]}):
            with self.subTest(changes=changes):
                self.write("quests.yaml", {"quests": [{**original, **changes}]})
                with self.assertRaisesMessage(ContentPackError, "active legacy"):
                    self.preview()
                definition.refresh_from_db()
                self.assertEqual(definition.coin_reward, 50)
                self.assertEqual(definition.target_value, 2)
                self.assertEqual(list(definition.skill_tags.values_list("skill_id", "xp_weight")), [(first.pk, 1)])
                accepted.refresh_from_db()
                self.assertEqual(accepted.reward_items_snapshot, [])
        self.write("quests.yaml", {"quests": [{**original, "name": "Cosmetic rename", "description": "A revised description"}]})
        plan = self.preview()
        self.assertEqual(plan["stats"]["skipped"]["protected_active_legacy_quests"], 1)
        self.publish(plan)
        definition.refresh_from_db()
        self.assertEqual(definition.name, "Cosmetic rename")

    def test_fractional_nested_quantities_and_weights_are_rejected(self):
        self.items()
        base = {"id": "integers", "name": "Integer rewards", "description": "Synthetic", "quest_type": "collection", "target_value": 1}
        for changes in ({"reward_items": [{"slug": "token", "quantity": 1.5}]},
                        {"skill_tags": [{"skill": "No lookup should occur", "weight": 1.5}]}):
            with self.subTest(changes=changes):
                self.write("quests.yaml", {"quests": [{**base, **changes}]})
                with self.assertRaisesMessage(ContentPackError, "whole number"):
                    self.preview()
        (self.path / "quests.yaml").unlink()
        self.write("drops.yaml", {"macros": [{"triggers": ["chore_complete"], "item_type": "food", "weight_by_rarity": {"common": 1.5}}]})
        with self.assertRaisesMessage(ContentPackError, "whole number"):
            self.preview()

    def test_deleted_author_retains_audit_without_blocking_account_deletion(self):
        self.items()
        plan = self.preview()
        self.publish(plan)
        self.actor.delete()
        receipt = ContentPackPublication.objects.get(pk=plan["preview_id"])
        self.assertIsNone(receipt.actor_id)
        self.assertTrue(receipt.published_at)
        self.assertTrue(receipt.changes)

    def test_plan_does_not_disclose_other_family_shop_provenance(self):
        other_family = make_family("Private shop").family
        reward = Reward.objects.create(family=other_family, name="Synthetic private shop name", cost_coins=50)
        ContentPackEntry.objects.create(pack="private-shop-pack", family=other_family, kind="reward", key="Synthetic private shop name", model_label="rewards.reward", object_id=reward.pk)
        self.items()
        plan = self.preview()
        self.assertNotIn("Synthetic private shop name", str(plan))
        self.assertNotIn("private-shop-pack", str(plan))
        self.assertFalse(any(row["object"] == "publication:ownership" for row in plan["changes"]))

    def test_parameterless_badge_criteria_are_valid(self):
        self.write("badges.yaml", {"badges": [{"id": "first", "name": "First synthetic", "description": "Synthetic", "criteria_type": "first_clock_in", "criteria_value": {}}]})
        self.publish(self.preview())
        self.assertEqual(Badge.objects.get(name="First synthetic").criteria_value, {})

    def test_deleted_family_keeps_global_provenance_and_blocks_adoption(self):
        self.items()
        self.publish(self.preview())
        self.family.delete()
        self.assertTrue(ContentPackEntry.objects.filter(pack="test-pack", family__isnull=True).exists())
        self.assertFalse(ContentPackPublication.objects.filter(pack="test-pack").exists())
        other_family = make_family("New publisher").family
        other = User.objects.create_user(username="orphan-adopter", role="parent", is_staff=True, family=other_family)
        with self.assertRaisesMessage(ContentPackError, "another family"):
            preview_content_pack(self.path, "test-pack", other)

    def test_pack_identity_cannot_move_to_another_family(self):
        self.items()
        self.publish(self.preview())
        other_family = make_family("Other publisher").family
        other = User.objects.create_user(username="foreign-publisher", role="parent", is_staff=True, family=other_family)
        with self.assertRaisesMessage(ContentPackError, "another family"):
            preview_content_pack(self.path, "test-pack", other)




@skipUnless(connection.vendor == "postgresql", "Catalog write serialization requires PostgreSQL")
class PublicationWriteSerializationTests(TransactionTestCase):
    def test_catalog_snapshot_does_not_block_inventory_foreign_key_checks(self):
        from apps.rpg.content.publication import _catalog_lock, _snapshot
        family = make_family("FK compatibility").family
        child = User.objects.create_user(username="snapshot-fk-child", role="child", family=family)
        item = ItemDefinition.objects.create(slug="snapshot-fk-item", name="FK compatibility", icon="x", item_type="food")

        def completion_inventory_grant():
            from django.db import connection as worker_connection
            try:
                return UserInventory.objects.create(user_id=child.pk, item_id=item.pk, quantity=1).pk
            finally:
                worker_connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                _catalog_lock()
                _snapshot(family, lock=True)
                future = executor.submit(completion_inventory_grant)
                # A publication holding catalog metadata must permit a finishing
                # accepted quest's FK check without waiting for publication commit.
                self.assertIsNotNone(future.result(timeout=5))
        self.assertTrue(UserInventory.objects.filter(user=child, item=item).exists())

    def test_catalog_lock_blocks_a_legacy_writer_inserting_after_review(self):
        from apps.rpg.content.publication import _catalog_lock
        attempted = Event()

        def legacy_writer():
            from django.db import connection as worker_connection
            try:
                attempted.set()
                return ItemDefinition.objects.create(slug="late-legacy", name="Late legacy", icon="x", item_type="food").pk
            finally:
                worker_connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                _catalog_lock()
                future = executor.submit(legacy_writer)
                self.assertTrue(attempted.wait(timeout=5))
                with self.assertRaises(FutureTimeout):
                    future.result(timeout=0.15)
                self.assertFalse(ItemDefinition.objects.filter(slug="late-legacy").exists())
            self.assertIsNotNone(future.result(timeout=5))
        self.assertTrue(ItemDefinition.objects.filter(slug="late-legacy").exists())
