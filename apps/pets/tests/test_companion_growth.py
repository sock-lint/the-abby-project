"""Tests for the companion auto-growth surface — the silent daily tick
that's now visible as a frontend toast (or escalates to the evolve modal
when growth crosses the threshold)."""

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.pets.services import COMPANION_DAILY_GROWTH, EVOLUTION_THRESHOLD, PetService
from apps.projects.models import User
from apps.rpg.models import CharacterProfile


class CompanionAutoGrowthEventsTest(TestCase):
    """``auto_grow_companions`` now returns a per-pet event list and
    persists it to ``CharacterProfile.pending_companion_growth`` so the
    frontend can render toasts on the next page load."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="companionkid", password="test", role="child",
        )
        self.species = PetSpecies.objects.create(
            name="Companion", slug="companion",
            icon="\U0001f43e", food_preference="any",
        )
        self.potion = PotionType.objects.create(
            name="Fire", slug="fire", color_hex="#FF4500", rarity="common",
        )

    def _make_pet(self, growth=0):
        return UserPet.objects.create(
            user=self.user, species=self.species, potion=self.potion,
            growth_points=growth,
        )

    def test_returns_event_per_pet_with_growth_delta(self):
        pet = self._make_pet(growth=10)
        result = PetService.auto_grow_companions(self.user)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["pet_id"], pet.pk)
        self.assertEqual(event["growth_added"], COMPANION_DAILY_GROWTH)
        self.assertEqual(event["new_growth"], 10 + COMPANION_DAILY_GROWTH)
        self.assertFalse(event["evolved"])
        self.assertIsNone(event["mount_id"])
        # Surface fields the toast renders.
        self.assertEqual(event["species_name"], "Companion")
        self.assertEqual(event["potion_name"], "Fire")
        self.assertEqual(event["potion_slug"], "fire")

    def test_evolved_event_marks_evolved_and_mount_id(self):
        # One growth step away from evolving — auto-grow should push it over.
        pet = self._make_pet(growth=EVOLUTION_THRESHOLD - COMPANION_DAILY_GROWTH)
        result = PetService.auto_grow_companions(self.user)
        self.assertEqual(result["evolved"], 1)
        event = result["events"][0]
        self.assertTrue(event["evolved"])
        self.assertIsNotNone(event["mount_id"])
        # The mount row exists.
        self.assertTrue(UserMount.objects.filter(pk=event["mount_id"]).exists())
        pet.refresh_from_db()
        self.assertTrue(pet.evolved_to_mount)

    def test_persists_events_to_pending_queue(self):
        self._make_pet(growth=5)
        PetService.auto_grow_companions(self.user)
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(len(profile.pending_companion_growth), 1)
        self.assertEqual(profile.pending_companion_growth[0]["growth_added"], COMPANION_DAILY_GROWTH)

    def test_pending_queue_accumulates_across_calls(self):
        """Multiple un-seen daily ticks should stack so a returning user
        sees every tick they missed without polling daily check-ins."""
        self._make_pet(growth=5)
        PetService.auto_grow_companions(self.user)
        PetService.auto_grow_companions(self.user)
        PetService.auto_grow_companions(self.user)
        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(len(profile.pending_companion_growth), 3)

    def test_no_events_when_no_companion_pets_exist(self):
        # User has no companion pets.
        result = PetService.auto_grow_companions(self.user)
        self.assertEqual(result["events"], [])
        # Doesn't create a profile / pending queue if there's nothing to log.
        # (Profile may exist via signal — check it's still empty either way.)
        profile = CharacterProfile.objects.filter(user=self.user).first()
        if profile is not None:
            self.assertEqual(profile.pending_companion_growth, [])


class CompanionGrowthEndpointsTest(TestCase):
    """The recent + seen endpoints surface and clear the pending queue."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="endpointkid", password="test", role="child",
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.species = PetSpecies.objects.create(
            name="Companion", slug="companion",
            icon="\U0001f43e", food_preference="any",
        )
        self.potion = PotionType.objects.create(
            name="Fire", slug="fire", color_hex="#FF4500", rarity="common",
        )
        UserPet.objects.create(
            user=self.user, species=self.species, potion=self.potion,
            growth_points=10,
        )

    def test_recent_returns_pending_events(self):
        PetService.auto_grow_companions(self.user)
        response = self.client.get("/api/pets/companion-growth/recent/")
        self.assertEqual(response.status_code, 200)
        events = response.data["events"]
        self.assertEqual(len(events), 1)
        self.assertIn("growth_added", events[0])

    def test_recent_empty_when_no_pending(self):
        response = self.client.get("/api/pets/companion-growth/recent/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["events"], [])

    def test_seen_clears_pending_queue(self):
        PetService.auto_grow_companions(self.user)
        response = self.client.post("/api/pets/companion-growth/seen/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["cleared"])
        # Subsequent recent call returns empty.
        recent = self.client.get("/api/pets/companion-growth/recent/")
        self.assertEqual(recent.data["events"], [])

    def test_seen_is_idempotent(self):
        # Calling seen twice on an empty queue is a no-op.
        self.client.post("/api/pets/companion-growth/seen/")
        response = self.client.post("/api/pets/companion-growth/seen/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["cleared"])

    def test_recent_is_self_scoped(self):
        """Another user's pending queue is invisible from this token."""
        other = User.objects.create_user(
            username="othershore", password="test", role="child",
        )
        UserPet.objects.create(
            user=other, species=self.species, potion=self.potion,
            growth_points=10,
        )
        PetService.auto_grow_companions(other)

        response = self.client.get("/api/pets/companion-growth/recent/")
        self.assertEqual(response.status_code, 200)
        # No leak — this user has no pending events.
        self.assertEqual(response.data["events"], [])
