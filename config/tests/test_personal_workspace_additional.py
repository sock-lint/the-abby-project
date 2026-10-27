"""Personal participation and Family browsing retain separate saved records."""
import io
import zipfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.activity.models import ActivityEvent
from apps.chronicle.models import ChronicleEntry
from apps.chores.models import Chore, ChoreCompletion, ChoreSkillTag
from apps.creations.models import Creation
from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
from apps.payments.models import PaymentLedger
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdditionalPersonalWorkspaceTests(APITestCase):
    def setUp(self):
        household = make_family("Additional personal spaces", parents=[{"username": "space-parent"}, {"username": "space-coparent"}],
                                children=[{"username": "space-child"}, {"username": "space-sibling"}])
        other = make_family("Another household", parents=[{"username": "space-foreign-parent"}], children=[{"username": "space-foreign-child"}])
        self.parent, self.coparent = household.parents
        self.child, self.sibling = household.children
        self.foreign = other.children[0]
        self.family = household.family
        category = SkillCategory.objects.create(name="Art & Crafts")
        self.skill = Skill.objects.create(name="Drawing", category=category)
        self.client.force_authenticate(self.parent)

    def personal(self, method, path, data=None):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_ABBY_SPACE="personal")

    def test_parent_personal_chore_create_complete_once_awards_xp_coins_and_no_money(self):
        created = self.personal("post", "/api/chores/", {
            "title": "My practice", "recurrence": "daily", "reward_amount": "20.00",
            "coin_reward": 9, "xp_reward": 12, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        })
        self.assertEqual(created.status_code, 201, created.data)
        chore = Chore.objects.get(title="My practice")
        self.assertEqual(chore.assigned_to, self.parent)
        self.assertEqual(chore.reward_amount, Decimal("0"))
        self.assertFalse(chore.pending_parent_review)
        result = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(result.status_code, 201, result.data)
        completion = ChoreCompletion.objects.get(pk=result.data["id"])
        self.assertEqual(completion.user, self.parent)
        self.assertEqual(completion.status, "approved")
        self.assertEqual(completion.reward_amount_snapshot, 0)
        xp_after = SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points
        self.assertGreaterEqual(xp_after, 12)
        self.assertEqual(ActivityEvent.objects.get(subject=self.parent, event_type="award.xp", summary__contains="Chore: My practice").xp_delta, 12)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.parent, reason="chore_reward").values_list("amount", flat=True)), [9])
        self.assertFalse(PaymentLedger.objects.exists())
        repeated = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(ChoreCompletion.objects.count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, xp_after)
        self.assertEqual(CoinLedger.objects.filter(reason="chore_reward").count(), 1)

    def test_existing_parent_chore_with_money_never_credits_money_in_personal_space(self):
        chore = Chore.objects.create(family=self.family, title="Existing own duty", assigned_to=self.parent,
                                     created_by=self.parent, reward_amount=Decimal("20"), coin_reward=4)
        ChoreSkillTag.objects.create(chore=chore, skill=self.skill)
        result = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(ChoreCompletion.objects.get(pk=result.data["id"]).reward_amount_snapshot, 0)
        self.assertFalse(PaymentLedger.objects.exists())

    def test_personal_chores_cannot_target_child_coparent_shared_or_foreign_work(self):
        for owner in (self.child, self.coparent, self.foreign, None):
            chore = Chore.objects.create(family=owner.family if owner else self.family, title=f"Other duty {owner}",
                                         assigned_to=owner, created_by=self.parent)
            self.assertEqual(self.personal("post", f"/api/chores/{chore.pk}/complete/").status_code, 404)
        created = self.personal("post", "/api/chores/", {"title": "Misassigned", "assigned_to": self.child.pk})
        self.assertEqual(created.status_code, 400)
        self.assertFalse(ChoreCompletion.objects.exists())
        self.assertFalse(Chore.objects.filter(title="Misassigned").exists())
        self.assertEqual(self.personal("get", "/api/chores/").data, [])

    def test_child_header_cannot_enable_parent_completion_or_skip_approval(self):
        chore = Chore.objects.create(family=self.family, title="Child duty", assigned_to=self.child, created_by=self.parent, coin_reward=7)
        self.client.force_authenticate(self.child)
        result = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["status"], "pending")
        self.assertFalse(CoinLedger.objects.exists())

    def test_published_personal_chores_are_absent_from_proposal_list(self):
        Chore.objects.create(family=self.family, title="Published own chore", assigned_to=self.parent,
                             created_by=self.parent, pending_parent_review=False)
        response = self.personal("get", "/api/chores/?pending=true")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"], [])

    def test_personal_proposal_list_contains_only_own_pending_chores(self):
        own_pending = Chore.objects.create(family=self.family, title="Own pending chore", assigned_to=self.parent,
                                           created_by=self.parent, pending_parent_review=True)
        own_published = Chore.objects.create(family=self.family, title="Own published chore", assigned_to=self.parent,
                                             created_by=self.parent, pending_parent_review=False)
        for owner in (self.child, self.coparent, self.foreign, None):
            for pending in (True, False):
                Chore.objects.create(family=owner.family if owner else self.family,
                                     title=f"Other chore {owner} {pending}", assigned_to=owner,
                                     created_by=owner or self.parent, pending_parent_review=pending)
        proposals = self.personal("get", "/api/chores/?pending=true")
        self.assertEqual(proposals.status_code, 200, proposals.data)
        self.assertEqual([row["id"] for row in proposals.data["results"]], [own_pending.pk])
        available = self.personal("get", "/api/chores/")
        self.assertEqual([row["id"] for row in available.data], [own_published.pk])
        self.assertFalse(ChoreCompletion.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    })
    def test_personal_portfolio_lists_and_exports_only_own_records(self):
        own_project = Project.objects.create(title="My project", assigned_to=self.parent, created_by=self.parent)
        own_photo = ProjectPhoto.objects.create(project=own_project, user=self.parent, caption="mine",
                                                image=SimpleUploadedFile("mine.jpg", b"my image", content_type="image/jpeg"))
        creation = Creation.objects.create(user=self.parent, primary_skill=self.skill, occurred_on=timezone.localdate(), caption="my art",
                                           image=SimpleUploadedFile("my-art.jpg", b"my creation", content_type="image/jpeg"))
        ProjectPhoto.objects.create(project=own_project, user=self.coparent, caption="co-parent upload",
                                     image=SimpleUploadedFile("coparent.jpg", b"private coparent image", content_type="image/jpeg"))
        for owner in (self.child, self.coparent, self.foreign):
            project = Project.objects.create(title=f"Other project {owner.pk}", assigned_to=owner, created_by=owner)
            photo = ProjectPhoto.objects.create(project=project, user=owner, caption="someone else's photo",
                                                image=SimpleUploadedFile(f"other-{owner.pk}.jpg", b"other image", content_type="image/jpeg"))
            Creation.objects.create(user=owner, primary_skill=self.skill, occurred_on=timezone.localdate(), caption="someone else's art",
                                    image=SimpleUploadedFile(f"other-art-{owner.pk}.jpg", b"other creation", content_type="image/jpeg"))
            self.assertEqual(self.personal("get", f"/api/photos/{photo.pk}/").status_code, 404)
            rejected = self.personal("post", "/api/photos/", {"project": project.pk, "caption": "Wrong project"})
            self.assertEqual(rejected.status_code, 400)
            if owner == self.child:
                ProjectPhoto.objects.create(project=project, user=self.parent, caption="I photographed my child's project",
                                             image=SimpleUploadedFile("child-project.jpg", b"child project", content_type="image/jpeg"))
        assignment = HomeworkAssignment.objects.create(title="Child homework", subject="art", due_date=timezone.localdate(),
                                                       assigned_to=self.child, created_by=self.parent)
        submission = HomeworkSubmission.objects.create(assignment=assignment, user=self.child, status="approved", timeliness="on_time")
        HomeworkProof.objects.create(submission=submission, image=SimpleUploadedFile("child-homework.jpg", b"child homework", content_type="image/jpeg"))
        self.assertEqual([row["id"] for row in self.personal("get", "/api/photos/").data["results"]], [own_photo.pk])
        result = self.personal("get", "/api/portfolio/")
        self.assertEqual([row["project_id"] for row in result.data["projects"]], [own_project.pk])
        self.assertEqual([row["id"] for row in result.data["projects"][0]["photos"]], [own_photo.pk])
        self.assertEqual([row["id"] for row in result.data["creations"]], [creation.pk])
        self.assertEqual(result.data["homework"], [])
        exported = self.personal("get", "/api/export/portfolio/")
        self.assertEqual(exported.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            self.assertEqual(set(archive.namelist()), {f"My project/{own_photo.pk}_mine.jpg", f"creations_Art & Crafts/{creation.pk}_my art.jpg"})
            self.assertEqual({archive.read(path) for path in archive.namelist()}, {b"my image", b"my creation"})

    def test_family_child_overview_has_exact_saved_child_progress_and_never_awards_on_read(self):
        profile, _ = CharacterProfile.objects.update_or_create(user=self.child, defaults={"level": 3})
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=15, level=1)
        SkillProgress.objects.create(user=self.sibling, skill=self.skill, xp_points=80, level=2)
        badge = Badge.objects.create(name="Saved drawing badge", criteria_type="projects_completed", criteria_value={"count": 1})
        UserBadge.objects.create(user=self.child, badge=badge)
        species = PetSpecies.objects.create(slug="chick", sprite_key="cute-chick", name="Chick")
        potion = PotionType.objects.create(slug="base", name="Base")
        own_pet = UserPet.objects.create(user=self.child, species=species, potion=potion)
        own_mount = UserMount.objects.create(user=self.child, species=species, potion=potion)
        UserPet.objects.create(user=self.sibling, species=species, potion=potion)
        CoinLedger.objects.create(user=self.child, amount=21, reason="adjustment")
        CoinLedger.objects.create(user=self.sibling, amount=99, reason="adjustment")
        ChronicleEntry.objects.create(user=self.child, kind="journal", is_private=True, occurred_on=timezone.localdate(),
                                       chapter_year=2026, title="Private child title", summary="Private child body")
        with CaptureQueriesContext(connection) as queries:
            result = self.client.get(f"/api/children/{self.child.pk}/overview/")
            again = self.client.get(f"/api/children/{self.child.pk}/overview/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data, again.data)
        self.assertEqual(result.data["child"]["id"], self.child.pk)
        self.assertEqual(result.data["level"], profile.level)
        self.assertEqual(result.data["coin_balance"], 21)
        self.assertEqual(result.data["counts"], {"skills": 1, "badges": 1, "pets": 1, "mounts": 1})
        self.assertEqual([row["id"] for row in result.data["pets"]], [own_pet.pk])
        self.assertEqual([row["id"] for row in result.data["mounts"]], [own_mount.pk])
        self.assertNotIn("Private child", str(result.data))
        self.assertFalse(any(row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) for row in queries))
        self.assertEqual(self.client.get(f"/api/children/{self.foreign.pk}/overview/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/children/{self.coparent.pk}/overview/").status_code, 404)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.personal("get", f"/api/children/{self.child.pk}/overview/").status_code, 403)

    def test_child_overview_keeps_large_saved_collections_bounded(self):
        skills = Skill.objects.bulk_create([
            Skill(name=f"Another skill {index}", category=self.skill.category) for index in range(101)
        ])
        SkillProgress.objects.bulk_create([SkillProgress(user=self.child, skill=skill, xp_points=1) for skill in skills])
        result = self.client.get(f"/api/children/{self.child.pk}/overview/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["counts"]["skills"], 101)
        self.assertEqual(len(result.data["skills"]), 100)
