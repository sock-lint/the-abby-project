"""MCP family-scoping: list_children, get_user, update_child, dashboard."""
from django.test import TestCase

from apps.mcp_server.context import override_user, resolve_target_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import GetUserIn, ListChildrenIn, UpdateChildIn
from apps.mcp_server.tools.users import get_user, list_children, update_child
from config.tests.factories import make_family


class MCPResolveTargetUserTests(TestCase):
    def setUp(self):
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )

    def test_parent_can_resolve_own_child(self):
        target = resolve_target_user(self.a.parents[0], self.a.children[0].id)
        self.assertEqual(target, self.a.children[0])

    def test_parent_cannot_resolve_cross_family_child(self):
        with self.assertRaises(MCPNotFoundError):
            resolve_target_user(self.a.parents[0], self.b.children[0].id)

    def test_parent_cannot_resolve_cross_family_parent(self):
        with self.assertRaises(MCPNotFoundError):
            resolve_target_user(self.a.parents[0], self.b.parents[0].id)


class MCPListChildrenTests(TestCase):
    def setUp(self):
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac1"}, {"username": "ac2"}],
        )
        self.b = make_family(
            "B",
            children=[{"username": "bc"}],
        )

    def test_scoped_to_caller_family(self):
        with override_user(self.a.parents[0]):
            result = list_children(ListChildrenIn())
        usernames = {c["username"] for c in result["children"]}
        self.assertEqual(usernames, {"ac1", "ac2"})


class MCPGetUserCrossFamilyTests(TestCase):
    def setUp(self):
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "B",
            children=[{"username": "bc"}],
        )

    def test_parent_cannot_read_cross_family_user(self):
        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                get_user(GetUserIn(user_id=self.b.children[0].id))


class MCPUpdateChildCrossFamilyTests(TestCase):
    def setUp(self):
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
        )
        self.b = make_family(
            "B",
            children=[{"username": "bc"}],
        )

    def test_parent_cannot_update_cross_family_child(self):
        with override_user(self.a.parents[0]):
            with self.assertRaises(MCPNotFoundError):
                update_child(
                    UpdateChildIn(
                        user_id=self.b.children[0].id,
                        display_name="hax",
                    ),
                )


class MCPListPendingCreationsFamilyScopingTests(TestCase):
    """Audit C3: list_pending_creations is the MCP twin of
    ``CreationViewSet.pending`` and must be scoped to the parent's family.
    """

    def setUp(self):
        from apps.achievements.models import Skill, SkillCategory
        self.a = make_family(
            "A",
            parents=[{"username": "ap"}],
            children=[{"username": "ac"}],
        )
        self.b = make_family(
            "B",
            parents=[{"username": "bp"}],
            children=[{"username": "bc"}],
        )
        self.cat = SkillCategory.objects.create(name="Art & Crafts", icon="🎨")
        self.skill = Skill.objects.create(category=self.cat, name="Drawing")

    def _submit(self, child):
        import io
        from unittest.mock import patch
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.creations.services import CreationService

        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="JPEG")
        img = SimpleUploadedFile("art.jpg", buf.getvalue(), content_type="image/jpeg")
        with patch("apps.rpg.services.GameLoopService.on_task_completed"):
            c = CreationService.log_creation(child, image=img, primary_skill_id=self.skill.id)
        CreationService.submit_for_bonus(c)
        return c

    def test_pending_queue_excludes_other_families(self):
        from apps.mcp_server.schemas import ListPendingCreationsIn
        from apps.mcp_server.tools.creations import list_pending_creations

        own = self._submit(self.a.children[0])
        self._submit(self.b.children[0])

        with override_user(self.a.parents[0]):
            result = list_pending_creations(ListPendingCreationsIn())

        ids = [row["id"] for row in result["creations"]]
        self.assertEqual(ids, [own.id])
