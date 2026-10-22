"""Legacy assignment choices hide retired taxonomy while saved quests survive."""
from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.catalog_schemas import CatalogPageIn
from apps.mcp_server.schemas import AssignQuestIn, GetQuestIn, ListQuestCatalogIn, ListQuestsIn
from apps.mcp_server.tools import catalog, quests
from apps.quests.models import Quest, QuestDefinition, QuestParticipant, QuestSkillTag
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class QuestCatalogChoiceTests(TestCase):
    def setUp(self):
        own = make_family("Legacy assignment choices", parents=[{"username": "legacy-choice-parent", "is_staff": True}],
            children=[{"username": "legacy-choice-child"}])
        foreign = make_family("Foreign assignment choices", parents=[{"username": "legacy-choice-foreign", "is_staff": True}])
        self.parent, self.child, self.foreign = own.parents[0], own.children[0], foreign.parents[0]
        self.category = SkillCategory.objects.create(name="Assignment practice")
        self.subject = Subject.objects.create(name="Assignment subject", category=self.category)
        self.skill = Skill.objects.create(name="Assignment skill", category=self.category, subject=self.subject)
        self.tagged = self.definition("Tagged assignment")
        QuestSkillTag.objects.create(quest_definition=self.tagged, skill=self.skill)
        self.gated = self.definition("Skill-gated assignment", required_skill=self.skill, required_skill_level=1,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        self.filtered = self.definition("Category-filtered assignment", trigger_filter={
            "allowed_triggers": ["chore_complete"], "skill_category_id": self.category.pk})
        self.other = self.definition("Unrelated assignment")
        self.own_private = self.definition("Own family assignment", is_system=False, created_by=self.parent)
        self.foreign_private = self.definition("Foreign family assignment", is_system=False, created_by=self.foreign)

    def definition(self, name, **values):
        return QuestDefinition.objects.create(name=name, quest_type="collection", target_value=2,
            **{"is_system": True, "trigger_filter": {"allowed_triggers": ["chore_complete"]}, **values})

    def catalog_ids(self):
        with override_user(self.parent):
            result = quests.list_quest_catalog(ListQuestCatalogIn())
        return {row["id"] for row in result["quest_definitions"]}

    def test_new_assignment_choices_respect_each_retirement_level_and_restore(self):
        all_choices = {self.tagged.pk, self.gated.pk, self.filtered.pk, self.other.pk, self.own_private.pk}
        self.assertEqual(self.catalog_ids(), all_choices)
        for retired, unavailable in (
            (self.skill, {self.tagged.pk, self.gated.pk}),
            (self.subject, {self.tagged.pk, self.gated.pk}),
            (self.category, {self.tagged.pk, self.gated.pk, self.filtered.pk}),
        ):
            with self.subTest(retired=retired._meta.label_lower):
                retired.is_retired = True
                retired.save(update_fields=["is_retired"])
                with override_user(self.parent), self.assertRaisesRegex(MCPValidationError, "Retired"):
                    quests.assign_quest(AssignQuestIn(definition_id=self.tagged.pk, user_id=self.child.pk))
                self.assertEqual(self.catalog_ids(), all_choices - unavailable)
                with override_user(self.parent):
                    management = catalog.read_rpg_catalog(CatalogPageIn(section="quests"))["results"]
                self.assertTrue(unavailable <= {row["id"] for row in management})
                self.assertTrue(all(not row["available_for_new_user"] for row in management if row["id"] in unavailable))
                self.assertNotIn(self.foreign_private.pk, self.catalog_ids())
                retired.is_retired = False
                retired.save(update_fields=["is_retired"])
                self.assertEqual(self.catalog_ids(), all_choices)

    def test_retirement_hides_new_choice_but_keeps_saved_quest_and_family_history(self):
        with override_user(self.parent):
            accepted = quests.assign_quest(AssignQuestIn(definition_id=self.tagged.pk, user_id=self.child.pk))
        before = {model: list(model.objects.order_by("pk").values()) for model in (Quest, QuestParticipant)}
        self.category.is_retired = True
        self.category.save(update_fields=["is_retired"])
        self.assertNotIn(self.tagged.pk, self.catalog_ids())
        with override_user(self.parent):
            reopened = quests.get_quest(GetQuestIn(quest_id=accepted["id"]))
            history = quests.list_quests(ListQuestsIn(user_id=self.child.pk))
        self.assertEqual(reopened["id"], accepted["id"])
        self.assertEqual(reopened["definition"]["id"], self.tagged.pk)
        self.assertEqual([row["id"] for row in history["quests"]], [accepted["id"]])
        self.assertEqual(before, {model: list(model.objects.order_by("pk").values()) for model in before})
        self.assertFalse(Quest.objects.filter(definition__in=[self.gated, self.filtered]).exists())
