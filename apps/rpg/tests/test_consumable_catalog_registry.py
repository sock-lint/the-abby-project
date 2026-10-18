"""The audit's effect vocabulary executes the actual consumable handlers."""
from django.test import TestCase

from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


class ConsumableCatalogRegistryTests(TestCase):
    def setUp(self):
        self.child = make_family("Synthetic consumable registry", children=[{"username": "effect-child"}]).children[0]

    def test_every_registered_effect_dispatches_to_an_actual_handler(self):
        for effect in sorted(ConsumableService.SUPPORTED_EFFECTS):
            with self.subTest(effect=effect):
                item = ItemDefinition.objects.create(name=effect, slug=f"test-{effect.replace('_', '-')}",
                    icon="x", item_type="consumable", metadata={"effect": effect})
                profile = self.child.character_profile
                try:
                    result = ConsumableService._apply_effect(profile, effect, item)
                except ValueError as exc:
                    # Missing pets, food, quests or unlocked skills are expected
                    # with this fresh account; falling through dispatch is not.
                    self.assertNotIn("Unknown consumable effect", str(exc))
                else:
                    self.assertIsInstance(result, dict)

    def test_unknown_effect_rejects_without_consuming_inventory_or_updating_profile(self):
        for index, effect in enumerate(("unknown-effect", {"unexpected": "object"})):
            with self.subTest(effect=effect):
                item = ItemDefinition.objects.create(name="Invalid", slug=f"test-unknown-{index}", icon="x", item_type="consumable",
                                                     metadata={"effect": effect})
                inventory = UserInventory.objects.create(user=self.child, item=item, quantity=1)
                before = self.child.character_profile.updated_at
                with self.assertRaisesMessage(ValueError, "Unknown consumable effect"):
                    ConsumableService.use(self.child, item.pk)
                inventory.refresh_from_db()
                self.child.character_profile.refresh_from_db()
                self.assertEqual(inventory.quantity, 1)
                self.assertEqual(self.child.character_profile.updated_at, before)
