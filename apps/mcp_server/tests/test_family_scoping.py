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


class MCPTargetUserSweepTests(TestCase):
    """Audit C3 sweep — every MCP tool that resolves an optional ``user_id``
    on the parent path must use the canonical ``resolve_target_user`` helper
    which enforces same-family scoping. Five tool files previously defined
    a local ``_resolve_target`` that skipped the family check; this test
    pins each one against a cross-family probe.
    """

    def setUp(self):
        self.a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.parent_a = self.a.parents[0]
        self.kid_b = self.b.children[0]

    def test_achievements_get_skill_tree_cross_family_404(self):
        from apps.achievements.models import SkillCategory
        from apps.mcp_server.schemas import GetSkillTreeIn
        from apps.mcp_server.tools.achievements import get_skill_tree

        cat = SkillCategory.objects.create(name="Cooking", icon="chef")
        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                get_skill_tree(GetSkillTreeIn(category_id=cat.id, user_id=self.kid_b.id))

    def test_achievements_list_earned_badges_cross_family_404(self):
        from apps.mcp_server.schemas import ListEarnedBadgesIn
        from apps.mcp_server.tools.achievements import list_earned_badges

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                list_earned_badges(ListEarnedBadgesIn(user_id=self.kid_b.id))

    def test_payments_get_payment_balance_cross_family_404(self):
        from apps.mcp_server.schemas import GetPaymentBalanceIn
        from apps.mcp_server.tools.payments import get_payment_balance

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                get_payment_balance(GetPaymentBalanceIn(user_id=self.kid_b.id))

    def test_savings_list_savings_goals_cross_family_404(self):
        from apps.mcp_server.schemas import ListSavingsGoalsIn
        from apps.mcp_server.tools.savings import list_savings_goals

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                list_savings_goals(ListSavingsGoalsIn(user_id=self.kid_b.id))

    def test_timecards_list_time_entries_cross_family_404(self):
        from apps.mcp_server.schemas import ListTimeEntriesIn
        from apps.mcp_server.tools.timecards import list_time_entries

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                list_time_entries(ListTimeEntriesIn(user_id=self.kid_b.id))

    def test_timecards_get_active_entry_cross_family_404(self):
        from apps.mcp_server.schemas import GetActiveEntryIn
        from apps.mcp_server.tools.timecards import get_active_entry

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                get_active_entry(GetActiveEntryIn(user_id=self.kid_b.id))

    def test_portfolio_list_project_photos_cross_family_404(self):
        # ``list_project_photos`` doesn't take user_id — the cross-family
        # probe goes through ``get_portfolio_summary`` which does.
        from apps.mcp_server.schemas import GetPortfolioSummaryIn
        from apps.mcp_server.tools.portfolio import get_portfolio_summary

        with override_user(self.parent_a):
            with self.assertRaises(MCPNotFoundError):
                get_portfolio_summary(GetPortfolioSummaryIn(user_id=self.kid_b.id))


class MCPParentDefaultListFamilyScopingTests(TestCase):
    """Audit C3 sweep — when a parent calls list_chore_completions /
    list_homework_submissions WITHOUT a user_id, the result must be scoped
    to their own family rather than aggregating every household.
    """

    def setUp(self):
        from apps.chores.models import Chore, ChoreCompletion
        from apps.homework.models import HomeworkAssignment, HomeworkSubmission
        import datetime
        from decimal import Decimal

        self.a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        # Seed one chore completion per family.
        chore_a = Chore.objects.create(
            title="Trash A", recurrence="daily",
            assigned_to=self.a.children[0], created_by=self.a.parents[0],
        )
        chore_b = Chore.objects.create(
            title="Trash B", recurrence="daily",
            assigned_to=self.b.children[0], created_by=self.b.parents[0],
        )
        self.completion_a = ChoreCompletion.objects.create(
            chore=chore_a, user=self.a.children[0],
            status=ChoreCompletion.Status.PENDING,
            completed_date=datetime.date.today(),
            reward_amount_snapshot=Decimal("0.00"),
            coin_reward_snapshot=0,
        )
        ChoreCompletion.objects.create(
            chore=chore_b, user=self.b.children[0],
            status=ChoreCompletion.Status.PENDING,
            completed_date=datetime.date.today(),
            reward_amount_snapshot=Decimal("0.00"),
            coin_reward_snapshot=0,
        )
        # Seed one homework submission per family.
        hw_a = HomeworkAssignment.objects.create(
            title="Math A", subject="math", effort_level=3,
            due_date=datetime.date.today() + datetime.timedelta(days=1),
            assigned_to=self.a.children[0], created_by=self.a.parents[0],
        )
        hw_b = HomeworkAssignment.objects.create(
            title="Math B", subject="math", effort_level=3,
            due_date=datetime.date.today() + datetime.timedelta(days=1),
            assigned_to=self.b.children[0], created_by=self.b.parents[0],
        )
        self.submission_a = HomeworkSubmission.objects.create(
            assignment=hw_a, user=self.a.children[0],
        )
        HomeworkSubmission.objects.create(
            assignment=hw_b, user=self.b.children[0],
        )

    def test_list_chore_completions_parent_default_excludes_other_families(self):
        from apps.mcp_server.schemas import ListChoreCompletionsIn
        from apps.mcp_server.tools.chores import list_chore_completions

        with override_user(self.a.parents[0]):
            result = list_chore_completions(ListChoreCompletionsIn())
        ids = [row["id"] for row in result["completions"]]
        self.assertEqual(ids, [self.completion_a.id])

    def test_list_homework_submissions_parent_default_excludes_other_families(self):
        from apps.mcp_server.schemas import ListHomeworkSubmissionsIn
        from apps.mcp_server.tools.homework import list_homework_submissions

        with override_user(self.a.parents[0]):
            result = list_homework_submissions(ListHomeworkSubmissionsIn())
        ids = [row["id"] for row in result["submissions"]]
        self.assertEqual(ids, [self.submission_a.id])
