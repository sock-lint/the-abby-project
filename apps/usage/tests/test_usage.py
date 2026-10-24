import json
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chores.models import Chore, ChoreCompletion
from apps.families.models import Family, LiveTestFamily
from apps.projects.models import Project
from apps.reading.models import ReadingBook, ReadingSession
from apps.usage.models import UsageCollectionState, UsageEvent, UsageVisit
from apps.usage.reporting import build_usage_report
from apps.usage.services import prune_usage_data, record_action, record_visit
from config.tests.factories import make_family

UTC = datetime_timezone.utc
NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UsageTests(TestCase):
    def setUp(self):
        first = make_family("Synthetic household one", parents=[{"username": "staff-reader", "is_staff": True}], children=[{"username": "reader-one"}])
        second = make_family("Synthetic household two", parents=[{"username": "ordinary-parent"}], children=[{"username": "reader-two"}])
        self.family, self.staff, self.child = first.family, first.parents[0], first.children[0]
        self.other_family, self.parent, self.other_child = second.family, second.parents[0], second.children[0]
        UsageCollectionState.objects.update_or_create(pk=1, defaults={"started_at": NOW - timedelta(days=120)})
        self.client = APIClient()
        self.source_count = 0

    def event(self, actor=None, *, day=NOW, feature="reading", action="completed"):
        actor = actor or self.child
        self.source_count += 1
        return UsageEvent.objects.create(actor=actor, family_id=actor.family_id, role=actor.role, feature=feature, action=action, source="reading.readingsession", source_id=self.source_count, occurred_at=day)

    def reading(self, actor=None):
        actor = actor or self.child
        book = ReadingBook.objects.create(user=actor, title="Private title must never appear", client_request_id=uuid4(), create_payload={})
        return ReadingSession.objects.create(user=actor, book=book, occurred_on=NOW.date(), client_request_id=uuid4(), create_payload={}, reflection="Private reflection must never appear")

    def report(self, **kwargs):
        return build_usage_report(self.staff, now=NOW, **kwargs)

    def live_family(self):
        live = make_family("Synthetic live fixture", parents=[{"username": "observer-parent"}], children=[{"username": "observer-child"}])
        LiveTestFamily.objects.create(namespace="synthetic-observer", family=live.family, parent=live.parents[0], child=live.children[0])
        return live

    def test_dashboard_requires_staff_parent_and_superuser_for_deployment(self):
        self.assertEqual(self.client.get("/api/admin/usage/").status_code, 401)
        for actor in (self.child, self.parent):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get("/api/admin/usage/").status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/admin/usage/").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/usage/?scope=deployment").status_code, 403)
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get("/api/admin/usage/?scope=deployment").status_code, 200)

    def test_unknown_or_unbounded_filters_are_rejected(self):
        self.client.force_authenticate(self.staff)
        for query in ("days=1000", "days=foo", "days=-7", "role=staff", "feature=journal", "scope=other", "family_id=2", "user_id=3", "token=secret"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/api/admin/usage/?{query}").status_code, 400)
        self.assertEqual(self.client.get("/api/admin/usage/?days=7&_abby_session=synthetic&_abby_retry=1").status_code, 200)

    def test_family_scope_does_not_include_other_households_or_live_fixtures(self):
        self.event()
        self.event(self.other_child)
        live = self.live_family()
        self.event(live.children[0])
        self.assertEqual(self.report()["summary"]["current"]["actions"], 1)
        self.staff.is_superuser = True
        self.assertEqual(self.report(scope="deployment")["summary"]["current"]["active_families"], 2)

    def test_semantic_actions_are_counted_once_and_visits_are_separate(self):
        self.event(feature="homework", action="submitted")
        self.event(self.staff, feature="homework", action="approved")
        self.event(feature="rewards", action="requested")
        self.event(feature="habits", action="checked_in")
        self.event(feature="habits", action="completed")
        UsageVisit.objects.create(actor=self.parent, family=self.other_family, role="parent", occurred_on=NOW.date())
        UsageVisit.objects.create(actor=self.staff, family=self.family, role="parent", occurred_on=NOW.date())
        summary = self.report()["summary"]["current"]
        self.assertEqual(summary, {"active_families": 1, "active_children": 1, "active_parents": 1, "completed_activities": 2, "actions": 5, "visitors": 1})

    def test_role_feature_filters_and_zero_filled_daily_trend(self):
        self.event(day=NOW - timedelta(days=1))
        self.event(feature="movement")
        self.event(self.staff, feature="homework", action="approved")
        report = self.report(days=7, role="child", feature="reading")
        self.assertEqual(report["summary"]["current"]["actions"], 1)
        self.assertEqual(report["summary"]["current"]["active_parents"], 0)
        self.assertEqual(len(report["trend"]), 7)
        self.assertEqual(report["trend"][-2]["completed_activities"], 1)
        self.assertEqual(report["trend"][-1]["completed_activities"], 0)
        self.assertEqual(report["features"], [{"feature": "reading", "actors": 1, "actions": 1, "completed_activities": 1}])

    def test_partial_history_is_explicit_and_previous_counts_not_claimed_complete(self):
        UsageCollectionState.objects.filter(pk=1).update(started_at=NOW - timedelta(days=10))
        report = self.report(days=7)
        self.assertTrue(report["collection"]["history_complete"])
        self.assertFalse(report["collection"]["previous_history_complete"])
        self.assertFalse(self.report(days=28)["collection"]["history_complete"])
        self.assertFalse(self.report(days=90)["collection"]["previous_history_complete"])

    def test_expired_data_is_excluded_even_before_daily_cleanup(self):
        self.event(day=NOW - timedelta(days=91))
        self.event(day=NOW)
        report = self.report(days=90)
        self.assertEqual(report["summary"]["current"]["actions"], 1)
        self.assertEqual(report["summary"]["previous"]["actions"], 0)
        self.assertFalse(report["collection"]["previous_history_complete"])

    def test_weekly_summary_is_last_seven_days_independent_of_selected_range(self):
        self.event(day=NOW - timedelta(days=2))
        self.event(day=NOW - timedelta(days=12))
        report = self.report(days=28)
        self.assertEqual(report["summary"]["current"]["actions"], 2)
        self.assertEqual(report["weekly_summary"]["actions"], 1)
        self.assertEqual(report["weekly_summary"]["start"], "2026-10-17")

    def test_retention_uses_complete_active_family_weeks_and_deduplicates_people(self):
        # Latest complete week is October 12–18. Baselines are Oct 5–11 and Sep 14–20.
        self.event(day=datetime(2026, 10, 7, 10, tzinfo=UTC))
        self.event(self.staff, day=datetime(2026, 10, 8, 10, tzinfo=UTC))
        self.event(self.other_child, day=datetime(2026, 10, 9, 10, tzinfo=UTC))
        self.event(day=datetime(2026, 10, 15, 10, tzinfo=UTC))
        self.event(day=datetime(2026, 9, 16, 10, tzinfo=UTC))
        # A return in the current partial week does not count as a past-week return.
        self.event(self.other_child, day=NOW)
        self.staff.is_superuser = True
        retained = self.report(scope="deployment", role="parent", feature="rewards")["retention"]
        self.assertEqual(retained["week_1"]["eligible_families"], 2)
        self.assertEqual(retained["week_1"]["returned_families"], 1)
        self.assertEqual(retained["week_1"]["rate"], 0.5)
        self.assertEqual(retained["week_4"]["rate"], 1)
        self.assertEqual(retained["week_1"]["return_end"], "2026-10-18")

    def test_incomplete_retention_is_unknown_rather_than_zero(self):
        UsageCollectionState.objects.filter(pk=1).update(started_at=datetime(2026, 10, 6, 12, tzinfo=UTC))
        self.event(day=datetime(2026, 10, 7, 10, tzinfo=UTC))
        retained = self.report()["retention"]["week_1"]
        self.assertFalse(retained["history_complete"])
        self.assertIsNone(retained["eligible_families"])
        self.assertIsNone(retained["returned_families"])
        self.assertIsNone(retained["rate"])

    def test_complete_empty_retention_has_zero_eligible_but_no_invented_percentage(self):
        retained = self.report()["retention"]["week_1"]
        self.assertTrue(retained["history_complete"])
        self.assertEqual(retained["eligible_families"], 0)
        self.assertEqual(retained["returned_families"], 0)
        self.assertIsNone(retained["rate"])

    def test_onboarding_progresses_through_child_activity_and_parent_approval(self):
        created_at = NOW - timedelta(days=3)
        Family.objects.filter(pk=self.family.pk).update(created_at=created_at)
        User.objects.filter(pk=self.child.pk).update(date_joined=created_at + timedelta(hours=1))
        self.event(day=created_at + timedelta(days=1))
        self.event(self.staff, day=created_at + timedelta(days=2), feature="homework", action="approved")
        report = self.report(days=7, role="parent", feature="rewards")
        self.assertEqual({key: value for key, value in report["onboarding"].items() if key != "coverage"}, {"families_created": 1, "child_added": 1, "first_activity": 1, "first_parent_approval": 1})

    def test_reward_requests_and_negative_habits_do_not_complete_first_work_step(self):
        created_at = NOW - timedelta(days=3)
        Family.objects.filter(pk=self.family.pk).update(created_at=created_at)
        User.objects.filter(pk=self.child.pk).update(date_joined=created_at + timedelta(hours=1))
        self.event(day=created_at + timedelta(days=1), feature="rewards", action="requested")
        self.event(day=created_at + timedelta(days=1), feature="habits", action="checked_in")
        self.event(self.staff, day=created_at + timedelta(days=2), feature="rewards", action="approved")
        onboarding = self.report(days=7)["onboarding"]
        self.assertEqual(onboarding["child_added"], 1)
        self.assertEqual(onboarding["first_activity"], 0)
        self.assertEqual(onboarding["first_parent_approval"], 0)

    def completion(self, *, actor=None, status="pending", created_at=None, decided_at=None):
        actor = actor or self.child
        chore = Chore.objects.create(family=actor.family, title="Private chore", created_by=self.staff if actor == self.child else self.parent)
        row = ChoreCompletion.objects.create(chore=chore, user=actor, completed_date=NOW.date(), reward_amount_snapshot=0, coin_reward_snapshot=0, status=status, decided_by=self.staff if decided_at else None, decided_at=decided_at)
        if created_at:
            ChoreCompletion.objects.filter(pk=row.pk).update(created_at=created_at)
        return row

    def test_friction_current_queue_and_scoped_median_have_explicit_coverage(self):
        self.completion(created_at=NOW - timedelta(days=100))
        self.completion(actor=self.other_child)
        self.completion(status="approved", created_at=NOW - timedelta(hours=8), decided_at=NOW - timedelta(hours=4))
        self.completion(status="approved", created_at=NOW - timedelta(hours=10), decided_at=NOW - timedelta(hours=2))
        friction = self.report(days=7)["friction"]
        self.assertEqual(friction["pending_reviews"], 1)
        self.assertEqual(friction["median_approval_hours"], 6)
        self.assertEqual(friction["coverage"], ["homework", "chores"])
        self.assertIsNone(self.report(role="child")["friction"]["median_approval_hours"])
        self.assertIsNone(self.report(feature="rewards")["friction"]["pending_reviews"])

    def test_report_contains_aggregate_metadata_without_private_text_or_identities(self):
        self.reading()
        self.event()
        payload = json.dumps(self.report())
        for value in ("Private title", "Private reflection", "staff-reader", "reader-one", "Synthetic household"):
            self.assertNotIn(value, payload)
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        self.assertFalse(set(keys(self.report())) & {"id", "actor_id", "family_id", "source_id", "username", "display_name", "email", "reflection", "context"})

    def test_action_retries_across_two_actors_are_deduplicated(self):
        source = self.reading()
        first = record_action(self.child, "reading", "completed", source="reading.readingsession", source_id=source.pk)
        second = record_action(self.staff, "reading", "completed", source="reading.readingsession", source_id=source.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(second.actor_id, self.child.pk)

    def test_source_ownership_enum_and_active_actor_are_verified(self):
        source = self.reading(self.other_child)
        self.assertIsNone(record_action(self.child, "reading", "completed", source="reading.readingsession", source_id=source.pk))
        self.assertIsNone(record_action(self.child, "reading", "completed", source="journal.entry", source_id=1))
        self.assertIsNone(record_action(self.child, "reading", "approved", source="reading.readingsession", source_id=source.pk))
        source = self.reading()
        User.objects.filter(pk=self.child.pk).update(is_active=False)
        self.assertIsNone(record_action(self.child, "reading", "completed", source="reading.readingsession", source_id=source.pk))
        self.assertFalse(UsageEvent.objects.exists())

    def test_unassigned_project_approval_uses_creator_family_while_assignment_takes_precedence(self):
        unassigned = Project.objects.create(created_by=self.staff, assigned_to=None, title="Synthetic unassigned project", status="in_review")
        self.client.force_authenticate(self.staff)
        response = self.client.post(f"/api/projects/{unassigned.pk}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        event = UsageEvent.objects.get(feature="projects", action="approved")
        self.assertEqual(event.actor_id, self.staff.pk)
        self.assertEqual(event.family_id, self.family.pk)
        assigned_elsewhere = Project.objects.create(created_by=self.staff, assigned_to=self.other_child, title="Synthetic assigned project")
        self.assertIsNone(record_action(self.staff, "projects", "approved", source="projects.project", source_id=assigned_elsewhere.pk))
        self.assertEqual(UsageEvent.objects.count(), 1)

    def test_live_fixture_actions_and_visits_are_excluded_at_collection(self):
        live = self.live_family()
        actor = live.children[0]
        source = self.reading(actor)
        self.assertIsNone(record_action(actor, "reading", "completed", source="reading.readingsession", source_id=source.pk))
        self.assertIsNone(record_visit(actor))
        self.assertFalse(UsageEvent.objects.exists())
        self.assertFalse(UsageVisit.objects.exists())

    def test_visits_deduplicate_devices_use_utc_and_reject_client_identity(self):
        self.client.force_authenticate(self.child)
        with patch("apps.usage.services.timezone.now", return_value=NOW):
            self.assertEqual(self.client.post("/api/usage/visit/", {}, format="json").status_code, 204)
            self.assertEqual(self.client.post("/api/usage/visit/", {}, format="json").status_code, 204)
            for value in ({"user_id": self.other_child.pk}, {"date": "2000-01-01"}, {"role": "parent"}, []):
                self.assertEqual(self.client.post("/api/usage/visit/", value, format="json").status_code, 400)
        with patch("apps.usage.services.timezone.now", return_value=NOW + timedelta(days=1)):
            record_visit(self.child)
        self.assertEqual(UsageVisit.objects.count(), 2)
        self.assertEqual(UsageEvent.objects.count(), 0)

    def test_failed_telemetry_savepoint_does_not_poison_business_transaction(self):
        source = self.reading()
        with transaction.atomic(), patch("apps.usage.services.UsageEvent.objects.get_or_create", side_effect=DatabaseError("Private database detail")):
            with self.assertLogs("apps.usage.services", level="WARNING") as logs:
                self.assertIsNone(record_action(self.child, "reading", "completed", source="reading.readingsession", source_id=source.pk))
            self.assertNotIn("Private database detail", " ".join(logs.output))
            self.assertTrue(ReadingSession.objects.filter(pk=source.pk).exists())

    def test_action_rolls_back_with_its_business_transaction(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                source = self.reading()
                record_action(self.child, "reading", "completed", source="reading.readingsession", source_id=source.pk)
                self.assertTrue(UsageEvent.objects.exists())
                raise RuntimeError("Synthetic rollback")
        self.assertFalse(UsageEvent.objects.exists())

    def test_user_and_family_deletion_remove_linked_telemetry(self):
        self.event()
        self.event(self.staff, action="approved")
        UsageVisit.objects.create(actor=self.child, family=self.family, role="child", occurred_on=NOW.date())
        self.child.delete()
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertFalse(UsageVisit.objects.exists())
        self.family.delete()
        self.assertFalse(UsageEvent.objects.exists())

    def test_pruning_removes_raw_history_but_preserves_collection_boundary(self):
        boundary = UsageCollectionState.objects.get(pk=1).started_at
        self.event(day=NOW - timedelta(days=90))
        current = self.event(day=NOW - timedelta(days=89))
        UsageVisit.objects.create(actor=self.child, family=self.family, role="child", occurred_on=(NOW - timedelta(days=90)).date())
        result = prune_usage_data(now=NOW)
        self.assertEqual(result["events_deleted"], 1)
        self.assertEqual(result["visits_deleted"], 1)
        self.assertEqual(UsageEvent.objects.get().pk, current.pk)
        self.assertEqual(UsageCollectionState.objects.get(pk=1).started_at, boundary)

    def test_read_only_weekly_command_has_no_writes_or_email(self):
        self.event()
        before = UsageEvent.objects.count()
        out = StringIO()
        with patch("apps.usage.reporting.timezone.now", return_value=NOW):
            call_command("usage_summary", username=self.staff.username, stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["weekly_summary"]["actions"], 1)
        self.assertEqual(UsageEvent.objects.count(), before)
