"""Reading goals authored in MCP count the same saved Adventure as the app."""
from uuid import uuid4

from django.test import TestCase

from apps.mcp_server.challenge_schemas import CreateChallengeGoalIn, PreviewChallengeGoalIn
from apps.mcp_server.context import override_user
from apps.mcp_server.reading_schemas import CreateReadingBookIn, LogReadingSessionIn
from apps.mcp_server.tools import challenges, reading
from apps.quests.models import ChallengeOccurrence
from config.tests.factories import make_family


class ReadingGoalParityTests(TestCase):
    def test_preview_create_and_reading_log_advance_a_reading_goal_once(self):
        family = make_family("MCP reading goals", parents=[{"username":"goal-parent", "is_staff":True}],
                             children=[{"username":"goal-reader"}])
        parent, child = family.parents[0], family.children[0]
        fields = {"user_id":child.pk, "name":"One Reading Adventure", "trigger_type":"reading_logged",
                  "metric":"count", "target":"1", "unit":"actions", "period":"this_week"}
        with override_user(parent):
            preview = challenges.preview_challenge_goal(PreviewChallengeGoalIn(**fields))
            self.assertTrue(preview["valid"])
            goal = challenges.create_challenge_goal(CreateChallengeGoalIn(**fields, request_id=uuid4()))
            book = reading.create_reading_book(CreateReadingBookIn(user_id=child.pk, title="Synthetic book", client_request_id=uuid4()))
            params = LogReadingSessionIn(user_id=child.pk, book=book["id"], duration_minutes=10, client_request_id=uuid4())
            first = reading.log_reading_session(params)
            second = reading.log_reading_session(params)
        self.assertEqual(first["id"], second["id"])
        occurrence = ChallengeOccurrence.objects.get(pk=goal["id"].split(":")[-1])
        self.assertEqual(occurrence.progress, 1)
        self.assertEqual(occurrence.status, "completed")
