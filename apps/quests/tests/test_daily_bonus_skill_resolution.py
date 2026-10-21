"""Default daily XP uses its canonical skill; explicit source tags stay exact."""
from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.quests.daily_bonus import process_daily_bonus
from apps.quests.models import ChallengeActivity, DailyBonus
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class DailyBonusSkillResolutionTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "bonus-skill-child"}]).children[0]
        self.foreign = self.skill("A different category")

    def skill(self, category):
        skill = Skill.objects.create(name="Persistence", category=SkillCategory.objects.create(name=category))
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=100, level=1, unlocked=True)
        return skill

    def activity(self, context=None):
        now = timezone.now()
        return ChallengeActivity.objects.create(
            user=self.child, source_type="chore_complete", source_id="daily-resolution",
            trigger_type="chore_complete", occurred_at=now, occurred_on=now.date(), context=context or {},
        )

    def xp(self, skill):
        return SkillProgress.objects.get(user=self.child, skill=skill).xp_points

    def test_default_bonus_selects_life_skills_persistence_and_replays_once(self):
        canonical = self.skill("Life Skills")
        fact = self.activity()
        process_daily_bonus(self.child, fact)
        self.assertEqual(self.xp(canonical), 120)
        self.assertEqual(self.xp(self.foreign), 100)
        self.assertEqual(DailyBonus.objects.get(user=self.child).xp_awarded, 20)
        process_daily_bonus(self.child, fact)
        self.assertEqual(self.xp(canonical), 120)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, reason="daily_challenge").count(), 1)

    def test_missing_canonical_skill_does_not_award_another_category(self):
        process_daily_bonus(self.child, self.activity())
        bonus = DailyBonus.objects.get(user=self.child)
        self.assertEqual((bonus.coins_awarded, bonus.xp_awarded), (10, 0))
        self.assertEqual(self.xp(self.foreign), 100)

    def test_explicit_source_skill_ids_keep_precedence_over_the_default(self):
        canonical = self.skill("Life Skills")
        process_daily_bonus(self.child, self.activity({
            "skill_tags": [{"skill_id": self.foreign.pk, "xp_weight": 1}],
        }))
        self.assertEqual(self.xp(canonical), 100)
        self.assertEqual(self.xp(self.foreign), 120)
