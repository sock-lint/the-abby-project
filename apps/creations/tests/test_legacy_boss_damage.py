"""Creation rewards do not turn intentionally excluded triggers into boss work."""
import io
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.activity.models import ActivityEvent
from apps.creations.services import CreationService
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestRewardItem, QuestSkillTag
from apps.quests.services import QuestService, RAGE_SHIELD_CLIMB_STEP
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CreationLegacyBossDamageTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory(prefix="abby-creation-boss-tests-")
        self.addCleanup(media.cleanup)
        media_settings = override_settings(MEDIA_ROOT=media.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.child = make_family(children=[{"username": "creation-boss-child"}]).children[0]
        category = SkillCategory.objects.create(name="Art & Crafts")
        self.draw = Skill.objects.create(name="Drawing", category=category)
        self.progress = SkillProgress.objects.create(
            user=self.child, skill=self.draw, xp_points=100, level=1,
        )
        self.source_food = ItemDefinition.objects.create(
            slug="food-creation-source", name="Creation snack", item_type="food",
        )
        self.quest_food = ItemDefinition.objects.create(
            slug="food-creation-quest", name="Promised quest snack", item_type="food",
        )
        self.bonus_food = ItemDefinition.objects.create(
            slug="food-creation-bonus", name="Quest bonus snack", item_type="food",
        )
        DropTable.objects.create(trigger_type=TriggerType.CREATION_LOGGED, item=self.source_food)
        DropTable.objects.create(trigger_type=TriggerType.QUEST_COMPLETE, item=self.bonus_food)

    def start_quest(self, *, kind="boss", target=100, progress=0, rage=0):
        definition = QuestDefinition.objects.create(
            name="Accepted legacy creation challenge", description="An existing saved promise",
            quest_type=kind, target_value=target, duration_days=7,
            coin_reward=37, xp_reward=30, is_system=True,
        )
        QuestSkillTag.objects.create(quest_definition=definition, skill=self.draw)
        QuestRewardItem.objects.create(quest_definition=definition, item=self.quest_food)
        quest = QuestService.start_quest(self.child, definition.pk)
        # Make accidental zero-damage writes observable, including the timestamp
        # used by the nightly rage job to decide whether a child worked today.
        self.idle_at = timezone.now() - timedelta(days=2)
        Quest.objects.filter(pk=quest.pk).update(
            current_progress=progress, rage_shield=rage, updated_at=self.idle_at,
        )
        QuestParticipant.objects.filter(quest=quest, user=self.child).update(updated_at=self.idle_at)
        quest.refresh_from_db()
        return quest

    def log_creation(self):
        image = io.BytesIO()
        Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="JPEG")
        upload = SimpleUploadedFile("creation.jpg", image.getvalue(), content_type="image/jpeg")
        # Control chance only: exercise the real XP, drop, game-loop and quest paths.
        with patch("apps.rpg.services.random.random", return_value=0):
            return CreationService.log_creation(
                self.child, image=upload, primary_skill_id=self.draw.pk,
            )

    def assert_no_quest_payout(self, quest):
        self.assertFalse(CoinLedger.objects.filter(
            user=self.child, description=f"Quest complete: {quest.definition.name}",
        ).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.quest_food).exists())
        self.assertFalse(DropLog.objects.filter(
            user=self.child, trigger_type=TriggerType.QUEST_COMPLETE,
        ).exists())
        self.assertFalse(ActivityEvent.objects.filter(
            subject=self.child, event_type="quest.complete",
        ).exists())

    def test_eligible_creation_cannot_finish_or_pay_a_legacy_boss(self):
        quest = self.start_quest(progress=90)

        creation = self.log_creation()

        self.assertEqual(creation.xp_awarded, 10)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.source_food).quantity, 1)
        self.assertEqual(DropLog.objects.filter(
            user=self.child, trigger_type=TriggerType.CREATION_LOGGED,
        ).count(), 1)
        quest.refresh_from_db()
        participant = QuestParticipant.objects.get(quest=quest, user=self.child)
        self.assertEqual((quest.current_progress, quest.status), (90, Quest.Status.ACTIVE))
        self.assertEqual(participant.contribution, 0)
        self.assertEqual(quest.updated_at, self.idle_at)
        self.assertEqual(participant.updated_at, self.idle_at)
        self.assertFalse(ActivityEvent.objects.filter(
            subject=self.child, event_type="quest.progress",
        ).exists())
        self.assert_no_quest_payout(quest)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 110)

    def test_creation_does_not_count_as_rage_shield_activity(self):
        quest = self.start_quest(rage=15)

        self.log_creation()
        result = QuestService.apply_boss_rage()

        self.assertEqual(result, {"raged": 1, "decayed": 0})
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 15 + RAGE_SHIELD_CLIMB_STEP)
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.child).updated_at, self.idle_at)
        self.assertFalse(ActivityEvent.objects.filter(
            subject=self.child, event_type="quest.progress",
        ).exists())

    def test_intended_chore_damage_still_finishes_and_pays_a_legacy_boss_once(self):
        quest = self.start_quest(target=15)

        result = QuestService.record_progress(self.child, TriggerType.CHORE_COMPLETE)

        self.assertTrue(result["completed"])
        self.assertEqual(result["damage_dealt"], 15)
        quest.refresh_from_db()
        self.assertEqual((quest.current_progress, quest.status), (15, Quest.Status.COMPLETED))
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.child).contribution, 15)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.quest_food).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.bonus_food).quantity, 1)
        self.assertEqual(DropLog.objects.filter(
            user=self.child, trigger_type=TriggerType.QUEST_COMPLETE,
        ).count(), 1)
        self.assertEqual(CoinLedger.objects.get(
            user=self.child, description=f"Quest complete: {quest.definition.name}",
        ).amount, 37)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 130)
        self.assertIsNone(QuestService.record_progress(self.child, TriggerType.CHORE_COMPLETE))
        self.assertEqual(DropLog.objects.filter(
            user=self.child, trigger_type=TriggerType.QUEST_COMPLETE,
        ).count(), 1)

    def test_eligible_creation_still_counts_toward_a_legacy_collection(self):
        quest = self.start_quest(kind="collection", target=2)

        creation = self.log_creation()

        quest.refresh_from_db()
        self.assertEqual((quest.current_progress, quest.status), (1, Quest.Status.ACTIVE))
        self.assertEqual(QuestParticipant.objects.get(quest=quest, user=self.child).contribution, 1)
        self.assertEqual(creation.xp_awarded, 10)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.source_food).quantity, 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.xp_points, 110)
        self.assert_no_quest_payout(quest)
