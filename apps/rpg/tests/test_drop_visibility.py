from django.test import TestCase

from apps.rpg.models import DropLog, ItemDefinition
from apps.rpg.serializers import DropLogSerializer
from config.tests.factories import make_family


class DropRewardVisibilityTests(TestCase):
    def test_drop_exposes_real_item_action_details_and_saved_availability(self):
        child = make_family(children=[{"username": "drop-details-child"}]).children[0]
        item = ItemDefinition.objects.create(
            name="Saved accessory", icon="H", item_type="cosmetic_pet_accessory", rarity="rare",
            description="An old keepsake", metadata={"slot": "head"},
        )
        drop = DropLog.objects.create(user=child, item=item, trigger_type="project_complete")
        data = DropLogSerializer(drop).data
        self.assertEqual(data.get("item_type"), "cosmetic_pet_accessory")
        self.assertEqual(data.get("item_description"), "An old keepsake")
        self.assertEqual(data.get("item_metadata"), {"slot": "head"})
        self.assertIs(data.get("item_catalog_available"), False)

    def test_salvage_amount_uses_recorded_outcome_and_preserves_unknown_history(self):
        item = ItemDefinition(name="Changed frame", item_type="cosmetic_frame", coin_value=999)
        for saved_amount in (None, 0, 17):
            with self.subTest(saved_amount=saved_amount):
                drop = DropLog(item=item, was_salvaged=True, trigger_type="project_complete")
                drop.salvage_coins = saved_amount
                data = DropLogSerializer(drop).data
                self.assertIn("salvage_coins", data)
                self.assertEqual(data["salvage_coins"], saved_amount)
