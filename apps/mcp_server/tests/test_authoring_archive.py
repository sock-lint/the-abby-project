"""Authoring capacity can be reclaimed without erasing reviewed evidence."""
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.rpg.content import editorial, workbench
from apps.rpg.models import ProgressionExperiment, RPGContentDraft, RPGEditorialDraft
from apps.rpg.progression import experiments
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringArchiveTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "archive-author", "is_staff": True}]).parents[0]

    def wire(self, name, params, *, actor=None, confirmation=True):
        with override_user(actor or self.actor, scopes=frozenset({"mcp:author"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": confirmation})
        if isinstance(result, tuple):
            return result[1]
        self.assertFalse(result.isError, result.structuredContent)
        return result.structuredContent

    def create(self, kind):
        if kind == "content":
            return workbench.create_draft(self.actor, "Saved content")
        if kind == "editorial":
            return editorial.create_editorial_draft(self.actor, "affirmations", "Saved copy")
        return experiments.create_experiment(self.actor, {
            "name": "Saved hypothesis", "hypothesis": "A bounded synthetic hypothesis.",
            "config": {"horizon_days": 30, "trials": 1}, "candidate_daily_coins": 100,
            "targets": [{"metric": "closing_coins_p50", "min": 0}],
        })

    @staticmethod
    def tool(kind):
        return {"content": "set_content_draft_archived", "editorial": "set_editorial_draft_archived",
                "experiment": "set_progression_experiment_archived"}[kind]

    def params(self, kind, row, archived, **changes):
        return {"experiment_id" if kind == "experiment" else "draft_id": row["id"],
                "revision": row["revision"], "is_archived": archived, "request_id": str(uuid4()), **changes}

    def test_archive_setters_have_concrete_results_and_confirmed_retry_contract(self):
        entries = {entry.name: entry for entry in mcp._tool_manager.list_tools()}
        for kind in ("content", "editorial", "experiment"):
            with self.subTest(kind=kind):
                self.assertIn(self.tool(kind), entries.keys())
                entry = entries[self.tool(kind)]
                self.assertIn("is_archived", entry.output_schema["properties"])
                self.assertTrue(entry.annotations.destructiveHint)
                self.assertTrue(entry.annotations.idempotentHint)
                self.assertFalse(entry.annotations.readOnlyHint)

    def test_archive_frees_active_capacity_and_restore_checks_capacity(self):
        for kind, model, cap in (("content", RPGContentDraft, 30), ("editorial", RPGEditorialDraft, 30),
                                 ("experiment", ProgressionExperiment, 20)):
            with self.subTest(kind=kind):
                rows = [self.create(kind) for _ in range(cap)]
                with self.assertRaises(ValueError):
                    self.create(kind)
                archived = self.wire(self.tool(kind), self.params(kind, rows[0], True))
                self.assertTrue(archived["is_archived"])
                self.assertEqual(archived["revision"], 2)
                self.create(kind)
                self.assertEqual(model.objects.filter(actor=self.actor).count(), cap + 1)
                with override_user(self.actor, scopes=frozenset({"mcp:author"})):
                    result = async_to_sync(mcp.call_tool)(self.tool(kind), {
                        "params": self.params(kind, archived, False), "confirmation": True,
                    })
                self.assertTrue(result.isError)
                self.assertIn("capacity", result.structuredContent["error"]["message"].lower())

    def error(self, kind, params, *, actor=None, confirmation=True):
        with override_user(actor or self.actor, scopes=frozenset({"mcp:author"})):
            result = async_to_sync(mcp.call_tool)(self.tool(kind), {"params": params, "confirmation": confirmation})
        self.assertTrue(result.isError)
        return result.structuredContent["error"]

    def test_replay_after_restore_reports_current_and_original_state_without_reapplying(self):
        from apps.rpg.models import AuthoringArchiveReceipt
        for kind in ("content", "editorial", "experiment"):
            with self.subTest(kind=kind):
                row = self.create(kind)
                original = self.params(kind, row, True)
                archived = self.wire(self.tool(kind), original)
                restored = self.wire(self.tool(kind), self.params(kind, archived, False))
                replay = self.wire(self.tool(kind), original)
                self.assertEqual(replay["revision"], restored["revision"])
                self.assertFalse(replay["is_archived"])
                self.assertTrue(replay["replayed"])
                self.assertEqual(replay["operation"], {"is_archived": True, "revision": 2})
                self.assertEqual(AuthoringArchiveReceipt.objects.filter(actor=self.actor, kind=kind).count(), 2)
                changed = self.error(kind, {**original, "is_archived": False})
                self.assertEqual(changed["code"], "idempotency_conflict")
                self.assertEqual(self.error(kind, self.params(kind, row, True))["code"], "authoring_archive_conflict")

    def test_owner_confirmation_and_fresh_authority_are_required_even_for_replay(self):
        from apps.accounts.models import User
        other = make_family(parents=[{"username": "archive-other", "is_staff": True}]).parents[0]
        coparent = User.objects.create_user(username="archive-coparent", family=self.actor.family, role="parent", is_staff=True)
        for kind in ("content", "editorial", "experiment"):
            with self.subTest(kind=kind):
                row = self.create(kind)
                request = self.params(kind, row, True)
                self.assertEqual(self.error(kind, request, confirmation=False)["code"], "confirmation_required")
                for outsider in (other, coparent):
                    self.assertEqual(self.error(kind, request, actor=outsider)["code"], "not_found")
                self.wire(self.tool(kind), request)
                User.objects.filter(pk=self.actor.pk).update(is_staff=False)
                self.assertEqual(self.error(kind, request)["code"], "permission_denied")
                User.objects.filter(pk=self.actor.pk).update(is_staff=True)
                User.objects.filter(pk=self.actor.pk).update(family=other.family)
                self.assertEqual(self.error(kind, request)["code"], "permission_denied")
                User.objects.filter(pk=self.actor.pk).update(family=self.actor.family)

    def test_replay_after_source_deletion_never_recreates_record(self):
        for kind, model in (("content", RPGContentDraft), ("editorial", RPGEditorialDraft), ("experiment", ProgressionExperiment)):
            with self.subTest(kind=kind):
                row = self.create(kind)
                request = self.params(kind, row, True)
                self.wire(self.tool(kind), request)
                model.objects.filter(pk=row["id"]).delete()
                self.assertEqual(self.error(kind, request)["code"], "not_found")
                self.assertFalse(model.objects.filter(pk=row["id"]).exists())

    def test_archived_history_pages_beyond_active_capacity_and_exact_reads_retain_details(self):
        from apps.mcp_server.editorial_schemas import EditorialDraftPage
        for kind, model, list_tool, get_tool in (
            ("content", RPGContentDraft, "list_content_drafts", "get_content_draft"),
            ("editorial", RPGEditorialDraft, "list_editorial_drafts", "get_editorial_draft"),
            ("experiment", ProgressionExperiment, "list_progression_experiments", "get_progression_experiment"),
        ):
            with self.subTest(kind=kind):
                first = self.create(kind)
                self.wire(self.tool(kind), self.params(kind, first, True))
                # Historical notebooks exceed the old twenty-row native slice.
                source = model.objects.get(pk=first["id"])
                rows = []
                for index in range(24):
                    source.pk = uuid4()
                    source._state.adding = True
                    source.name = f"Archived {index}"
                    source.save(force_insert=True)
                    rows.append(source.pk)
                self.assertEqual(self.wire(list_tool, {})["total"], 0)
                seen, after = [], None
                while True:
                    page = self.wire(list_tool, {"include_archived": True, "limit": 7, **({"after": after} if after else {})})
                    if kind == "editorial":
                        EditorialDraftPage.model_validate(page)
                    values = page["experiments" if kind == "experiment" else "drafts"]
                    self.assertTrue(all(value["is_archived"] for value in values))
                    self.assertTrue(all("changes" not in value and "preview" not in value and "observations" not in value for value in values))
                    seen.extend(value["id"] for value in values)
                    after = page["next_after"]
                    if not after:
                        break
                self.assertEqual(len(seen), 25)
                self.assertEqual(len(set(seen)), 25)
                detail = self.wire(get_tool, {"experiment_id" if kind == "experiment" else "draft_id": first["id"]})
                self.assertTrue(detail["is_archived"])
                if kind == "experiment":
                    self.assertTrue(detail["observations_redacted"])
                else:
                    self.assertIn("changes", detail)

    def test_archived_retention_cap_does_not_delete_or_modify_retained_work(self):
        for kind, model in (("content", RPGContentDraft), ("editorial", RPGEditorialDraft), ("experiment", ProgressionExperiment)):
            with self.subTest(kind=kind):
                row = self.create(kind)
                source = model.objects.get(pk=row["id"])
                for _ in range(100):
                    source.pk, source.is_archived = uuid4(), True
                    source._state.adding = True
                    source.save(force_insert=True)
                error = self.error(kind, self.params(kind, row, True))
                self.assertIn("100", error["message"])
                self.assertEqual(model.objects.filter(actor=self.actor, is_archived=True).count(), 100)
                self.assertFalse(model.objects.get(pk=row["id"]).is_archived)

    def test_archived_native_writes_reject_and_published_history_remains_unchanged(self):
        from django.utils import timezone
        from apps.rpg.authoring_archive import AuthoringArchiveConflict
        for kind, model in (("content", RPGContentDraft), ("editorial", RPGEditorialDraft)):
            with self.subTest(kind=kind):
                row = self.create(kind)
                # Publication is a separate existing flow. Organization must leave
                # the saved publication time, review evidence and content intact.
                model.objects.filter(pk=row["id"]).update(published_at=timezone.now())
                before = model.objects.get(pk=row["id"])
                archived = self.wire(self.tool(kind), self.params(kind, row, True))
                after = model.objects.get(pk=row["id"])
                self.assertEqual(after.published_at, before.published_at)
                self.assertEqual(after.changes, before.changes)
                for write in ((lambda: workbench.save_draft(self.actor, row["id"], archived["revision"], [])),
                              (lambda: workbench.preview_draft(self.actor, row["id"], archived["revision"]))):
                    if kind == "content":
                        with self.assertRaises(AuthoringArchiveConflict):
                            write()
                if kind == "editorial":
                    with self.assertRaises(AuthoringArchiveConflict):
                        editorial.save_editorial_draft(self.actor, row["id"], archived["revision"], [])
                    with self.assertRaises(AuthoringArchiveConflict):
                        editorial.preview_editorial_draft(self.actor, row["id"], archived["revision"])
        row = self.create("experiment")
        archived = self.wire(self.tool("experiment"), self.params("experiment", row, True))
        for function, args in ((experiments.save_experiment, ({},)), (experiments.prepare_comparison, ()),
                               (experiments.prepare_observation, ())):
            with self.assertRaises(experiments.ExperimentConflict):
                function(self.actor, row["id"], archived["revision"], *args)

    def test_preupgrade_publication_digest_replays_and_archival_retains_receipt(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.rpg.content.publication import _digest
        from apps.rpg.models import ContentPackPublication
        row = self.create("content")
        draft = RPGContentDraft.objects.get(pk=row["id"])
        old_digest = _digest({"draft": str(draft.pk), "revision": draft.revision, "changes": draft.changes})
        plan = ContentPackPublication.objects.create(pack=f"wb-{draft.pk.hex}", actor=self.actor,
            family=self.actor.family, content_digest=old_digest, state_digest="a" * 64,
            changes=[], stats={}, expires_at=timezone.now() + timedelta(minutes=30), published_at=timezone.now())
        draft.preview, draft.published_at = plan, plan.published_at
        draft.save(update_fields=["preview", "published_at"])
        replay = workbench.publish_draft(self.actor, draft.pk, draft.revision, plan.pk, old_digest)
        self.assertEqual(replay["preview"]["content_digest"], old_digest)
        archived = self.wire(self.tool("content"), self.params("content", row, True))
        historical = workbench.get_draft(self.actor, draft.pk)
        self.assertEqual(historical["revision"], archived["revision"])
        self.assertEqual(historical["preview"]["content_digest"], old_digest)
        self.assertEqual(historical["preview"]["published_at"], plan.published_at.isoformat())

    def test_archive_between_detached_comparison_and_save_rejects_new_evidence(self):
        from unittest.mock import patch
        from apps.rpg.authoring_archive import set_archived
        from apps.rpg.models import ProgressionComparison
        row = self.create("experiment")
        prepare = experiments.prepare_comparison

        def archive_after_prepare(*args, **kwargs):
            result = prepare(*args, **kwargs)
            set_archived(self.actor, "experiment", row["id"], row["revision"], True, uuid4(), confirmation=True)
            return result

        with patch.object(experiments, "prepare_comparison", side_effect=archive_after_prepare):
            with self.assertRaises(experiments.ExperimentConflict):
                experiments.compare_experiment(self.actor, row["id"], row["revision"])
        self.assertTrue(ProgressionExperiment.objects.get(pk=row["id"]).is_archived)
        self.assertFalse(ProgressionComparison.objects.filter(experiment_id=row["id"]).exists())

    def test_archived_checkpoints_remain_redacted_without_read_grant(self):
        from apps.rpg.models import ProgressionObservation
        from apps.rpg.progression.observations import economy_observations
        row = self.create("experiment")
        ProgressionObservation.objects.create(experiment_id=row["id"], experiment_revision=1,
            payload=economy_observations(self.actor), binding={"source_commit": "synthetic"})
        self.wire(self.tool("experiment"), self.params("experiment", row, True))
        private = self.wire("get_progression_experiment", {"experiment_id": row["id"]})
        self.assertEqual(private["observations"], [])
        self.assertTrue(private["observations_redacted"])
        with override_user(self.actor, scopes=frozenset({"mcp:author", "mcp:read"})):
            response = async_to_sync(mcp.call_tool)("get_progression_experiment", {"params": {"experiment_id": row["id"]}})
        full = response[1] if isinstance(response, tuple) else response.structuredContent
        self.assertFalse(full["observations_redacted"])
        self.assertEqual(len(full["observations"]), 1)
        self.assertTrue(full["is_archived"])
