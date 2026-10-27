"""Real Coin producers keep their amounts and once-only gates when attributed."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.services import AwardService
from apps.activity.models import ActivityEvent
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chronicle.tasks import chronicle_birthday_check
from apps.chores.models import Chore, ChoreCompletion
from apps.dev_tools.operations import force_drop
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import AdjustCoinsIn
from apps.mcp_server.tools.rewards import adjust_coins
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.projects.savings_service import SavingsGoalService
from apps.quests.goals import _occurrence, ingest_activity
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, PerfectDayReceipt, UserInventory
from apps.rpg.services import ConsumableService, DropService, GameLoopService
from apps.rpg.tasks import evaluate_perfect_day_task
from apps.wellbeing.models import DailyWellbeingEntry
from apps.wellbeing.services import WellbeingService
from config.tests.factories import make_family


SYNTHETIC_POLICY = {
    "schema_version": 1,
    "pets": [{"species_slug": "source-species", "sprite_key": "source-sprite",
              "potion_slugs": ["source-base"]}],
    "potion_slugs": ["source-base"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
}


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=SYNTHETIC_POLICY,
    COINS_PER_SAVINGS_GOAL_DOLLAR=2,
)
class CoinSourceProducerTests(TestCase):
    def setUp(self):
        self.household = make_family(
            "Coin source producers", parents=[{"username": "source-parent", "is_staff": True}],
            children=[{"username": "source-child", "date_of_birth": date(2011, 10, 26)}],
        )
        self.parent, self.child = self.household.parents[0], self.household.children[0]
        self.profile = CharacterProfile.objects.get(user=self.child)
        self.profile.last_active_date = timezone.localdate()
        self.profile.login_streak = 20
        self.profile.coin_boost_expires_at = timezone.now() + timedelta(hours=1)
        self.profile.save(update_fields=["last_active_date", "login_streak", "coin_boost_expires_at"])

    def entries(self):
        return list(CoinLedger.objects.filter(user=self.child).order_by("pk").values_list(
            "source", "reason", "amount",
        ))

    def owned_egg(self, user=None):
        species = PetSpecies.objects.create(
            slug="source-species", name="Source species", sprite_key="source-sprite",
        )
        potion = PotionType.objects.create(slug="source-base", name="Source base")
        UserMount.objects.create(user=user or self.child, species=species, potion=potion)
        return ItemDefinition.objects.create(
            slug="source-egg", name="Promised egg", item_type="egg", pet_species=species,
            coin_value=13,
        )

    def owned_frame(self):
        frame = ItemDefinition.objects.create(
            slug="source-frame", name="Source frame", item_type="cosmetic_frame",
            rarity="uncommon", coin_value=250,
        )
        UserInventory.objects.create(user=self.child, item=frame, quantity=1)
        return frame

    def test_daily_check_in_keeps_streak_cap_and_cannot_repeat_or_double(self):
        self.profile.last_active_date = timezone.localdate() - timedelta(days=1)
        self.profile.login_streak = 19
        self.profile.save(update_fields=["last_active_date", "login_streak"])

        GameLoopService.on_task_completed(self.child, "daily_check_in", {"drops_allowed": False})
        GameLoopService.on_task_completed(self.child, "daily_check_in", {"drops_allowed": False})

        self.assertEqual(self.entries(), [("daily_check_in", "adjustment", 15)])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.login_streak, 20)

    def test_automatic_challenge_base_and_promised_egg_salvage_share_source_once(self):
        egg = self.owned_egg()
        now = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.household.family, created_by=self.parent,
            name="Accepted automatic challenge", metric="count", target=1,
            trigger_filter={"allowed_triggers": ["habit_log"]},
            timezone_name="America/Phoenix", starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(days=1), coin_reward=7, xp_reward=0,
            reward_items=[{"item_id": egg.pk, "quantity": 2}],
        )

        ingest_activity(self.child, "habit_log", "source-habit", "habit_log", occurred_at=now)
        occurrence = ChallengeOccurrence.objects.get(goal=goal)
        saved_receipt = occurrence.reward_receipt
        ingest_activity(self.child, "habit_log", "source-habit", "habit_log", occurred_at=now)
        ingest_activity(self.child, "habit_log", "another-habit", "habit_log", occurred_at=now)

        self.assertEqual(self.entries(), [
            ("automatic_challenge", "adjustment", 7),
            ("automatic_challenge", "adjustment", 26),
        ])
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.reward_receipt, saved_receipt)
        self.assertEqual(saved_receipt["coins"], 33)
        self.assertEqual(saved_receipt["items"][0]["salvaged_to_coins"], 26)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=egg).exists())

    def test_legacy_quest_base_and_egg_salvage_share_source_and_completion_gate(self):
        egg = self.owned_egg()
        definition = QuestDefinition.objects.create(
            name="Saved legacy quest", created_by=self.parent, quest_type="collection",
            target_value=1, duration_days=7, coin_reward=9, xp_reward=0,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=egg, quantity=2)
        quest = QuestService.start_quest(self.child, definition.pk)

        first = QuestService.record_progress(self.child, "chore_complete")
        QuestService.record_progress(self.child, "chore_complete")

        self.assertTrue(first["completed"])
        quest.refresh_from_db()
        self.assertEqual(quest.status, "completed")
        self.assertEqual(self.entries(), [
            ("legacy_quest", "adjustment", 9), ("legacy_quest", "adjustment", 26),
        ])

    def test_automatic_zero_quantity_egg_keeps_accepted_reward_and_replay_receipt(self):
        egg = self.owned_egg()
        now = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.household.family, created_by=self.parent,
            name="Accepted zero-quantity egg", metric="count", target=1,
            trigger_filter={"allowed_triggers": ["habit_log"]},
            timezone_name="America/Phoenix", starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(days=1), coin_reward=7, xp_reward=0,
            reward_items=[{"item_id": egg.pk, "quantity": 0}],
        )
        occurrence = _occurrence(goal, now)
        accepted_snapshot = deepcopy(occurrence.snapshot)

        ingest_activity(self.child, "habit_log", "zero-egg-habit", "habit_log", occurred_at=now)
        occurrence.refresh_from_db()
        saved_receipt = deepcopy(occurrence.reward_receipt)
        self.assertEqual(occurrence.status, "completed")
        self.assertIsNotNone(occurrence.awarded_at)
        self.assertEqual(occurrence.snapshot, accepted_snapshot)
        self.assertEqual((saved_receipt["coins"], saved_receipt["xp"]), (7, 0))
        self.assertEqual((saved_receipt["items"][0]["quantity"],
                          saved_receipt["items"][0]["salvaged_to_coins"]), (0, 0))

        ingest_activity(self.child, "habit_log", "zero-egg-habit", "habit_log", occurred_at=now)
        ingest_activity(self.child, "habit_log", "another-zero-egg-habit", "habit_log", occurred_at=now)

        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, accepted_snapshot)
        self.assertEqual(occurrence.reward_receipt, saved_receipt)
        self.assertEqual(self.entries(), [("automatic_challenge", "adjustment", 7)])
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=egg).exists())

    def test_legacy_zero_quantity_egg_keeps_base_reward_without_zero_credit(self):
        egg = self.owned_egg()
        definition = QuestDefinition.objects.create(
            name="Legacy zero-quantity egg", created_by=self.parent, quest_type="collection",
            target_value=1, duration_days=7, coin_reward=9, xp_reward=0,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=egg, quantity=0)
        quest = QuestService.start_quest(self.child, definition.pk)
        accepted_items = deepcopy(quest.reward_items_snapshot)

        result = QuestService.record_progress(self.child, "chore_complete")

        quest.refresh_from_db()
        self.assertEqual(quest.status, "completed")
        self.assertEqual(quest.reward_items_snapshot, accepted_items)
        self.assertEqual((result["rewards"]["coins"], result["rewards"]["xp"]), (9, 0))
        self.assertEqual((result["rewards"]["items"][0]["quantity"],
                          result["rewards"]["items"][0]["salvaged_to_coins"]), (0, 0))
        self.assertIsNone(QuestService.record_progress(self.child, "chore_complete"))
        self.assertIsNone(QuestService._complete_quest(quest, self.child))
        self.assertEqual(self.entries(), [("legacy_quest", "adjustment", 9)])
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=egg).exists())

    def test_coop_zero_quantity_egg_keeps_each_recipients_original_outcome(self):
        family = make_family(
            "Zero-quantity co-op", parents=[{"username": "zero-egg-parent"}],
            children=[{"username": "zero-egg-owner"}, {"username": "zero-egg-finisher"}],
        )
        owner, finisher = family.children
        egg = self.owned_egg(user=owner)
        definition = QuestDefinition.objects.create(
            name="Co-op zero-quantity egg", created_by=family.parents[0], quest_type="collection",
            target_value=1, duration_days=7, coin_reward=9, xp_reward=0,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestRewardItem.objects.create(quest_definition=definition, item=egg, quantity=0)
        quest = QuestService.start_co_op_quest(definition.pk, [finisher, owner])
        accepted_items = deepcopy(quest.reward_items_snapshot)

        result = QuestService.record_progress(finisher, "chore_complete")

        quest.refresh_from_db()
        self.assertEqual(quest.status, "completed")
        self.assertEqual(quest.reward_items_snapshot, accepted_items)
        self.assertEqual((result["rewards"]["coins"], result["rewards"]["xp"]), (9, 0))
        self.assertEqual(result["rewards"]["items"][0]["quantity"], 0)
        self.assertNotIn("salvaged_to_coins", result["rewards"]["items"][0])
        owner_receipt = ActivityEvent.objects.get(subject=owner, event_type="quest.complete").context["extras"]
        self.assertEqual((owner_receipt["coin_reward"], owner_receipt["xp_reward"]), (9, 0))
        self.assertEqual((owner_receipt["item_rewards"][0]["quantity"],
                          owner_receipt["item_rewards"][0]["salvaged_to_coins"]), (0, 0))
        self.assertFalse(UserInventory.objects.filter(user=owner, item=egg).exists())
        # A nonduplicate zero-quantity grant retains its historical empty stack.
        self.assertEqual(UserInventory.objects.get(user=finisher, item=egg).quantity, 0)

        for child in family.children:
            self.assertIsNone(QuestService.record_progress(child, "chore_complete"))
            self.assertIsNone(QuestService._complete_quest(quest, child))
            self.assertEqual(list(CoinLedger.objects.filter(user=child).values_list(
                "source", "reason", "amount",
            )), [("legacy_quest", "adjustment", 9)])
            self.assertEqual(ActivityEvent.objects.filter(subject=child, event_type="quest.complete").count(), 1)

    def test_perfect_day_keeps_fifteen_and_one_daily_receipt_with_active_boost(self):
        chore = Chore.objects.create(
            family=self.household.family, title="Make the bed", created_by=self.parent,
            assigned_to=self.child, recurrence="daily",
        )
        ChoreCompletion.objects.create(
            chore=chore, user=self.child, completed_date=timezone.localdate(), status="approved",
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )

        evaluate_perfect_day_task()
        evaluate_perfect_day_task()

        self.assertEqual(self.entries(), [("perfect_day", "adjustment", 15)])
        self.assertEqual(PerfectDayReceipt.objects.filter(user=self.child).count(), 1)

    def test_writing_is_one_flat_payment_shared_by_both_writing_endpoints(self):
        first = WellbeingService.submit_gratitude(self.child, ["A good day"])
        WellbeingService.submit_gratitude(self.child, ["An edited note"])
        request_id = uuid4()
        entry = ChronicleService.write_journal(
            self.child, title="Today", summary="A private synthetic memory", client_entry_id=request_id,
        )
        replay = ChronicleService.write_journal(
            self.child, title="Today", summary="A private synthetic memory", client_entry_id=request_id,
        )

        self.assertEqual(first["coin_awarded"], 2)
        self.assertEqual(replay.pk, entry.pk)
        self.assertEqual(self.entries(), [("writing", "adjustment", 2)])
        self.assertIsNotNone(DailyWellbeingEntry.objects.get(user=self.child).coin_paid_at)

    @patch("apps.wellbeing.services.GRATITUDE_FIRST_OF_DAY_COINS", 0)
    def test_zero_writing_reward_does_not_create_ledger_or_paid_sentinel(self):
        result = WellbeingService.award_daily_writing_coins(self.child, timezone.localdate())

        self.assertEqual(result, {"coins_awarded": 0, "coin_status": "unavailable"})
        self.assertEqual(self.entries(), [])
        self.assertIsNone(DailyWellbeingEntry.objects.get(user=self.child).coin_paid_at)

    def test_savings_uses_frozen_rate_and_does_not_repeat_or_honor_coin_boost(self):
        goal = SavingsGoalService.create_goal(self.child, title="A new milestone", target_amount=Decimal("12.50"))
        with override_settings(COINS_PER_SAVINGS_GOAL_DOLLAR=90):
            PaymentService.record_entry(self.child, Decimal("12.50"), PaymentLedger.EntryType.ADJUSTMENT)
            SavingsGoalService.check_and_complete(self.child)

        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)
        self.assertEqual(goal.reward_rate_snapshot, 2)
        self.assertEqual(self.entries(), [("savings", "adjustment", 25)])

    def test_birthday_keeps_direct_fixed_gift_and_original_receipt_on_retry(self):
        with override_settings(BIRTHDAY_COIN_GIFT=200):
            chronicle_birthday_check(birthday_date="2026-10-26")
        with override_settings(BIRTHDAY_COIN_GIFT=900):
            chronicle_birthday_check(birthday_date="2026-10-26")

        self.assertEqual(self.entries(), [("birthday", "adjustment", 200)])
        receipt = ChronicleEntry.objects.get(user=self.child, kind="birthday")
        self.assertEqual(receipt.metadata["gift_coins"], 200)

    @override_settings(BIRTHDAY_COIN_GIFT=0)
    def test_zero_birthday_keeps_its_existing_unattributed_zero_row(self):
        chronicle_birthday_check(birthday_date="2026-10-26")
        chronicle_birthday_check(birthday_date="2026-10-26")

        self.assertEqual(self.entries(), [("", "adjustment", 0)])
        self.assertEqual(ChronicleEntry.objects.get(user=self.child, kind="birthday").metadata["gift_coins"], 0)

    def test_ordinary_and_accomplishment_salvage_keep_ten_coin_cap(self):
        frame = self.owned_frame()
        for trigger in ("project_complete", "badge_earned"):
            DropTable.objects.create(trigger_type=trigger, item=frame, weight=1)

        DropService.process_drops(self.child, "project_complete")
        DropService.award_accomplishment(self.child, "badge_earned")

        self.assertEqual(self.entries(), [("cosmetic_salvage", "adjustment", 10)] * 2)
        self.assertEqual(list(DropLog.objects.filter(user=self.child).values_list("salvage_coins", flat=True)), [10, 10])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)

    def test_owned_lucky_dip_retains_full_value_for_each_consumed_item(self):
        self.owned_frame()
        dip = ItemDefinition.objects.create(
            slug="source-lucky-dip", name="Owned Lucky Dip", item_type="consumable",
            metadata={"effect": "lucky_dip", "rarities": ["uncommon"]},
        )
        UserInventory.objects.create(user=self.child, item=dip, quantity=2)

        ConsumableService.use(self.child, dip.pk, quantity=2)
        with self.assertRaises(ValueError):
            ConsumableService.use(self.child, dip.pk)

        self.assertEqual(self.entries(), [("consumable_salvage", "adjustment", 250)] * 2)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=dip).exists())

    def test_rest_manual_grant_is_typed_but_negative_adjustment_stays_unknown(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        for amount in (37, -11):
            response = client.post("/api/coins/adjust/", {
                "user_id": self.child.pk, "amount": amount, "description": "Synthetic adjustment",
            }, format="json")
            self.assertEqual(response.status_code, 201, response.data)

        self.assertEqual(self.entries(), [("manual_grant", "adjustment", 37), ("", "adjustment", -11)])
        self.assertEqual(CoinService.get_balance(self.child), 26)

    def test_mcp_manual_grant_is_typed_but_spend_adjustment_stays_unknown(self):
        with override_user(self.parent):
            positive = adjust_coins(AdjustCoinsIn(user_id=self.child.pk, amount=37, description="Grant"))
            negative = adjust_coins(AdjustCoinsIn(user_id=self.child.pk, amount=-11, description="Revoke"))

        self.assertEqual((positive["new_balance"], negative["new_balance"]), (37, 26))
        self.assertEqual(self.entries(), [("manual_grant", "adjustment", 37), ("", "adjustment", -11)])

    def test_dev_tools_forced_salvage_is_manual_and_keeps_full_item_value(self):
        frame = self.owned_frame()

        force_drop(self.child, slug=frame.slug, salvage=True, count=2)

        self.assertEqual(self.entries(), [("manual_grant", "adjustment", 250)] * 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)

    def test_default_award_helper_keeps_existing_boostable_reason_and_blank_source(self):
        AwardService.grant(self.child, coins=17, coin_reason=CoinLedger.Reason.HOURLY)

        self.assertEqual(self.entries(), [("", "hourly", 34)])
