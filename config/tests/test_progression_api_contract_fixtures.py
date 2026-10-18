"""Raw designer endpoints over fixed, synthetic global content."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory
from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rpg.models import DropTable, ItemDefinition
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None, SOURCE_COMMIT="")
class ProgressionLabResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        designer = make_family(
            "Synthetic progression design",
            family_id=31,
            parents=[{"id": 7, "username": "fixture-progression-designer", "is_staff": True}],
        ).parents[0]
        self.client.force_authenticate(designer)
        language = SkillCategory.objects.create(id=501, name="Language Arts")
        life = SkillCategory.objects.create(id=502, name="Life Skills")
        physical = SkillCategory.objects.create(id=503, name="Physical")
        art = SkillCategory.objects.create(id=504, name="Art & Crafts")
        Skill.objects.create(id=511, name="Reading Comprehension", category=language)
        persistence = Skill.objects.create(id=512, name="Persistence", category=life)
        Skill.objects.create(id=513, name="Mindfulness", category=physical)
        Skill.objects.create(id=514, name="Endurance", category=physical)
        Skill.objects.create(id=515, name="Drawing", category=art)
        base = PotionType.objects.create(id=522, slug="base", name="Base", color_hex="#8B7355")
        chick = PetSpecies.objects.create(id=521, slug="chick", name="Chick", sprite_key="cute-chick")
        chick.available_potions.add(base)
        items = [
            ItemDefinition.objects.create(id=531, slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=chick, metadata={"species": "chick"}),
            ItemDefinition.objects.create(id=532, slug="base-potion", name="Base Potion", item_type="potion", potion_type=base, metadata={"variant": "base"}),
            ItemDefinition.objects.create(id=533, slug="food-birdseed", name="Birdseed", item_type="food", food_species=chick),
            ItemDefinition.objects.create(id=534, slug="lab-coin-pouch", name="Small Coin Pouch", item_type="coin_pouch", metadata={"coins": 7}),
            ItemDefinition.objects.create(id=535, slug="lab-frame", name="Practice Frame", item_type="cosmetic_frame", coin_value=3),
        ]
        for index, item in enumerate(items):
            DropTable.objects.create(id=541 + index, trigger_type="chore_complete", item=item, weight=10)
        DropTable.objects.create(id=546, trigger_type="reading_logged", item=items[2], weight=10)
        DropTable.objects.create(id=547, trigger_type="reading_logged", item=items[3], weight=5)
        Badge.objects.create(
            id=551, name="First lab chore", description="One synthetic approved chore",
            criteria_type="chore_completions", criteria_value={"count": 1}, xp_bonus=5,
        )
        quest = QuestDefinition.objects.create(
            id=561, name="Regular lab chores", description="Two synthetic approved chores",
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
            coin_reward=12, xp_reward=15, is_system=True,
        )
        QuestSkillTag.objects.create(id=562, quest_definition=quest, skill=persistence, xp_weight=1)

    def test_metadata_and_seeded_report_match_shared_wire_contract(self):
        metadata = self.assert_response_fixture(
            self.client.get("/api/rpg/progression-lab/"), "progression-lab-metadata.json",
        )
        self.assertEqual(metadata["catalog"]["supported_pet_variants"], 1)
        self.assertEqual(metadata["catalog"]["supported_items"], 5)
        report = self.assert_response_fixture(self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {"horizon_days": 30, "trials": 3, "seed": 17, "chores_per_day": 1,
             "chore_coins": 5, "habits_per_day": 0, "journal_per_day": False},
            format="json",
        ), "progression-lab-report.json")
        self.assertEqual(report["config"]["trials"], 3)
        self.assertEqual(len(report["trace"]), 30)
        self.assertTrue(report["journey"]["events"])
        self.assertEqual(report["coverage"]["initial_state"]["coins"], 0)

    def test_purchases_and_money_match_shared_wire_contract(self):
        response = self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {
                "horizon_days": 30, "trials": 3, "seed": 17,
                "chores_per_day": 1, "chore_coins": 5,
                "habits_per_day": 0, "journal_per_day": False,
                "project_minutes": 20,
                "economy": {
                    "enabled": True, "start_date": "2026-01-20",
                    "purchase_strategy": "buy_affordable",
                    "monthly_family_budget_cents": 600,
                    "chore_money_cents": 25, "project_hourly_money_cents": 800,
                    "exchange_shortfalls": True, "monthly_exchange_limit_cents": 100,
                    "printing": {"minutes_per_coin": 10, "monthly_minutes": 30, "monthly_grams": 20},
                    "offers": [
                        {"key": "outing", "label": "Practice outing", "kind": "real_world",
                         "coin_price": 50, "repeat_every_days": 7, "stock": 2,
                         "family_cost_cents": 500, "print_minutes": 0, "print_grams": 0},
                        {"key": "print", "label": "Practice print", "kind": "printing",
                         "coin_price": 0, "repeat_every_days": 7, "stock": None,
                         "family_cost_cents": 25, "print_minutes": 21, "print_grams": 10},
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        report = self.assert_response_fixture(response, "progression-lab-economy-report.json")
        self.assertTrue(report["economy"]["enabled"])
        self.assertEqual(report["config"]["economy"]["start_date"], "2026-01-20")

    def test_daily_reward_budget_matches_shared_wire_contract(self):
        response = self.client.post(
            "/api/rpg/progression-lab/simulate/",
            {"horizon_days": 30, "trials": 3, "seed": 17,
             "chores_per_day": 1, "chore_coins": 5,
             "habits_per_day": 0, "journal_per_day": False,
             "reward_budget": {"daily_coins": 5}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        # Assert behavior before the fixture comparison so a fixture rewrite
        # cannot accidentally turn an uncapped response into passing evidence.
        self.assertEqual(response.data["config"]["reward_budget"]["daily_coins"], 5)
        budget = response.data["reward_budget"]["summary"]
        self.assertGreater(budget["omitted_coins"]["p50"], 0)
        self.assertLessEqual(budget["awarded_coins"]["p90"], 5 * response.data["summary"]["active_days"])
        self.assert_response_fixture(response, "progression-lab-reward-budget-report.json")

    def test_companion_badges_pay_once_when_care_reaches_their_milestones(self):
        quest = QuestDefinition.objects.get(pk=561)
        quest.target_value = 1
        quest.save(update_fields=["target_value"])
        for item_id, quantity in ((531, 1), (532, 1), (533, 30)):
            QuestRewardItem.objects.create(quest_definition=quest, item_id=item_id, quantity=quantity)
        names = ["First lab hatch", "First lab species", "First lab grown companion"]
        for pk, name, criteria_type, rarity, xp_bonus in (
            (552, names[0], "pets_hatched", "common", 7),
            (553, names[1], "pet_species_owned", "uncommon", 8),
            (554, names[2], "mounts_evolved", "rare", 9),
        ):
            Badge.objects.create(
                id=pk, name=name, criteria_type=criteria_type, criteria_value={"count": 1},
                rarity=rarity, xp_bonus=xp_bonus,
            )
        response = self.client.post("/api/rpg/progression-lab/simulate/", {
            "horizon_days": 30, "trials": 1, "seed": 17, "reading_minutes": 0,
            "chores_per_day": 1, "chore_coins": 5, "chore_xp": 100,
            "habits_per_day": 0, "journal_per_day": False, "expeditions_per_day": 0,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        report = response.json()
        earned = [event for event in report["journey"]["events"]
                  if event["source"] == "badge_earned" and event["target"] in names]
        # Exercise the real endpoint independently of the generated snapshots.
        self.assertEqual([(event["target"], event["day"]) for event in earned],
                         [(name, 1) for name in names])
        self.assertEqual(report["summary"]["finite_breakdown"]["badge"], 4)
        self.assertTrue(all(day["badges_p50"] == 4 for day in report["trace"]))
        badges = next(source for source in report["flows"]["sources"] if source["source"] == "badges")
        self.assertEqual((badges["coins"], badges["xp"]), (60.0, 29.0))
