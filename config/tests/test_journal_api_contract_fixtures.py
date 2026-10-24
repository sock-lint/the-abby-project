"""Shared journal receipts and history produced through the real REST API."""
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.chronicle.models import ChronicleEntry
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import UpdateCategoryIn, UpdateSkillIn
from apps.mcp_server.tools import achievements
from apps.rewards.models import CoinLedger
from apps.wellbeing.models import DailyWellbeingEntry
from apps.wellbeing.services import WellbeingService
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "journal-api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class JournalApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        super().setUp()
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=shared_fixtures.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Journal Fixture Family", family_id=41,
            parents=[{"id": 6, "username": "journal-fixture-parent"}],
            children=[
                {"id": 7, "username": "journal-fixture-child"},
                {"id": 8, "username": "journal-fixture-sibling"},
            ],
        )
        self.child, self.sibling = household.children
        self.parent = household.parents[0]
        self.outsider = make_family(
            "Other Journal Fixture Family", family_id=42,
            children=[{"id": 99, "username": "journal-fixture-outsider"}],
        ).children[0]
        category = SkillCategory.objects.create(id=31, name="Language Arts")
        self.writing = Skill.objects.create(id=32, name="Creative Writing", category=category)
        self.vocabulary = Skill.objects.create(id=33, name="Vocabulary", category=category)
        ChronicleEntry.objects.create(
            id=400, user=self.outsider, kind=ChronicleEntry.Kind.MANUAL,
            occurred_on=date(2026, 10, 9), chapter_year=2026,
            title="Another family's memory",
        )
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ChronicleEntry]):
                cursor.execute(sql)
        token = Token.objects.create(user=self.child, key="j" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.submission = {
            "title": "A little note about today",
            "summary": "Today was hard. I still made time to draw.",
            "is_private": True,
            "client_entry_id": "33333333-3333-4333-8333-333333333333",
        }

    def post(self):
        return self.client.post("/api/chronicle/journal/", self.submission, format="json")

    def test_create_replay_today_and_edit_retain_one_confirmed_receipt(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        receipt = response.json()["reward_receipt"]
        self.assertEqual(receipt.get("coins_awarded"), 2)
        self.assertEqual(receipt.get("coin_status"), "awarded")
        self.assertEqual(receipt["xp_awarded"], 15)
        original_ledger = list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount"))
        created = self.assert_response_fixture(response, "journal-created.json", status=201)
        self.assertEqual(created["user"], self.child.pk)
        self.assertTrue(created["is_private"])
        self.assertEqual(self.assert_response_fixture(self.post(), "journal-replayed.json"), created)
        self.assertEqual(self.assert_response_fixture(
            self.client.get("/api/chronicle/journal/today/"), "journal-today.json",
        ), created)
        edited = self.assert_response_fixture(self.client.patch(
            f"/api/chronicle/{created['id']}/journal/",
            {"summary": "Today was hard. Drawing helped me feel calmer."}, format="json",
        ), "journal-edited.json")
        self.assertEqual(edited["reward_receipt"], created["reward_receipt"])
        self.assertEqual(self.post().json(), edited)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount")), original_ledger)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=2).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.writing).xp_points, 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.vocabulary).xp_points, 5)

    def test_summary_preserves_legacy_daily_note_privacy_without_retroactive_rewards(self):
        created = self.post()
        self.assertEqual(created.status_code, 201, created.content)
        original_ledger = list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount"))
        source = DailyWellbeingEntry.objects.create(
            user=self.child, date=date(2026, 10, 9), affirmation_slug="fixture-affirmation",
            gratitude_lines=["A small note from yesterday.", "A friend listened."],
            coin_paid_at=shared_fixtures.FIXED_NOW,
        )
        # Production migration projects existing rows; use the same compatibility
        # writer for this synthetic history without adding mutations to GET.
        WellbeingService._sync_daily_note(source)
        response = self.client.get("/api/chronicle/summary/")
        self.assertEqual(response.status_code, 200, response.content)
        chapters = response.json()["chapters"]
        self.assertEqual(len(chapters), 1)
        entries = chapters[0]["entries"]
        self.assertEqual(len(entries), 2)
        self.assertEqual([entry["kind"] for entry in entries], ["journal", "daily_note"])
        note = entries[1]
        self.assertTrue(note["is_private"])
        self.assertEqual(note["reward_receipt"]["xp_awarded"], 0)
        self.assertEqual(note["reward_receipt"]["coins_awarded"], 0)
        self.assertEqual(note["reward_receipt"]["coin_status"], "unavailable")
        self.assert_response_fixture(response, "journal-summary-legacy.json")
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount")), original_ledger)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.writing).xp_points, 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.vocabulary).xp_points, 5)
        self.client.force_authenticate(self.parent)
        parent = self.assert_response_fixture(self.client.get(
            "/api/chronicle/summary/", {"user_id": self.child.pk},
        ), "journal-summary-parent-private.json")
        self.assertEqual(parent["chapters"], [])
        for reader in (self.sibling, self.outsider):
            self.client.force_authenticate(reader)
            chapters = self.client.get("/api/chronicle/summary/").json()["chapters"]
            self.assertFalse(any(
                entry["user"] == self.child.pk
                for chapter in chapters for entry in chapter["entries"]
            ))

    def test_old_client_daily_note_and_new_journal_share_one_daily_coin_award(self):
        WellbeingService.submit_gratitude(self.child, ["The old client's note is preserved."])
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        receipt = response.json()["reward_receipt"]
        self.assertEqual(receipt["coins_awarded"], 0)
        self.assertEqual(receipt["coin_status"], "already_received")
        self.assertEqual(receipt["xp_awarded"], 15)
        self.assert_response_fixture(response, "journal-coins-already-received.json", status=201)
        self.assertEqual(CoinLedger.objects.filter(user=self.child, amount=2).count(), 1)

    def test_journal_receipt_preserves_fixed_skill_identities_after_taxonomy_renames(self):
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        with override_user(self.parent):
            achievements.update_category(UpdateCategoryIn(
                category_id=self.writing.category_id, name="Written Expression",
            ))
            achievements.update_skill(UpdateSkillIn(skill_id=self.writing.pk, name="Story Craft"))
            achievements.update_skill(UpdateSkillIn(skill_id=self.vocabulary.pk, name="Word Power"))

        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        receipt = response.json()["reward_receipt"]
        self.assertEqual(receipt["status"], "awarded")
        self.assertEqual(receipt["xp_awarded"], 15)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.writing).xp_points, 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.vocabulary).xp_points, 5)
        self.assertEqual(
            {row["skill_id"]: row["xp"] for row in receipt["skills"]},
            {self.writing.pk: 10, self.vocabulary.pk: 5},
        )
        created = self.assert_response_fixture(response, "journal-renamed-taxonomy.json", status=201)
        original_ledger = list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount"))
        self.assertEqual(self.post().json(), created)
        self.assertEqual(self.client.get("/api/chronicle/journal/today/").json(), created)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("pk", "amount")), original_ledger)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.writing).xp_points, 10)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.vocabulary).xp_points, 5)
