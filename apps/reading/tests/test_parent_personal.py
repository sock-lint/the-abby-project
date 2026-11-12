from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.reading.models import ReadingBook, ReadingDailyReward
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParentPersonalReadingTests(TestCase):
    def setUp(self):
        family = make_family("Personal readers", parents=[{"username": "reader-parent"}, {"username": "coparent"}],
                             children=[{"username": "reader-child"}])
        self.parent, self.coparent = family.parents
        self.child = family.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.parent)
        self.client.credentials(HTTP_X_ABBY_SPACE="personal")

    def test_parent_can_keep_own_books_and_earn_daily_reading_coins_once(self):
        category = SkillCategory.objects.create(name="Language Arts")
        skill = Skill.objects.create(name="Reading Comprehension", category=category)
        book = self.client.post("/api/reading-books/", {
            "title": "My own reading", "client_request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(book.status_code, 201, book.data)
        self.assertEqual(book.data["user"], self.parent.pk)
        payload = {"book": book.data["id"], "duration_minutes": 10, "client_request_id": str(uuid4())}
        logged = self.client.post("/api/reading-sessions/", payload, format="json")
        self.assertEqual(logged.status_code, 201, logged.data)
        self.assertEqual(self.client.post("/api/reading-sessions/", payload, format="json").status_code, 200)
        receipt = ReadingDailyReward.objects.get(user=self.parent)
        self.assertIsNotNone(receipt.awarded_at)
        self.assertEqual(receipt.coins_awarded, 5)
        self.assertEqual(receipt.xp_awarded, 15)
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=skill).xp_points, 15)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent, reason="reading").count(), 1)
        self.assertEqual(self.client.get("/api/reading/summary/").data["books_total"], 1)

    def test_parent_personal_discovery_and_feedback_are_own_preferences(self):
        picks = self.client.get("/api/reading/recommendations/")
        self.assertEqual(picks.status_code, 200, picks.data)
        self.assertTrue(picks.data["results"])
        catalog_id = picks.data["results"][0]["id"]
        saved = self.client.post("/api/reading/discovery-feedback/", {"catalog_id": catalog_id, "choice": "not_interested"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(self.client.get("/api/reading/discovery-feedback/").data["results"], [{"catalog_id": catalog_id, "choice": "not_interested"}])
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/reading/discovery-feedback/").data["results"], [])

    def test_personal_reading_cannot_target_any_other_reader(self):
        for user in (self.child, self.coparent):
            with self.subTest(user=user.pk):
                response = self.client.post("/api/reading-books/", {
                    "user_id": user.pk, "title": "Wrong reader", "client_request_id": str(uuid4()),
                }, format="json")
                self.assertIn(response.status_code, (400, 404))
        self.assertFalse(ReadingBook.objects.exists())

    def test_coparent_cannot_read_or_correct_parent_private_shelf_in_either_space(self):
        book = ReadingBook.objects.create(user=self.parent, title="Private shelf", client_request_id=uuid4(), create_payload={})
        self.client.force_authenticate(self.coparent)
        for headers in ({}, {"HTTP_X_ABBY_SPACE": "personal"}):
            self.client.credentials(**headers)
            self.assertEqual(self.client.get(f"/api/reading-books/{book.pk}/").status_code, 404)
            self.assertEqual(self.client.patch(f"/api/reading-books/{book.pk}/", {"title": "Changed"}).status_code, 404)
        self.client.credentials()
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(f"/api/reading-books/{book.pk}/").status_code, 200)
