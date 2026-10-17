from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone as datetime_timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from config.tests.factories import make_family

from apps.reading.models import ReadingBook, ReadingSession


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingAPITests(TestCase):
    def setUp(self):
        household = make_family(
            "Readers", parents=[{"username": "parent"}],
            children=[{"username": "reader"}, {"username": "sibling"}],
        )
        other = make_family("Other readers", parents=[{"username": "other-parent"}], children=[{"username": "other-child"}])
        self.family = household.family
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        self.book = self.make_book(self.child)
        self.sibling_book = self.make_book(self.sibling, "Sibling book")
        self.other_book = self.make_book(self.other_child, "Foreign book")

    def make_book(self, user, title="The Wild Robot", **extra):
        return ReadingBook.objects.create(
            user=user, title=title, author="Peter Brown", client_request_id=uuid4(), create_payload={}, **extra,
        )

    def make_session(self, user=None, book=None, **extra):
        return ReadingSession.objects.create(
            user=user or self.child, book=book or self.book, occurred_on=date(2020, 1, 1),
            duration_minutes=20, client_request_id=uuid4(), create_payload={}, **extra,
        )

    def create_book(self, **extra):
        return self.client.post("/api/reading-books/", {
            "title": "A new book", "client_request_id": str(uuid4()), **extra,
        }, format="json")

    def create_session(self, **extra):
        return self.client.post("/api/reading-sessions/", {
            "book": self.book.id, "duration_minutes": 20, "client_request_id": str(uuid4()), **extra,
        }, format="json")

    def test_all_reading_surfaces_require_authentication(self):
        self.client.force_authenticate(None)
        for url in (
            "/api/reading-books/", "/api/reading-sessions/", "/api/reading/summary/", "/api/reading/recommendations/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.create_book().status_code, 401)
        self.assertEqual(self.create_session().status_code, 401)

    def test_child_shelf_and_log_are_scoped_to_self(self):
        own = self.make_session()
        self.make_session(self.sibling, self.sibling_book)
        self.make_session(self.other_child, self.other_book)
        self.assertEqual([row["id"] for row in self.client.get("/api/reading-books/").data["results"]], [self.book.id])
        self.assertEqual([row["id"] for row in self.client.get("/api/reading-sessions/").data["results"]], [own.id])
        for book in (self.sibling_book, self.other_book):
            for method in (self.client.get, self.client.patch, self.client.delete):
                with self.subTest(book=book.pk, method=method.__name__):
                    self.assertEqual(method(f"/api/reading-books/{book.pk}/").status_code, 404)

    def test_child_cannot_read_change_or_delete_other_readers_sessions(self):
        for user, book in ((self.sibling, self.sibling_book), (self.other_child, self.other_book)):
            session = self.make_session(user, book)
            for method in (self.client.get, self.client.patch, self.client.delete):
                with self.subTest(user=user.id, method=method.__name__):
                    self.assertEqual(method(f"/api/reading-sessions/{session.pk}/").status_code, 404)

    def test_parent_sees_family_shelf_and_can_select_one_child(self):
        self.client.force_authenticate(self.parent)
        all_rows = self.client.get("/api/reading-books/").data["results"]
        self.assertEqual({row["id"] for row in all_rows}, {self.book.id, self.sibling_book.id})
        selected = self.client.get("/api/reading-books/", {"user_id": self.child.id})
        self.assertEqual([row["id"] for row in selected.data["results"]], [self.book.id])
        self.assertEqual(self.client.get("/api/reading-books/", {"user_id": self.other_child.id}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/reading-books/{self.other_book.id}/", {"title": "Probe"}).status_code, 404)

    def test_parent_must_select_same_family_child_for_every_create(self):
        self.client.force_authenticate(self.parent)
        for create in (self.create_book, self.create_session):
            with self.subTest(create=create.__name__):
                self.assertEqual(create().status_code, 400)
                self.assertEqual(create(user_id=self.parent.id).status_code, 404)
                self.assertEqual(create(user_id=self.other_child.id).status_code, 404)
                response = create(user_id=self.child.id)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["user"], self.child.id)

    def test_child_cannot_impersonate_sibling_even_with_same_family_book(self):
        self.assertEqual(self.create_book(user_id=self.sibling.id).status_code, 400)
        self.assertEqual(self.create_session(user_id=self.sibling.id, book=self.sibling_book.id).status_code, 400)
        self.assertEqual(self.create_session(book=self.sibling_book.id).status_code, 400)
        self.assertEqual(self.create_session(book=self.other_book.id).status_code, 400)
        self.assertEqual(self.create_book(user_id=self.child.id).status_code, 201)

    def test_parent_cannot_attach_child_log_to_another_readers_book(self):
        self.client.force_authenticate(self.parent)
        for book in (self.sibling_book, self.other_book):
            response = self.create_session(user_id=self.child.id, book=book.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("book", response.data)

    def test_malformed_target_and_book_ids_return_400(self):
        self.client.force_authenticate(self.parent)
        for bad_id in ("abc", "1.0", "", "-2", "0", "²", "9" * 100, None, True, []):
            with self.subTest(bad_id=bad_id):
                self.assertEqual(self.create_book(user_id=bad_id).status_code, 400)
                self.assertEqual(self.create_session(user_id=bad_id).status_code, 400)
        for url in ("/api/reading-books/", "/api/reading-sessions/", "/api/reading/summary/", "/api/reading/recommendations/"):
            self.assertEqual(self.client.get(url, {"user_id": "abc"}).status_code, 400)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/reading-sessions/?book=abc").status_code, 400)

    def test_book_fields_and_defaults_are_saved_without_reward_fields(self):
        response = self.create_book(title="  The Secret Garden  ", interests=["animals", "friendship", "animals"])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "The Secret Garden")
        self.assertEqual(response.data["author"], "")
        self.assertEqual(response.data["status"], "reading")
        self.assertEqual(response.data["interests"], ["animals", "friendship"])
        self.assertNotIn("create_payload", response.data)
        self.assertNotIn("xp_awarded", response.data)

    def test_malformed_book_payloads_are_rejected(self):
        for invalid in (
            {"title": " "}, {"title": "a" * 201}, {"author": "a" * 161}, {"status": "invented"},
            {"interests": ["unknown"]}, {"interests": ["animals"] * 7}, {"interests": "animals"},
            {"client_request_id": "not-a-uuid"}, {"user": self.other_child.id},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.create_book(**invalid).status_code, 400)
        self.assertEqual(self.client.post("/api/reading-books/", {"title": "Book"}, format="json").status_code, 400)

    def test_book_create_retry_is_normalized_and_survives_corrections(self):
        request_id = str(uuid4())
        first = self.create_book(title="  Original title ", interests=["fantasy", "animals"], client_request_id=request_id)
        book_id = first.data["id"]
        corrected = self.client.patch(f"/api/reading-books/{book_id}/", {"title": "Corrected", "status": "finished"}, format="json")
        self.assertEqual(corrected.status_code, 200)
        retry = self.create_book(title="Original title", interests=["animals", "fantasy"], client_request_id=request_id)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["id"], book_id)
        self.assertEqual(retry.data["title"], "Corrected")
        self.assertEqual(retry.data["status"], "finished")
        conflict = self.create_book(title="Different", client_request_id=request_id)
        self.assertEqual(conflict.status_code, 400)
        self.assertEqual(ReadingBook.objects.filter(user=self.child, client_request_id=request_id).count(), 1)

    def test_same_uuid_is_separate_for_each_reader(self):
        self.client.force_authenticate(self.parent)
        request_id = str(uuid4())
        for child in (self.child, self.sibling):
            response = self.create_book(user_id=child.id, client_request_id=request_id)
            self.assertEqual(response.status_code, 201)
        self.assertEqual(ReadingBook.objects.filter(client_request_id=request_id).count(), 2)

    def test_books_cannot_be_reassigned_or_change_request_identity(self):
        for field, value in (("user", self.sibling.id), ("user_id", self.sibling.id), ("client_request_id", str(uuid4()))):
            response = self.client.patch(f"/api/reading-books/{self.book.id}/", {field: value}, format="json")
            self.assertEqual(response.status_code, 400)
        self.book.refresh_from_db()
        self.assertEqual(self.book.user_id, self.child.id)

    def test_session_saves_all_formats_and_optional_reading_details(self):
        for book_format in ("print", "ebook", "audiobook"):
            response = self.create_session(
                occurred_on="2020-01-02", duration_minutes=0, pages_read=8, section="Chapters 1–2",
                reflection="The robot helped an animal. I wonder who will help her next.",
                format=book_format, reaction="loved",
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["format"], book_format)
            self.assertEqual(response.data["book_title"], self.book.title)
            self.assertEqual(response.data["book_author"], self.book.author)
            self.assertEqual(response.data["pages_read"], 8)
            self.assertEqual(response.data["occurred_on"], "2020-01-02")
            self.assertEqual(response.data["reaction"], "loved")
            self.assertNotIn("create_payload", response.data)

    def test_chapter_or_reflection_alone_is_a_valid_session(self):
        for details in ({"section": "Chapter 4"}, {"reflection": "A surprising friendship began."}):
            response = self.create_session(duration_minutes=0, **details)
            self.assertEqual(response.status_code, 201)
        empty = self.create_session(duration_minutes=0, pages_read=0, section=" ", reflection=" ")
        self.assertEqual(empty.status_code, 400)

    def test_session_validation_limits_and_required_uuid(self):
        for invalid in (
            {"duration_minutes": -1}, {"duration_minutes": 601}, {"duration_minutes": 1.5},
            {"pages_read": -1}, {"pages_read": 2001}, {"section": "a" * 121},
            {"reflection": "a" * 3001}, {"format": "video"}, {"reaction": "amazing"},
            {"occurred_on": "not-a-date"}, {"occurred_on": "9999-01-01"},
            {"book": 9999999}, {"book": None}, {"client_request_id": "invalid"},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.create_session(**invalid).status_code, 400)
        response = self.client.post("/api/reading-sessions/", {"book": self.book.id, "duration_minutes": 5}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_default_date_and_future_guard_follow_family_local_day(self):
        self.family.timezone = "America/Los_Angeles"
        self.family.save(update_fields=["timezone"])
        self.child.family.refresh_from_db()
        with patch("django.utils.timezone.now", return_value=datetime(2026, 6, 2, 1, tzinfo=datetime_timezone.utc)):
            response = self.create_session()
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data["occurred_on"], "2026-06-01")
            self.assertEqual(self.create_session(occurred_on="2026-06-02").status_code, 400)
            summary = self.client.get("/api/reading/summary/").data
            self.assertEqual(summary["today"], "2026-06-01")
            self.assertEqual(summary["timezone"], "America/Los_Angeles")

    def test_omitted_session_date_retry_survives_midnight(self):
        request_id = str(uuid4())
        with patch("django.utils.timezone.now", return_value=datetime(2026, 6, 1, 19, tzinfo=datetime_timezone.utc)):
            first = self.create_session(client_request_id=request_id)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 6, 2, 19, tzinfo=datetime_timezone.utc)):
            retry = self.create_session(client_request_id=request_id)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["id"], first.data["id"])
        self.assertEqual(retry.data["occurred_on"], first.data["occurred_on"])

    def test_session_retry_returns_corrected_entry_and_conflicts_do_not_duplicate(self):
        request_id = str(uuid4())
        first = self.create_session(reflection="Original reflection", client_request_id=request_id)
        url = f"/api/reading-sessions/{first.data['id']}/"
        changed = self.client.patch(url, {"reflection": "A correction", "duration_minutes": 15}, format="json")
        self.assertEqual(changed.status_code, 200)
        retry = self.create_session(reflection="Original reflection", client_request_id=request_id)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["reflection"], "A correction")
        self.assertEqual(retry.data["duration_minutes"], 15)
        self.assertEqual(self.create_session(reflection="Different", client_request_id=request_id).status_code, 400)
        self.assertEqual(ReadingSession.objects.filter(client_request_id=request_id).count(), 1)

    def test_session_corrections_cannot_change_owner_book_or_clear_all_reading_details(self):
        session = self.make_session()
        url = f"/api/reading-sessions/{session.id}/"
        for invalid in (
            {"book": self.sibling_book.id}, {"user": self.sibling.id}, {"user_id": self.sibling.id},
            {"client_request_id": str(uuid4())}, {"duration_minutes": 0}, {"occurred_on": "9999-01-01"},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.patch(url, invalid, format="json").status_code, 400)
        self.client.force_authenticate(self.parent)
        response = self.client.patch(url, {"duration_minutes": 0, "section": "Chapter 1", "occurred_on": "2020-01-02"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["book"], self.book.id)
        self.assertEqual(response.data["user"], self.child.id)
        self.assertEqual(response.data["section"], "Chapter 1")

    def test_book_deletion_preserves_sessions_and_deleting_entry_updates_summary(self):
        session = self.make_session(pages_read=12)
        denied = self.client.delete(f"/api/reading-books/{self.book.id}/")
        self.assertEqual(denied.status_code, 409)
        self.assertTrue(ReadingSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.client.delete(f"/api/reading-sessions/{session.id}/").status_code, 204)
        summary = self.client.get("/api/reading/summary/").data
        self.assertEqual((summary["sessions_total"], summary["total_minutes"], summary["total_pages"]), (0, 0, 0))
        self.assertEqual(self.client.delete(f"/api/reading-books/{self.book.id}/").status_code, 204)

    def test_account_deletion_can_cascade_through_its_own_books_and_sessions(self):
        session = self.make_session()
        self.child.delete()
        self.assertFalse(ReadingSession.objects.filter(pk=session.pk).exists())
        self.assertFalse(ReadingBook.objects.filter(pk=self.book.pk).exists())

    def test_summary_counts_confirmed_shelf_and_corrected_log_only(self):
        self.book.status = ReadingBook.Status.FINISHED
        self.book.save()
        own = self.make_session(pages_read=9)
        self.make_session(self.sibling, self.sibling_book, pages_read=99)
        self.client.patch(f"/api/reading-sessions/{own.id}/", {"duration_minutes": 25, "pages_read": 11}, format="json")
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/reading/summary/").status_code, 400)
        self.assertEqual(self.client.get("/api/reading/summary/", {"user_id": self.other_child.id}).status_code, 404)
        summary = self.client.get("/api/reading/summary/", {"user_id": self.child.id}).data
        self.assertEqual({key: summary[key] for key in ("books_total", "books_finished", "sessions_total", "total_minutes", "total_pages")}, {
            "books_total": 1, "books_finished": 1, "sessions_total": 1, "total_minutes": 25, "total_pages": 11,
        })

    def test_list_pagination_and_selected_book_filter(self):
        second = self.make_book(self.child, "Another book")
        for _ in range(22):
            self.make_session()
        another = self.make_session(book=second)
        first_page = self.client.get("/api/reading-sessions/").data
        self.assertEqual(first_page["count"], 23)
        self.assertEqual(len(first_page["results"]), 20)
        self.assertIsNotNone(first_page["next"])
        selected = self.client.get("/api/reading-sessions/", {"book": second.id}).data
        self.assertEqual(selected["count"], 1)
        self.assertEqual(selected["results"][0]["id"], another.id)

    def test_recommendation_endpoint_is_scoped_and_interest_is_validated(self):
        self.client.force_authenticate(self.parent)
        with patch("apps.reading.recommendations.recommend_books", return_value={"results": [], "basis": "A starting shelf"}) as recommend:
            self.assertEqual(self.client.get("/api/reading/recommendations/").status_code, 400)
            self.assertEqual(self.client.get("/api/reading/recommendations/", {"user_id": self.other_child.id}).status_code, 404)
            self.assertEqual(self.client.get("/api/reading/recommendations/", {"user_id": self.child.id, "interest": "bogus"}).status_code, 400)
            response = self.client.get("/api/reading/recommendations/", {"user_id": self.child.id, "interest": "animals"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["basis"], "A starting shelf")
            self.assertEqual(recommend.call_count, 1)
            self.assertEqual(recommend.call_args.args[0].id, self.child.id)
            self.assertEqual(recommend.call_args.kwargs, {"interest": "animals"})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency requires PostgreSQL.")
        household = make_family("Concurrent readers", children=[{"username": "reader"}])
        self.child = household.children[0]
        self.book = ReadingBook.objects.create(
            user=self.child, title="A book", client_request_id=uuid4(), create_payload={},
        )

    def concurrent_posts(self, url, payloads):
        barrier = Barrier(2)

        def post(payload):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.child)
                barrier.wait(timeout=10)
                response = client.post(url, payload, format="json")
                return response.status_code, response.data
            finally:
                # The app uses persistent DB connections. Worker thread-local
                # connections must close before Django drops its test database.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(post, payloads, timeout=30))
        return results

    def test_concurrent_book_retry_saves_once(self):
        request_id = str(uuid4())
        payload = {"title": "A new book", "client_request_id": request_id}
        results = self.concurrent_posts("/api/reading-books/", [payload, payload])
        self.assertEqual(sorted(code for code, _ in results), [200, 201])
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(ReadingBook.objects.filter(user=self.child, client_request_id=request_id).count(), 1)

    def test_concurrent_session_retry_saves_once(self):
        request_id = str(uuid4())
        payload = {"book": self.book.id, "duration_minutes": 20, "client_request_id": request_id}
        results = self.concurrent_posts("/api/reading-sessions/", [payload, payload])
        self.assertEqual(sorted(code for code, _ in results), [200, 201])
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(ReadingSession.objects.filter(user=self.child, client_request_id=request_id).count(), 1)

    def test_concurrent_conflicting_session_request_rejects_one_without_duplicate(self):
        request_id = str(uuid4())
        payload = {"book": self.book.id, "duration_minutes": 20, "client_request_id": request_id}
        results = self.concurrent_posts("/api/reading-sessions/", [payload, {**payload, "duration_minutes": 21}])
        self.assertEqual(sorted(code for code, _ in results), [201, 400])
        self.assertEqual(ReadingSession.objects.filter(user=self.child, client_request_id=request_id).count(), 1)
