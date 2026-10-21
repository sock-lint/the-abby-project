"""Global delete endpoints preserve saved credit, definitions and source identity."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, Skill, SkillCategory, SkillPrerequisite, SkillProgress, Subject, UserBadge
from apps.creations.models import Creation
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.projects.models import Project
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, ChallengeSchedule, QuestDefinition, QuestSkillTag
from apps.rpg.models import ContentPackEntry, RPGContentOverride
from config.tests.factories import make_family


DETAIL = "This taxonomy entry is in use and cannot be deleted."
CONFLICT = {"detail": DETAIL, "code": "taxonomy_in_use"}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyDeletionTests(TestCase):
    def setUp(self):
        own = make_family("Deletion author", parents=[{"username": "delete-author", "is_staff": True}])
        other = make_family("Other deletion family", parents=[{"username": "other-delete-author", "is_staff": True}],
                            children=[{"username": "other-delete-child"}])
        self.parent, self.other_parent, self.child = own.parents[0], other.parents[0], other.children[0]
        self.category = SkillCategory.objects.create(name="Unused synthetic taxonomy")

    def skill(self, name="Synthetic skill"):
        return Skill.objects.create(name=name, category=self.category)

    def badge(self):
        return Badge.objects.create(name="Synthetic badge", description="Rule", criteria_type="first_project")

    def quest(self, **values):
        return QuestDefinition.objects.create(name="Private promise", description="Private", created_by=self.other_parent,
                                              quest_type="collection", target_value=1, **values)

    def override(self, obj, *, family=None, source=None, values=None):
        return RPGContentOverride.objects.create(model_label=obj._meta.label_lower, object_id=obj.pk,
            family=family or self.parent.family, source_lookup=source or {"name": obj.name},
            values=values or {"name": obj.name, "_authoring": {"version": 1, "source": "mcp"}})

    def delete(self, surface, kind, obj, *, actor=None, **extra):
        actor = actor or self.parent
        if surface == "rest":
            client = APIClient()
            client.force_authenticate(actor)
            route = {"category": "categories", "subject": "subjects", "skill": "skills", "badge": "badges"}[kind]
            response = client.delete(f"/api/{route}/{obj.pk}/")
            return response.status_code, response.data
        with override_user(actor):
            result = async_to_sync(mcp.call_tool)(f"delete_{kind}", {
                "params": {f"{kind}_id": obj.pk}, "confirmation": True, **extra,
            })
        payload = result.structuredContent if hasattr(result, "structuredContent") else result[1]
        return (400 if getattr(result, "isError", False) else 200), payload

    def assert_blocked(self, kind, obj):
        for surface in ("rest", "mcp"):
            with self.subTest(surface=surface):
                status, data = self.delete(surface, kind, obj)
                if surface == "rest":
                    self.assertEqual((status, data), (409, CONFLICT))
                else:
                    self.assertEqual(status, 400)
                    self.assertEqual(data["error"]["code"], "taxonomy_in_use")
                    self.assertEqual(data["error"]["message"], DETAIL)
                    self.assertEqual(data["error"]["field_errors"], {})
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_nonempty_category_preserves_foreign_owned_skill_and_xp(self):
        skill = self.skill()
        self.override(skill, family=self.other_parent.family)
        progress = SkillProgress.objects.create(user=self.child, skill=skill, xp_points=300, level=2)
        self.assert_blocked("category", self.category)
        self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())
        self.assertEqual(SkillProgress.objects.get(pk=progress.pk).xp_points, 300)

    def test_category_with_only_project_set_null_reference_is_in_use(self):
        project = Project.objects.create(title="Private project", category=self.category, created_by=self.other_parent)
        self.assert_blocked("category", self.category)
        project.refresh_from_db()
        self.assertEqual(project.category_id, self.category.pk)

    def test_subject_keeps_foreign_skill_and_badge_links(self):
        subject = Subject.objects.create(name="Shared subject", category=self.category)
        skill, badge = self.skill(), self.badge()
        Skill.objects.filter(pk=skill.pk).update(subject=subject)
        Badge.objects.filter(pk=badge.pk).update(subject=subject)
        self.override(skill, family=self.other_parent.family)
        self.assert_blocked("subject", subject)
        skill.refresh_from_db()
        badge.refresh_from_db()
        self.assertEqual((skill.subject_id, badge.subject_id), (subject.pk, subject.pk))

    def test_skill_keeps_saved_progress_private_tags_and_other_skill_prerequisites(self):
        skill, successor = self.skill(), self.skill("Successor")
        SkillProgress.objects.create(user=self.child, skill=skill, xp_points=300, level=2)
        tag = QuestSkillTag.objects.create(quest_definition=self.quest(), skill=skill)
        edge = SkillPrerequisite.objects.create(skill=successor, required_skill=skill)
        self.assert_blocked("skill", skill)
        self.assertTrue(QuestSkillTag.objects.filter(pk=tag.pk).exists())
        self.assertTrue(SkillPrerequisite.objects.filter(pk=edge.pk).exists())

    def test_hidden_creation_fk_is_reported_as_generic_conflict(self):
        skill = self.skill()
        Creation.objects.create(user=self.child, primary_skill=skill, image="synthetic.png", occurred_on=timezone.localdate())
        self.assert_blocked("skill", skill)

    def test_badge_keeps_earned_marker_and_private_gate(self):
        badge = self.badge()
        earned = UserBadge.objects.create(user=self.child, badge=badge)
        quest = self.quest(required_badge=badge)
        self.assert_blocked("badge", badge)
        self.assertTrue(UserBadge.objects.filter(pk=earned.pk).exists())
        quest.refresh_from_db()
        self.assertEqual(quest.required_badge_id, badge.pk)

    def goal(self):
        now = timezone.now()
        return ChallengeGoal.objects.create(user=self.child, family=self.child.family, created_by=self.other_parent,
            name="Saved personal promise", metric="count", target=1, timezone_name="UTC", starts_at=now,
            ends_at=now + timedelta(days=7))

    def test_saved_goal_skill_tags_are_dependencies_without_runtime_fks(self):
        skill, goal = self.skill(), self.goal()
        goal.skill_tags = [{"skill_id": skill.pk, "xp_weight": 1}]
        goal.save(update_fields=["skill_tags"])
        self.assert_blocked("skill", skill)

    def test_saved_occurrence_skill_tags_are_dependencies_after_goal_tags_change(self):
        skill, goal = self.skill(), self.goal()
        ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            status="completed", snapshot={"skill_tags": [{"skill_id": skill.pk, "xp_weight": 1}]})
        self.assert_blocked("skill", skill)

    def test_future_schedule_skill_tags_are_dependencies(self):
        skill, goal = self.skill(), self.goal()
        ChallengeSchedule.objects.create(goal=goal, starts_at=goal.ends_at,
            snapshot={"skill_tags": [{"skill_id": skill.pk, "xp_weight": 1}]})
        self.assert_blocked("skill", skill)

    def test_retained_source_category_identity_is_still_in_use(self):
        other_category = SkillCategory.objects.create(name="Current category")
        skill = Skill.objects.create(name="Moved skill", category=other_category)
        self.override(skill, source={"name": skill.name, "category_id": self.category.pk})
        self.assert_blocked("category", self.category)

    def test_malformed_retained_source_fails_closed_without_server_error(self):
        skill = self.skill()
        self.override(skill, source={"name": ["Invalid source name"], "category_id": self.category.pk})
        self.assert_blocked("skill", skill)

    def test_retained_override_prerequisite_blocks_an_otherwise_unused_skill(self):
        skill, successor = self.skill(), self.skill("Authored successor")
        self.override(successor, values={"prerequisites": [{"required_skill_id": skill.pk, "required_level": 1}]})
        self.assert_blocked("skill", skill)

    def test_retained_quest_override_skill_and_badge_references_are_dependencies(self):
        skill, badge, quest = self.skill(), self.badge(), self.quest()
        self.override(quest, values={"required_badge": badge.pk, "skill_tags": [{"skill_id": skill.pk}]})
        self.assert_blocked("skill", skill)
        self.assert_blocked("badge", badge)

    def test_saved_catalog_gate_blocks_skill_and_badge_after_runtime_gate_changes(self):
        skill, badge, goal = self.skill(), self.badge(), self.goal()
        goal.catalog_gate_snapshot = {"required_skill_id": skill.pk, "required_badge_id": badge.pk}
        goal.save(update_fields=["catalog_gate_snapshot"])
        self.assert_blocked("skill", skill)
        self.assert_blocked("badge", badge)

    def test_category_named_by_badge_rule_is_in_use(self):
        Badge.objects.create(name="Mastery", description="Rule", criteria_type="category_mastery",
                             criteria_value={"category": self.category.name, "min_level": 2})
        self.assert_blocked("category", self.category)

    def test_category_quest_trigger_filter_is_a_runtime_dependency(self):
        self.quest(trigger_filter={"skill_category_id": self.category.pk})
        self.assert_blocked("category", self.category)

    def test_category_goal_trigger_filter_is_a_saved_dependency(self):
        goal = self.goal()
        goal.trigger_filter = {"skill_category_id": self.category.pk}
        goal.save(update_fields=["trigger_filter"])
        self.assert_blocked("category", self.category)

    def test_category_occurrence_filter_survives_template_and_goal_rule_changes(self):
        goal = self.goal()
        ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            snapshot={"filter": {"skill_category_id": self.category.pk}}, status="completed")
        self.assert_blocked("category", self.category)

    def test_category_future_schedule_filter_is_a_saved_dependency(self):
        goal = self.goal()
        ChallengeSchedule.objects.create(goal=goal, starts_at=goal.ends_at,
            snapshot={"filter": {"skill_category_id": self.category.pk}})
        self.assert_blocked("category", self.category)

    def test_category_retained_quest_filter_is_a_source_dependency(self):
        quest = self.quest()
        self.override(quest, values={"trigger_filter": {"skill_category_id": self.category.pk}})
        self.assert_blocked("category", self.category)

    def test_category_retained_badge_name_rule_is_a_source_dependency(self):
        badge = self.badge()
        self.override(badge, values={"criteria_type": "category_projects",
                                   "criteria_value": {"category": self.category.name.upper(), "count": 1}})
        self.assert_blocked("category", self.category)

    def test_category_projects_name_is_case_insensitive(self):
        Badge.objects.create(name="Project category", description="Rule", criteria_type="category_projects",
                             criteria_value={"category": self.category.name.upper(), "count": 1})
        self.assert_blocked("category", self.category)

    def test_plural_category_count_is_not_a_named_category_dependency(self):
        Badge.objects.create(name="Broad projects", description="Rule", criteria_type="category_projects",
                             criteria_value={"categories": 3, "category": self.category.name})
        self.assertEqual(self.delete("rest", "category", self.category)[0], 204)

    def test_category_mastery_name_remains_exact(self):
        Badge.objects.create(name="Different mastery", description="Rule", criteria_type="category_mastery",
                             criteria_value={"category": self.category.name.upper(), "min_level": 2})
        self.assertEqual(self.delete("rest", "category", self.category)[0], 204)

    def test_taxonomy_added_inside_registered_bundled_pack_is_indexed(self):
        from apps.rpg.content.taxonomy_deletion import _bundled_identities
        category = SkillCategory.objects.create(name="New installed taxonomy")
        with TemporaryDirectory(prefix="abby-taxonomy-sources-") as directory:
            root = Path(directory)
            for pack, filenames in {
                "initial": ("skill_tree.yaml", "badges.yaml"),
                "bundled/reading-adventures": ("skill_tree.yaml",),
                "bundled/collector-reading-2026": ("badges.yaml",),
            }.items():
                path = root / "content/rpg" / pack
                path.mkdir(parents=True)
                for filename in filenames:
                    data = "{}\n"
                    if pack == "bundled/reading-adventures":
                        data = "categories:\n  - name: New installed taxonomy\n"
                    (path / filename).write_text(data)
            _bundled_identities.cache_clear()
            self.addCleanup(_bundled_identities.cache_clear)
            with override_settings(BASE_DIR=root):
                self.assert_blocked("category", category)

    def test_bundled_source_cannot_be_deleted_even_when_runtime_empty(self):
        category = SkillCategory.objects.create(name="Coding")
        self.assert_blocked("category", category)

    def test_renamed_bundled_source_keeps_its_earliest_identity(self):
        category = SkillCategory.objects.create(name="Authored coding label")
        self.override(category, source={"name": "Coding"})
        self.assert_blocked("category", category)

    def test_missing_bundled_source_fails_closed_without_exposing_paths(self):
        from apps.rpg.content.taxonomy_deletion import _bundled_identities
        _bundled_identities.cache_clear()
        self.addCleanup(_bundled_identities.cache_clear)
        with patch("apps.rpg.content.taxonomy_deletion.Path.read_text", side_effect=FileNotFoundError("Private path")):
            self.assert_blocked("skill", self.skill())

    def test_pack_claim_requires_reconciliation_even_for_own_unused_row(self):
        skill = self.skill()
        ContentPackEntry.objects.create(pack="own-pack", family=self.parent.family, kind="skill", key="skill",
                                        model_label="achievements.skill", object_id=skill.pk)
        self.assert_blocked("skill", skill)
        self.assertTrue(ContentPackEntry.objects.filter(object_id=skill.pk).exists())

    def test_foreign_target_is_read_only_for_rest_and_mcp(self):
        skill = self.skill()
        self.override(skill, family=self.other_parent.family)
        for surface in ("rest", "mcp"):
            status, data = self.delete(surface, "skill", skill)
            self.assertEqual(status, 403 if surface == "rest" else 400)
            if surface == "mcp":
                self.assertEqual(data["error"]["code"], "permission_denied")
            self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())

    def test_unused_own_direct_override_is_cleaned_without_orphans(self):
        for surface in ("rest", "mcp"):
            skill = self.skill(f"Unused own {surface}")
            override = self.override(skill)
            object_id = skill.pk
            status, data = self.delete(surface, "skill", skill)
            self.assertEqual(status, 204 if surface == "rest" else 200)
            if surface == "mcp":
                self.assertEqual(data, {"deleted": True, "skill_id": object_id})
            self.assertFalse(Skill.objects.filter(pk=object_id).exists())
            self.assertFalse(RPGContentOverride.objects.filter(pk=override.pk).exists())

    def test_unused_unclaimed_and_missing_keep_existing_response_contract(self):
        for surface in ("rest", "mcp"):
            skill = self.skill(f"Unused {surface}")
            self.assertEqual(self.delete(surface, "skill", skill)[0], 204 if surface == "rest" else 200)
            status, data = self.delete(surface, "skill", skill)
            self.assertEqual(status, 404 if surface == "rest" else 400)
            if surface == "mcp":
                self.assertEqual(data["error"]["code"], "not_found")

    def test_all_four_unused_direct_rows_delete_and_cleanup_only_their_metadata(self):
        untouched = self.override(self.skill("Keep override"))
        for surface in ("rest", "mcp"):
            for kind in ("category", "subject", "skill", "badge"):
                with self.subTest(surface=surface, kind=kind):
                    if kind == "category":
                        obj = SkillCategory.objects.create(name=f"Empty {surface} category")
                    elif kind == "subject":
                        obj = Subject.objects.create(name=f"Empty {surface} subject", category=self.category)
                    elif kind == "skill":
                        obj = self.skill(f"Empty {surface} skill")
                    else:
                        obj = Badge.objects.create(name=f"Empty {surface} badge", description="Rule", criteria_type="first_project")
                    owned = self.override(obj)
                    pk = obj.pk
                    status, data = self.delete(surface, kind, obj)
                    self.assertEqual(status, 204 if surface == "rest" else 200)
                    if surface == "mcp":
                        self.assertEqual(data, {f"{kind}_id": pk, "deleted": True})
                    self.assertFalse(type(obj).objects.filter(pk=pk).exists())
                    self.assertFalse(RPGContentOverride.objects.filter(pk=owned.pk).exists())
        self.assertTrue(RPGContentOverride.objects.filter(pk=untouched.pk).exists())

    def test_mcp_requires_confirmation_and_publish_scope(self):
        skill = self.skill()
        status, data = self.delete("mcp", "skill", skill, confirmation=False)
        self.assertEqual(data["error"]["code"], "confirmation_required")
        with override_user(self.parent, scopes=frozenset({"mcp:read"})):
            result = async_to_sync(mcp.call_tool)("delete_skill", {"params": {"skill_id": skill.pk}, "confirmation": True})
        self.assertEqual(result.structuredContent["error"]["code"], "permission_denied")
        self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())

    def test_stale_authority_cannot_delete_unused_row(self):
        from apps.accounts.models import User
        for surface in ("rest", "mcp"):
            for change in ({"is_active": False}, {"is_staff": False}, {"role": "child"}, {"family_id": self.child.family_id}):
                with self.subTest(surface=surface, change=change):
                    skill = self.skill(f"Unused stale {surface} {len(change)} {Skill.objects.count()}")
                    User.objects.filter(pk=self.parent.pk).update(**change)
                    status, _ = self.delete(surface, "skill", skill)
                    self.assertEqual(status, 403 if surface == "rest" else 400)
                    self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())
                    User.objects.filter(pk=self.parent.pk).update(is_active=True, is_staff=True, role="parent", family_id=self.parent.family_id)
