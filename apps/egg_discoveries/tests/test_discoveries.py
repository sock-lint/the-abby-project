from datetime import timedelta
from itertools import permutations
from unittest.mock import patch
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, UserMount, UserPet
from apps.quests.activity import household_timezone
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, UserInventory
from config.tests.factories import make_family

from apps.egg_discoveries.models import DiscoveryActivityCredit, DiscoveryRequest, DiscoverySearch, EggDiscovery, PracticeSession
from apps.egg_discoveries.services import DiscoveryConflict, credit_activity, envelope, log_practice, pause_discovery, select_discovery
from .factories import ASSET_POLICY, make_catalog


@override_settings(
    EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={}, RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class DiscoveryTests(TestCase):
    def setUp(self):
        family = make_family("Discovery", parents=[{"username": "discovery-parent"}], children=[
            {"username": "discoverer"}, {"username": "discovery-sibling"},
        ])
        self.child, self.sibling = family.children
        self.parent = family.parents[0]
        self.outsider = make_family("Outside", children=[{"username": "outside-discoverer"}]).children[0]
        self.catalog = make_catalog()
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def day(self):
        return timezone.localdate(timezone=household_timezone(self.child))

    def select(self, pair=None, *, request_id=None):
        pair = pair or self.catalog.ordinary
        select_discovery(self.child, offer_key=pair.key, client_request_id=request_id or uuid4())
        return EggDiscovery.objects.get(user=self.child, offer_key=pair.key)

    def credit(self, category, minutes, *, key=None, day=None):
        return credit_activity(self.child, category=category, source_kind="synthetic", source_key=str(key or uuid4()),
                               minutes=minutes, occurred_on=day or self.day())

    def unlock_rare(self):
        for pair in (self.catalog.ordinary, self.catalog.other):
            UserPet.objects.create(user=self.child, species=pair.species, potion=self.catalog.base)

    def quantities(self):
        return dict(UserInventory.objects.filter(user=self.child).values_list("item_id", "quantity"))

    def test_disabled_flag_is_empty_authenticated_read_and_no_progress_or_mutation(self):
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            response = self.client.get("/api/egg-discoveries/")
            self.assertEqual(response.json(), {"enabled": False, "offers": [], "discoveries": [], "active_id": None})
            self.assertEqual(self.client.post("/api/egg-discoveries/select/", {
                "offer_key": self.catalog.ordinary.key, "client_request_id": str(uuid4()),
            }, format="json").status_code, 409)
            credit = self.credit("movement", 120)
            self.assertEqual(credit.credited_minutes, 0)
            self.assertIsNone(credit.discovery_id)
        self.assertEqual(DiscoveryActivityCredit.objects.count(), 1)
        self.assertFalse(EggDiscovery.objects.exists())
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/egg-discoveries/").status_code, 401)

    def test_disabled_source_uuid_remains_spent_when_feature_is_enabled(self):
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            original = credit_activity(self.child, category="movement", source_kind="movement_session", source_key="saved-before-enable",
                                       minutes=120, occurred_on=self.day())
        self.assertIsNotNone(original)
        discovery = self.select()
        replay = credit_activity(self.child, category="movement", source_kind="movement_session", source_key="saved-before-enable",
                                 minutes=120, occurred_on=self.day())
        self.assertEqual(original.pk, replay.pk)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)
        self.assertFalse(UserInventory.objects.exists())
        self.assertFalse(DiscoverySearch.objects.exists())

    def test_disabled_movement_save_delete_and_recreate_uuid_never_gains_credit(self):
        from apps.movement.models import MovementType
        from apps.movement.services import MovementSessionService

        movement_type = MovementType.objects.create(name="Switch-on walking", slug="switch-on-walking")
        request_id = uuid4()
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            original = MovementSessionService.log_session(self.child, movement_type=movement_type,
                duration_minutes=60, client_request_id=request_id)
        discovery = self.select()
        original_id = original.pk
        original.delete()
        recreated = MovementSessionService.log_session(self.child, movement_type=movement_type,
            duration_minutes=60, client_request_id=request_id)
        self.assertNotEqual(recreated.pk, original_id)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)
        receipt = DiscoveryActivityCredit.objects.get(user=self.child, source_kind="movement_session", source_key=str(request_id))
        self.assertEqual(receipt.credited_minutes, 0)
        self.assertIsNone(receipt.discovery_id)

    def test_read_never_accepts_rolls_or_awards_and_exposes_only_egg_presentation(self):
        self.unlock_rare()
        with patch("apps.egg_discoveries.services.random.random") as roll:
            first = self.client.get("/api/egg-discoveries/").json()
            second = self.client.get("/api/egg-discoveries/").json()
        self.assertEqual(first, second)
        self.assertEqual(len(first["offers"]), 3)
        self.assertTrue(next(offer for offer in first["offers"] if offer["tier"] == "rare")["eligible"])
        self.assertEqual(set(first["offers"][0]["egg_item"]), {"id", "name", "icon", "sprite_key"})
        roll.assert_not_called()
        self.assertFalse(EggDiscovery.objects.exists())
        self.assertFalse(UserInventory.objects.exists())

    def test_ordinary_requires_four_hours_and_ninety_minutes_in_two_types(self):
        discovery = self.select()
        with patch("apps.egg_discoveries.services.random.random") as roll:
            self.credit("reading", 150)
            self.credit("practice", 89)
            discovery.refresh_from_db()
            self.assertEqual(discovery.status, "active")
            self.assertEqual(self.quantities(), {})
            self.credit("practice", 1)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "completed")
        self.assertEqual(self.quantities(), {self.catalog.ordinary.egg.pk: 1, self.catalog.potion.pk: 1, self.catalog.food.pk: 2})
        self.assertEqual(discovery.reward_receipt["items"][0]["item_id"], self.catalog.ordinary.egg.pk)
        self.assertIsNone(envelope(self.child)["active_id"])
        self.assertFalse(DiscoverySearch.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(DropLog.objects.exists())
        roll.assert_not_called()

    def test_ordinary_one_type_alone_never_completes_even_after_many_hours(self):
        discovery = self.select()
        self.credit("reading", 600)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertFalse(UserInventory.objects.exists())

    def test_rare_requires_two_distinct_hatched_species_not_two_potion_appearances(self):
        self.assertFalse(next(offer for offer in envelope(self.child)["offers"] if offer["key"] == self.catalog.rare.key)["eligible"])
        UserPet.objects.create(user=self.child, species=self.catalog.ordinary.species, potion=self.catalog.base)
        from apps.pets.models import PotionType
        other_potion = PotionType.objects.create(slug="saved-appearance", name="Saved appearance")
        UserPet.objects.create(user=self.child, species=self.catalog.ordinary.species, potion=other_potion)
        with self.assertRaises(DiscoveryConflict):
            self.select(self.catalog.rare)
        UserPet.objects.create(user=self.child, species=self.catalog.other.species, potion=self.catalog.base, evolved_to_mount=True)
        self.assertEqual(self.select(self.catalog.rare).snapshot["tier"], "rare")

    def test_completed_hatch_receipts_retain_unlock_after_pet_deletion(self):
        now = timezone.now()
        for pair in (self.catalog.ordinary, self.catalog.other):
            PetIncubation.objects.create(user=self.child, request_id=uuid4(), species=pair.species,
                potion_type=self.catalog.base, egg_item=pair.egg, potion_item=self.catalog.potion,
                accepted_pair={}, started_at=now, ready_at=now, hatched_at=now)
        self.assertEqual(self.select(self.catalog.rare).snapshot["tier"], "rare")

    def test_rare_four_misses_then_fifth_guarantee_after_five_balanced_hours(self):
        self.unlock_rare()
        discovery = self.select(self.catalog.rare)
        self.credit("reading", 150)
        key = str(uuid4())
        with patch("apps.egg_discoveries.services.random.random", return_value=0.99) as roll:
            self.credit("movement", 150, key=key)
            self.credit("movement", 150, key=key)
        self.assertEqual(roll.call_count, 4)
        self.assertEqual(list(discovery.searches.values_list("number", "found", "guaranteed")), [
            (1, False, False), (2, False, False), (3, False, False), (4, False, False), (5, True, True),
        ])
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "completed")
        self.assertEqual(self.quantities()[self.catalog.rare.egg.pk], 1)
        self.assertEqual(envelope(self.child)["discoveries"][0]["remaining_searches"], 0)

    def test_rare_twenty_percent_boundary_and_stops_after_first_success(self):
        self.unlock_rare()
        discovery = self.select(self.catalog.rare)
        self.credit("reading", 150)
        with patch("apps.egg_discoveries.services.random.random", side_effect=[0.20, 0.199999]) as roll:
            self.credit("practice", 150)
        self.assertEqual(roll.call_count, 2)
        self.assertEqual(list(discovery.searches.values_list("number", "found")), [(1, False), (2, True)])
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes, {"reading": 150, "movement": 0, "practice": 150})

    def test_rare_activity_order_and_splitting_do_not_strand_third_category(self):
        self.unlock_rare()
        discovery = self.select(self.catalog.rare)
        with patch("apps.egg_discoveries.services.random.random", return_value=0.99) as roll:
            self.credit("reading", 30)
            self.credit("movement", 30)
            self.assertEqual(discovery.searches.count(), 1)
            for _ in range(4):
                self.credit("practice", 15)
        self.assertEqual(discovery.searches.count(), 2)
        self.assertEqual(roll.call_count, 2)

    def test_five_hour_guarantee_works_in_every_three_category_order(self):
        for index, order in enumerate(permutations(("reading", "movement", "practice"))):
            with self.subTest(order=order):
                self.child = make_family(f"Order {index}", children=[{"username": f"order-child-{index}"}]).children[0]
                self.unlock_rare()
                discovery = self.select(self.catalog.rare)
                with patch("apps.egg_discoveries.services.random.random", return_value=0.99) as roll:
                    for category in order:
                        self.credit(category, 100)
                discovery.refresh_from_db()
                self.assertEqual(discovery.status, "completed")
                self.assertEqual(discovery.searches.count(), 5)
                self.assertEqual(roll.call_count, 4)
                self.assertEqual(sum(discovery.minutes.values()), 300)

    def test_splitting_all_three_categories_into_short_sessions_preserves_guarantee(self):
        self.unlock_rare()
        discovery = self.select(self.catalog.rare)
        with patch("apps.egg_discoveries.services.random.random", return_value=0.99) as roll:
            for category in ("reading", "movement", "practice"):
                for _ in range(10):
                    self.credit(category, 10)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "completed")
        self.assertEqual(discovery.searches.count(), 5)
        self.assertEqual(roll.call_count, 4)
        self.assertEqual(discovery.minutes, {"reading": 100, "movement": 100, "practice": 100})

    def test_switching_preserves_totals_and_source_cannot_transfer_or_replay(self):
        first = self.select()
        key = str(uuid4())
        self.credit("reading", 90, key=key)
        second = self.select(self.catalog.other)
        self.credit("reading", 90, key=key)
        self.credit("practice", 30)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "paused")
        self.assertEqual(first.minutes["reading"], 90)
        self.assertEqual(second.minutes, {"reading": 0, "movement": 0, "practice": 30})
        self.select()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("active", "paused"))

    def test_paused_and_historical_and_no_active_sources_remain_spent(self):
        first_key, old_key, paused_key = str(uuid4()), str(uuid4()), str(uuid4())
        self.credit("reading", 120, key=first_key)
        discovery = self.select()
        self.credit("reading", 120, key=old_key, day=self.day() - timedelta(days=1))
        pause_discovery(self.child, discovery_id=discovery.pk, client_request_id=uuid4())
        self.credit("reading", 120, key=paused_key)
        self.select()
        for key in (first_key, old_key, paused_key):
            self.credit("reading", 120, key=key)
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes["reading"], 0)
        self.assertEqual(DiscoveryActivityCredit.objects.count(), 3)

    def test_source_tombstone_survives_discovery_removal_and_cannot_move(self):
        first = self.select()
        self.credit("reading", 90, key="retained-source")
        first.delete()
        second = self.select(self.catalog.other)
        self.credit("reading", 90, key="retained-source")
        second.refresh_from_db()
        self.assertEqual(second.minutes["reading"], 0)
        credit = DiscoveryActivityCredit.objects.get(source_key="retained-source")
        self.assertIsNone(credit.discovery_id)
        self.assertEqual(credit.credited_minutes, 90)

    def test_season_only_gates_initial_start_and_frozen_promise_resumes_after_retirement(self):
        day = self.day()
        season = {"starts_on": day.isoformat(), "ends_on": day.isoformat()}
        with override_settings(EGG_DISCOVERY_SEASONS={self.catalog.ordinary.key: season}):
            discovery = self.select()
        pause_discovery(self.child, discovery_id=discovery.pk, client_request_id=uuid4())
        with override_settings(RPG_ASSET_SUPPORT_POLICY={**ASSET_POLICY, "pets": []},
                               EGG_DISCOVERY_SEASONS={self.catalog.ordinary.key: {"starts_on": "2000-01-01", "ends_on": "2000-01-02"}}):
            self.select()
            self.credit("reading", 150)
            self.credit("practice", 90)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "completed")
        self.assertEqual(discovery.snapshot["season"], season)
        self.assertEqual(self.quantities()[self.catalog.ordinary.egg.pk], 1)

    def test_closed_or_malformed_season_cannot_accept_new_discovery(self):
        for season in ({"starts_on": "2000-01-01", "ends_on": "2000-01-02"},
                       {"starts_on": "2026-12-01", "ends_on": "2026-01-01"}, {"starts_on": "invalid"}):
            with self.subTest(season=season), override_settings(EGG_DISCOVERY_SEASONS={self.catalog.ordinary.key: season}):
                with self.assertRaises(DiscoveryConflict):
                    self.select()
        self.assertFalse(EggDiscovery.objects.exists())

    def test_owned_pending_and_inventory_pairs_cannot_start_duplicate_discovery(self):
        pair = self.catalog.ordinary
        inventory = UserInventory.objects.create(user=self.child, item=pair.egg, quantity=1)
        with self.assertRaises(DiscoveryConflict):
            self.select()
        inventory.delete()
        mount = UserMount.objects.create(user=self.child, species=pair.species, potion=self.catalog.base)
        with self.assertRaises(DiscoveryConflict):
            self.select()
        mount.delete()
        now = timezone.now()
        PetIncubation.objects.create(user=self.child, request_id=uuid4(), species=pair.species, potion_type=self.catalog.base,
            egg_item=pair.egg, potion_item=self.catalog.potion, accepted_pair={}, started_at=now, ready_at=now)
        with self.assertRaises(DiscoveryConflict):
            self.select()

    def test_changed_reward_binding_fails_closed_and_rolls_back_source(self):
        discovery = self.select()
        self.credit("reading", 150)
        self.catalog.ordinary.egg.pet_species = self.catalog.other.species
        self.catalog.ordinary.egg.save(update_fields=["pet_species"])
        with self.assertRaises(DiscoveryConflict):
            self.credit("practice", 90, key="rebound")
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertEqual(discovery.minutes["practice"], 0)
        self.assertFalse(DiscoveryActivityCredit.objects.filter(source_key="rebound").exists())
        self.assertFalse(UserInventory.objects.exists())

    def test_failed_reward_rolls_back_search_credit_and_inventory_together(self):
        self.unlock_rare()
        discovery = self.select(self.catalog.rare)
        self.credit("reading", 30)
        with patch("apps.egg_discoveries.services.random.random", return_value=0), patch(
            "apps.egg_discoveries.services.grant_item", side_effect=RuntimeError("synthetic reward failure"),
        ), self.assertRaisesRegex(RuntimeError, "synthetic reward failure"):
            self.credit("practice", 30, key="failed")
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertEqual(discovery.minutes["practice"], 0)
        self.assertFalse(DiscoverySearch.objects.exists())
        self.assertFalse(DiscoveryActivityCredit.objects.filter(source_key="failed").exists())
        with patch("apps.egg_discoveries.services.random.random", return_value=0):
            self.credit("practice", 30, key="failed")
        self.assertEqual(self.quantities()[self.catalog.rare.egg.pk], 1)

    def test_uuid_commands_replay_without_reactivating_or_recrediting(self):
        request_id = uuid4()
        first = self.select(request_id=request_id)
        self.select(self.catalog.other)
        self.assertFalse(select_discovery(self.child, offer_key=self.catalog.ordinary.key, client_request_id=request_id))
        first.refresh_from_db()
        self.assertEqual(first.status, "paused")
        with self.assertRaises(DiscoveryConflict):
            select_discovery(self.child, offer_key=self.catalog.other.key, client_request_id=request_id)
        with self.assertRaises(DiscoveryConflict):
            log_practice(self.child, name="Drawing", minutes=30, client_request_id=request_id)
        practice_id = uuid4()
        self.assertTrue(log_practice(self.child, name=" Drawing ", minutes=30, client_request_id=practice_id))
        self.assertFalse(log_practice(self.child, name="Drawing", minutes=30, client_request_id=practice_id))
        with self.assertRaises(DiscoveryConflict):
            log_practice(self.child, name="Drawing", minutes=60, client_request_id=practice_id)
        self.assertEqual(PracticeSession.objects.count(), 1)

    def test_account_and_parent_reads_are_self_scoped_and_selectors_rejected(self):
        discovery = self.select()
        for observer in (self.sibling, self.parent, self.outsider):
            self.client.force_authenticate(observer)
            self.assertEqual(self.client.get("/api/egg-discoveries/").json()["discoveries"], [])
            self.assertEqual(self.client.get(f"/api/egg-discoveries/?user_id={self.child.pk}").status_code, 400)
            self.assertEqual(self.client.post(f"/api/egg-discoveries/{discovery.pk}/pause/", {
                "client_request_id": str(uuid4()),
            }, format="json").status_code, 404)
        self.client.force_authenticate(self.parent)
        response = self.client.post("/api/egg-discoveries/select/", {
            "offer_key": self.catalog.ordinary.key, "client_request_id": str(uuid4()),
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(EggDiscovery.objects.get(pk=response.json()["active_id"]).user_id, self.parent.pk)

    def test_practice_api_rejects_invalid_and_reward_control_fields(self):
        self.select()
        for fields in ({"minutes": 0}, {"minutes": 241}, {"minutes": True}, {"name": " "}, {"user_id": self.sibling.pk},
                       {"category": "reading"}, {"found": True}, {"coins": 1000}):
            response = self.client.post("/api/egg-discoveries/practice/", {
                "name": "Drawing", "minutes": 30, "client_request_id": str(uuid4()), **fields,
            }, format="json")
            self.assertEqual(response.status_code, 400, (fields, response.content))
        self.assertFalse(PracticeSession.objects.exists())

    def test_protected_rewards_and_database_active_constraint_preserve_promises(self):
        first = self.select()
        with self.assertRaises(ProtectedError):
            self.catalog.food.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            EggDiscovery.objects.create(user=self.child, offer_key=self.catalog.other.key, species=self.catalog.other.species,
                potion_type=self.catalog.base, egg_item=self.catalog.other.egg, potion_item=self.catalog.potion,
                food_item=self.catalog.food, snapshot=first.snapshot)
        self.child.delete()
        self.assertFalse(EggDiscovery.objects.exists())
        self.assertFalse(DiscoveryRequest.objects.exists())
