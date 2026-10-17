"""Security regressions: OAuth grants and global authoring fail closed."""
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.mcp_server.auth import _resolve_user
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import WritePackFileIn, RegisterSpriteAssetsIn
from apps.mcp_server.tools.content_packs import write_pack_file
from apps.mcp_server.tools.sprite_assets import register_sprite_assets
from config.tests.factories import make_oauth_token


@override_settings(MCP_RESOURCE_URL="https://example.test/mcp")
class TokenPermissionRegressionTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="regression-parent", password="pw", role="parent", is_staff=True,
        )

    def test_missing_resource_is_rejected(self):
        token, _ = make_oauth_token(self.parent, resource="")
        self.assertIsNone(_resolve_user(token.token))

    def test_missing_or_legacy_scope_is_rejected(self):
        for scope in ("", "mcp", "unrelated", "mcp:read unrelated"):
            with self.subTest(scope=scope):
                token, _ = make_oauth_token(self.parent, scope=scope)
                self.assertIsNone(_resolve_user(token.token))

    def test_lost_staff_role_is_rejected(self):
        token, _ = make_oauth_token(self.parent)
        self.parent.is_staff = False
        self.parent.save(update_fields=["is_staff"])
        self.assertIsNone(_resolve_user(token.token))

    def test_global_writes_reject_ordinary_parents_before_any_io(self):
        self.parent.is_staff = False
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory), override_user(self.parent):
            with self.assertRaises(MCPPermissionDenied):
                write_pack_file(WritePackFileIn(pack="permission-probe", filename="items.yaml", yaml_content="items: []"))
            with self.assertRaises(MCPPermissionDenied):
                register_sprite_assets(RegisterSpriteAssetsIn(pack="permission-probe"))


class MCPPrivateObjectRegressionTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from apps.homework.models import HomeworkAssignment, HomeworkProof, HomeworkSubmission
        from apps.movement.models import MovementSession, MovementType
        from apps.portfolio.models import ProjectPhoto
        from apps.projects.models import Project
        from config.tests.factories import make_family

        self.a = make_family("A", parents=[{"username": "parent-a"}], children=[{"username": "child-a"}])
        self.b = make_family("B", parents=[{"username": "parent-b"}], children=[{"username": "child-b"}])
        self.project = Project.objects.create(title="Private B project", assigned_to=self.b.children[0], created_by=self.b.parents[0])
        self.photo = ProjectPhoto.objects.create(project=self.project, user=self.b.children[0])
        assignment = HomeworkAssignment.objects.create(
            title="Private B homework", assigned_to=self.b.children[0], created_by=self.b.parents[0],
            subject="math", due_date=timezone.localdate(),
        )
        submission = HomeworkSubmission.objects.create(assignment=assignment, user=self.b.children[0])
        self.proof = HomeworkProof.objects.create(submission=submission, image="")
        movement_type = MovementType.objects.create(name="Walk", slug="walk")
        self.session = MovementSession.objects.create(
            user=self.b.children[0], movement_type=movement_type,
            duration_minutes=5, occurred_on=timezone.localdate(),
        )

    def test_private_objects_cannot_be_read_or_deleted_by_another_family(self):
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import (
            DeleteHomeworkProofIn, DeleteMovementSessionIn, DeleteProjectPhotoIn,
            GetMovementSessionIn, ListProjectPhotosIn,
        )
        from apps.mcp_server.tools import movement, portfolio

        calls = [
            (portfolio.list_project_photos, ListProjectPhotosIn(project_id=self.project.pk)),
            (portfolio.delete_project_photo, DeleteProjectPhotoIn(photo_id=self.photo.pk)),
            (portfolio.delete_homework_proof, DeleteHomeworkProofIn(proof_id=self.proof.pk)),
            (movement.get_movement_session, GetMovementSessionIn(session_id=self.session.pk)),
            (movement.delete_movement_session, DeleteMovementSessionIn(session_id=self.session.pk)),
        ]
        with override_user(self.a.parents[0]):
            for fn, params in calls:
                with self.subTest(tool=fn.__name__), self.assertRaises(MCPNotFoundError):
                    fn(params)
        self.photo.refresh_from_db()
        self.proof.refresh_from_db()
        self.session.refresh_from_db()

    def test_project_photo_access_matches_assigned_and_unassigned_family_rules(self):
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import DeleteProjectPhotoIn, ListProjectPhotosIn
        from apps.mcp_server.tools.portfolio import delete_project_photo, list_project_photos
        from apps.portfolio.models import ProjectPhoto
        from apps.projects.models import Project

        own_draft = Project.objects.create(title="Own unassigned draft", created_by=self.a.parents[0])
        own_photo = ProjectPhoto.objects.create(project=own_draft, user=self.a.parents[0])
        foreign_draft = Project.objects.create(title="Foreign unassigned draft", created_by=self.b.parents[0])
        foreign_photo = ProjectPhoto.objects.create(project=foreign_draft, user=self.b.parents[0])
        reassigned = Project.objects.create(title="Assigned away", created_by=self.a.parents[0], assigned_to=self.b.children[0])
        reassigned_photo = ProjectPhoto.objects.create(project=reassigned, user=self.a.parents[0])
        assigned_here = Project.objects.create(title="Assigned here", created_by=self.b.parents[0], assigned_to=self.a.children[0])
        accessible_photo = ProjectPhoto.objects.create(project=assigned_here, user=self.b.parents[0])
        with override_user(self.a.parents[0]):
            for project, photo in ((own_draft, own_photo), (assigned_here, accessible_photo)):
                self.assertEqual(list_project_photos(ListProjectPhotosIn(project_id=project.pk))["photos"][0]["id"], photo.pk)
                self.assertTrue(delete_project_photo(DeleteProjectPhotoIn(photo_id=photo.pk))["deleted"])
            for project, photo in ((foreign_draft, foreign_photo), (reassigned, reassigned_photo)):
                with self.assertRaises(MCPNotFoundError):
                    list_project_photos(ListProjectPhotosIn(project_id=project.pk))
                with self.assertRaises(MCPNotFoundError):
                    delete_project_photo(DeleteProjectPhotoIn(photo_id=photo.pk))
                photo.refresh_from_db()


class ReadOnlyFilesystemTests(TestCase):
    def test_content_reads_never_create_pack_directories(self):
        from pathlib import Path
        from apps.mcp_server.errors import MCPNotFoundError
        from apps.mcp_server.schemas import GetContentPackIn, ListContentPacksIn, ReadPackFileIn
        from apps.mcp_server.tools.content_packs import get_content_pack, list_content_packs, read_pack_file
        parent = User.objects.create_user(username="reader", role="parent", password="pw", is_staff=True)
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory), override_user(parent):
            self.assertEqual(list_content_packs(ListContentPacksIn()), {"packs": [], "count": 0})
            for function, params in (
                (get_content_pack, GetContentPackIn(pack="missing")),
                (read_pack_file, ReadPackFileIn(pack="missing", filename="items.yaml")),
            ):
                with self.assertRaises(MCPNotFoundError):
                    function(params)
            self.assertEqual(list(Path(directory).iterdir()), [])
