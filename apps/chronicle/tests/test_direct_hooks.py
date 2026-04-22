"""Hooks for flows that don't route through GameLoopService.on_task_completed."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chronicle.models import ChronicleEntry

User = get_user_model()


class ExchangeServiceHookTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="mom", password="pw", role=User.Role.PARENT,
        )
        self.child = User.objects.create_user(
            username="kid", password="pw", role=User.Role.CHILD,
        )

    def test_approving_exchange_emits_first_exchange_approved(self):
        from apps.payments.models import PaymentLedger
        from apps.payments.services import PaymentService
        from apps.rewards.models import ExchangeRequest
        from apps.rewards.services import ExchangeService

        # Seed $50 payment balance so the approval balance check passes.
        PaymentService.record_entry(
            self.child, Decimal("50.00"), PaymentLedger.EntryType.ADJUSTMENT,
        )

        # Create an exchange request directly (bypass request_exchange to
        # avoid the "money held" issue — the approve method re-checks balance).
        exchange = ExchangeRequest.objects.create(
            user=self.child,
            dollar_amount=Decimal("10.00"),
            coin_amount=100,
            exchange_rate=10,
            status=ExchangeRequest.Status.PENDING,
        )

        ExchangeService.approve(exchange, parent=self.parent)

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.child,
                kind="first_ever",
                event_slug="first_exchange_approved",
            ).exists()
        )

    def test_duplicate_approval_does_not_double_write(self):
        """record_first is idempotent — a second approval on a different
        exchange does not create a second ChronicleEntry."""
        from apps.payments.models import PaymentLedger
        from apps.payments.services import PaymentService
        from apps.rewards.models import ExchangeRequest
        from apps.rewards.services import ExchangeService

        PaymentService.record_entry(
            self.child, Decimal("100.00"), PaymentLedger.EntryType.ADJUSTMENT,
        )

        exchange1 = ExchangeRequest.objects.create(
            user=self.child,
            dollar_amount=Decimal("10.00"),
            coin_amount=100,
            exchange_rate=10,
            status=ExchangeRequest.Status.PENDING,
        )
        exchange2 = ExchangeRequest.objects.create(
            user=self.child,
            dollar_amount=Decimal("10.00"),
            coin_amount=100,
            exchange_rate=10,
            status=ExchangeRequest.Status.PENDING,
        )

        ExchangeService.approve(exchange1, parent=self.parent)
        ExchangeService.approve(exchange2, parent=self.parent)

        self.assertEqual(
            ChronicleEntry.objects.filter(
                user=self.child, event_slug="first_exchange_approved",
            ).count(),
            1,
        )


class PetServiceHookTests(TestCase):
    def setUp(self):
        from apps.pets.models import PetSpecies, PotionType
        from apps.rpg.models import ItemDefinition, UserInventory

        self.user = User.objects.create_user(
            username="kid", password="pw", role=User.Role.CHILD,
        )

        # Species and potion — matched via metadata name lookup (legacy path).
        self.species = PetSpecies.objects.create(
            name="Testfox", icon="\U0001f98a", food_preference="berries",
        )
        self.potion_type = PotionType.objects.create(
            name="Gold", color_hex="#FFD700",
        )

        # Items — use the metadata-based legacy path so no typed FK migration needed.
        self.egg_item = ItemDefinition.objects.create(
            name="Testfox Egg", icon="\U0001f95a",
            item_type=ItemDefinition.ItemType.EGG,
            rarity="common",
            metadata={"species": "testfox"},
        )
        self.potion_item = ItemDefinition.objects.create(
            name="Gold Potion", icon="\U0001f9ea",
            item_type=ItemDefinition.ItemType.POTION,
            rarity="common",
            metadata={"variant": "gold"},
        )
        self.food_item = ItemDefinition.objects.create(
            name="Berries", icon="\U0001fad0",
            item_type=ItemDefinition.ItemType.FOOD,
            rarity="common",
            metadata={"food_type": "berries"},
        )

        # Seed inventory.
        UserInventory.objects.create(user=self.user, item=self.egg_item, quantity=1)
        UserInventory.objects.create(user=self.user, item=self.potion_item, quantity=1)
        UserInventory.objects.create(user=self.user, item=self.food_item, quantity=10)

    def test_hatching_first_pet_emits_first_pet_hatched(self):
        from apps.pets.services import PetService

        PetService.hatch_pet(self.user, self.egg_item.id, self.potion_item.id)

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user,
                kind="first_ever",
                event_slug="first_pet_hatched",
            ).exists()
        )

    def test_evolving_pet_emits_first_mount_evolved(self):
        from apps.pets.services import PetService

        pet = PetService.hatch_pet(self.user, self.egg_item.id, self.potion_item.id)

        # Force growth to 99 — one preferred-food feed (+15, capped at 100) triggers evolution.
        pet.growth_points = 99
        pet.save(update_fields=["growth_points"])

        # Re-seed food (hatch consumed nothing; inventory row may still exist — just ensure qty).
        from apps.rpg.models import UserInventory
        UserInventory.objects.update_or_create(
            user=self.user, item=self.food_item,
            defaults={"quantity": 1},
        )

        PetService.feed_pet(self.user, pet.id, self.food_item.id)

        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.user,
                kind="first_ever",
                event_slug="first_mount_evolved",
            ).exists()
        )
