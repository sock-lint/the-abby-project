"""Direct tests for the toast & ceremony operations added 2026-05-11.

These call ``apps.dev_tools.operations`` directly with resolved User objects
(skipping the management-command and DRF view layers). The HTTP wiring +
permission gates live in ``test_views.py``; the family-scoping resolution
happens in ``config.viewsets.get_child_or_404`` which both views use.

Each op gets coverage for: happy path, at least one failure mode, and the
shape of the returned dict (which the frontend cards read for the result
line). The pre-positioning ops (``set_pet_growth``, ``grant_hatch_ingredients``,
``clear_mount_breed_cooldowns``) intentionally do NOT fire the resulting
ceremony — they just write state — so the assertions stop at "state was
written."
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from django.utils import timezone

from config.tests.factories import make_family


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ForceApprovalNotificationTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_chore_approved_writes_notification_row(self):
        from apps.dev_tools.operations import force_approval_notification
        from apps.notifications.models import Notification

        result = force_approval_notification(
            self.child, flow="chore", outcome="approved",
        )
        self.assertEqual(result["notification_type"], "chore_approved")
        n = Notification.objects.get(pk=result["notification_id"])
        self.assertEqual(n.user, self.child)
        self.assertEqual(n.notification_type, "chore_approved")
        self.assertIn("simulated approval", n.message)

    def test_exchange_rejected_maps_to_exchange_denied(self):
        from apps.dev_tools.operations import force_approval_notification

        result = force_approval_notification(
            self.child, flow="exchange", outcome="rejected",
        )
        self.assertEqual(result["notification_type"], "exchange_denied")

    def test_reject_with_note_lands_in_body(self):
        from apps.dev_tools.operations import force_approval_notification

        result = force_approval_notification(
            self.child, flow="homework", outcome="rejected",
            note="needs more sources",
        )
        self.assertIn("needs more sources", result["message"])

    def test_unknown_flow_raises_operation_error(self):
        from apps.dev_tools.operations import OperationError, force_approval_notification

        with self.assertRaises(OperationError):
            force_approval_notification(
                self.child, flow="nope", outcome="approved",
            )


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ForceQuestProgressTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def _make_definition(self):
        from apps.quests.models import QuestDefinition

        return QuestDefinition.objects.create(
            name="Test Boss",
            description="A test foe.",
            icon="⚔️",
            quest_type=QuestDefinition.QuestType.BOSS,
            target_value=100,
            duration_days=7,
            coin_reward=20,
            xp_reward=50,
            is_system=True,
        )

    def test_bumps_existing_active_quest(self):
        from apps.dev_tools.operations import force_quest_progress
        from apps.quests.models import Quest
        from apps.quests.services import QuestService

        definition = self._make_definition()
        QuestService.start_quest(self.child, definition.pk)

        result = force_quest_progress(self.child, delta=15)
        self.assertEqual(result["delta"], 15)
        self.assertEqual(result["current_progress"], 15)
        self.assertEqual(result["target_value"], 100)
        self.assertEqual(result["progress_percent"], 15.0)

        quest = Quest.objects.get(participants__user=self.child)
        self.assertEqual(quest.current_progress, 15)

    def test_creates_quest_when_no_active_one(self):
        from apps.dev_tools.operations import force_quest_progress
        from apps.quests.models import Quest

        self._make_definition()
        result = force_quest_progress(self.child, delta=10)
        self.assertEqual(result["current_progress"], 10)
        self.assertTrue(
            Quest.objects.filter(
                participants__user=self.child, status="active",
            ).exists(),
        )

    def test_caps_at_target_value(self):
        from apps.dev_tools.operations import force_quest_progress
        from apps.quests.services import QuestService

        definition = self._make_definition()
        QuestService.start_quest(self.child, definition.pk)
        force_quest_progress(self.child, delta=80)
        result = force_quest_progress(self.child, delta=80)
        self.assertEqual(result["current_progress"], 100)
        self.assertEqual(result["progress_percent"], 100.0)

    def test_no_eligible_definition_raises(self):
        from apps.dev_tools.operations import OperationError, force_quest_progress

        with self.assertRaises(OperationError) as ctx:
            force_quest_progress(self.child, delta=10)
        self.assertIn("QuestDefinition", str(ctx.exception))


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class MarkDailyChallengeReadyTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]

    def test_creates_and_marks_complete(self):
        from apps.dev_tools.operations import mark_daily_challenge_ready
        from apps.quests.models import DailyChallenge

        result = mark_daily_challenge_ready(self.child)
        self.assertTrue(result["ready"])
        self.assertEqual(
            result["current_progress"], result["target_value"],
        )
        row = DailyChallenge.objects.get(pk=result["challenge_id"])
        self.assertEqual(row.current_progress, row.target_value)
        self.assertIsNotNone(row.completed_at)
        self.assertTrue(row.is_complete)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class SetPetGrowthTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}, {"username": "sib"}],
        )
        self.child = fam.children[0]
        self.sibling = fam.children[1]
        from apps.pets.models import PetSpecies, PotionType, UserPet

        species = PetSpecies.objects.create(
            slug="fox", name="Fox", icon="🦊",
        )
        potion_a = PotionType.objects.create(slug="ember", name="Ember")
        potion_b = PotionType.objects.create(slug="frost", name="Frost")
        self.pet = UserPet.objects.create(
            user=self.child, species=species, potion=potion_a,
            growth_points=10, evolved_to_mount=False,
        )
        self.evolved_pet = UserPet.objects.create(
            user=self.child, species=species, potion=potion_b,
            growth_points=100, evolved_to_mount=True,
        )

    def test_happy_path(self):
        from apps.dev_tools.operations import set_pet_growth

        result = set_pet_growth(self.child, pet_id=self.pet.pk, growth=99)
        self.assertEqual(result["growth_points"], 99)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 99)

    def test_other_users_pet_raises(self):
        from apps.dev_tools.operations import OperationError, set_pet_growth

        with self.assertRaises(OperationError):
            set_pet_growth(self.sibling, pet_id=self.pet.pk)

    def test_evolved_pet_raises(self):
        from apps.dev_tools.operations import OperationError, set_pet_growth

        with self.assertRaises(OperationError):
            set_pet_growth(self.child, pet_id=self.evolved_pet.pk)

    def test_out_of_range_growth_raises(self):
        from apps.dev_tools.operations import OperationError, set_pet_growth

        with self.assertRaises(OperationError):
            set_pet_growth(self.child, pet_id=self.pet.pk, growth=100)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class GrantHatchIngredientsTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]
        from apps.pets.models import PetSpecies, PotionType
        from apps.rpg.models import ItemDefinition

        self.species = PetSpecies.objects.create(
            slug="fox", name="Fox", icon="🦊",
        )
        self.potion = PotionType.objects.create(slug="ember", name="Ember")
        ItemDefinition.objects.create(
            slug="egg-fox", name="Fox Egg", icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            pet_species=self.species,
        )
        ItemDefinition.objects.create(
            slug="potion-ember", name="Ember Potion", icon="🧪",
            item_type=ItemDefinition.ItemType.POTION,
            potion_type=self.potion,
        )

    def test_drops_egg_and_potion_into_inventory(self):
        from apps.dev_tools.operations import grant_hatch_ingredients
        from apps.rpg.models import UserInventory

        result = grant_hatch_ingredients(
            self.child, species_slug="fox", potion_slug="ember",
        )
        self.assertEqual(result["egg"]["slug"], "egg-fox")
        self.assertEqual(result["potion"]["slug"], "potion-ember")
        self.assertEqual(
            UserInventory.objects.filter(user=self.child).count(), 2,
        )

    def test_missing_species_raises(self):
        from apps.dev_tools.operations import OperationError, grant_hatch_ingredients

        with self.assertRaises(OperationError):
            grant_hatch_ingredients(
                self.child, species_slug="nope", potion_slug="ember",
            )

    def test_restricted_species_potion_combo_raises(self):
        from apps.dev_tools.operations import OperationError, grant_hatch_ingredients
        from apps.pets.models import PotionType

        # Narrow species.available_potions to a different potion so the
        # selected combo is rejected.
        other = PotionType.objects.create(slug="frost", name="Frost")
        self.species.available_potions.set([other])
        with self.assertRaises(OperationError):
            grant_hatch_ingredients(
                self.child, species_slug="fox", potion_slug="ember",
            )


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ClearBreedCooldownsTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]
        from apps.pets.models import PetSpecies, PotionType, UserMount

        species = PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        potion_a = PotionType.objects.create(slug="ember", name="Ember")
        potion_b = PotionType.objects.create(slug="frost", name="Frost")
        now = timezone.now()
        self.m1 = UserMount.objects.create(
            user=self.child, species=species, potion=potion_a,
            last_bred_at=now,
        )
        self.m2 = UserMount.objects.create(
            user=self.child, species=species, potion=potion_b,
            last_bred_at=now,
        )

    def test_clears_all_when_no_mount_id(self):
        from apps.dev_tools.operations import clear_mount_breed_cooldowns

        result = clear_mount_breed_cooldowns(self.child)
        self.assertEqual(result["mounts_reset"], 2)
        self.m1.refresh_from_db()
        self.m2.refresh_from_db()
        self.assertIsNone(self.m1.last_bred_at)
        self.assertIsNone(self.m2.last_bred_at)

    def test_clears_only_named_mount(self):
        from apps.dev_tools.operations import clear_mount_breed_cooldowns

        result = clear_mount_breed_cooldowns(self.child, mount_id=self.m1.pk)
        self.assertEqual(result["mounts_reset"], 1)
        self.m1.refresh_from_db()
        self.m2.refresh_from_db()
        self.assertIsNone(self.m1.last_bred_at)
        self.assertIsNotNone(self.m2.last_bred_at)

    def test_unknown_mount_raises(self):
        from apps.dev_tools.operations import OperationError, clear_mount_breed_cooldowns

        with self.assertRaises(OperationError):
            clear_mount_breed_cooldowns(self.child, mount_id=99999)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class SeedCompanionGrowthTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]
        from apps.pets.models import PetSpecies

        PetSpecies.objects.create(
            slug="companion", name="Companion", icon="🐾",
            sprite_key="companion",
        )

    def test_appends_ticks_to_queue(self):
        from apps.dev_tools.operations import seed_companion_growth
        from apps.rpg.models import CharacterProfile

        result = seed_companion_growth(self.child, ticks=3)
        self.assertEqual(result["events_seeded"], 3)
        self.assertFalse(result["has_evolve_event"])

        profile = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(len(profile.pending_companion_growth), 3)

    def test_force_evolve_flags_final_entry(self):
        from apps.dev_tools.operations import seed_companion_growth
        from apps.rpg.models import CharacterProfile

        result = seed_companion_growth(self.child, ticks=2, force_evolve=True)
        self.assertTrue(result["has_evolve_event"])
        profile = CharacterProfile.objects.get(user=self.child)
        events = profile.pending_companion_growth
        self.assertEqual(len(events), 2)
        self.assertTrue(events[-1]["evolved"])
        self.assertEqual(events[-1]["new_growth"], 100)

    def test_missing_companion_species_raises(self):
        from apps.dev_tools.operations import OperationError, seed_companion_growth
        from apps.pets.models import PetSpecies

        PetSpecies.objects.filter(slug="companion").delete()
        with self.assertRaises(OperationError):
            seed_companion_growth(self.child)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class MarkExpeditionReadyTests(TestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "p"}],
            children=[{"username": "abby"}],
        )
        self.child = fam.children[0]
        from apps.pets.models import PetSpecies, PotionType, UserMount

        species = PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        potion = PotionType.objects.create(slug="ember", name="Ember")
        self.mount = UserMount.objects.create(
            user=self.child, species=species, potion=potion,
        )

    def test_creates_ready_expedition_with_backdated_returns_at(self):
        from apps.dev_tools.operations import mark_expedition_ready
        from apps.pets.models import MountExpedition

        result = mark_expedition_ready(
            self.child, mount_id=self.mount.pk, tier="standard",
        )
        self.assertEqual(result["tier"], "standard")
        self.assertIsNotNone(result["coins"])
        exp = MountExpedition.objects.get(pk=result["expedition_id"])
        self.assertEqual(exp.status, MountExpedition.Status.ACTIVE)
        # returns_at backdated so the row reads as ready immediately
        self.assertTrue(exp.is_ready)

    def test_picks_first_available_mount_when_id_omitted(self):
        from apps.dev_tools.operations import mark_expedition_ready

        result = mark_expedition_ready(self.child, tier="short")
        self.assertEqual(result["mount_id"], self.mount.pk)

    def test_already_active_expedition_raises(self):
        from apps.dev_tools.operations import OperationError, mark_expedition_ready

        mark_expedition_ready(self.child, mount_id=self.mount.pk)
        with self.assertRaises(OperationError):
            mark_expedition_ready(self.child, mount_id=self.mount.pk)

    def test_unknown_tier_raises(self):
        from apps.dev_tools.operations import OperationError, mark_expedition_ready

        with self.assertRaises(OperationError):
            mark_expedition_ready(
                self.child, mount_id=self.mount.pk, tier="nope",
            )

    def test_no_free_mount_raises(self):
        from apps.dev_tools.operations import OperationError, mark_expedition_ready
        from apps.pets.models import UserMount

        UserMount.objects.filter(user=self.child).delete()
        with self.assertRaises(OperationError):
            mark_expedition_ready(self.child, tier="standard")
