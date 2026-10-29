"""Real reading/movement saves feed discoveries without changing their rewards."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import UUID

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementDailyCounter, MovementType, MovementTypeSkillTag
from apps.movement.services import MovementSessionService
from apps.reading.models import ReadingDailyReward
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


FIXED_NOW = datetime(2026, 10, 20, 19, tzinfo=datetime_timezone.utc)


def request_uuid(number):
    return str(UUID(int=number))


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
    EGG_DISCOVERY_ENABLED=True,
)
class EggDiscoverySourceAdapterTests(APITestCase):
    def setUp(self):
        from apps.egg_discoveries.tests.factories import ASSET_POLICY

        policy = override_settings(RPG_ASSET_SUPPORT_POLICY=ASSET_POLICY)
        policy.enable()
        self.addCleanup(policy.disable)
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Discovery adapter family", parents=[{"username": "discovery-parent"}],
            children=[{"username": "discovery-child"}, {"username": "discovery-sibling"}],
        )
        household.family.timezone = "America/Phoenix"
        household.family.save(update_fields=["timezone"])
        self.child, self.sibling = household.children
        self.parent = household.parents[0]
        self.outsider = make_family("Other discovery family", children=[{"username": "other-discovery-child"}]).children[0]
        self.client.force_authenticate(self.child)
        self.reading_skill = Skill.objects.create(
            category=SkillCategory.objects.create(name="Language Arts"), name="Reading Comprehension",
        )
        self.movement_skill = Skill.objects.create(
            category=SkillCategory.objects.create(name="Physical"), name="Movement practice",
        )
        self.movement_type = MovementType.objects.create(name="Discovery walking", slug="discovery-walking")
        MovementTypeSkillTag.objects.create(movement_type=self.movement_type, skill=self.movement_skill)
        self.book = self.client.post("/api/reading-books/", {
            "title": "Synthetic discovery book", "client_request_id": request_uuid(1),
        }, format="json").json()

    def _select_ordinary(self):
        from apps.egg_discoveries.models import EggDiscovery
        from apps.egg_discoveries.tests.factories import make_catalog

        make_catalog()
        response = self.client.get("/api/egg-discoveries/")
        self.assertEqual(response.status_code, 200, response.content)
        ordinary = next(offer for offer in response.json()["offers"] if offer["tier"] == "ordinary")
        selected = self.client.post("/api/egg-discoveries/select/", {
            "offer_key": ordinary["key"], "client_request_id": request_uuid(2),
        }, format="json")
        self.assertEqual(selected.status_code, 201, selected.content)
        return EggDiscovery.objects.get(user=self.child, status="active")

    def _read(self, number, minutes=0, **extra):
        response = self.client.post("/api/reading-sessions/", {
            "book": self.book["id"], "duration_minutes": minutes,
            "client_request_id": request_uuid(number), **extra,
        }, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)
        return response

    def _move(self, number, minutes=10, **extra):
        return MovementSessionService.log_session(
            self.child, movement_type=self.movement_type, duration_minutes=minutes,
            client_request_id=UUID(request_uuid(number)), **extra,
        )

    def test_discovery_endpoint_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/egg-discoveries/").status_code, 401)

    def test_reading_credits_full_new_minutes_after_daily_reading_reward_is_capped(self):
        discovery = self._select_ordinary()
        self._read(10, 35)
        self._read(11, 40, format="audiobook")
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes.get("reading"), 75)
        daily = ReadingDailyReward.objects.get(user=self.child)
        self.assertEqual(daily.minutes_credited, 10)
        self.assertEqual(daily.coins_awarded, 5)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.reading_skill).xp_points, 15)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child, reason="reading").values_list("amount", flat=True)), [5])

    def test_reading_history_notes_replay_and_deleted_uuid_never_supply_new_progress(self):
        discovery = self._select_ordinary()
        first = self._read(20, 35).json()
        self.assertEqual(self._read(20, 35).status_code, 200)
        corrected = self.client.patch(f"/api/reading-sessions/{first['id']}/", {
            "duration_minutes": 600,
        }, format="json")
        self.assertEqual(corrected.status_code, 200, corrected.content)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{first['id']}/").status_code, 204)
        self._read(20, 35)
        old_day = (FIXED_NOW - timedelta(days=1)).date().isoformat()
        old = self._read(21, 90, occurred_on=old_day).json()
        notes = self._read(22, 0, section="Finished the introduction").json()
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{old['id']}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{notes['id']}/").status_code, 204)
        # Request tombstones preserve zero eligibility after deletion too.
        self._read(21, 90)
        self._read(22, 90)
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes.get("reading"), 35)
        self.assertEqual(discovery.searches.count(), 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="reading").count(), 1)

    def test_movement_over_daily_xp_cap_still_contributes_full_discovery_minutes(self):
        discovery = self._select_ordinary()
        sessions = [self._move(30 + number) for number in range(3)]
        sessions.append(self._move(33, 45))
        self.assertEqual([session.xp_awarded for session in sessions], [5, 5, 5, 0])
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes.get("movement"), 75)
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 4)

    def test_movement_deleted_uuid_and_historical_source_cannot_create_new_searches(self):
        discovery = self._select_ordinary()
        session = self._move(40, 30)
        self.assertEqual(self._move(40, 30).pk, session.pk)
        session.delete()
        self._move(40, 30)
        historical = self._move(41, 60, occurred_at=FIXED_NOW - timedelta(days=1))
        historical.delete()
        self._move(41, 60)
        discovery.refresh_from_db()
        self.assertEqual(discovery.minutes.get("movement"), 30)
        self.assertEqual(discovery.searches.count(), 0)

    def test_another_child_or_parent_cannot_read_or_pause_the_owners_discovery(self):
        discovery = self._select_ordinary()
        self._read(45, 35)
        for actor in (self.sibling, self.outsider, self.parent):
            self.client.force_authenticate(actor)
            response = self.client.get("/api/egg-discoveries/", {"user_id": self.child.pk})
            self.assertEqual(response.status_code, 400, response.content)
            response = self.client.get("/api/egg-discoveries/")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["discoveries"], [])
            self.assertIsNone(response.json()["active_id"])
            paused = self.client.post(f"/api/egg-discoveries/{discovery.pk}/pause/", {
                "client_request_id": request_uuid(46),
            }, format="json")
            self.assertEqual(paused.status_code, 404, paused.content)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertEqual(discovery.minutes.get("reading"), 35)

    def test_work_saved_before_selecting_a_target_is_not_banked_or_replayed_into_it(self):
        previous = self._read(47, 60).json()
        discovery = self._select_ordinary()
        self._read(47, 60)
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{previous['id']}/").status_code, 204)
        self._read(47, 60)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)

    def test_reading_uuid_saved_before_enable_cannot_gain_credit_after_delete_and_recreate(self):
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            original = self._read(48, 60).json()
        discovery = self._select_ordinary()
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{original['id']}/").status_code, 204)
        self._read(48, 60)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)

    def test_surviving_movement_uuid_saved_before_enable_remains_a_replay(self):
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            original = self._move(49, 60)
        discovery = self._select_ordinary()
        self.assertEqual(self._move(49, 60).pk, original.pk)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)

    def test_movement_uuid_saved_before_enable_cannot_gain_credit_after_delete_and_recreate(self):
        with override_settings(EGG_DISCOVERY_ENABLED=False):
            original = self._move(55, 60)
        discovery = self._select_ordinary()
        original.delete()
        self._move(55, 60)
        discovery.refresh_from_db()
        self.assertEqual(sum(discovery.minutes.values()), 0)

    def test_rebound_egg_does_not_rollback_movement_logs_or_their_normal_rewards(self):
        from apps.rpg.models import ItemDefinition

        discovery = self._select_ordinary()
        self._read(70, 150)
        ItemDefinition.objects.filter(pk=discovery.egg_item_id).update(metadata={"species": "changed-binding"})
        sessions = [self._move(71, 90), self._move(72, 30)]
        self.assertEqual([session.xp_awarded for session in sessions], [45, 15])
        self.assertEqual(MovementDailyCounter.objects.get(user=self.child).count, 2)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertIsNone(discovery.reward_receipt)
        self.assertEqual(discovery.minutes, {"reading": 150, "movement": 120, "practice": 0})

    def test_busy_discovery_catalog_does_not_rollback_reading_or_its_daily_reward(self):
        from apps.quests.availability import RetryCatalogBusy

        discovery = self._select_ordinary()
        self._move(73, 90)
        with patch("apps.egg_discoveries.services.lock_retry_reward_catalog",
                   side_effect=RetryCatalogBusy("Synthetic catalog contention")):
            self._read(74, 150)
        discovery.refresh_from_db()
        self.assertEqual(discovery.status, "active")
        self.assertIsNone(discovery.reward_receipt)
        self.assertEqual(discovery.minutes, {"reading": 150, "movement": 90, "practice": 0})
        daily = ReadingDailyReward.objects.get(user=self.child)
        self.assertEqual((daily.minutes_credited, daily.coins_awarded), (10, 5))
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.reading_skill).xp_points, 15)

    @override_settings(EGG_DISCOVERY_ENABLED=False)
    def test_feature_off_preserves_ordinary_reading_and_movement_rewards(self):
        from apps.egg_discoveries.models import DiscoveryActivityCredit, EggDiscovery

        self._read(50, 40)
        sessions = [self._move(51 + number, 30) for number in range(4)]
        self.assertEqual([session.xp_awarded for session in sessions], [15, 15, 15, 0])
        self.assertEqual(ReadingDailyReward.objects.get(user=self.child).minutes_credited, 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.reading_skill).xp_points, 15)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child, reason="reading").values_list("amount", flat=True)), [5])
        # Normal movement writes retain request identities for a future
        # activation, but the disabled feature earns no progress or rewards.
        self.assertEqual(DiscoveryActivityCredit.objects.filter(source_kind="movement_session").count(), 4)
        self.assertFalse(DiscoveryActivityCredit.objects.exclude(credited_minutes=0).exists())
        self.assertFalse(EggDiscovery.objects.exists())
