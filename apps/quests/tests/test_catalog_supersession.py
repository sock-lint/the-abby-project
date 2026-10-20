"""Duplicate catalog identities retire future offers without rewriting promises."""
import importlib
import os
import subprocess
import sys
import textwrap
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory
from apps.mcp_server.catalog import audit_catalog_rows, catalog_row
from apps.quests.controls import control_context
from apps.quests.goals import _occurrence, ingest_activity, list_goals
from apps.quests.milestone_eligibility import milestone_eligibility, validate_milestone_gate
from apps.quests.models import (
    ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant,
)
from apps.quests.queries import active_system_definitions, definitions_visible_to
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


class CatalogSupersessionTests(TestCase):
    def setUp(self):
        household = make_family("Catalog reconciliation", parents=[{"username": "reconcile-parent"}],
                                children=[{"username": "reconcile-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        self.now = timezone.now()

    def definition(self, **changes):
        values = {"name": "A stable catalog challenge", "description": "First description",
                  "quest_type": "collection", "target_value": 1, "duration_days": 7,
                  "trigger_filter": {"allowed_triggers": ["movement_session"]},
                  "coin_reward": 5, "is_system": True}
        return QuestDefinition.objects.create(**{**values, **changes})

    def reconcile(self):
        migration = importlib.import_module("apps.quests.migrations.0010_catalog_supersession")
        migration.reconcile_definitions(apps, SimpleNamespace(connection=connection))

    def saved_goal(self, definition):
        goal = ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, catalog_definition=definition, is_catalog=True,
            name=definition.name, description="Accepted description", metric="count", target=1,
            unit="actions", trigger_filter=definition.trigger_filter, timezone_name="America/Phoenix",
            starts_at=self.now - timedelta(days=1), ends_at=self.now + timedelta(days=6),
            repeat_days=7, coin_reward=5,
        )
        row = ChallengeOccurrence.objects.create(
            goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
            snapshot={"name": goal.name, "description": goal.description, "metric": "count",
                      "target": "1", "unit": "actions", "filter": goal.trigger_filter,
                      "coins": 5, "xp": 0, "skill_tags": [], "items": [],
                      "catalog_name": definition.name, "catalog_type": "collection"},
        )
        return goal, row

    def test_divergent_system_names_are_held_from_new_offers_starts_and_audited(self):
        first = self.definition()
        second = self.definition(target_value=3)
        private = self.definition(is_system=False, created_by=self.parent)
        self.assertEqual(list_goals(self.child)["results"], [])
        self.assertEqual(list(definitions_visible_to(self.parent)), [private])
        with self.assertRaisesMessage(ValueError, "Quest not found"):
            QuestService.start_quest(self.child, first.pk)
        findings, _ = audit_catalog_rows("quests", [first, second])
        self.assertEqual({row["id"] for row in findings if row["code"] == "ambiguous_system_quest"},
                         {first.pk, second.pk})
        self.assertFalse(catalog_row("quests", first)["available_for_new_user"])
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_reconciled_duplicate_enrolls_and_pays_only_one_new_goal(self):
        canonical = self.definition()
        alias = self.definition(description="A harmless display edit")
        private = self.definition(is_system=False, created_by=self.parent)
        self.reconcile()
        alias.refresh_from_db()
        self.assertEqual(alias.superseded_by_id, canonical.pk)
        self.assertEqual(set(definitions_visible_to(self.parent).values_list("pk", flat=True)),
                         {canonical.pk, private.pk})
        offered = timezone.now()
        with patch("django.utils.timezone.now", return_value=offered):
            list_goals(self.child)
            ingest_activity(self.child, "movement_session", "after-reconciliation", "movement_session",
                            occurred_at=offered, context={"duration_minutes": 5})
        self.assertEqual(ChallengeGoal.objects.count(), 1)
        self.assertEqual(ChallengeGoal.objects.get().catalog_definition_id, canonical.pk)
        self.assertEqual(list(CoinLedger.objects.values_list("amount", flat=True)), [5])
        self.assertEqual(ChallengeOccurrence.objects.get().status, "completed")
        row = catalog_row("quests", alias)
        self.assertEqual(row["superseded_by"], canonical.pk)
        self.assertFalse(row["available_for_new_user"])

    def test_milestone_gate_differences_keep_distinct_definitions_and_promises(self):
        category = SkillCategory.objects.create(name="Reconciliation skills")
        skill = Skill.objects.create(name="First required skill", category=category)
        other_skill = Skill.objects.create(name="Other required skill", category=category)
        prior = self.definition(name="First prerequisite")
        other_prior = self.definition(name="Other prerequisite")
        gates = {"prerequisite_quest": prior, "required_skill": skill, "required_skill_level": 1}
        canonical = self.definition(**gates)
        alias = self.definition(**gates, description="Equivalent future display copy")
        divergent = [self.definition(**{**gates, **change}) for change in (
            {"prerequisite_quest": other_prior}, {"required_skill": other_skill}, {"required_skill_level": 2},
        )]
        for definition in divergent:
            self.saved_goal(definition)
        goals_before = list(ChallengeGoal.objects.order_by("pk").values())
        windows_before = list(ChallengeOccurrence.objects.order_by("pk").values())

        self.reconcile()

        alias.refresh_from_db()
        self.assertEqual(alias.superseded_by_id, canonical.pk, "genuine duplicates still reconcile")
        self.assertFalse(QuestDefinition.objects.filter(pk__in=[row.pk for row in divergent],
                                                      superseded_by__isnull=False).exists())
        self.assertEqual(list(ChallengeGoal.objects.order_by("pk").values()), goals_before)
        self.assertEqual(list(ChallengeOccurrence.objects.order_by("pk").values()), windows_before)
        self.assertFalse(CoinLedger.objects.exists())

    def test_equivalent_prerequisite_is_canonicalized_without_rewriting_accepted_gates(self):
        prior = self.definition(name="Equivalent prerequisite")
        alias = self.definition(name=prior.name)
        dependent = self.definition(name="Dependent milestone", prerequisite_quest=alias,
                                    trigger_filter={"allowed_triggers": ["reading_logged"]})
        private = self.definition(name="Private gated history", prerequisite_quest=alias,
                                  is_system=False, created_by=self.parent)
        owned = self.definition(name="Owned system gated history", prerequisite_quest=alias, created_by=self.parent)
        goal, window = self.saved_goal(dependent)
        goal.catalog_gate_snapshot = {"version": 1, "prerequisite_quest_id": alias.pk,
                                      "required_skill_id": None, "required_skill_level": 0,
                                      "required_badge_id": None}
        goal.save(update_fields=["catalog_gate_snapshot"])
        window.snapshot["catalog_gate"] = goal.catalog_gate_snapshot
        window.save(update_fields=["snapshot"])
        before_goal = ChallengeGoal.objects.values().get(pk=goal.pk)
        before_window = ChallengeOccurrence.objects.values().get(pk=window.pk)
        before_owned = [QuestDefinition.objects.values().get(pk=row.pk) for row in (private, owned)]

        self.reconcile()

        dependent.refresh_from_db()
        self.assertEqual(dependent.prerequisite_quest_id, prior.pk)
        validate_milestone_gate(dependent)
        completed = Quest.objects.create(definition=alias, status="completed", end_date=self.now)
        QuestParticipant.objects.create(quest=completed, user=self.child)
        self.assertTrue(milestone_eligibility(self.child, dependent, new_enrollment=False)["unlocked"])
        self.assertTrue(control_context(self.child)["milestone_retry"][dependent.pk],
                        "batched eligibility uses the same canonical prerequisite")
        self.assertEqual(ChallengeGoal.objects.values().get(pk=goal.pk), before_goal)
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=window.pk), before_window)
        self.assertEqual([QuestDefinition.objects.values().get(pk=row.pk) for row in (private, owned)], before_owned)
        self.assertFalse(CoinLedger.objects.exists())

    def test_sole_alias_goal_keeps_identity_and_repeat_anchor_when_repointed(self):
        canonical = self.definition(is_repeatable=True)
        alias = self.definition(is_repeatable=True)
        goal, row = self.saved_goal(alias)
        before = ChallengeOccurrence.objects.values().get(pk=row.pk)
        self.reconcile()
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, canonical.pk)
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=row.pk), before)
        future = _occurrence(goal, row.ends_at + timedelta(seconds=1))
        self.assertEqual(future.goal_id, goal.pk)
        self.assertEqual(future.starts_at, row.ends_at)

    def test_overlapping_alias_keeps_accepted_window_but_never_repeats(self):
        canonical = self.definition(is_repeatable=True)
        alias = self.definition(is_repeatable=True)
        self.saved_goal(canonical)
        goal, row = self.saved_goal(alias)
        before = ChallengeOccurrence.objects.values().get(pk=row.pk)
        self.reconcile()
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, alias.pk)
        self.assertEqual(_occurrence(goal, self.now).pk, row.pk)
        self.assertIsNone(_occurrence(goal, row.ends_at + timedelta(seconds=1)))
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=row.pk), before)
        self.assertEqual(ChallengeOccurrence.objects.filter(goal=goal).count(), 1)
        self.assertFalse(CoinLedger.objects.exists())
        with self.assertRaises(ProtectedError):
            canonical.delete()

    def test_legacy_alias_completion_blocks_canonical_reacceptance_and_enrollment(self):
        canonical = self.definition()
        alias = self.definition()
        completed = Quest.objects.create(definition=alias, status="completed", end_date=self.now)
        QuestParticipant.objects.create(quest=completed, user=self.child)
        self.reconcile()
        with self.assertRaisesMessage(ValueError, "already completed"):
            QuestService.start_quest(self.child, canonical.pk)
        self.assertEqual(list_goals(self.child)["results"][0]["id"], f"legacy:{completed.pk}")
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())

    def test_bundled_reload_updates_only_the_canonical_definition(self):
        from apps.rpg.content.loader import ContentPack

        canonical = self.definition()
        alias = self.definition()
        self.reconcile()
        saved_alias = QuestDefinition.objects.values().get(pk=alias.pk)
        pack = ContentPack(Path(__file__).parent, parsed_content={"quests": {"quests": [{
            "name": canonical.name, "description": "Updated future offer", "quest_type": "collection",
            "target_value": 3, "duration_days": 7, "coin_reward": 8,
            "trigger_filter": {"allowed_triggers": ["movement_session"]},
        }]}})
        pack.load()
        canonical.refresh_from_db()
        self.assertEqual((canonical.target_value, canonical.coin_reward), (3, 8))
        self.assertEqual(QuestDefinition.objects.values().get(pk=alias.pk), saved_alias)
        self.assertEqual(QuestDefinition.objects.count(), 2)
        self.assertNotIn("ambiguous_global_quest", pack.stats.skipped)

    def test_creator_owned_system_identity_and_goal_survive_unowned_reconciliation(self):
        canonical = self.definition()
        alias = self.definition()
        owned = self.definition(created_by=self.parent)
        owned_goal, owned_window = self.saved_goal(owned)
        unrelated = self.definition(name="Unambiguous global challenge")
        saved_definition = QuestDefinition.objects.values().get(pk=owned.pk)
        saved_goal = ChallengeGoal.objects.values().get(pk=owned_goal.pk)
        saved_window = ChallengeOccurrence.objects.values().get(pk=owned_window.pk)

        self.reconcile()

        alias.refresh_from_db()
        self.assertEqual(alias.superseded_by_id, canonical.pk)
        self.assertEqual(QuestDefinition.objects.values().get(pk=owned.pk), saved_definition)
        self.assertEqual(ChallengeGoal.objects.values().get(pk=owned_goal.pk), saved_goal)
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=owned_window.pk), saved_window)
        self.assertEqual(set(definitions_visible_to(self.parent).values_list("pk", flat=True)), {unrelated.pk})
        list_goals(self.child)
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=canonical).exists())
        self.assertTrue(ChallengeGoal.objects.filter(catalog_definition=unrelated).exists())
        findings, _ = audit_catalog_rows("quests", [canonical, owned])
        self.assertEqual({row["id"] for row in findings if row["code"] == "ambiguous_system_quest"},
                         {canonical.pk, owned.pk})
        self.assertFalse(CoinLedger.objects.exists())

    def test_workbench_can_edit_canonical_copy_but_cannot_reactivate_an_alias(self):
        from apps.rpg.content.loader import ContentPackError
        from apps.rpg.content.workbench import create_draft, preview_draft, save_draft

        canonical = self.definition()
        alias = self.definition()
        self.reconcile()
        self.parent.is_staff = True
        self.parent.save(update_fields=["is_staff"])
        draft = create_draft(self.parent, "Reviewed canonical display update")

        def change(definition):
            return [{"section": "quests", "object_id": definition.pk, "key": "canonical",
                     "values": {"description": "Reviewed future display copy"}}]

        draft = save_draft(self.parent, draft["id"], draft["revision"], change(canonical))
        preview = preview_draft(self.parent, draft["id"], draft["revision"])
        self.assertTrue(preview["preview"])
        canonical.refresh_from_db()
        self.assertEqual(canonical.description, "First description", "preview rolls back writes")
        draft = save_draft(self.parent, draft["id"], draft["revision"], change(alias))
        with self.assertRaisesMessage(ContentPackError, "retained alias"):
            preview_draft(self.parent, draft["id"], draft["revision"])


    def test_reverse_id_chain_equivalence_preserves_saved_history(self):
        # The deepest dependants have the smallest IDs. FK assignment happens
        # only after all prerequisite nodes exist; all final paths are valid.
        reading = {"allowed_triggers": ["reading_logged"]}
        tip = [self.definition(name="Chain tip", trigger_filter=reading) for _ in range(2)]
        middle = [self.definition(name="Chain middle", trigger_filter=reading) for _ in range(2)]
        prior = [self.definition(name="Chain starter", trigger_filter=reading) for _ in range(2)]
        for children, parents in ((tip, middle), (middle, prior)):
            for child, parent in zip(children, parents):
                child.prerequisite_quest = parent
                child.save(update_fields=["prerequisite_quest"])
        goal, occurrence = self.saved_goal(middle[1])
        occurrence.status = "completed"
        occurrence.progress = 1
        occurrence.completed_at = occurrence.awarded_at = self.now
        occurrence.reward_receipt = {"coins": 5}
        occurrence.save()
        CoinLedger.objects.create(user=self.child, amount=5, reason="adjustment")
        before_window = ChallengeOccurrence.objects.values().get(pk=occurrence.pk)
        before_ledger = list(CoinLedger.objects.values())
        self.reconcile()
        pairs = [(row[0].pk, row[1].pk, QuestDefinition.objects.get(pk=row[1].pk).superseded_by_id)
                 for row in (prior, middle, tip)]
        visible = set(active_system_definitions().values_list("pk", flat=True))
        self.assertEqual([actual for canonical, alias, actual in pairs], [row[0].pk for row in (prior, middle, tip)])
        self.assertTrue({row[0].pk for row in (prior, middle, tip)} <= visible)
        self.assertEqual(QuestDefinition.objects.get(pk=middle[0].pk).prerequisite_quest_id, prior[0].pk)
        self.assertEqual(QuestDefinition.objects.get(pk=tip[0].pk).prerequisite_quest_id, middle[0].pk)
        goal.refresh_from_db()
        self.assertEqual(goal.catalog_definition_id, middle[0].pk)
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=occurrence.pk), before_window)
        self.assertEqual(list(CoinLedger.objects.values()), before_ledger)
        before_second = {model: list(model.objects.order_by("pk").values())
                         for model in (QuestDefinition, ChallengeGoal, ChallengeOccurrence, CoinLedger)}
        self.reconcile()
        self.assertEqual({model: list(model.objects.order_by("pk").values()) for model in before_second}, before_second)

    def test_invalid_paths_and_divergent_gates_remain_unchanged(self):
        reading = {"allowed_triggers": ["reading_logged"]}
        cycles = [self.definition(name=f'Cycle node {index}', trigger_filter=reading) for index in range(2)]
        for row, parent in zip(cycles, reversed(cycles)):
            row.prerequisite_quest = parent
            row.save(update_fields=["prerequisite_quest"])
        self_gated = [self.definition(name="Self gated duplicate", trigger_filter=reading) for _ in range(2)]
        for row in self_gated:
            row.prerequisite_quest = row
            row.save(update_fields=["prerequisite_quest"])
        blocked = [self.definition(name="Cycle successors", prerequisite_quest=cycles[0], trigger_filter=reading)
                   for _ in range(2)]
        private = self.definition(name="Private prerequisite", is_system=False, created_by=self.parent)
        blocked += [self.definition(name="Private successors", prerequisite_quest=private, trigger_filter=reading)
                    for _ in range(2)]
        root = self.definition(name="A trusted prerequisite")
        owned_alias = self.definition(name="Owner alias is not trusted", created_by=self.parent, superseded_by=root)
        blocked += [self.definition(name="Mixed provenance successors", prerequisite_quest=parent, trigger_filter=reading)
                    for parent in (root, owned_alias)]
        protected = [*cycles, *self_gated, *blocked, private, owned_alias]
        before = {row.pk: QuestDefinition.objects.values().get(pk=row.pk) for row in protected}
        category = SkillCategory.objects.create(name="Divergent chain gates")
        skill = Skill.objects.create(name="First skill", category=category)
        other_skill = Skill.objects.create(name="Other skill", category=category)
        other_prior = self.definition(name="A different prerequisite")
        common = {"trigger_filter": reading, "prerequisite_quest": root, "required_skill": skill, "required_skill_level": 1}
        divergent = [self.definition(name="Truly divergent dependent", **{**common, **change}) for change in (
            {}, {"required_skill_level": 2}, {"required_skill": other_skill}, {"prerequisite_quest": other_prior},
        )]
        for definition in divergent:
            self.saved_goal(definition)
        goals = list(ChallengeGoal.objects.order_by("pk").values())
        windows = list(ChallengeOccurrence.objects.order_by("pk").values())
        self.reconcile()
        self.assertEqual({row.pk: QuestDefinition.objects.values().get(pk=row.pk) for row in protected}, before)
        self.assertFalse(QuestDefinition.objects.filter(pk__in=[row.pk for row in divergent],
                                                       superseded_by__isnull=False).exists())
        self.assertEqual(list(ChallengeGoal.objects.order_by("pk").values()), goals)
        self.assertEqual(list(ChallengeOccurrence.objects.order_by("pk").values()), windows)
        self.assertFalse(CoinLedger.objects.exists())

    def test_existing_trusted_alias_chains_resolve_to_direct_identities_once(self):
        root = self.definition(name="Retained canonical")
        alias = self.definition(name=root.name, superseded_by=root)
        old_alias = self.definition(name=root.name, superseded_by=alias)
        reading = {"allowed_triggers": ["reading_logged"]}
        dependent = self.definition(name="Retained dependent", prerequisite_quest=root, trigger_filter=reading)
        dependent_alias = self.definition(name=dependent.name, prerequisite_quest=old_alias, trigger_filter=reading)
        goal, occurrence = self.saved_goal(old_alias)
        before = ChallengeOccurrence.objects.values().get(pk=occurrence.pk)
        self.reconcile()
        old_alias.refresh_from_db()
        dependent_alias.refresh_from_db()
        goal.refresh_from_db()
        self.assertEqual(old_alias.superseded_by_id, root.pk)
        self.assertEqual(dependent_alias.superseded_by_id, dependent.pk)
        self.assertEqual(goal.catalog_definition_id, root.pk)
        self.assertEqual(ChallengeOccurrence.objects.values().get(pk=occurrence.pk), before)
        before_second = {model: list(model.objects.order_by("pk").values())
                         for model in (QuestDefinition, ChallengeGoal, ChallengeOccurrence, CoinLedger)}
        self.reconcile()
        self.assertEqual({model: list(model.objects.order_by("pk").values()) for model in before_second}, before_second)


class CatalogSupersessionMigrationTests(SimpleTestCase):
    def test_historical_upgrade_preserves_paid_unpaid_and_private_promises(self):
        script = textwrap.dedent('''
            from datetime import timedelta
            import django
            django.setup()
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from django.utils import timezone
            assert connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            # Migrate the real tables whose records this upgrade must preserve,
            # plus their declared dependencies; unrelated app leaves add no
            # coverage to this data migration and slow isolated setup.
            preserved_apps = {"accounts", "achievements", "rewards", "rpg"}
            others = [node for node in executor.loader.graph.leaf_nodes() if node[0] in preserved_apps]
            before = others + [("quests", "0009_challenge_discovery")]
            after = others + [("quests", "0010_catalog_supersession")]
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            Family = old.get_model("families", "Family")
            User = old.get_model(settings.AUTH_USER_MODEL)
            Definition = old.get_model("quests", "QuestDefinition")
            Tag = old.get_model("quests", "QuestSkillTag")
            Reward = old.get_model("quests", "QuestRewardItem")
            Goal = old.get_model("quests", "ChallengeGoal")
            Occurrence = old.get_model("quests", "ChallengeOccurrence")
            family = Family.objects.create(name="Historical duplicate household", slug="historical-duplicates")
            parent = User.objects.create(username="historical-parent", role="parent", family=family)
            sole = User.objects.create(username="historical-sole-alias", role="child", family=family)
            both = User.objects.create(username="historical-both-identities", role="child", family=family)
            category = old.get_model("achievements", "SkillCategory").objects.create(name="Historical skill category")
            skill = old.get_model("achievements", "Skill").objects.create(name="Historical skill", category=category)
            item = old.get_model("rpg", "ItemDefinition").objects.create(
                name="Historical title", slug="historical-title", item_type="cosmetic_title")
            def definition(**changes):
                fields = dict(name="An exact duplicate", description="Saved copy", quest_type="collection",
                    target_value=2, duration_days=7, coin_reward=7, xp_reward=20, is_repeatable=True,
                    is_system=True, trigger_filter={"allowed_triggers":["movement_session"]})
                fields.update(changes)
                row = Definition.objects.create(**fields)
                Tag.objects.create(quest_definition=row, skill=skill, xp_weight=1)
                Reward.objects.create(quest_definition=row, item=item, quantity=1)
                return row
            canonical = definition()
            alias = definition(description="Later harmless presentation")
            private = definition(is_system=False, created_by=parent)
            owned_system = definition(created_by=parent)
            divergent = []
            for fields in ({"target_value":3}, {"duration_days":8}, {"coin_reward":8},
                           {"xp_reward":21}, {"is_repeatable":False}, {"quest_type":"boss"},
                           {"trigger_filter":{"allowed_triggers":["journal_entry"]}}):
                divergent.append(definition(**fields))
            different_weight = definition()
            Tag.objects.filter(quest_definition=different_weight).update(xp_weight=2)
            different_item = definition()
            Reward.objects.filter(quest_definition=different_item).update(quantity=2)
            divergent.extend([different_weight, different_item])
            now = timezone.now()
            def goal(user, definition, catalog=True):
                return Goal.objects.create(user=user, family=family, catalog_definition=definition,
                    is_catalog=catalog, name="Accepted promise", description="Original private description",
                    metric="count", target=2, unit="actions", starts_at=now-timedelta(days=1),
                    ends_at=now+timedelta(days=6), timezone_name="America/Phoenix", repeat_days=7,
                    coin_reward=7, xp_reward=20, skill_tags=[{"skill_id":skill.pk,"xp_weight":1}])
            sole_goal = goal(sole, alias)
            canonical_goal = goal(both, canonical)
            alias_goal = goal(both, alias)
            private_goal = goal(sole, private, False)
            owned_system_goal = goal(sole, owned_system)
            snapshot = {"name":"Accepted promise", "coins":7, "xp":20, "items":[{"item_id":item.pk,"quantity":1}]}
            paid = Occurrence.objects.create(goal=sole_goal, starts_at=now-timedelta(days=8),
                ends_at=now-timedelta(days=1), snapshot=snapshot, progress=2, status="completed",
                completed_at=now-timedelta(days=2), awarded_at=now-timedelta(days=2), reward_receipt={"coins":7,"xp":20})
            unpaid = Occurrence.objects.create(goal=sole_goal, starts_at=sole_goal.starts_at,
                ends_at=sole_goal.ends_at, snapshot=snapshot, progress=1)
            for row in (canonical_goal, alias_goal, private_goal, owned_system_goal):
                Occurrence.objects.create(goal=row, starts_at=row.starts_at, ends_at=row.ends_at,
                    snapshot=snapshot, progress=1)
            fact = old.get_model("quests", "ChallengeActivity").objects.create(user=sole,
                source_type="movement_session", source_id="historical-safe-1", trigger_type="movement_session",
                occurred_at=now, occurred_on=now.date(), context={"duration_minutes":5})
            old.get_model("quests", "ChallengeContribution").objects.create(occurrence=unpaid, activity=fact, amount=1)
            old.get_model("quests", "ChallengePin").objects.create(user=sole, occurrence=unpaid)
            legacy = old.get_model("quests", "Quest").objects.create(definition=alias, end_date=now, status="completed")
            old.get_model("quests", "QuestParticipant").objects.create(quest=legacy, user=sole)
            old.get_model("rewards", "CoinLedger").objects.create(user=sole, amount=7, reason="adjustment")
            old.get_model("rpg", "UserInventory").objects.create(user=sole, item=item, quantity=1)
            old.get_model("achievements", "SkillProgress").objects.create(user=sole, skill=skill, xp_points=20)
            tracked = [("quests", name) for name in ("QuestDefinition", "ChallengeGoal", "ChallengeOccurrence",
                "ChallengeActivity", "ChallengeContribution", "ChallengePin", "Quest", "QuestParticipant")]
            tracked += [("rewards", "CoinLedger"), ("rpg", "UserInventory"), ("achievements", "SkillProgress")]
            saved = {(app,name):list(old.get_model(app,name).objects.order_by("pk").values()) for app,name in tracked}
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            new = executor.loader.project_state(after).apps
            for (app,name), rows in saved.items():
                expected = rows
                if name == "ChallengeGoal":
                    expected = [{**row,"catalog_definition_id":canonical.pk} if row["id"] == sole_goal.pk else row for row in rows]
                actual = list(new.get_model(app,name).objects.order_by("pk").values(*rows[0].keys()))
                assert actual == expected, (name,actual,expected)
            Definition = new.get_model("quests", "QuestDefinition")
            assert Definition.objects.get(pk=alias.pk).superseded_by_id == canonical.pk
            assert Definition.objects.get(pk=canonical.pk).superseded_by_id is None
            assert Definition.objects.get(pk=private.pk).superseded_by_id is None
            assert Definition.objects.get(pk=owned_system.pk).superseded_by_id is None
            assert not Definition.objects.filter(pk__in=[row.pk for row in divergent],superseded_by__isnull=False).exists()
            print("Historical duplicate reconciliation preserves every paid, unpaid and private promise")
        ''')
        env = {**os.environ, "DATABASE_URL": "sqlite:///:memory:",
               "DJANGO_SETTINGS_MODULE": "config.settings_test", "SECRET_KEY": "synthetic-supersession-migration"}
        result = subprocess.run([sys.executable, "-c", script], env=env, cwd=Path(__file__).resolve().parents[3],
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Historical duplicate reconciliation preserves", result.stdout)

