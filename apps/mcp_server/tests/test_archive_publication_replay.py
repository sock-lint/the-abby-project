"""Organization changes cannot invalidate an exact completed publication retry."""
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.accounts.models import User
from apps.rpg.content import editorial, workbench
from apps.rpg.models import ItemDefinition, RPGContentDraft, RPGEditorialDraft
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ArchivePublicationReplayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = make_family("Publication archive replay", parents=[
            {"username": "publication-archive-author", "is_staff": True},
        ]).parents[0]
        self.item = ItemDefinition.objects.create(slug="archive-replay-food", name="Original food",
            item_type="food", metadata={"growth": 1})

    def response(self, name, params):
        with override_user(self.actor, scopes=frozenset({"mcp:author", "mcp:publish", "mcp:catalog"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        if isinstance(result, tuple):
            return True, result[1]
        return not result.isError, result.structuredContent

    def wire(self, name, params):
        success, result = self.response(name, params)
        self.assertTrue(success, result)
        return result

    def published(self, kind, *, complete=True):
        create = {"name": "Completed private publication"}
        if kind == "editorial":
            create["section"] = "lorebook"
        draft = self.wire(f"create_{kind}_draft", create)
        changes = ([{"section": "items", "object_id": self.item.pk, "key": "food",
            "values": {"name": "Published food"}}] if kind == "content" else
            [{"slug": "duties", "values": {"title": "Published shared duties"}}])
        draft = self.wire(f"save_{kind}_draft", {"draft_id": draft["id"],
            "revision": draft["revision"], "changes": changes})
        draft = self.wire(f"preview_{kind}_draft", {"draft_id": draft["id"], "revision": draft["revision"]})
        plan = draft["preview"]
        params = {"draft_id": draft["id"], "revision": draft["revision"],
            "preview_id": plan["preview_id" if kind == "content" else "id"],
            "content_digest": plan["content_digest"]}
        if kind == "content":
            self.wire("simulate_content_draft", {key: value for key, value in {
                **params, "config": {"horizon_days": 30, "trials": 1},
            }.items() if key != "content_digest"})
        if not complete:
            return draft, params
        saved = self.wire(f"publish_{kind}_draft", params)
        self.assertEqual(self.wire(f"publish_{kind}_draft", params), saved)
        return saved, params

    def transition(self, kind, row, archived):
        return self.wire(f"set_{kind}_draft_archived", {"draft_id": row["id"],
            "revision": row["revision"], "is_archived": archived, "request_id": str(uuid4())})

    def assert_same_publication(self, result, published):
        self.assertEqual(result["published_at"], published["published_at"])
        self.assertEqual(result["preview"], published["preview"])
        self.assertEqual(result["changes"], published["changes"])

    def test_mcp_completed_content_replay_survives_archive_and_restore(self):
        self.check_mcp_replay("content")

    def test_mcp_completed_editorial_replay_survives_archive_and_restore(self):
        self.check_mcp_replay("editorial")

    def check_mcp_replay(self, kind):
        published, params = self.published(kind)
        archived = self.transition(kind, published, True)
        self.assert_same_publication(self.wire(f"publish_{kind}_draft", params), published)
        restored = self.transition(kind, archived, False)
        replay = self.wire(f"publish_{kind}_draft", params)
        self.assert_same_publication(replay, published)
        self.assertFalse(replay["is_archived"])
        self.assertEqual(replay["revision"], restored["revision"])

    def test_native_content_publication_replay_uses_original_preview_revision(self):
        self.check_native_replay("content")

    def test_native_editorial_publication_replay_uses_original_preview_revision(self):
        self.check_native_replay("editorial")

    def check_native_replay(self, kind):
        published, params = self.published(kind)
        archived = self.transition(kind, published, True)
        self.transition(kind, archived, False)
        publish = workbench.publish_draft if kind == "content" else editorial.publish_editorial_draft
        self.assert_same_publication(publish(self.actor, **params), published)

    def test_wrong_plan_digest_or_organizational_revision_cannot_replay_completed_publication(self):
        for kind in ("content", "editorial"):
            with self.subTest(kind=kind):
                published, params = self.published(kind)
                archived = self.transition(kind, published, True)
                restored = self.transition(kind, archived, False)
                for wrong in ({"preview_id": str(uuid4())}, {"content_digest": "f" * 64},
                              {"revision": restored["revision"]}, {"revision": params["revision"] + 1}):
                    success, _ = self.response(f"publish_{kind}_draft", {**params, **wrong})
                    self.assertFalse(success, (kind, wrong))
                model = RPGContentDraft if kind == "content" else RPGEditorialDraft
                row = model.objects.get(pk=published["id"])
                self.assertEqual(row.revision, restored["revision"])
                self.assertFalse(row.is_archived)

    def test_unpublished_draft_cannot_publish_through_historical_revision_path(self):
        for kind in ("content", "editorial"):
            with self.subTest(kind=kind):
                reviewed, params = self.published(kind, complete=False)
                archived = self.transition(kind, reviewed, True)
                self.assertFalse(self.response(f"publish_{kind}_draft", params)[0])
                restored = self.transition(kind, archived, False)
                self.assertFalse(self.response(f"publish_{kind}_draft", params)[0])
                self.assertFalse(self.response(f"publish_{kind}_draft",
                    {**params, "revision": restored["revision"]})[0])
                model = RPGContentDraft if kind == "content" else RPGEditorialDraft
                self.assertIsNone(model.objects.get(pk=reviewed["id"]).published_at)

    def test_completed_replay_still_requires_current_staff_family_and_exact_author(self):
        other = make_family("Other publication archive family", parents=[
            {"username": "publication-archive-other", "is_staff": True},
        ]).parents[0]
        coparent = User.objects.create_user(username="publication-archive-coparent", password="pw",
            family=self.actor.family, role="parent", is_staff=True)
        original_family_id = self.actor.family_id
        for kind in ("content", "editorial"):
            with self.subTest(kind=kind):
                published, params = self.published(kind)
                self.transition(kind, published, True)
                User.objects.filter(pk=self.actor.pk).update(is_staff=False)
                self.assertFalse(self.response(f"publish_{kind}_draft", params)[0])
                User.objects.filter(pk=self.actor.pk).update(is_staff=True, family=other.family)
                self.assertFalse(self.response(f"publish_{kind}_draft", params)[0])
                User.objects.filter(pk=self.actor.pk).update(family_id=original_family_id)
                original_actor = self.actor
                try:
                    self.actor = coparent
                    self.assertFalse(self.response(f"publish_{kind}_draft", params)[0])
                finally:
                    self.actor = original_actor
                self.assert_same_publication(self.wire(f"publish_{kind}_draft", params), published)
