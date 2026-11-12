"""Current parent participation does not retroactively settle old parent dailies."""
from datetime import timedelta

from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementType, MovementTypeSkillTag
from apps.quests.activity import record_activity
from apps.quests.daily_bonus import settle_legacy_bonuses
from apps.quests.models import DailyBonus, DailyChallenge
from apps.rewards.models import CoinLedger
from config.tests.base import BaseFamilyAPITestCase


class ParentLegacyBonusBoundaryTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "legacy-bonus-parent"}]
    family_children = [{"username": "legacy-bonus-child"}]

    def setUp(self):
        self.parent, self.child = self.parents[0], self.children[0]
        category = SkillCategory.objects.create(name="Life Skills")
        self.skill = Skill.objects.create(name="Persistence", category=category)
        self.old_day = timezone.localdate() - timedelta(days=40)
        self.parent_legacy = self.legacy(self.parent)

    def legacy(self, user):
        return DailyChallenge.objects.create(
            user=user, date=self.old_day, challenge_type="chores", target_value=2,
            current_progress=2, coin_reward=10, xp_reward=20,
        )

    def assert_old_parent_unpaid(self):
        self.parent_legacy.refresh_from_db()
        self.assertEqual((self.parent_legacy.coin_reward, self.parent_legacy.xp_reward), (10, 20))
        self.assertFalse(DailyBonus.objects.filter(user=self.parent, date=self.old_day).exists())

    def test_old_completed_parent_daily_stays_unsettled_without_new_progression(self):
        self.assertEqual(settle_legacy_bonuses(), 0)
        self.assertEqual(settle_legacy_bonuses(), 0)
        self.assert_old_parent_unpaid()
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())

    def test_child_historical_promise_still_settles_once_without_parent_consuming_limit(self):
        child_legacy = self.legacy(self.child)
        self.assertEqual(settle_legacy_bonuses(limit=1), 1)
        self.assertEqual(settle_legacy_bonuses(limit=1), 0)
        self.assert_old_parent_unpaid()
        child_legacy.refresh_from_db()
        self.assertEqual((child_legacy.coin_reward, child_legacy.xp_reward), (0, 0))
        child_bonus = DailyBonus.objects.get(user=self.child, date=self.old_day)
        self.assertEqual((child_bonus.coins_awarded, child_bonus.xp_awarded), (10, 20))
        self.assertEqual(list(CoinLedger.objects.values_list("user_id", "amount")), [(self.child.pk, 10)])
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 20)
        self.assertFalse(SkillProgress.objects.filter(user=self.parent).exists())

    def test_current_personal_saved_movement_still_earns_parent_bonus_once(self):
        movement_type = MovementType.objects.create(name="Parent daily walk", slug="parent-daily-walk")
        MovementTypeSkillTag.objects.create(movement_type=movement_type, skill=self.skill)
        self.client.force_authenticate(self.parent)
        response = self.client.post("/api/movement-sessions/", {
            "movement_type_id": movement_type.pk, "duration_minutes": 10,
        }, format="json", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(response.status_code, 201, response.content)
        bonus = DailyBonus.objects.get(user=self.parent)
        self.assertEqual((bonus.coins_awarded, bonus.xp_awarded), (10, 20))
        self.assertNotEqual(bonus.date, self.old_day)
        before = list(CoinLedger.objects.values_list("pk", "user_id", "amount"))
        record_activity(self.parent, "movement_session", {"session_id": response.data["id"], "duration_minutes": 999})
        self.assertEqual(settle_legacy_bonuses(), 0)
        self.assertEqual(list(CoinLedger.objects.values_list("pk", "user_id", "amount")), before)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, reason="daily_challenge").count(), 1)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assert_old_parent_unpaid()
