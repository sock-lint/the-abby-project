"""Parent goals cannot impersonate catalog quest achievements or unlocks."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.criteria import _boss_quests_completed, _collection_quests_completed, _quest_completed
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.chores.models import Chore, ChoreCompletion
from apps.chores.services import ChoreService
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class AutomaticQuestCriteriaTests(TestCase):
    def setUp(self):
        family = make_family("Quest badge identity", parents=[{"username": "identityparent"}],
                             children=[{"username": "identitychild"}, {"username": "identitysibling"}])
        self.parent, self.child, self.sibling = family.parents[0], *family.children
        category = SkillCategory.objects.create(name="Quest badge skill")
        skill = Skill.objects.create(name="Quest badge effort", category=category)
        self.progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1)
        ChallengeEnrollment.objects.create(user=self.child, starts_at=timezone.now() - timedelta(days=1))
        self.apprentice = QuestDefinition.objects.create(
            name="Apprentice Path", description="The actual catalog boss", is_system=True,
            quest_type="boss", target_value=100, duration_days=7,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        self.named_badge = Badge.objects.create(
            name="Apprentice Path Complete", description="Finish the catalog boss",
            criteria_type="quest_completed", criteria_value={"quest_name": "Apprentice Path"},
            rarity="uncommon", xp_bonus=40,
        )
        self.journeyman = QuestDefinition.objects.create(
            name="Journeyman Trial", description="The gated next catalog boss", is_system=True,
            quest_type="boss", target_value=100, duration_days=7, required_badge=self.named_badge,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        list_goals(self.child)

    def create_parent_goal(self, name):
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post("/api/challenges/goals/", {
            "user_id": self.child.pk, "name": name, "trigger_type": "chore_complete",
            "metric": "count", "target": "1", "unit": "actions", "period": "this_week",
            "coin_reward": 7, "xp_reward": 0,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return ChallengeOccurrence.objects.get(goal__catalog_definition__isnull=True)

    def approve_chore(self):
        chore = Chore.objects.create(title="One valid chore", family=self.child.family, created_by=self.parent,
                                     reward_amount=0, coin_reward=0, xp_reward=0)
        completion = ChoreCompletion.objects.create(
            chore=chore, user=self.child, completed_date=timezone.localdate(),
            reward_amount_snapshot=0, coin_reward_snapshot=0,
        )
        ChoreService.approve_completion(completion, self.parent)

    def test_parent_named_goal_does_not_award_catalog_badge_xp_or_unlock(self):
        parent = self.create_parent_goal("Apprentice Path")
        self.approve_chore()
        parent.refresh_from_db()
        self.assertEqual((parent.status, parent.progress, parent.reward_receipt["coins"]), ("completed", 1, 7))
        boss = ChallengeOccurrence.objects.get(goal__catalog_definition=self.apprentice)
        self.assertEqual((boss.status, boss.progress), ("active", 15))
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=self.named_badge).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 100)
        self.assertFalse(CoinLedger.objects.filter(user=self.child, reason="badge_bonus").exists())
        list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.journeyman).exists())
        self.assertFalse(_quest_completed(self.child, {"quest_name": "Apprentice Path"}))

    def test_parent_count_goal_does_not_earn_collection_or_generic_quest_count(self):
        collection_badge = Badge.objects.create(
            name="Catalog collection completion", criteria_type="collection_quests_completed",
            criteria_value={"count": 1}, xp_bonus=30,
        )
        self.create_parent_goal("One approved chore")
        self.approve_chore()
        self.assertFalse(_collection_quests_completed(self.child, {"count": 1}))
        self.assertFalse(_quest_completed(self.child, {"quest_names": [], "count": 1}))
        self.assertFalse(UserBadge.objects.filter(user=self.child, badge=collection_badge).exists())

    def test_real_catalog_boss_earns_named_badge_and_unlocks_next_goal(self):
        for _ in range(7):
            self.approve_chore()
        boss = ChallengeOccurrence.objects.get(goal__catalog_definition=self.apprentice)
        self.assertEqual((boss.status, boss.progress), ("completed", 105))
        self.assertTrue(UserBadge.objects.filter(user=self.child, badge=self.named_badge).exists())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 140)
        list_goals(self.child)
        self.assertTrue(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.journeyman).exists())

    def test_catalog_definition_identity_controls_name_and_subtype(self):
        collection = QuestDefinition.objects.create(
            name="Catalog collection", quest_type="collection", is_system=True,
            target_value=1, duration_days=7, trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        self.approve_chore()
        goal = ChallengeGoal.objects.get(user=self.child, catalog_definition=collection)
        # Display text and a mutable metric cannot turn the definition into another quest.
        goal.name = "Apprentice Path"
        goal.metric = "minutes"
        goal.save(update_fields=["name", "metric"])
        self.assertTrue(_quest_completed(self.child, {"quest_name": collection.name}))
        self.assertFalse(_quest_completed(self.child, {"quest_name": "Apprentice Path"}))
        self.assertTrue(_collection_quests_completed(self.child, {"count": 1}))
        self.assertTrue(_quest_completed(self.child, {"quest_names": [], "count": 1}))
        self.assertFalse(_quest_completed(self.child, {"quest_names": [], "count": 2}))
        self.assertFalse(_boss_quests_completed(self.child, {"count": 1}))
        self.assertFalse(_collection_quests_completed(self.sibling, {"count": 1}))
        self.assertFalse(_quest_completed(self.sibling, {"quest_name": collection.name}))
