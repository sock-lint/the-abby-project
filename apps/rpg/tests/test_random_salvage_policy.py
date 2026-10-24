"""Only new ordinary draws use the bounded salvage policy."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.rewards.models import CoinLedger
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService, DropService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RandomSalvagePolicyTests(TestCase):
    def setUp(self):
        self.user = make_family("Random salvage", children=[{"username": "child"}]).children[0]
        self.frame = ItemDefinition.objects.create(slug="rare-frame", name="Rare frame", item_type="cosmetic_frame", rarity="rare", coin_value=150)
        UserInventory.objects.create(user=self.user, item=self.frame, quantity=1)

    def test_new_ordinary_duplicate_pays_ten_without_repricing_the_owned_definition(self):
        DropTable.objects.create(trigger_type="project_complete", item=self.frame, weight=1)
        with patch("apps.rpg.services.random.random", return_value=0):
            drops = DropService.process_drops(self.user, "project_complete")
        self.assertEqual(drops[0]["salvage_coins"], 10)
        self.assertEqual(CoinLedger.objects.get(user=self.user).amount, 10)
        self.frame.refresh_from_db()
        self.assertEqual(self.frame.coin_value, 150)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.frame).quantity, 1)

    def test_owned_lucky_dip_keeps_full_original_duplicate_salvage(self):
        dip = ItemDefinition.objects.create(slug="lucky-dip", name="Lucky Dip", item_type="consumable", rarity="rare", metadata={"effect": "lucky_dip", "rarities": ["rare"]})
        UserInventory.objects.create(user=self.user, item=dip, quantity=1)
        ConsumableService.use(self.user, dip.pk)
        self.assertEqual(CoinLedger.objects.get(user=self.user).amount, 150)

    def test_owned_mystery_box_keeps_original_pouch_pool_and_face_value(self):
        pouch = ItemDefinition.objects.create(slug="pouch-small", name="Original pouch", item_type="coin_pouch", rarity="common", coin_value=5, metadata={"coins": 5})
        ItemDefinition.objects.create(slug="pouch-small-v2", name="Smaller pouch", item_type="coin_pouch", rarity="common", coin_value=1, metadata={"coins": 1, "no_random_drop": True})
        box = ItemDefinition.objects.create(slug="mystery-box", name="Mystery box", item_type="consumable", rarity="rare", metadata={"effect": "mystery_box", "rarities": ["common"]})
        UserInventory.objects.create(user=self.user, item=box, quantity=1)
        result = ConsumableService.use(self.user, box.pk)
        self.assertEqual(result["detail"]["granted_item_id"], pouch.pk)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=pouch).quantity, 1)
