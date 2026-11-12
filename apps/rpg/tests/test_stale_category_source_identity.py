"""Deleted category targets do not reserve names or impersonate live identities."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
import yaml

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rpg.content.authoring import record_direct_override, validate_source_identity
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import ContentPackEntry, RPGContentOverride
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StaleCategorySourceIdentityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = make_family("Stale category source", parents=[{
            "username": "stale-category-parent", "is_staff": True,
        }]).parents[0]
        temporary = TemporaryDirectory(prefix="abby-stale-category-source-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        (self.path / "skill_tree.yaml").write_text(yaml.safe_dump({
            "categories": [{"name": "Robotics"}],
            "subjects": [{"name": "Mechanisms", "category": "Robotics"}],
            "skills": [{"name": "Gears", "category": "Robotics", "subject": "Mechanisms"}],
        }), encoding="utf-8")

    def wire(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        payload = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", payload, payload)
        return payload

    def stale(self):
        category = SkillCategory.objects.get(pk=self.wire("create_category", {"name": "Robotics"})["id"])
        source = RPGContentOverride.objects.get(model_label="achievements.skillcategory", object_id=category.pk)
        previous_id = category.pk
        category.delete()  # Historical ORM/admin cleanup can leave non-FK provenance.
        self.assertTrue(RPGContentOverride.objects.filter(pk=source.pk).exists())
        self.assertFalse(SkillCategory.objects.filter(pk=previous_id).exists())
        return previous_id, source

    def override(self, category, lookup=None, marker=None):
        return RPGContentOverride.objects.create(model_label="achievements.skillcategory", object_id=category.pk,
            family=self.actor.family, source_lookup={"name": "Robotics"} if lookup is None else lookup,
            values={"_authoring": {"version": 1, "source": "mcp"} if marker is None else marker})

    def snapshot(self):
        return {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            SkillCategory, Subject, Skill, RPGContentOverride, ContentPackEntry,
        )}

    def startup(self):
        output = StringIO()
        with patch("apps.rpg.management.commands.loadrpgcontent.BUNDLED_PACKS", ((self.path, ""),)), \
                patch("apps.rpg.management.commands.loadrpgcontent.retire_unused_catalog_once", return_value=None):
            call_command("loadrpgcontent", stdout=output)
        return output.getvalue()

    def load_source(self, **options):
        try:
            call_command("loadrpgcontent", **options)
        except CommandError as error:
            self.fail(f"Recoverable stale category source rejected: {error}")

    def assert_recreated(self, previous_id, source):
        source_before = {field.attname: deepcopy(getattr(source, field.attname))
            for field in source._meta.concrete_fields}
        category = SkillCategory.objects.get(name="Robotics")
        self.assertNotEqual(category.pk, previous_id)
        skill = Skill.objects.get(name="Gears")
        self.assertEqual(skill.category_id, category.pk)
        self.assertEqual(skill.subject.category_id, category.pk)
        self.assertEqual(skill.subject.name, "Mechanisms")
        source.refresh_from_db()
        self.assertEqual(RPGContentOverride.objects.filter(pk=source.pk).values().get(), source_before)
        self.assertEqual(source.object_id, previous_id)
        return category

    def test_explicit_unkeyed_load_restores_canonical_category_and_dependents(self):
        previous_id, source = self.stale()
        self.load_source(pack=str(self.path), stdout=StringIO())
        self.assert_recreated(previous_id, source)
        before = self.snapshot()
        self.load_source(pack=str(self.path), stdout=StringIO())
        self.assertEqual(self.snapshot(), before)

    def test_default_startup_restores_deleted_target_without_deferring_dependents(self):
        previous_id, source = self.stale()
        output = self.startup()
        self.assertNotIn("category_source_conflict", output)
        self.assert_recreated(previous_id, source)
        before = self.snapshot()
        self.assertNotIn("category_source_conflict", self.startup())
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_accepts_recovery_but_preserves_every_saved_row(self):
        self.stale()
        before = self.snapshot()
        output = StringIO()
        self.load_source(pack=str(self.path), dry_run=True, stdout=output)
        self.assertIn("created skill_category: 1", output.getvalue())
        self.assertEqual(self.snapshot(), before)

    def test_registered_recreation_then_rename_and_reload_keeps_the_new_live_identity(self):
        previous_id, stale = self.stale()
        stale_before = RPGContentOverride.objects.filter(pk=stale.pk).values().get()
        recreated = self.wire("create_category", {"name": "Robotics"})
        self.assertNotEqual(recreated["id"], previous_id)
        self.wire("update_category", {"category_id": recreated["id"], "name": "Mechatronics"})
        self.load_source(pack=str(self.path), stdout=StringIO())
        self.assertEqual(list(SkillCategory.objects.values_list("pk", "name")), [(recreated["id"], "Mechatronics")])
        self.assertEqual(Skill.objects.get(name="Gears").category_id, recreated["id"])
        stale.refresh_from_db()
        self.assertEqual(RPGContentOverride.objects.filter(pk=stale.pk).values().get(), stale_before)
        before = self.snapshot()
        self.startup()
        self.assertEqual(self.snapshot(), before)

    def test_multiple_dangling_exact_sources_cannot_form_a_live_identity_tie(self):
        first_id, first = self.stale()
        deleted = SkillCategory.objects.create(name="Deleted second category")
        second = self.override(deleted)
        deleted.delete()
        source_rows = list(RPGContentOverride.objects.order_by("pk").values())
        self.load_source(pack=str(self.path), stdout=StringIO())
        self.assert_recreated(first_id, first)
        self.assertEqual(list(RPGContentOverride.objects.order_by("pk").values()), source_rows)
        self.assertNotEqual(SkillCategory.objects.get(name="Robotics").pk, second.object_id)

    def test_dangling_and_live_exact_sources_preserve_only_the_actual_live_target(self):
        _previous_id, stale = self.stale()
        retained = SkillCategory.objects.create(name="Mechatronics")
        live = self.override(retained)
        before_sources = list(RPGContentOverride.objects.order_by("pk").values())
        self.load_source(pack=str(self.path), stdout=StringIO())
        self.assertEqual(list(SkillCategory.objects.values_list("pk", "name")), [(retained.pk, "Mechatronics")])
        self.assertEqual(Skill.objects.get(name="Gears").category_id, retained.pk)
        self.assertEqual(list(RPGContentOverride.objects.order_by("pk").values()), before_sources)
        self.assertNotEqual(stale.object_id, live.object_id)

    def test_two_actual_live_exact_sources_remain_ambiguous_even_with_dangling_history(self):
        self.stale()
        for name in ("Engineering", "Mechatronics"):
            self.override(SkillCategory.objects.create(name=name))
        before = self.snapshot()
        with self.assertRaisesRegex(CommandError, "More than one authored entry"):
            call_command("loadrpgcontent", pack=str(self.path), stdout=StringIO())
        self.assertEqual(self.snapshot(), before)

    def test_actual_retained_case_variant_still_rejects_manual_load_and_defers_startup(self):
        category = SkillCategory.objects.get(pk=self.wire("create_category", {"name": "robotics"})["id"])
        self.wire("update_category", {"category_id": category.pk, "name": "Mechatronics"})
        before = self.snapshot()
        with self.assertRaises(CommandError):
            call_command("loadrpgcontent", pack=str(self.path), stdout=StringIO())
        self.assertEqual(self.snapshot(), before)
        self.assertIn("category_source_conflict", self.startup())
        self.assertEqual(self.snapshot(), before)

    def test_deleted_keyed_target_still_requires_explicit_claim_reconciliation(self):
        previous_id, _source = self.stale()
        ContentPackEntry.objects.create(pack="owned", family=self.actor.family, kind="skillcategory",
            key=json.dumps({"name": "Robotics"}, sort_keys=True, separators=(",", ":")),
            model_label="achievements.skillcategory", object_id=previous_id)
        before = self.snapshot()
        with self.assertRaisesRegex(ContentPackError, "Owned skillcategory .* is missing"):
            ContentPack(self.path, pack_key="owned", family=self.actor.family).load()
        self.assertEqual(self.snapshot(), before)

    def test_nonmatching_source_shape_and_untrusted_provenance_do_not_reserve_a_category(self):
        for lookup, marker in (({"name": "Robotics", "extra": 1}, {"version": 1, "source": "mcp"}),
                ({"name": "Robotics"}, {"version": 2, "source": "mcp"}),
                ({"name": "Robotics"}, {"version": 1, "source": "other"})):
            with self.subTest(lookup=lookup, marker=marker):
                category = SkillCategory.objects.create(name=f"Other {SkillCategory.objects.count()}")
                self.override(category, lookup, marker)
                validate_source_identity(SkillCategory(name="Robotics"))

    def test_recording_a_new_override_still_rejects_an_actual_live_retainer(self):
        retained = SkillCategory.objects.create(name="Mechatronics")
        self.override(retained)
        candidate = SkillCategory.objects.create(name="Robotics")
        before = self.snapshot()
        with self.assertRaisesRegex(ContentPackError, "earlier authored entry"):
            record_direct_override(self.actor, candidate, {"name": "Robotics"})
        self.assertEqual(self.snapshot(), before)

    def test_other_model_source_identity_fences_are_unchanged(self):
        category = SkillCategory.objects.create(name="Live parent")
        skill = Skill.objects.create(category=category, name="Deleted skill")
        RPGContentOverride.objects.create(model_label="achievements.skill", object_id=skill.pk,
            family=self.actor.family, source_lookup={"name": skill.name, "category_id": category.pk},
            values={"_authoring": {"version": 1, "source": "mcp"}})
        skill.delete()
        with self.assertRaises(ContentPackError):
            validate_source_identity(Skill(category=category, name="Deleted skill"))
