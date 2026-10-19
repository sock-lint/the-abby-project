"""Daily writing has one history and one shared first-save coin allowance."""
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import SkillProgress
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chronicle.tests.test_journal import _make_language_arts_skills
from apps.mcp_server.context import override_user
from apps.mcp_server.schemas import GetChronicleSummaryIn, ListChronicleEntriesIn
from apps.mcp_server.tools.chronicle import get_chronicle_summary, list_chronicle_entries
from apps.rewards.models import CoinLedger
from apps.wellbeing.models import DailyWellbeingEntry
from apps.wellbeing.services import WellbeingService
from config.tests.factories import make_family


class UnifiedJournalTests(TestCase):
    def setUp(self):
        family = make_family(
            parents=[{"username": "parent"}],
            children=[{"username": "writer"}, {"username": "sibling"}],
        )
        self.parent = family.parents[0]
        self.child, self.sibling = family.children
        self.other = make_family(parents=[{"username": "other-parent"}]).parents[0]
        _make_language_arts_skills()
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        patcher = mock.patch("apps.chronicle.services.GameLoopService.on_task_completed", return_value={})
        self.loop = patcher.start()
        self.addCleanup(patcher.stop)

    def journal(self, **overrides):
        return ChronicleService.write_journal(
            self.child, title="My day", summary="A few words.", **overrides,
        )

    def test_journal_save_awards_verified_flat_coins_once_with_original_xp(self):
        request_id = uuid4()
        entry = self.journal(client_entry_id=request_id)
        receipt = entry.metadata["reward_receipt"]
        self.assertEqual(receipt["coins_awarded"], 2)
        self.assertEqual(receipt["coin_status"], "awarded")
        self.assertEqual(receipt["xp_awarded"], 15)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).get().amount, 2)
        self.assertIsNotNone(DailyWellbeingEntry.objects.get(user=self.child).coin_paid_at)
        ChronicleService.update_journal(self.child, entry, summary="More thoughts.")
        replay = self.journal(client_entry_id=request_id)
        self.assertEqual(replay.metadata["reward_receipt"], receipt)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
        self.loop.assert_called_once()

    def test_both_save_orders_share_one_coin_allowance(self):
        for note_first in (True, False):
            with self.subTest(note_first=note_first):
                day = timezone.localdate() + timedelta(days=int(note_first))
                with mock.patch("django.utils.timezone.localdate", return_value=day):
                    if note_first:
                        note = WellbeingService.submit_gratitude(self.child, ["Something small."])
                        journal = self.journal()
                        self.assertEqual(note["coin_awarded"], 2)
                        self.assertEqual(journal.metadata["reward_receipt"]["coin_status"], "already_received")
                        self.assertEqual(journal.metadata["reward_receipt"]["coins_awarded"], 0)
                    else:
                        self.journal()
                        note = WellbeingService.submit_gratitude(self.child, ["Something small."])
                        self.assertEqual(note["coin_awarded"], 0)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [2, 2])

    def test_legacy_writes_sync_their_private_memory_without_touching_shared_journal(self):
        journal = self.journal(is_private=False)
        first = WellbeingService.submit_gratitude(self.child, ["My private thought.", "Another thought."])
        note = ChronicleEntry.objects.get(user=self.child, kind="daily_note")
        self.assertEqual(note.summary, "My private thought.\n\nAnother thought.")
        self.assertTrue(note.is_private)
        self.assertEqual(note.daily_note_source_id, first["entry"].pk)
        self.assertEqual(note.occurred_on, first["entry"].date)
        self.assertEqual(note.metadata["reward_receipt"]["xp_awarded"], 0)
        self.assertEqual(note.metadata["reward_receipt"]["coins_awarded"], 0)
        WellbeingService.submit_gratitude(self.child, ["Updated private thought."])
        note.refresh_from_db()
        journal.refresh_from_db()
        self.assertEqual(note.summary, "Updated private thought.")
        self.assertEqual(journal.summary, "A few words.")
        self.assertFalse(journal.is_private)
        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, kind="daily_note").count(), 1)
        self.assertEqual(SkillProgress.objects.filter(user=self.child).count(), 2)
        self.loop.assert_called_once()

    def test_legacy_note_never_gets_journal_xp_or_a_meadow_bloom(self):
        from apps.achievements.criteria import _journal_entries_written, _journal_streak_days

        WellbeingService.submit_gratitude(self.child, ["I would like to remember this."])
        self.assertFalse(SkillProgress.objects.filter(user=self.child).exists())
        self.loop.assert_not_called()
        response = self.client.get("/api/chronicle/meadow/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["keepsake_count"], 0)
        self.assertFalse(_journal_entries_written(self.child, {"count": 1}))
        self.assertFalse(_journal_streak_days(self.child, {"days": 1}))
        history = self.client.get("/api/chronicle/?kind=daily_note").json()
        entries = history.get("results", history) if isinstance(history, dict) else history
        self.assertEqual(len(entries), 1)

    def test_daily_notes_are_self_only_even_if_a_bad_row_says_shared(self):
        note = ChronicleEntry.objects.create(
            user=self.child, kind="daily_note", is_private=False,
            occurred_on=timezone.localdate(), chapter_year=2026,
            title="Private daily note", summary="A private thought.",
        )
        for user in (self.parent, self.other, self.sibling):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(f"/api/chronicle/{note.pk}/").status_code, 404)
                with override_user(user):
                    listing = list_chronicle_entries(ListChronicleEntriesIn())
                self.assertEqual(listing["entries"], [])
        with override_user(self.parent):
            summary = get_chronicle_summary(GetChronicleSummaryIn(user_id=self.child.pk))
            listing = list_chronicle_entries(ListChronicleEntriesIn(user_id=self.child.pk))
        self.assertEqual(summary["chapters"], [])
        self.assertEqual(listing["entries"], [])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(f"/api/chronicle/?user_id={self.child.pk}").json()["results"], [])
        self.assertEqual(self.client.get(f"/api/chronicle/summary/?user_id={self.child.pk}").json()["chapters"], [])
        self.assertEqual(self.client.post(f"/api/chronicle/{note.pk}/mark-viewed/").status_code, 404)
        self.client.force_authenticate(self.child)
        own = self.client.get(f"/api/chronicle/{note.pk}/")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["reward_receipt"]["xp_awarded"], 0)
        self.assertEqual(own.json()["reward_receipt"]["coins_awarded"], 0)
        self.assertEqual(self.client.patch(f"/api/chronicle/{note.pk}/journal/", {"is_private": False}).status_code, 403)
        self.assertEqual(self.client.get(f"/api/chronicle/entries/{note.pk}/comments/").status_code, 404)
        with override_user(self.child):
            own_notes = list_chronicle_entries(ListChronicleEntriesIn(kind="daily_note"))
        self.assertEqual([row["id"] for row in own_notes["entries"]], [note.pk])
        with override_user(self.parent):
            filtered = list_chronicle_entries(ListChronicleEntriesIn(user_id=self.child.pk, kind="daily_note"))
        self.assertEqual(filtered["entries"], [])

    def test_coin_sentinel_failure_rolls_back_ledger_but_keeps_journal_and_xp(self):
        original_save = DailyWellbeingEntry.save

        def interrupted_save(entry, *args, **kwargs):
            if "coin_paid_at" in (kwargs.get("update_fields") or []):
                raise RuntimeError("interrupted coin sentinel save")
            return original_save(entry, *args, **kwargs)

        request_id = uuid4()
        with mock.patch.object(DailyWellbeingEntry, "save", interrupted_save):
            with self.assertLogs("apps.wellbeing.services", level="ERROR"):
                journal = self.journal(client_entry_id=request_id)
        receipt = journal.metadata["reward_receipt"]
        self.assertEqual(receipt["coins_awarded"], 0)
        self.assertEqual(receipt["coin_status"], "unavailable")
        self.assertEqual(receipt["xp_awarded"], 15)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertEqual(self.journal(client_entry_id=request_id).metadata["reward_receipt"], receipt)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        # A subsequent legacy save may recover the still-unpaid allowance;
        # replaying or editing a journal never changes its original receipt.
        self.assertEqual(WellbeingService.submit_gratitude(self.child, ["Another thought."])["coin_awarded"], 2)
        self.assertEqual(WellbeingService.submit_gratitude(self.child, ["Edited thought."])["coin_awarded"], 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)

    def test_legacy_coin_failure_preserves_findable_note_and_allows_one_recovery(self):
        def interrupted_award(user, amount, reason, **kwargs):
            CoinLedger.objects.create(user=user, amount=amount, reason=reason)
            raise RuntimeError("interrupted legacy award")

        with mock.patch("apps.rewards.services.CoinService.award_coins", side_effect=interrupted_award):
            with self.assertLogs("apps.wellbeing.services", level="ERROR"):
                result = WellbeingService.submit_gratitude(self.child, ["A saved hard day."])
        self.assertEqual(result["coin_awarded"], 0)
        self.assertIsNone(result["entry"].coin_paid_at)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertEqual(ChronicleEntry.objects.get(kind="daily_note").summary, "A saved hard day.")
        journal = self.journal()
        self.assertEqual(journal.metadata["reward_receipt"]["coins_awarded"], 2)
        self.assertEqual(WellbeingService.submit_gratitude(self.child, ["A correction."])["coin_awarded"], 0)
        self.assertEqual(CoinLedger.objects.filter(user=self.child).count(), 1)
