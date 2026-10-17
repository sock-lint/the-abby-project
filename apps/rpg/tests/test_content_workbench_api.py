"""The browser workflow preserves scopes, stale reviews and real catalog state."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.models import ItemDefinition, RPGContentDraft, UserInventory
from config.tests.factories import make_family


ROOT = "/api/rpg/content-workbench/"
SCENARIO = {
    "horizon_days": 30, "trials": 1, "seed": 17, "active_days_per_week": 7,
    "chores_per_day": 1, "reading_minutes": 0, "project_minutes": 0,
    "habits_per_day": 0, "journal_per_day": False, "movement_sessions_per_day": 0,
    "creations_per_day": 0, "expeditions_per_day": 0,
}


@override_settings(ALLOWED_HOSTS=["testserver"])
class ContentWorkbenchAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        household = make_family("Workbench API", parents=[{"username": "api-designer", "is_staff": True}])
        self.actor = household.parents[0]
        self.client.force_authenticate(self.actor)
        category = SkillCategory.objects.create(name="Life Skills")
        Skill.objects.create(name="Persistence", category=category)
        self.item = ItemDefinition.objects.create(slug="api-food", name="Snack", icon="x", item_type="food")
        self.quest = QuestDefinition.objects.create(name="API chores", description="Do chores", quest_type="collection",
            target_value=2, duration_days=7, trigger_filter={"allowed_triggers": ["chore_complete"]}, is_system=True)

    def post(self, url, data, status=200):
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def create(self):
        draft = self.post(ROOT + "drafts/", {"name": "API proposal"}, status=201)
        return draft, ROOT + f"drafts/{draft['id']}/"

    def test_all_authoring_endpoints_require_authenticated_staff_parents(self):
        endpoints = [("get", ROOT), ("post", ROOT + "drafts/")]
        draft = ROOT + "drafts/00000000-0000-4000-8000-000000000001/"
        endpoints += [("get", draft), ("patch", draft)]
        endpoints += [("post", draft + action + "/") for action in ("preview", "simulate", "publish")]
        parents = make_family("Unprivileged", parents=[{"username": "regular-parent"}],
            children=[{"username": "staff-child", "is_staff": True}])
        for user, expected in ((None, 401), (parents.parents[0], 403), (parents.children[0], 403)):
            self.client.force_authenticate(user)
            for method, url in endpoints:
                with self.subTest(user=user, method=method, url=url):
                    self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, expected)
        self.assertEqual(RPGContentDraft.objects.count(), 0)

    def test_draft_selection_is_bound_to_actor_and_family_and_queries_cannot_target_accounts(self):
        draft, url = self.create()
        outsider = make_family("Other API", parents=[{"username": "other-designer", "is_staff": True}]).parents[0]
        for viewer in (outsider, User.objects.create_user(username="coparent-designer", role="parent",
                is_staff=True, family=self.actor.family)):
            self.client.force_authenticate(viewer)
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.actor)
        self.assertEqual(self.client.get(ROOT + "?user_id=123").status_code, 400)
        self.assertEqual(self.client.get(ROOT + "?_abby_session=synthetic").status_code, 200)

    def test_create_save_compare_and_explicit_publish_use_one_exact_review(self):
        draft, url = self.create()
        changes = [
            {"section": "items", "object_id": None, "key": "new-snack", "values": {
                "slug": "api-new-snack", "name": "New snack", "icon": "x", "item_type": "food"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "chores", "values": {
                "coin_reward": 17, "reward_items": [{"item_key": "new-snack", "quantity": 2}]}},
        ]
        saved = self.client.patch(url, {"revision": draft["revision"], "changes": changes}, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        draft = saved.json()
        self.assertEqual(self.client.patch(url, {"revision": 1, "changes": changes}, format="json").status_code, 409)
        preview = self.post(url + "preview/", {"revision": draft["revision"]})["preview"]
        counts = (User.objects.count(), UserInventory.objects.count(), ItemDefinition.objects.count())
        self.assertFalse(ItemDefinition.objects.filter(slug="api-new-snack").exists())
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.coin_reward, 0)
        publish = {"revision": draft["revision"], "preview_id": preview["preview_id"],
            "content_digest": preview["content_digest"], "confirmation": True}
        self.post(url + "publish/", publish, status=409)
        comparison = self.post(url + "simulate/", {"revision": draft["revision"],
            "preview_id": preview["preview_id"], "config": SCENARIO})
        self.assertEqual(comparison["baseline"]["config"], comparison["proposed"]["config"])
        self.assertNotEqual(comparison["baseline"]["catalog"]["fingerprint"], comparison["proposed"]["catalog"]["fingerprint"])
        self.assertEqual((User.objects.count(), UserInventory.objects.count(), ItemDefinition.objects.count()), counts)
        self.post(url + "publish/", {**publish, "confirmation": False}, status=400)
        result = self.post(url + "publish/", publish)
        self.assertIsNotNone(result["published_at"])
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.coin_reward, 17)
        self.assertEqual(self.quest.reward_items.get().item.slug, "api-new-snack")
        self.assertEqual(self.post(url + "publish/", publish)["published_at"], result["published_at"])
        self.assertEqual(ItemDefinition.objects.filter(slug="api-new-snack").count(), 1)

    def test_invalid_payloads_are_rejected_without_draft_or_catalog_writes(self):
        for body in ({}, {"name": "x", "user_id": 7}, {"name": []}, {"name": ""}):
            self.post(ROOT + "drafts/", body, status=400)
        self.assertEqual(RPGContentDraft.objects.count(), 0)
        draft, url = self.create()
        for changes in (None, [None], [{"section": "items", "object_id": self.item.pk, "key": "snack", "values": None}]):
            response = self.client.patch(url, {"revision": draft["revision"], "changes": changes}, format="json")
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.client.get(url).json()["revision"], draft["revision"])
