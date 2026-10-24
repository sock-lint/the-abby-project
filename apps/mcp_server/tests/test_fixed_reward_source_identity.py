"""Fixed journal and daily XP retain catalog identities through MCP authoring."""
import io
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.services import ChronicleService
from apps.chores.models import Chore, ChoreSkillTag
from apps.chores.services import ChoreService
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.daily_bonus import process_daily_bonus
from apps.quests.models import ChallengeActivity, DailyBonus
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import RPGContentOverride
from config.tests.factories import make_family


SOURCE = {
    "categories": [{"name": "Language Arts"}, {"name": "Life Skills"}, {"name": "Other practice"}],
    "skills": [
        {"name": "Creative Writing", "category": "Language Arts"},
        {"name": "Vocabulary", "category": "Language Arts"},
        {"name": "Persistence", "category": "Life Skills"},
    ],
}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FixedRewardSourceIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        household = make_family("Fixed reward source identity", parents=[
            {"username": "fixed-source-parent", "is_staff": True},
        ], children=[{"username": f"fixed-source-child-{index}"} for index in range(4)])
        self.parent = household.parents[0]
        self.children = household.children
        self.language = SkillCategory.objects.create(name="Language Arts")
        self.life = SkillCategory.objects.create(name="Life Skills")
        self.other = SkillCategory.objects.create(name="Other practice")
        self.writing = Skill.objects.create(name="Creative Writing", category=self.language)
        self.vocabulary = Skill.objects.create(name="Vocabulary", category=self.language)
        self.persistence = Skill.objects.create(name="Persistence", category=self.life)
        # Random catalog drops are unrelated to the fixed XP destinations.
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def wire(self, name, params, *, actor=None):
        with override_user(actor or self.parent, scopes=frozenset({
            "mcp:read", "mcp:write", "mcp:author", "mcp:catalog", "mcp:publish",
        })):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            self.assertNotIn("error", result[1], result[1])
            return result[1]
        self.assertFalse(result.isError, result.structuredContent)
        return result.structuredContent

    def reload_source(self):
        ContentPack(Path(__file__).parent, parsed_content={"skill_tree": SOURCE}).load(stdout=io.StringIO())
        self.assertEqual(Skill.objects.count(), 3)

    def journal(self, index=0, *, rest=False):
        child = self.children[index]
        params = {"title": "Practice reflection", "summary": "I practiced and saved a synthetic memory."}
        if rest:
            client = APIClient()
            client.force_authenticate(child)
            response = client.post("/api/chronicle/journal/", params, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            saved = response.data
        else:
            saved = self.wire("write_journal", params, actor=child)
        entry = ChronicleEntry.objects.get(pk=saved["id"])
        self.assertEqual(saved["reward_receipt"], entry.metadata["reward_receipt"])
        return saved

    def xp(self, child, skill):
        return SkillProgress.objects.filter(user=child, skill=skill).values_list("xp_points", flat=True).first() or 0

    def assert_journal(self, saved, index=0, *, writing=10, vocabulary=5):
        receipt = saved["reward_receipt"]
        self.assertEqual(receipt["xp_awarded"], writing + vocabulary)
        self.assertEqual(receipt["status"], "awarded" if writing + vocabulary else "unavailable")
        self.assertEqual({row["skill_id"]: row["xp"] for row in receipt["skills"]}, {
            skill.pk: amount for skill, amount in [(self.writing, writing), (self.vocabulary, vocabulary)] if amount
        })
        child = self.children[index]
        self.assertEqual((self.xp(child, self.writing), self.xp(child, self.vocabulary)), (writing, vocabulary))

    def daily(self, index=0, *, explicit_skill=None):
        child = self.children[index]
        chore = Chore.objects.create(title=f"Synthetic approved task {index}", family=self.parent.family,
            created_by=self.parent, recurrence="daily", reward_amount=0, coin_reward=0, xp_reward=0)
        if explicit_skill is not None:
            ChoreSkillTag.objects.create(chore=chore, skill=explicit_skill, xp_weight=1)
        completion = ChoreService.submit_completion(child, chore)
        ChoreService.approve_completion(completion, self.parent)
        return DailyBonus.objects.get(user=child)

    def assert_daily(self, bonus, index=0, *, skill=None, xp=20):
        self.assertEqual((bonus.coin_reward, bonus.coins_awarded, bonus.xp_reward, bonus.xp_awarded),
                         (10, 10, 20 if xp else 0, xp))
        self.assertEqual(self.xp(self.children[index], skill or self.persistence), xp)
        self.assertEqual(CoinLedger.objects.filter(user=self.children[index], reason="daily_challenge").count(), 1)

    def test_journal_category_rename_and_source_reload_preserve_both_measured_destinations(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        self.reload_source()
        self.language.refresh_from_db()
        self.assertEqual(self.language.name, "Communication Arts")
        self.assertEqual(RPGContentOverride.objects.get(model_label="achievements.skillcategory",
            object_id=self.language.pk).source_lookup, {"name": "Language Arts"})
        self.assert_journal(self.journal())

    def test_journal_skill_renames_and_reload_preserve_the_ten_five_split(self):
        for skill, name in [(self.writing, "Story Craft"), (self.vocabulary, "Word Practice")]:
            self.wire("update_skill", {"skill_id": skill.pk, "name": name})
        self.reload_source()
        self.assert_journal(self.journal())

    def test_journal_renamed_and_reparented_skills_keep_native_rest_award(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        for skill, name in [(self.writing, "Story Craft"), (self.vocabulary, "Word Practice")]:
            self.wire("update_skill", {"skill_id": skill.pk, "name": name,
                "category_id": self.other.pk, "clear_subject": True})
        self.reload_source()
        for skill in (self.writing, self.vocabulary):
            skill.refresh_from_db()
            self.assertEqual(skill.category_id, self.other.pk)
        self.assert_journal(self.journal(rest=True))

    def test_journal_rename_restore_and_unrelated_edit_leave_the_same_awards(self):
        saved = [self.journal(0)]
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Story Craft"})
        saved.append(self.journal(1))
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Creative Writing"})
        saved.append(self.journal(2))
        self.wire("update_category", {"category_id": self.other.pk, "name": "Unrelated renamed category"})
        saved.append(self.journal(3))
        for index, result in enumerate(saved):
            with self.subTest(index=index):
                self.assert_journal(result, index)

    def test_daily_renamed_and_reparented_skill_and_category_keep_native_chore_bonus(self):
        self.wire("update_category", {"category_id": self.life.pk, "name": "Everyday Practice"})
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady Practice",
            "category_id": self.other.pk, "clear_subject": True})
        self.reload_source()
        self.assertEqual(RPGContentOverride.objects.get(model_label="achievements.skill",
            object_id=self.persistence.pk).source_lookup, {"name": "Persistence", "category_id": self.life.pk})
        self.assert_daily(self.daily())

    def test_daily_rename_restore_and_unrelated_edit_preserve_bonus_and_replay(self):
        bonuses = [self.daily(0)]
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady Practice"})
        bonuses.append(self.daily(1))
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Persistence"})
        bonuses.append(self.daily(2))
        self.wire("update_category", {"category_id": self.other.pk, "name": "Unrelated renamed category"})
        bonuses.append(self.daily(3))
        for index, bonus in enumerate(bonuses):
            with self.subTest(index=index):
                self.assert_daily(bonus, index)
                fact = ChallengeActivity.objects.get(user=self.children[index], trigger_type="chore_complete")
                self.assertIsNone(process_daily_bonus(self.children[index], fact))
                self.assert_daily(DailyBonus.objects.get(pk=bonus.pk), index)

    def test_retired_fixed_identities_keep_journal_and_daily_xp(self):
        for category in (self.language, self.life):
            self.wire("update_category", {"category_id": category.pk, "name": f"Retained {category.name}",
                "is_retired": True})
        for skill in (self.writing, self.vocabulary, self.persistence):
            self.wire("update_skill", {"skill_id": skill.pk, "name": f"Retained {skill.name}", "is_retired": True})
        self.reload_source()
        self.assert_journal(self.journal())
        self.assert_daily(self.daily(1), 1)

    def test_source_less_canonical_catalog_still_awards_without_an_override(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        self.assert_journal(self.journal())
        self.assert_daily(self.daily(1), 1)

    def test_current_and_retained_category_collision_awards_neither_identity(self):
        for category in (self.language, self.life):
            self.wire("update_category", {"category_id": category.pk, "name": f"Retained {category.name}"})
        rogue_language = SkillCategory.objects.create(name="Language Arts")
        rogue_life = SkillCategory.objects.create(name="Life Skills")
        rogue_skills = [Skill.objects.create(name=name, category=category) for name, category in [
            ("Creative Writing", rogue_language), ("Vocabulary", rogue_language), ("Persistence", rogue_life),
        ]]
        self.assert_journal(self.journal(), writing=0, vocabulary=0)
        self.assert_daily(self.daily(1), 1, xp=0)
        self.assertFalse(SkillProgress.objects.filter(skill__in=rogue_skills).exists())

    def test_ambiguous_skill_identity_preserves_only_unambiguous_journal_tag(self):
        for original in (self.writing, self.persistence):
            rogue = Skill.objects.create(name=f"Unrelated {original.name}", category=self.other)
            RPGContentOverride.objects.create(family=self.parent.family, model_label="achievements.skill",
                object_id=rogue.pk, source_lookup={"name": original.name, "category_id": original.category_id},
                values={"_authoring": {"version": 1, "source": "mcp"}})
        self.assert_journal(self.journal(), writing=0, vocabulary=15)
        self.assert_daily(self.daily(1), 1, xp=0)
        self.assertFalse(SkillProgress.objects.filter(skill__category=self.other).exists())

    def test_missing_canonical_destinations_do_not_use_same_named_foreign_skills(self):
        Skill.objects.all().delete()
        foreign = [Skill.objects.create(name=name, category=self.other)
                   for name in ("Creative Writing", "Vocabulary", "Persistence")]
        self.assert_journal(self.journal(), writing=0, vocabulary=0)
        self.assert_daily(self.daily(1), 1, xp=0)
        self.assertFalse(SkillProgress.objects.filter(skill__in=foreign).exists())

    def test_renamed_locked_skills_still_require_ordinary_unlock_eligibility(self):
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Locked story craft", "is_locked_by_default": True})
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Locked steady practice", "is_locked_by_default": True})
        self.assert_journal(self.journal(), writing=0, vocabulary=5)
        bonus = self.daily(1)
        self.assertEqual((bonus.coins_awarded, bonus.xp_reward, bonus.xp_awarded), (10, 20, 0))
        self.assertEqual(self.xp(self.children[1], self.persistence), 0)

    def test_explicit_daily_source_tag_precedes_renamed_default_destination(self):
        explicit = Skill.objects.create(name="Approved task skill", category=self.other)
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady Practice"})
        self.assert_daily(self.daily(explicit_skill=explicit), skill=explicit)
        self.assertEqual(self.xp(self.children[0], self.persistence), 0)

    def test_saved_journal_replay_and_edit_preserve_the_original_receipt_after_renames(self):
        child = self.children[0]
        params = {"title": "Saved reflection", "summary": "An immutable original save.", "client_entry_id": uuid4()}
        first = ChronicleService.write_journal(child, **params)
        receipt = first.metadata["reward_receipt"]
        self.assertEqual(receipt["xp_awarded"], 15)
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Story Craft"})
        self.reload_source()
        replay = ChronicleService.write_journal(child, **params)
        self.assertEqual(replay.metadata["reward_receipt"], receipt)
        edited = self.wire("update_journal", {"entry_id": first.pk, "summary": "Edited reflection."}, actor=child)
        self.assertEqual(edited["reward_receipt"], receipt)
        self.assertEqual((self.xp(child, self.writing), self.xp(child, self.vocabulary)), (10, 5))
        self.assertEqual(ChronicleEntry.objects.filter(user=child, kind="journal").count(), 1)

    def test_restoring_missing_catalog_does_not_backfill_saved_journal_or_bonus(self):
        Skill.objects.all().delete()
        child = self.children[0]
        params = {"title": "Saved without catalog", "summary": "Keep the original receipt.", "client_entry_id": uuid4()}
        journal = ChronicleService.write_journal(child, **params)
        receipt = journal.metadata["reward_receipt"]
        self.assertEqual((receipt["status"], receipt["xp_awarded"]), ("unavailable", 0))
        bonus = self.daily()
        self.assertEqual((bonus.coins_awarded, bonus.xp_reward, bonus.xp_awarded), (10, 0, 0))
        self.reload_source()
        replay = ChronicleService.write_journal(child, **params)
        self.assertEqual(replay.metadata["reward_receipt"], receipt)
        fact = ChallengeActivity.objects.get(user=child, trigger_type="chore_complete")
        self.assertIsNone(process_daily_bonus(child, fact))
        bonus.refresh_from_db()
        self.assertEqual((bonus.coins_awarded, bonus.xp_reward, bonus.xp_awarded), (10, 0, 0))
        self.assertFalse(SkillProgress.objects.filter(user=child).exists())
        self.assertEqual(CoinLedger.objects.filter(user=child, reason="daily_challenge").count(), 1)
