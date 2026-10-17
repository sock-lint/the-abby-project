from datetime import date, timedelta
from urllib.parse import urlparse
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from config.tests.factories import make_family

from apps.reading.catalog import BOOK_CATALOG, INTERESTS
from apps.reading.models import ReadingBook, ReadingSession
from apps.reading.recommendations import recommend_books


class ReadingRecommendationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        family = make_family(children=[{"username": "reader"}, {"username": "sibling"}])
        cls.reader, cls.sibling = family.children
        cls.other = make_family(name="Other", children=[{"username": "other-reader"}]).children[0]

    def book(self, title="An original book", *, interests=(), user=None, **kwargs):
        return ReadingBook.objects.create(
            user=user or self.reader,
            title=title,
            interests=list(interests),
            client_request_id=uuid4(),
            create_payload={},
            **kwargs,
        )

    def session(self, book, reaction="liked", *, user=None, **kwargs):
        return ReadingSession.objects.create(
            user=user or book.user,
            book=book,
            occurred_on=kwargs.pop("occurred_on", date.today()),
            reaction=reaction,
            client_request_id=uuid4(),
            create_payload={},
            **kwargs,
        )

    def set_age(self, age):
        today = date.today()
        try:
            birthday = today.replace(year=today.year - age)
        except ValueError:
            birthday = date(today.year - age, 2, 28)
        self.reader.date_of_birth = birthday
        self.reader.save(update_fields=["date_of_birth"])

    def test_starter_picks_are_varied_deterministic_and_bounded(self):
        result = recommend_books(self.reader)
        self.assertEqual(result, recommend_books(self.reader))
        self.assertEqual(len(result["results"]), 6)
        topics = {topic for book in result["results"] for topic in book["interests"]}
        self.assertGreaterEqual(len(topics), 6)
        self.assertIn("Starter picks", result["basis"])
        self.assertIn("not reading levels", result["basis"])
        self.assertTrue(all(book["age_min"] <= 8 for book in result["results"]))

    def test_selected_topic_limits_results_and_explains_choice(self):
        self.set_age(10)
        result = recommend_books(self.reader, interest="mystery")
        self.assertTrue(result["results"])
        for book in result["results"]:
            self.assertIn("mystery", book["interests"])
            self.assertEqual(book["reason"], "Because you chose mystery.")
        self.assertIn("Exploring mystery", result["basis"])

    def test_fifteen_year_old_has_a_full_starter_shelf(self):
        self.set_age(15)
        result = recommend_books(self.reader)

        self.assertEqual(result, recommend_books(self.reader))
        self.assertEqual(len(result["results"]), 6)
        self.assertEqual(len({book["id"] for book in result["results"]}), 6)
        for book in result["results"]:
            with self.subTest(book=book["id"]):
                self.assertLessEqual(book["age_min"], 15)
                self.assertTrue(book["age_max"] is None or book["age_max"] >= 15)
                self.assertTrue(book["reason"])

    def test_teen_fantasy_picks_replenish_after_saving_a_full_shelf(self):
        self.set_age(15)
        first = recommend_books(self.reader, interest="fantasy")
        self.assertEqual(len(first["results"]), 6)
        self.assertEqual(first, recommend_books(self.reader, interest="fantasy"))
        for book in first["results"]:
            self.book(book["title"], interests=book["interests"], status="want_to_read")

        following = recommend_books(self.reader, interest="fantasy")
        self.assertEqual(len(following["results"]), 6)
        self.assertEqual(following, recommend_books(self.reader, interest="fantasy"))
        first_ids = {book["id"] for book in first["results"]}
        following_ids = {book["id"] for book in following["results"]}
        self.assertEqual(len(first_ids), 6)
        self.assertEqual(len(following_ids), 6)
        self.assertTrue(first_ids.isdisjoint(following_ids))
        for book in first["results"] + following["results"]:
            with self.subTest(book=book["id"]):
                self.assertIn("fantasy", book["interests"])
                self.assertLessEqual(book["age_min"], 15)
                self.assertTrue(book["age_max"] is None or book["age_max"] >= 15)
                self.assertEqual(book["reason"], "Because you chose fantasy.")

    def test_saved_topics_and_liked_reading_influence_ranking(self):
        self.set_age(10)
        self.book("Fantasy adventure", interests=["fantasy", "adventure"])
        science = self.book("My science book", interests=["science"])
        self.session(science, reaction="loved")
        result = recommend_books(self.reader)
        self.assertIn("science", result["results"][0]["interests"])
        self.assertEqual(result["results"][0]["reason"], "More science after a book you loved.")
        self.assertIn("liked or loved", result["basis"])

    def test_shelf_topics_work_before_first_session(self):
        self.set_age(10)
        self.book(interests=["history"])
        result = recommend_books(self.reader)
        self.assertIn("history", result["results"][0]["interests"])
        self.assertEqual(result["results"][0]["reason"], "More history, a topic on your shelf.")

    def test_latest_reaction_wins_and_repeat_logs_do_not_amplify_topic(self):
        self.set_age(10)
        science = self.book(interests=["science"])
        for _ in range(3):
            self.session(science, "loved", occurred_on=date.today() - timedelta(days=1))
        self.session(science, "not_for_me")
        result = recommend_books(self.reader)
        self.assertFalse(any("you loved" in book["reason"] for book in result["results"]))
        self.assertNotIn("liked or loved", result["basis"])

    def test_known_age_respects_both_publisher_bounds_and_open_ended_guidance(self):
        for age in (6, 10, 13, 17):
            with self.subTest(age=age):
                self.set_age(age)
                result = recommend_books(self.reader)
                self.assertTrue(result["results"])
                for book in result["results"]:
                    self.assertLessEqual(book["age_min"], age)
                    if book["age_max"] is not None:
                        self.assertGreaterEqual(book["age_max"], age)
        self.assertTrue(any(book["age_max"] is None for book in result["results"]))

    def test_every_shelf_status_excludes_owned_titles_normalizing_case_and_spaces(self):
        self.set_age(8)
        for status, title in zip(ReadingBook.Status.values, BOOK_CATALOG[:4]):
            self.book(f"  {title['title'].swapcase().replace(' ', '   ')}  ", status=status)
        result_ids = {book["id"] for book in recommend_books(self.reader)["results"]}
        self.assertTrue(result_ids.isdisjoint(book["id"] for book in BOOK_CATALOG[:4]))

    def test_other_users_shelves_and_sessions_never_affect_picks(self):
        self.set_age(10)
        expected = recommend_books(self.reader)
        for user in (self.sibling, self.other):
            book = self.book("The Wild Robot", user=user, interests=["history"])
            self.session(book, "loved")
            # Defense in depth for an inconsistent row bypassing API validation.
            self.session(book, "loved", user=self.reader)
        self.assertEqual(recommend_books(self.reader), expected)

    def test_reflection_content_is_not_loaded_or_used(self):
        self.set_age(10)
        book = self.book(interests=["friendship"])
        session = self.session(book, "liked", reflection="Private words about fantasy and science.")
        with CaptureQueriesContext(connection) as queries:
            expected = recommend_books(self.reader)
        self.assertEqual(len(queries), 3)
        self.assertTrue(all("reflection" not in query["sql"].lower() for query in queries))
        session.reflection = "A completely different private thought about history."
        session.save(update_fields=["reflection"])
        self.assertEqual(recommend_books(self.reader), expected)
        self.assertNotIn("Private words", str(expected))

    def test_catalog_metadata_has_sources_unique_ids_and_short_original_descriptions(self):
        self.assertEqual(len(BOOK_CATALOG), len({book["id"] for book in BOOK_CATALOG}))
        self.assertGreaterEqual(len(BOOK_CATALOG), 12)
        for book in BOOK_CATALOG:
            with self.subTest(book=book["id"]):
                self.assertLessEqual(len(book["description"]), 180)
                self.assertTrue(book["title"])
                self.assertTrue(book["author"])
                self.assertTrue(set(book["interests"]).issubset(INTERESTS))
                source = urlparse(book["source_url"])
                self.assertEqual(source.scheme, "https")
                self.assertIn(source.hostname, {
                    "www.penguinrandomhouse.com", "assets.penguinrandomhouse.com",
                    "www.hachettebookgroup.com", "books.disney.com",
                    "us.macmillan.com", "macmillanlibrary.com",
                })

    def test_a_fully_saved_catalog_returns_an_honest_empty_result(self):
        for book in BOOK_CATALOG:
            self.book(book["title"])
        self.assertEqual(recommend_books(self.reader)["results"], [])
