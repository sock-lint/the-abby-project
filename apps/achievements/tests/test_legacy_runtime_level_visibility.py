"""Legacy goal visibility follows native threshold coercion without loosening authoring."""
from copy import deepcopy
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.availability import badge_goal_is_available
from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge, XP_THRESHOLDS
from apps.achievements.services import BadgeService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, UserInventory
from config.tests.factories import make_family


LEVEL_CASES = (
    ('skill_level_reached', 'level', {'count': 1}),
    ('subjects_completed', 'min_level', {'count': 1}),
    ('skill_categories_breadth', 'min_level', {'categories': 1}),
    ('category_mastery', 'min_level', {'category': 'Legacy runtime category'}),
)
REACHABLE_LEVELS = ('2', ' 2 ', 1.5, 0, -1, True, False, '6', 5.9)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], ALLOWED_HOSTS=['testserver'])
class LegacyRuntimeLevelVisibilityTests(TestCase):
    def setUp(self):
        cache.clear()
        household = make_family('Legacy native level goals', parents=[{'username': 'legacy-level-author', 'is_staff': True}], children=[{'username': 'legacy-level-child'}])
        self.actor, self.child = household.parents[0], household.children[0]
        self.category = SkillCategory.objects.create(name='Legacy runtime category')
        self.subject = Subject.objects.create(name='Legacy subject', category=self.category)
        self.skill = Skill.objects.create(name='Legacy skill', category=self.category, subject=self.subject)
        self.progress = SkillProgress.objects.create(user=self.child, skill=self.skill, level=max(XP_THRESHOLDS), xp_points=XP_THRESHOLDS[max(XP_THRESHOLDS)], unlocked=True)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def badge(self, case, level, *, save=True):
        kind, field, others = case
        values = dict(name=f'Legacy {kind} {Badge.objects.count()}', description='Synthetic retained native goal', criteria_type=kind, criteria_value={**others, field: level}, xp_bonus=0, award_coins=False)
        return Badge.objects.create(**values) if save else Badge(**values)

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({'mcp:catalog', 'mcp:publish'})):
            result = async_to_sync(mcp.call_tool)(name, {'params': params, 'confirmation': True})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def state(self):
        return {model._meta.label_lower: list(model.objects.order_by('pk').values()) for model in (Badge, SkillProgress, UserBadge, CoinLedger, UserInventory, DropLog)}

    def test_each_native_coercible_threshold_remains_available(self):
        for case in LEVEL_CASES:
            for level in REACHABLE_LEVELS:
                with self.subTest(kind=case[0], level=level):
                    badge = self.badge(case, level, save=False)
                    self.assertTrue(BadgeService._check_criteria(self.child, badge))
                    self.assertTrue(badge_goal_is_available(badge, self.child))

    def test_fractional_legacy_threshold_preserves_each_native_comparison(self):
        self.progress.level = 1
        self.progress.xp_points = XP_THRESHOLDS[1]
        self.progress.save(update_fields=['level', 'xp_points'])
        for case in LEVEL_CASES:
            with self.subTest(kind=case[0]):
                badge = self.badge(case, 1.5)
                self.assertEqual(BadgeService._check_criteria(self.child, badge), case[0] == 'category_mastery')
                self.assertTrue(badge_goal_is_available(badge, self.child))
        earned = BadgeService.evaluate_badges(self.child, scopes={'skill_xp'})
        self.assertEqual([badge.criteria_type for badge in earned], ['category_mastery'])
        self.progress.level = 2
        self.progress.xp_points = XP_THRESHOLDS[2]
        self.progress.save(update_fields=['level', 'xp_points'])
        self.assertEqual(len(BadgeService.evaluate_badges(self.child, scopes={'skill_xp'})), 3)

    def test_readers_keep_reachable_legacy_goals_and_never_award_or_rewrite(self):
        badges = [self.badge(case, level) for case in LEVEL_CASES for level in ('2', 1.5, 0, True, False, 5.9)]
        before = self.state()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/badges/')
            choices = response.json()['results']
            page = 1
            while response.json()['next']:
                page += 1
                response = self.client.get('/api/badges/', {'page': page})
                choices.extend(response.json()['results'])
            catalog = self.wire('read_rpg_catalog', {'section': 'badges'})
            audit = self.wire('audit_rpg_catalog', {'section': 'badges'})
            summary = self.client.get('/api/achievements/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in choices}, {badge.pk for badge in badges})
        self.assertTrue(all(row['catalog_available'] for row in choices))
        self.assertNotIn('error', catalog, catalog)
        self.assertEqual({row['id'] for row in catalog['results'] if row['available_for_new_user']}, {badge.pk for badge in badges})
        self.assertEqual({row['id'] for row in audit['findings'] if row['code'] == 'invalid_badge_criteria'}, {badge.pk for badge in badges})
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['total_badges'], len(badges))
        self.assertEqual(self.state(), before)
        writes = [q['sql'] for q in queries.captured_queries if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])

    def test_native_awards_legacy_goal_once_without_normalizing_saved_criteria(self):
        badges = [self.badge(case, level) for case in LEVEL_CASES for level in ('2', 1.5, 0, True, False, 5.9)]
        criteria = {badge.pk: deepcopy(badge.criteria_value) for badge in badges}
        self.assertEqual({badge.pk for badge in BadgeService.evaluate_badges(self.child, scopes={'skill_xp'})}, set(criteria))
        after = self.state()
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={'skill_xp'}), [])
        self.assertEqual(self.state(), after)
        self.assertEqual(dict(Badge.objects.values_list('pk', 'criteria_value')), criteria)

    def test_effectively_unreachable_legacy_goals_stay_hidden_with_earned_history_retained(self):
        earned = []
        for case in LEVEL_CASES:
            for level in (7, '7', 7.9, 1000000):
                badge = self.badge(case, level)
                self.assertFalse(BadgeService._check_criteria(self.child, badge))
                self.assertFalse(badge_goal_is_available(badge, self.child))
            retained = self.badge(case, '7')
            UserBadge.objects.create(user=self.child, badge=retained)
            earned.append(retained)
        before = self.state()
        response = self.client.get('/api/badges/')
        history = self.client.get('/api/badges/earned/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.json()['results']}, {badge.pk for badge in earned})
        self.assertTrue(all(row['catalog_available'] is False for row in response.json()['results']))
        self.assertEqual({row['badge']['id'] for row in history.json()['results']}, {badge.pk for badge in earned})
        self.assertTrue(all(row['badge']['catalog_available'] is False for row in history.json()['results']))
        self.assertEqual(self.state(), before)

    def test_unusable_thresholds_are_not_advertised_as_native_reachable(self):
        for case in LEVEL_CASES:
            for level in (None, 'not-a-level', '1.5', [], {}, float('inf'), float('-inf'), float('nan')):
                with self.subTest(kind=case[0], level=level):
                    badge = self.badge(case, level, save=False)
                    with self.assertRaises((ValueError, TypeError, OverflowError)):
                        BadgeService._check_criteria(self.child, badge)
                    self.assertFalse(badge_goal_is_available(badge, self.child))

    def test_new_registered_authoring_remains_strict_for_legacy_coercible_values(self):
        before = self.state()
        for case in LEVEL_CASES:
            for level in ('2', 1.5, 0, True, False, 6.9, None):
                badge = self.badge(case, level, save=False)
                body = {key: getattr(badge, key) for key in ('name', 'description', 'criteria_type', 'criteria_value', 'xp_bonus', 'award_coins')}
                with self.subTest(kind=case[0], level=level):
                    result = self.wire('create_badge', body)
                    self.assertIn('error', result, result)
                    self.assertNotEqual(result['error']['code'], 'internal_error')
        self.assertEqual(self.state(), before)

    def test_effective_level_cap_tracks_installed_curve_after_native_coercion(self):
        with patch.dict(XP_THRESHOLDS, {0: 0, 1: 100, 2: 300, 3: 600}, clear=True):
            for case in LEVEL_CASES:
                with self.subTest(kind=case[0]):
                    self.assertTrue(badge_goal_is_available(self.badge(case, '3', save=False)))
                    self.assertEqual(badge_goal_is_available(self.badge(case, 3.9, save=False)), case[0] == 'category_mastery')
                    self.assertFalse(badge_goal_is_available(self.badge(case, '4', save=False)))

    def test_fraction_above_the_curve_is_reachable_only_for_native_mastery_truncation(self):
        for case in LEVEL_CASES:
            with self.subTest(kind=case[0]):
                badge = self.badge(case, 6.9)
                reachable = case[0] == 'category_mastery'
                self.assertEqual(BadgeService._check_criteria(self.child, badge), reachable)
                self.assertEqual(badge_goal_is_available(badge, self.child), reachable)

    def test_mcp_legacy_level_compatibility_keeps_unrelated_invalid_fields_unavailable(self):
        badges = []
        for case in LEVEL_CASES:
            malformed = [{'unknown_key': 1}]
            malformed += [{'category': None}, {'category': 5}] if case[0] == 'category_mastery' else [{'count' if case[0] != 'skill_categories_breadth' else 'categories': '1'}]
            for other in malformed:
                badge = self.badge(case, '2')
                badge.criteria_value.update(other)
                badge.save(update_fields=['criteria_value'])
                badges.append(badge)
        for kind, criteria in (('pets_hatched', {'count': 'bad'}), ('subjects_completed', {'count': None, 'min_level': '2'}), ('total_coins_earned', {'amount': 'bad'})):
            badges.append(Badge.objects.create(name=f'Other malformed {kind}', description='Malformed unrelated criterion', criteria_type=kind, criteria_value=criteria, xp_bonus=0, award_coins=False))
        before = self.state()
        catalog = self.wire('read_rpg_catalog', {'section': 'badges'})
        self.assertNotIn('error', catalog, catalog)
        self.assertEqual({row['id'] for row in catalog['results']}, {badge.pk for badge in badges})
        self.assertTrue(all(row['available_for_new_user'] is False for row in catalog['results']))
        self.assertEqual(self.state(), before)

    def test_omitted_threshold_keeps_each_native_default_and_curve_limit(self):
        for case in LEVEL_CASES:
            with self.subTest(kind=case[0]):
                badge = self.badge(case, 1, save=False)
                del badge.criteria_value[case[1]]
                self.assertTrue(BadgeService._check_criteria(self.child, badge))
                self.assertTrue(badge_goal_is_available(badge, self.child))
                with patch.dict(XP_THRESHOLDS, {0: 0, 1: 100}, clear=True):
                    self.assertEqual(badge_goal_is_available(badge, self.child), case[0] == 'skill_categories_breadth')
