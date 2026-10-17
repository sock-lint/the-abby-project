"""Database drafts evaluate and publish exact global content without editing YAML."""
from datetime import timedelta
from pathlib import Path
import tempfile

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory
from apps.quests.models import Quest, QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.workbench import create_draft, describe_workbench, save_draft, preview_draft, publish_draft, get_draft, simulate_draft
from apps.rpg.models import ContentPackEntry, ItemDefinition, UserInventory
from config.tests.factories import make_family


class ContentWorkbenchTests(TestCase):
    def setUp(self):
        self.family = make_family("Designers").family
        self.actor = User.objects.create_user(username="designer", role="parent", is_staff=True, family=self.family)
        self.item = ItemDefinition.objects.create(slug="test-food", name="Apple", icon="x", item_type="food", coin_value=2)
        category = SkillCategory.objects.create(name="Tests")
        self.skill = Skill.objects.create(name="Practice", category=category)
        self.quest = QuestDefinition.objects.create(name="Practice twice", description="Synthetic challenge", is_system=True,
            quest_type="collection", target_value=2, coin_reward=5, xp_reward=10)
        QuestSkillTag.objects.create(quest_definition=self.quest, skill=self.skill)
        QuestRewardItem.objects.create(quest_definition=self.quest, item=self.item, quantity=1)

    def draft(self, changes):
        draft = create_draft(self.actor, "Test design")
        return save_draft(self.actor, draft["id"], draft["revision"], changes)

    def publish(self, draft):
        draft = preview_draft(self.actor, draft["id"], draft["revision"])
        plan = draft["preview"]
        simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], {"horizon_days": 30, "trials": 1})
        return publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])

    def test_preview_is_private_and_rolls_back_then_publish_keeps_ids_and_promises(self):
        accepted = Quest.objects.create(definition=self.quest, end_date=timezone.now() + timedelta(days=7))
        UserInventory.objects.create(user=self.actor, item=self.item, quantity=4)
        draft = self.draft([
            {"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "Bright Apple"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {"name": "A new title", "reward_items": []}},
        ])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        self.item.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(self.item.name, "Apple")
        self.assertIsNone(accepted.reward_items_snapshot)
        self.assertTrue(reviewed["preview"]["changes"])
        published = self.publish(draft)
        self.assertTrue(published["published_at"])
        self.item.refresh_from_db()
        self.quest.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual((self.item.name, self.quest.name), ("Bright Apple", "A new title"))
        self.assertEqual(accepted.reward_items_snapshot[0]["item_id"], self.item.pk)
        self.assertEqual(accepted.reward_items_snapshot[0]["item_name"], "Apple")
        self.assertFalse(self.quest.reward_items.exists())
        self.assertEqual(UserInventory.objects.get(user=self.actor, item=self.item).quantity, 4)

    def test_published_override_survives_yaml_reload_including_original_name(self):
        self.publish(self.draft([
            {"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "Bright Apple"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {"name": "Renamed", "coin_reward": 12}},
        ]))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "items.yaml").write_text("items:\n- slug: test-food\n  name: Apple\n  icon: x\n  item_type: food\n")
            (path / "quests.yaml").write_text("quests:\n- name: Practice twice\n  quest_type: collection\n  target_value: 2\n  coin_reward: 5\n")
            before = {file.name: file.read_bytes() for file in path.iterdir()}
            ContentPack(path).load()
            self.assertEqual({file.name: file.read_bytes() for file in path.iterdir()}, before)
        self.item.refresh_from_db()
        self.quest.refresh_from_db()
        self.assertEqual((self.item.name, self.quest.name, self.quest.coin_reward), ("Bright Apple", "Renamed", 12))
        self.assertEqual(QuestDefinition.objects.count(), 1)

    def test_stale_revision_preview_and_catalog_refuse_without_publication(self):
        draft = self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "Pear"}}])
        with self.assertRaisesMessage(ContentPackError, "revision"):
            save_draft(self.actor, draft["id"], draft["revision"] - 1, [])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        ItemDefinition.objects.filter(pk=self.item.pk).update(coin_value=99)
        plan = reviewed["preview"]
        with self.assertRaisesMessage(ContentPackError, "Catalog state changed"):
            publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Apple")

    def test_drafts_and_pack_edits_require_exact_actor_family_ownership(self):
        draft = self.draft([])
        other = User.objects.create_user(username="other", role="parent", is_staff=True, family=make_family("Others").family)
        with self.assertRaisesMessage(ContentPackError, "not found"):
            get_draft(other, draft["id"])
        ContentPackEntry.objects.create(pack="others", family=other.family, kind="itemdefinition", key="apple",
            model_label="rpg.itemdefinition", object_id=self.item.pk)
        with self.assertRaisesMessage(ContentPackError, "another family"):
            self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "No"}}])

    def test_new_item_reference_and_exact_skill_links_publish_together(self):
        draft = self.draft([
            {"section": "items", "object_id": None, "key": "new-food", "values": {"slug": "new-food", "name": "Pear", "icon": "x", "item_type": "food"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {
                "reward_items": [{"item_key": "new-food", "quantity": 3}],
                "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 2}]}},
        ])
        self.publish(draft)
        reward = self.quest.reward_items.get()
        self.assertEqual((reward.item.slug, reward.quantity), ("new-food", 3))
        self.assertEqual(self.quest.skill_tags.get().xp_weight, 2)

    def test_active_legacy_scalars_and_private_quest_edits_are_blocked(self):
        Quest.objects.create(definition=self.quest, end_date=timezone.now() + timedelta(days=7))
        draft = self.draft([{"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {"coin_reward": 20}}])
        with self.assertRaisesMessage(ContentPackError, "active legacy"):
            preview_draft(self.actor, draft["id"], draft["revision"])
        private = QuestDefinition.objects.create(name="Private", description="private", quest_type="collection", target_value=1, created_by=self.actor)
        with self.assertRaisesMessage(ContentPackError, "catalog"):
            self.draft([{"section": "quests", "object_id": private.pk, "key": "private", "values": {"name": "No"}}])

    def test_invalid_global_filters_refs_and_item_effects_reject(self):
        invalid = [
            ("quests", self.quest.pk, {"trigger_filter": {"project_id": 42}}),
            ("quests", self.quest.pk, {"reward_items": [{"item_id": 999999, "quantity": 1}]}),
            ("quests", self.quest.pk, {"skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 0}]}),
            ("items", None, {"slug": "bad", "name": "Bad", "icon": "x", "item_type": "consumable", "metadata": {"effect": "unknown"}}),
        ]
        for section, object_id, values in invalid:
            with self.subTest(values=values), self.assertRaises(ContentPackError):
                draft = self.draft([{"section": section, "object_id": object_id, "key": "bad", "values": values}])
                preview_draft(self.actor, draft["id"], draft["revision"])

    def test_item_only_edit_freezes_old_legacy_presentation_before_change(self):
        accepted = Quest.objects.create(definition=self.quest, end_date=timezone.now() + timedelta(days=7))
        self.publish(self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "New name"}}]))
        accepted.refresh_from_db()
        self.assertEqual(accepted.reward_items_snapshot[0]["item_name"], "Apple")

    def test_simulation_is_required_and_edit_invalidates_evaluation(self):
        draft = self.draft([{"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {"coin_reward": 50}}])
        draft = preview_draft(self.actor, draft["id"], draft["revision"])
        plan = draft["preview"]
        with self.assertRaisesMessage(ContentPackError, "Simulate"):
            publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])
        comparison = simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], {"horizon_days": 30, "trials": 1})
        self.assertEqual(comparison["baseline"]["config"], comparison["proposed"]["config"])
        self.assertNotEqual(comparison["baseline"]["catalog"]["fingerprint"], comparison["proposed"]["catalog"]["fingerprint"])
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.coin_reward, 5)
        changed = save_draft(self.actor, draft["id"], draft["revision"], draft["changes"])
        self.assertIsNone(changed["preview"])
        self.assertIsNone(changed["simulation"])

    def test_bad_item_metadata_never_publishes_unusable_runtime_effects(self):
        invalid = [
            ("food", {"growth": 31}), ("food", {"growth": True}),
            ("coin_pouch", {"coins": -1}), ("coin_pouch", {}),
            ("consumable", {"effect": "xp_boost", "duration_hours": "abc"}),
            ("consumable", {"effect": "growth_tonic", "feeds": 1000000}),
            ("consumable", {"effect": "food_basket", "count": 0}),
            ("consumable", {"effect": "mystery_box", "rarities": ["unknown"]}),
        ]
        for item_type, metadata in invalid:
            with self.subTest(metadata=metadata), self.assertRaises(ContentPackError):
                draft = self.draft([{"section": "items", "object_id": None, "key": "bad", "values": {
                    "slug": "bad", "name": "Bad", "icon": "x", "item_type": item_type, "metadata": metadata}}])
                preview_draft(self.actor, draft["id"], draft["revision"])

    def test_malformed_nested_browser_values_are_validation_errors(self):
        for change in (
            {"section": [], "object_id": None, "key": "bad", "values": {}},
            {"section": "items", "object_id": self.item.pk, "key": "bad", "values": None},
            {"section": "items", "object_id": None, "key": "bad", "values": {"item_type": []}},
            {"section": "quests", "object_id": self.quest.pk, "key": "bad", "values": {"trigger_filter": []}},
            {"section": "quests", "object_id": self.quest.pk, "key": "bad", "values": {"trigger_filter": {"allowed_triggers": [[]]}}},
        ):
            with self.subTest(change=change), self.assertRaises(ContentPackError):
                self.draft([change])

    def test_generated_egg_override_survives_species_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "pet_species.yaml").write_text("species:\n- slug: test-animal\n  name: Test animal\n  icon: x\n")
            ContentPack(path).load()
            egg = ItemDefinition.objects.get(slug="test-animal-egg")
            self.publish(self.draft([{"section": "items", "object_id": egg.pk, "key": "egg", "values": {"name": "Special egg"}}]))
            ContentPack(path).load()
        egg.refresh_from_db()
        self.assertEqual(egg.name, "Special egg")

    def test_existing_item_behavior_is_versioned_instead_of_rewriting_owned_items(self):
        UserInventory.objects.create(user=self.actor, item=self.item, quantity=4)
        for values in ({"rarity": "legendary"}, {"coin_value": 50}, {"metadata": {"growth": 20}}):
            with self.subTest(values=values), self.assertRaisesMessage(ContentPackError, "new item version"):
                self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": values}])
        # Forms can round-trip the unchanged behavior alongside display edits.
        self.publish(self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {
            "name": "Bright Apple", "rarity": self.item.rarity, "coin_value": self.item.coin_value,
            "metadata": self.item.metadata}}]))
        self.item.refresh_from_db()
        self.assertEqual((self.item.name, self.item.rarity, self.item.coin_value), ("Bright Apple", "common", 2))
        self.assertEqual(UserInventory.objects.get(user=self.actor, item=self.item).quantity, 4)

    def test_new_item_warnings_bind_stable_keys_across_preview_and_publication_sequences(self):
        draft = self.draft([
            {"section": "items", "object_id": None, "key": "accessory", "values": {
                "slug": "future-accessory", "name": "Future accessory", "icon": "x", "item_type": "cosmetic_pet_accessory"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {
                "reward_items": [{"item_key": "accessory", "quantity": 1}]}},
        ])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        plan = reviewed["preview"]
        warning = next(finding for finding in plan["audits"]["findings"] if finding["code"] == "unsupported_reward_item")
        self.assertIn("item future-accessory;", warning["detail"])
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT nextval(pg_get_serial_sequence('rpg_itemdefinition', 'id'))")
        else:
            # SQLite does not consume IDs on savepoint rollback, so advance
            # its disposable sequence without leaving a catalog change.
            padding = ItemDefinition.objects.create(slug="sequence-padding", name="Padding", item_type="food")
            padding.delete()
        simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], {"horizon_days": 30, "trials": 1})
        published = publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])
        self.assertTrue(published["published_at"])

    def test_rule_change_invalidates_an_evaluated_draft(self):
        draft = self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "Pear"}}])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        plan = reviewed["preview"]
        simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], {"horizon_days": 30, "trials": 1})
        with override_settings(COINS_PER_HOUR=999), self.assertRaisesMessage(ContentPackError, "Simulation rules changed"):
            publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])

    def test_private_templates_and_their_reward_changes_are_outside_global_review(self):
        private = QuestDefinition.objects.create(name="Private homework", description="Private family description",
            quest_type="collection", target_value=2, created_by=self.actor)
        private_link = QuestRewardItem.objects.create(quest_definition=private, item=self.item)
        QuestSkillTag.objects.create(quest_definition=private, skill=self.skill)
        metadata = describe_workbench(self.actor)
        self.assertEqual([row["id"] for row in metadata["catalog"]["quests"]], [self.quest.pk])
        self.assertNotIn(private.pk, [row["id"] for row in metadata["catalog"]["items"][0]["used_by"]["quests"]])
        draft = self.draft([{"section": "items", "object_id": self.item.pk, "key": "apple", "values": {"name": "Pear"}}])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        plan = reviewed["preview"]
        private.description = "Different private text"
        private.save()
        private_link.quantity = 3
        private_link.save()
        simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], {"horizon_days": 30, "trials": 1})
        self.assertTrue(publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])["published_at"])
