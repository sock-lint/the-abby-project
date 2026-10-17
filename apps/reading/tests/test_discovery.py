from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from config.tests.factories import make_family

from apps.reading.models import ReadingBook
from apps.reading.recommendations import recommend_books


def catalog_book(identifier, **overrides):
    return {
        "id": identifier, "title": identifier.replace("-", " ").title(),
        "author": "An Author", "interests": ("fantasy",),
        "age_min": 8, "age_max": 12, "description": "An original description.",
        "source_url": "https://www.penguinrandomhouse.com/books/example/",
        "isbn": "9780000000000", "cover_url": "https://covers.openlibrary.org/b/isbn/9780000000000-M.jpg",
        "page_count": 180, "formats": ("print",), "moods": ("exciting",),
        "styles": (), "themes": ("dragons",), "series": None,
        **overrides,
    }


class ReadingDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        family = make_family(children=[{"username": "discovery-reader"}, {"username": "discovery-sibling"}])
        cls.reader, cls.sibling = family.children
        today = date.today()
        cls.reader.date_of_birth = date(today.year - 10, today.month, min(today.day, 28))
        cls.reader.save(update_fields=["date_of_birth"])

    def shelf(self, entry, *, status="finished", user=None, author=None):
        return ReadingBook.objects.create(
            user=user or self.reader, title=entry["title"],
            author=entry["author"] if author is None else author,
            status=status, interests=list(entry["interests"]),
            client_request_id=uuid4(), create_payload={},
        )

    def picks(self, catalog, **filters):
        with patch("apps.reading.recommendations.BOOK_CATALOG", tuple(catalog)):
            return recommend_books(self.reader, **filters)

    def test_mood_style_format_and_theme_filters_intersect(self):
        wanted = catalog_book("dragon-comic", moods=("funny",), styles=("graphic_novel",), formats=("print", "ebook"))
        catalog = [wanted, catalog_book("wrong-mood"),
                   catalog_book("wrong-style", moods=("funny",)),
                   catalog_book("wrong-format", moods=("funny",), styles=("graphic_novel",), formats=("audiobook",)),
                   catalog_book("wrong-theme", moods=("funny",), styles=("graphic_novel",), formats=("ebook",), themes=("space",))]
        result = self.picks(catalog, mood="funny", style="graphic_novel", format="ebook", theme="dragons")
        self.assertEqual([book["id"] for book in result["results"]], [wanted["id"]])

    def test_length_boundaries_and_unknown_lengths(self):
        catalog = [catalog_book(f"pages-{pages}", page_count=pages) for pages in (None, 200, 201, 349, 350)]
        for length, expected in (("short", {"pages-200"}), ("medium", {"pages-201", "pages-349"}), ("long", {"pages-350"})):
            with self.subTest(length=length):
                result = self.picks(catalog, length=length)
                self.assertEqual({book["id"] for book in result["results"]}, expected)

    def test_search_uses_title_author_and_curated_tags(self):
        catalog = [catalog_book("ocean-story", author="Morgan Writer", themes=("nature",), styles=("short_chapters",)), catalog_book("dragon-book")]
        for query in ("OCEAN", "morgan writer", "nature", "short chapters"):
            with self.subTest(query=query):
                result = self.picks(catalog, q=query)
                self.assertEqual([book["id"] for book in result["results"]], ["ocean-story"])

    def test_read_alikes_rank_specific_shared_themes_above_broad_topics(self):
        anchor = catalog_book("my-favorite", themes=("dragons", "family"))
        closer = catalog_book("dragon-friends", themes=("dragons", "family"))
        broader = catalog_book("other-fantasy", themes=("magic",))
        result = self.picks([anchor, broader, closer], similar_to=anchor["id"])
        self.assertEqual(result["results"][0]["id"], closer["id"])
        self.assertNotIn(anchor["id"], {book["id"] for book in result["results"]})
        self.assertEqual(result["results"][0]["reason_kind"], "similar")
        self.assertIn(anchor["title"], result["results"][0]["reason"])
        self.assertIn("dragons", result["results"][0]["reason"])

    def test_series_offers_only_the_next_volume_after_finishing(self):
        series = [catalog_book(f"volume-{position}", series={"id": "dragon-series", "title": "Dragon Series", "position": position}) for position in range(1, 4)]
        self.shelf(series[0], status="reading")
        result = self.picks(series + [catalog_book("another-story")])
        self.assertTrue({"volume-2", "volume-3"}.isdisjoint(book["id"] for book in result["results"]))
        ReadingBook.objects.filter(user=self.reader).update(status="finished")
        result = self.picks(series + [catalog_book("another-story")])
        self.assertEqual(result["results"][0]["id"], "volume-2")
        self.assertEqual(result["results"][0]["reason_kind"], "series")
        self.assertNotIn("volume-3", {book["id"] for book in result["results"]})
        self.shelf(series[1])
        result = self.picks(series)
        self.assertEqual([book["id"] for book in result["results"]], ["volume-3"])

    def test_series_never_skips_an_unfinished_or_missing_earlier_volume(self):
        series = [catalog_book(f"part-{position}", series={"id": "series", "title": "Series", "position": position}) for position in range(1, 4)]
        self.shelf(series[1])
        result = self.picks(series)
        self.assertEqual([book["id"] for book in result["results"]], ["part-1"])
        self.assertEqual(self.picks(series[2:])["results"], [])

    def test_rotation_exposes_other_matching_books_deterministically(self):
        catalog = [catalog_book(f"choice-{number}") for number in range(13)]
        first = self.picks(catalog)
        following = self.picks(catalog, rotation=1)
        self.assertEqual(following, self.picks(catalog, rotation=1))
        self.assertTrue({book["id"] for book in first["results"]}.isdisjoint(book["id"] for book in following["results"]))
        self.assertEqual(first["total"], 13)
        self.assertTrue(first["has_more"])
        self.assertEqual(following["rotation"], 1)

    def test_default_feed_reserves_an_unfamiliar_topic_without_changing_explicit_filters(self):
        catalog = [catalog_book(f"fantasy-{number}") for number in range(7)] + [catalog_book("science-surprise", interests=("science",), themes=("space",))]
        self.shelf(catalog_book("already-loved-fantasy"))
        result = self.picks(catalog)
        surprise = next(book for book in result["results"] if book["id"] == "science-surprise")
        self.assertEqual(surprise["reason_kind"], "surprise")
        filtered = self.picks(catalog, interest="fantasy")
        self.assertTrue(all("fantasy" in book["interests"] for book in filtered["results"]))

    def test_expanded_filters_keep_age_and_owned_title_boundaries(self):
        owned = catalog_book("already-owned")
        self.shelf(owned, status="want_to_read")
        catalog = [owned, catalog_book("older-reader", age_min=14), catalog_book("younger-reader", age_max=8), catalog_book("appropriate")]
        result = self.picks(catalog, mood="exciting", rotation=1000)
        self.assertEqual([book["id"] for book in result["results"]], ["appropriate"])

    def test_feedback_excludes_only_this_readers_choices(self):
        from apps.reading.models import ReadingDiscoveryFeedback

        catalog = [catalog_book("hidden"), catalog_book("already-read"), catalog_book("sibling-hidden"), catalog_book("visible")]
        ReadingDiscoveryFeedback.objects.create(user=self.reader, catalog_id="hidden", choice="not_interested")
        ReadingDiscoveryFeedback.objects.create(user=self.reader, catalog_id="already-read", choice="already_read")
        ReadingDiscoveryFeedback.objects.create(user=self.sibling, catalog_id="sibling-hidden", choice="not_interested")
        result = self.picks(catalog)
        self.assertEqual({book["id"] for book in result["results"]}, {"sibling-hidden", "visible"})

    def test_catalog_matching_accepts_legacy_blank_author_only_for_unique_title(self):
        from apps.reading.recommendations import catalog_entry_for_book

        entry = catalog_book("a-known-book")
        with patch("apps.reading.recommendations.BOOK_CATALOG", (entry,)):
            self.assertEqual(catalog_entry_for_book({"title": "  A KNOWN   BOOK ", "author": "an author"})["id"], entry["id"])
            self.assertEqual(catalog_entry_for_book({"title": entry["title"], "author": ""})["id"], entry["id"])
            self.assertIsNone(catalog_entry_for_book({"title": entry["title"], "author": "Different author"}))
        with patch("apps.reading.recommendations.BOOK_CATALOG", (entry, {**entry, "id": "other", "author": "Different author"})):
            self.assertIsNone(catalog_entry_for_book({"title": entry["title"], "author": ""}))
