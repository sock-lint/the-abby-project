from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress, UserBadge, Badge
from apps.chores.models import Chore, ChoreCompletion
from apps.chronicle.models import ChronicleEntry
from apps.creations.models import Creation
from apps.habits.models import Habit, HabitLog
from apps.homework.models import HomeworkAssignment
from apps.payments.models import PaymentLedger
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.projects.models import Project, User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition
from apps.timecards.models import TimeEntry

from ..services import EXPECTED_ENTRY_SLUGS, load_lorebook_catalog


class LorebookViewTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="child", password="pw", role="child")

    def test_anonymous_request_is_rejected(self):
        resp = self.client.get("/api/lorebook/")
        self.assertEqual(resp.status_code, 401)

    def test_catalog_contains_expected_entries(self):
        slugs = {entry["slug"] for entry in load_lorebook_catalog()}
        self.assertEqual(slugs, EXPECTED_ENTRY_SLUGS)

    def test_parent_gets_full_reference_unlocked(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/lorebook/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["counts"], {"unlocked": 17, "total": 17})
        self.assertEqual(len(data["entries"]), 17)
        self.assertTrue(all(entry["unlocked"] for entry in data["entries"]))
        self.assertTrue(
            all(entry["unlocked_reason"] == "parent_reference" for entry in data["entries"])
        )

    def test_fresh_child_sees_entries_locked(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/lorebook/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["counts"]["total"], 17)
        by_slug = {entry["slug"]: entry for entry in data["entries"]}
        for slug in ["duties", "pets", "money", "quests", "cosmetics"]:
            self.assertFalse(by_slug[slug]["unlocked"])

    def test_child_unlocks_are_derived_from_existing_data(self):
        category = SkillCategory.objects.create(name="Making", icon="🛠️")
        skill = Skill.objects.create(name="Planning", category=category)
        badge = Badge.objects.create(
            name="First Seal",
            description="Earn a seal",
            criteria_type=Badge.CriteriaType.FIRST_PROJECT,
            criteria_value=1,
        )
        chore = Chore.objects.create(
            title="Dishes",
            created_by=self.parent,
            assigned_to=self.child,
            reward_amount=Decimal("1.00"),
            coin_reward=1,
        )
        ChoreCompletion.objects.create(
            chore=chore,
            user=self.child,
            completed_date=timezone.localdate(),
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=Decimal("1.00"),
            coin_reward_snapshot=1,
        )
        habit = Habit.objects.create(name="Read", user=self.child, created_by=self.parent)
        HabitLog.objects.create(habit=habit, user=self.child, direction=1)
        HomeworkAssignment.objects.create(
            title="Math",
            subject=HomeworkAssignment.Subject.MATH,
            due_date=timezone.localdate(),
            assigned_to=self.child,
            created_by=self.parent,
        )
        ChronicleEntry.objects.create(
            user=self.child,
            kind=ChronicleEntry.Kind.JOURNAL,
            occurred_on=timezone.localdate(),
            chapter_year=timezone.localdate().year,
            title="Today",
        )
        ChronicleEntry.objects.create(
            user=self.child,
            kind=ChronicleEntry.Kind.MILESTONE,
            occurred_on=timezone.localdate(),
            chapter_year=timezone.localdate().year,
            title="Big day",
        )
        Creation.objects.create(
            user=self.child,
            image="creations/test.png",
            occurred_on=timezone.localdate(),
            primary_skill=skill,
        )
        project = Project.objects.create(
            title="Birdhouse",
            assigned_to=self.child,
            created_by=self.parent,
        )
        TimeEntry.objects.create(
            user=self.child,
            project=project,
            clock_in=timezone.now() - timedelta(hours=1),
            clock_out=timezone.now(),
            status=TimeEntry.Status.COMPLETED,
        )
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=5, level=0)
        UserBadge.objects.create(user=self.child, badge=badge)
        item = ItemDefinition.objects.create(name="Apple", icon="🍎", item_type="food")
        DropLog.objects.create(user=self.child, item=item, trigger_type="chore_complete")
        species = PetSpecies.objects.create(name="Fox", slug="fox", icon="🦊")
        potion = PotionType.objects.create(name="Sunny", slug="sunny")
        pet = UserPet.objects.create(user=self.child, species=species, potion=potion)
        UserMount.objects.create(user=self.child, species=species, potion=potion)
        CharacterProfile.objects.filter(user=self.child).update(
            login_streak=2,
            active_frame=item,
        )
        CoinLedger.objects.create(
            user=self.child,
            amount=5,
            reason=CoinLedger.Reason.ADJUSTMENT,
            description="test",
            created_by=self.parent,
        )
        PaymentLedger.objects.create(
            user=self.child,
            amount=Decimal("2.00"),
            entry_type=PaymentLedger.EntryType.ADJUSTMENT,
            created_by=self.parent,
        )
        definition = QuestDefinition.objects.create(
            name="Trial",
            description="Test",
            quest_type=QuestDefinition.QuestType.BOSS,
            target_value=10,
            end_date=timezone.now() + timedelta(days=7),
        )
        quest = Quest.objects.create(
            definition=definition,
            end_date=timezone.now() + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)

        self.client.force_authenticate(self.child)
        data = self.client.get("/api/lorebook/").json()
        unlocked = {entry["slug"] for entry in data["entries"] if entry["unlocked"]}
        self.assertEqual(unlocked, EXPECTED_ENTRY_SLUGS)
