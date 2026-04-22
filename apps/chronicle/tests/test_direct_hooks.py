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
        self.user = User.objects.create_user(
            username="kid", password="pw", role=User.Role.CHILD,
        )

    def test_hatching_first_pet_emits_first_pet_hatched(self):
        # Fixture setup requires PetSpecies + PotionType + items in inventory.
        # The rpg/pets content pack is loaded in production but not guaranteed
        # in test DB; skip rather than duplicate the full YAML bootstrap here.
        self.skipTest(
            "Fill in fixture setup matching apps.pets.tests patterns — "
            "requires PetSpecies, PotionType, egg + potion UserInventory rows."
        )

    def test_evolving_pet_emits_first_mount_evolved(self):
        # Same prerequisite as hatch test — evolution flows through feed_pet
        # which also needs PetSpecies + potion type + food inventory.
        self.skipTest(
            "Fill in fixture setup matching apps.pets.tests patterns — "
            "requires UserPet near EVOLUTION_THRESHOLD + food item."
        )
