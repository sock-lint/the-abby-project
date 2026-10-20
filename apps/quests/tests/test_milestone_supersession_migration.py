"""Real historical milestone state precedes catalog identity reconciliation."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from django.test import SimpleTestCase


class MilestoneSupersessionMigrationTests(SimpleTestCase):
    def test_upgrade_preserves_distinct_gates_and_canonicalizes_equivalent_prerequisites(self):
        script = textwrap.dedent('''
            from datetime import timedelta
            import django
            django.setup()
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            from django.utils import timezone
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            preserved_apps = {"accounts", "achievements", "rewards", "rpg"}
            others = [node for node in executor.loader.graph.leaf_nodes() if node[0] in preserved_apps]
            before = others + [("quests", "0010_milestone_gate_acceptance")]
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            Definition = old.get_model("quests", "QuestDefinition")
            Family = old.get_model("families", "Family")
            User = old.get_model("accounts", "User")
            family = Family.objects.create(name="Milestone upgrade", slug="milestone-upgrade")
            parent = User.objects.create(username="milestone-upgrade-parent", role="parent", family=family)
            child = User.objects.create(username="milestone-upgrade-child", role="child", family=family)
            category = old.get_model("achievements", "SkillCategory").objects.create(name="Upgrade skills")
            Skill = old.get_model("achievements", "Skill")
            skill = Skill.objects.create(name="Reading", category=category)
            other_skill = Skill.objects.create(name="Other reading", category=category)
            def definition(name, **changes):
                fields = dict(name=name, quest_type="collection", target_value=3, duration_days=14,
                              is_system=True, trigger_filter={"allowed_triggers": ["reading_logged"]})
                return Definition.objects.create(**{**fields, **changes})
            # Descendants precede prerequisites in ID order.
            tips = [definition("Equivalent final") for _ in range(2)]
            middles = [definition("Equivalent middle") for _ in range(2)]
            prior = definition("Equivalent starter")
            prior_alias = definition(prior.name)
            other_prior = definition("Different starter")
            for children, parents in ((tips, middles), (middles, [prior, prior_alias])):
                for descendant, prerequisite in zip(children, parents):
                    Definition.objects.filter(pk=descendant.pk).update(prerequisite_quest_id=prerequisite.pk)
            gates = dict(prerequisite_quest=prior, required_skill=skill, required_skill_level=1)
            canonical = definition("Divergent milestone", **gates)
            alias = definition(canonical.name, **gates, description="Equivalent display copy")
            divergent = [definition(canonical.name, **{**gates, **change}) for change in (
                {"required_skill_level": 2}, {"required_skill": other_skill}, {"prerequisite_quest": other_prior},
            )]
            dependent = definition("Dependent milestone", prerequisite_quest=prior_alias)
            owned = definition("Owned legacy policy", prerequisite_quest=prior_alias, created_by=parent)
            private = definition("Private legacy policy", prerequisite_quest=prior_alias, created_by=parent,
                                 is_system=False)
            owned_before = list(Definition.objects.filter(pk__in=[owned.pk, private.pk]).order_by("pk").values())
            now = timezone.now()
            gate = {"version": 1, "prerequisite_quest_id": prior_alias.pk,
                    "required_skill_id": None, "required_skill_level": 0, "required_badge_id": None}
            Goal = old.get_model("quests", "ChallengeGoal")
            Occurrence = old.get_model("quests", "ChallengeOccurrence")
            alias_goal_id = None
            for index, policy in enumerate([dependent, *divergent, middles[1]]):
                goal = Goal.objects.create(user=child, family=family, catalog_definition=policy, is_catalog=True,
                    name=policy.name, metric="count", target=3, unit="actions", starts_at=now-timedelta(days=2),
                    ends_at=now+timedelta(days=12), catalog_gate_snapshot=gate, catalog_gate_activity_id=17)
                if policy.pk == middles[1].pk:
                    alias_goal_id = goal.pk
                Occurrence.objects.create(goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
                    snapshot={"name": policy.name, "catalog_gate": gate, "coins": 7}, progress=3 if index == 0 else 1,
                    status="completed" if index == 0 else "active", awarded_at=now if index == 0 else None,
                    completed_at=now if index == 0 else None, reward_receipt={"coins": 7} if index == 0 else {})
            legacy = old.get_model("quests", "Quest").objects.create(
                definition=prior_alias, end_date=now, status="completed", reward_items_snapshot=[])
            old.get_model("quests", "QuestParticipant").objects.create(quest=legacy, user=child)
            old.get_model("rewards", "CoinLedger").objects.create(user=child, amount=7, reason="adjustment")
            old.get_model("achievements", "SkillProgress").objects.create(user=child, skill=skill, xp_points=10)
            tracked = [("quests", name) for name in ("ChallengeGoal", "ChallengeOccurrence", "Quest", "QuestParticipant")]
            tracked += [("rewards", "CoinLedger"), ("achievements", "SkillProgress")]
            saved = {(app, name): list(old.get_model(app, name).objects.order_by("pk").values()) for app, name in tracked}

            executor = MigrationExecutor(connection)
            after = others + [("quests", "0013_merge_milestone_and_goal_controls")]
            executor.migrate(after)
            new = executor.loader.project_state(after).apps
            Definition = new.get_model("quests", "QuestDefinition")
            assert Definition.objects.get(pk=alias.pk).superseded_by_id == canonical.pk
            assert not Definition.objects.filter(pk__in=[row.pk for row in divergent],
                                                 superseded_by__isnull=False).exists(), "distinct gates collapsed"
            assert Definition.objects.get(pk=prior_alias.pk).superseded_by_id == prior.pk
            assert Definition.objects.get(pk=dependent.pk).prerequisite_quest_id == prior.pk
            assert Definition.objects.get(pk=middles[1].pk).superseded_by_id == middles[0].pk
            assert Definition.objects.get(pk=tips[1].pk).superseded_by_id == tips[0].pk
            assert Definition.objects.get(pk=middles[0].pk).prerequisite_quest_id == prior.pk
            assert Definition.objects.get(pk=tips[0].pk).prerequisite_quest_id == middles[0].pk
            assert list(Definition.objects.filter(pk__in=[owned.pk, private.pk]).order_by("pk")
                        .values(*owned_before[0])) == owned_before
            for (app, name), rows in saved.items():
                expected = rows
                if name == "ChallengeGoal":
                    expected = [{**row, "catalog_definition_id": middles[0].pk}
                                if row["id"] == alias_goal_id else row for row in rows]
                assert list(new.get_model(app, name).objects.order_by("pk").values(*rows[0])) == expected, name
            plan = executor.loader.graph.forwards_plan(("quests", "0010_catalog_supersession"))
            assert plan.index(("quests", "0010_milestone_gate_acceptance")) < plan.index(
                ("quests", "0010_catalog_supersession")), "reconciliation lacks historical milestone fields"
            print("Historical milestone equivalence, prerequisites and saved rewards preserved")
        ''')
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({"DATABASE_URL": "sqlite:///:memory:", "DJANGO_SETTINGS_MODULE": "config.settings_test",
                    "SECRET_KEY": "synthetic-milestone-upgrade", "SENTRY_DSN": "", "PYTHONDONTWRITEBYTECODE": "1"})
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[3], env=env,
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Historical milestone equivalence, prerequisites and saved rewards preserved", result.stdout)
