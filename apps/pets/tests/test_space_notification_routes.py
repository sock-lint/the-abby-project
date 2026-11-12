"""Child companion updates open Family; personal receipts open owned pets."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import Notification
from apps.pets.expeditions import ExpeditionService
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import PetService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CompanionNotificationSpaceTests(TestCase):
    def setUp(self):
        family = make_family(
            "Companion notification spaces",
            parents=[{"username": "companion-parent"}, {"username": "companion-coparent"}],
            children=[{"username": "companion-child"}],
        )
        self.parents = family.parents
        self.child = family.children[0]
        self.foreign = make_family(
            "Other companion family", parents=[{"username": "companion-outsider"}],
        ).parents[0]
        self.species = PetSpecies.objects.create(slug="notification-wolf", name="Notification Wolf")
        self.potion = PotionType.objects.create(slug="notification-base", name="Base")

    def evolve(self, owner):
        pet = UserPet.objects.create(
            user=owner, species=self.species, potion=self.potion, growth_points=100,
        )
        return PetService._save_growth(pet, update_fields=["growth_points"])

    def claim(self, owner):
        mount = UserMount.objects.create(user=owner, species=self.species, potion=self.potion)
        expedition = MountExpedition.objects.create(
            mount=mount, tier="short", started_at=timezone.now() - timedelta(hours=3),
            returns_at=timezone.now() - timedelta(hours=1), loot={"coins": 3, "items": []},
        )
        with self.captureOnCommitCallbacks(execute=True):
            return ExpeditionService.claim(owner, expedition.pk)

    def assert_child_routes(self, notification_type):
        self.assertEqual(
            Notification.objects.get(user=self.child, notification_type=notification_type).link,
            "/bestiary?tab=mounts",
        )
        for parent in self.parents:
            self.assertEqual(
                Notification.objects.get(user=parent, notification_type=notification_type).link,
                f"/family?child={self.child.pk}",
            )
        self.assertFalse(Notification.objects.filter(user=self.foreign).exists())

    def test_child_evolution_notifications_open_the_childs_family_overview(self):
        self.evolve(self.child)
        self.assert_child_routes("pet_evolved")

    def test_child_expedition_notifications_open_the_childs_family_overview(self):
        result = self.claim(self.child)
        self.assertTrue(result["freshly_claimed"])
        self.assert_child_routes("expedition_returned")

    def test_parent_evolution_receipt_keeps_its_personal_pet_destination(self):
        self.evolve(self.parents[0])
        receipt = Notification.objects.get(
            user=self.parents[0], notification_type="pet_evolved",
            title="Notification Wolf evolved into a mount!",
        )
        self.assertEqual(receipt.link, "/bestiary?tab=mounts&space=personal")
        self.assertFalse(Notification.objects.filter(user=self.child).exists())

    def test_parent_expedition_receipt_keeps_its_personal_pet_destination(self):
        self.claim(self.parents[0])
        receipt = Notification.objects.get(
            user=self.parents[0], notification_type="expedition_returned",
            title="Notification Wolf is back from an expedition!",
        )
        self.assertEqual(receipt.link, "/bestiary?tab=mounts&space=personal")
        self.assertFalse(Notification.objects.filter(user=self.child).exists())
