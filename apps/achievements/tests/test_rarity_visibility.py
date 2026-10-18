from django.test import TestCase, override_settings

from apps.achievements.models import Badge, UserBadge
from apps.achievements.serializers import BadgeSerializer, UserBadgeSerializer
from config.tests.factories import make_family


class BadgeRewardVisibilityTests(TestCase):
    @override_settings(COINS_PER_BADGE_RARITY={"rare": 47})
    def test_catalog_and_earned_badges_expose_settings_base_bonus(self):
        child = make_family(children=[{"username": "badge-bonus-child"}]).children[0]
        badge = Badge.objects.create(name="Earned rare badge", rarity="rare", criteria_type="first_project")
        earned = UserBadge.objects.create(user=child, badge=badge)
        self.assertEqual(BadgeSerializer(badge).data.get("coin_bonus"), 47)
        self.assertEqual(UserBadgeSerializer(earned).data["badge"].get("coin_bonus"), 47)

    @override_settings(COINS_PER_BADGE_RARITY={"legendary": 150})
    def test_badge_opt_out_and_unmapped_tiers_show_zero_base_bonus(self):
        for rarity, award_coins in [("legendary", False), ("common", True)]:
            with self.subTest(rarity=rarity, award_coins=award_coins):
                badge = Badge(name="No bonus", rarity=rarity, criteria_type="first_project", award_coins=award_coins)
                self.assertEqual(BadgeSerializer(badge).data.get("coin_bonus"), 0)
