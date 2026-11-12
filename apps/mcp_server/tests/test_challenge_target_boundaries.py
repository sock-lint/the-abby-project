"""Challenge tools supervise children while keeping another parent's goals private."""
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import challenges
from apps.quests.models import ChallengeOccurrence, ChallengePin
from apps.rewards.models import CoinLedger
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class ChallengeTargetBoundaryTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "boundary-parent", "is_staff": True},
                      {"username": "boundary-coparent", "is_staff": True}]
    family_children = [{"username": "boundary-child"}]

    def setUp(self):
        self.parent, self.coparent = self.parents
        self.child = self.children[0]
        self.foreign = make_family("Foreign challenge target", parents=[{"username": "foreign-boundary-parent"}]).parents[0]
        self.own_id = self.create_goal(self.parent, personal=True)
        self.coparent_id = self.create_goal(self.coparent, personal=True)
        self.other_coparent_id = self.create_goal(self.coparent, personal=True)
        self.child_id = self.create_goal(self.child)
        self.client.force_authenticate(self.parent)

    def create_goal(self, target, *, personal=False):
        self.client.force_authenticate(target if personal else self.parent)
        response = self.client.post("/api/challenges/goals/", {
            "user_id": target.pk, "name": f"Own goal for {target.username}",
            "description": f"Personal note for {target.username}",
            "trigger_type": "habit_log", "metric": "count", "target": 3,
            "unit": "actions", "period": "this_week",
        }, format="json", **({"HTTP_X_ABBY_SPACE": "personal"} if personal else {}))
        self.assertEqual(response.status_code, 201, response.content)
        return response.data["id"]

    def wire(self, actor, name, **params):
        with override_user(actor, scopes=frozenset({"mcp:read", "mcp:write"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def test_coparent_list_refuses_the_same_target_as_rest_and_mcp_detail(self):
        for headers in ({}, {"HTTP_X_ABBY_SPACE": "personal"}):
            response = self.client.get(f"/api/challenges/?user_id={self.coparent.pk}", **headers)
            self.assertEqual(response.status_code, 404)
        with CaptureQueriesContext(connection) as captured:
            listed = self.wire(self.parent, "list_challenges", user_id=self.coparent.pk)
        self.assertEqual(listed.get("error", {}).get("code"), "not_found")
        self.assertNotIn("results", listed)
        detail = self.wire(self.parent, "get_challenge", user_id=self.coparent.pk, challenge_id=self.coparent_id)
        self.assertEqual(detail.get("error", {}).get("code"), "not_found")
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                             for query in captured))

    def test_coparent_cannot_replace_or_clear_another_parents_saved_pin(self):
        original = ChallengeOccurrence.objects.get(pk=int(self.other_coparent_id.split(":")[1]))
        pin = ChallengePin.objects.create(user=self.coparent, occurrence=original)
        for tool_name, challenge_id in (("pin_challenge", self.coparent_id),
                                         ("unpin_challenge", self.other_coparent_id)):
            with self.subTest(tool_name=tool_name):
                response = self.wire(self.parent, tool_name, user_id=self.coparent.pk, challenge_id=challenge_id)
                self.assertEqual(response.get("error", {}).get("code"), "not_found")
                pin.refresh_from_db()
                self.assertEqual(pin.occurrence_id, original.pk)
        self.assertFalse(CoinLedger.objects.exists())

    def test_parent_self_and_same_family_child_keep_list_and_pin_access(self):
        for actor, target, challenge_id in ((self.parent, self.parent, self.own_id),
                                            (self.parent, self.child, self.child_id),
                                            (self.child, self.child, self.child_id)):
            for selector in ({"user_id": target.pk}, *([{}] if actor.pk == target.pk else [])):
                with self.subTest(actor=actor.pk, target=target.pk, selector=selector):
                    listed = self.wire(actor, "list_challenges", **selector)
                    self.assertNotIn("error", listed)
                    self.assertEqual(listed["user_id"], target.pk)
                    self.assertEqual([row["id"] for row in listed["results"]], [challenge_id])
                    if target.role == "parent":
                        self.assertIsNone(listed["daily_bonus"])
                    pinned = self.wire(actor, "pin_challenge", challenge_id=challenge_id, **selector)
                    self.assertEqual(pinned, {"pin": challenge_id})
                    cleared = self.wire(actor, "unpin_challenge", challenge_id=challenge_id, **selector)
                    self.assertEqual(cleared, {"pin": None})
        self.assertFalse(CoinLedger.objects.exists())

    def test_foreign_child_selectors_and_changed_target_role_keep_authority_guards(self):
        for actor, target, code in ((self.parent, self.foreign, "not_found"),
                                    (self.child, self.parent, "permission_denied")):
            for tool_name in ("list_challenges", "pin_challenge", "unpin_challenge"):
                params = {"user_id": target.pk}
                if tool_name != "list_challenges":
                    params["challenge_id"] = self.own_id
                response = self.wire(actor, tool_name, **params)
                self.assertEqual(response.get("error", {}).get("code"), code)
        resolve = challenges.resolve_target_user

        def promote_after_selection(actor, requested_id):
            target = resolve(actor, requested_id)
            get_user_model().objects.filter(pk=target.pk).update(role="parent")
            return target

        with patch.object(challenges, "resolve_target_user", side_effect=promote_after_selection):
            result = self.wire(self.parent, "pin_challenge", user_id=self.child.pk, challenge_id=self.child_id)
        self.assertEqual(result.get("error", {}).get("code"), "not_found")
        self.assertFalse(ChallengePin.objects.filter(user=self.child).exists())
