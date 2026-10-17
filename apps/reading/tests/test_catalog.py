from collections import defaultdict
from urllib.parse import urlparse

from django.test import SimpleTestCase

from apps.reading.catalog import BOOK_CATALOG
from apps.reading.catalog_data import CATALOG_DETAILS
from apps.reading.constants import (
    DISCOVERY_FORMATS,
    DISCOVERY_MOODS,
    DISCOVERY_STYLES,
    DISCOVERY_THEMES,
    INTERESTS,
)


class ReadingDiscoveryCatalogTests(SimpleTestCase):
    def test_editions_have_valid_isbns_and_explicit_unknown_page_counts(self):
        self.assertGreaterEqual(len(BOOK_CATALOG), 60)
        self.assertEqual(len(BOOK_CATALOG), len({book["id"] for book in BOOK_CATALOG}))
        self.assertEqual(set(CATALOG_DETAILS), {book["id"] for book in BOOK_CATALOG})
        for book in BOOK_CATALOG:
            with self.subTest(book=book["id"]):
                isbn = book["isbn"]
                self.assertRegex(isbn, r"^97[89]\d{10}$")
                self.assertEqual(
                    sum(int(digit) * (1 if index % 2 == 0 else 3)
                        for index, digit in enumerate(isbn)) % 10,
                    0,
                    "ISBN checksum must match the sourced edition",
                )
                pages = book["page_count"]
                self.assertTrue(pages is None or type(pages) is int and pages > 0)
                self.assertEqual(
                    book["cover_url"],
                    f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false",
                )
        editions = {book["id"]: book for book in BOOK_CATALOG}
        # Print and ebook editions can have different page counts. These are
        # the particular publisher-listed editions, not generic work lengths.
        self.assertEqual(editions["roller-girl"]["page_count"], 256)
        self.assertEqual(editions["eragon"]["page_count"], 528)
        self.assertIsNone(editions["blazewrath-games"]["page_count"])

    def test_discovery_tags_and_sources_are_bounded_and_reviewable(self):
        publishers = {
            "www.penguinrandomhouse.com", "assets.penguinrandomhouse.com",
            "www.hachettebookgroup.com", "books.disney.com",
            "us.macmillan.com", "macmillanlibrary.com",
        }
        for book in BOOK_CATALOG:
            with self.subTest(book=book["id"]):
                self.assertTrue(book["formats"])
                self.assertTrue(book["moods"])
                for field, allowed in (
                    ("interests", INTERESTS), ("formats", DISCOVERY_FORMATS),
                    ("moods", DISCOVERY_MOODS), ("styles", DISCOVERY_STYLES),
                    ("themes", DISCOVERY_THEMES),
                ):
                    self.assertEqual(len(book[field]), len(set(book[field])))
                    self.assertLessEqual(set(book[field]), set(allowed))
                self.assertLessEqual(len(book["description"]), 180)
                self.assertIn(book["source_url"], book["source_urls"])
                for url in book["source_urls"]:
                    source = urlparse(url)
                    self.assertEqual(source.scheme, "https")
                    self.assertIn(source.hostname, publishers)
                    self.assertIsNone(source.username)
                    self.assertIsNone(source.password)

    def test_ordered_series_offer_adjacent_volumes_for_several_age_groups(self):
        series = defaultdict(list)
        for book in BOOK_CATALOG:
            if book["series"]:
                series[book["series"]["id"]].append(book)
        for series_id in ("wild-robot", "percy-jackson", "magic-tree-house", "inheritance-cycle"):
            with self.subTest(series=series_id):
                volumes = sorted(series[series_id], key=lambda book: book["series"]["position"])
                self.assertEqual([book["series"]["position"] for book in volumes], [1, 2, 3])
                self.assertEqual(len({book["author"] for book in volumes}), 1)
                self.assertEqual(len({book["series"]["title"] for book in volumes}), 1)
                self.assertEqual(len({(book["age_min"], book["age_max"]) for book in volumes}), 1)

    def test_expansion_includes_nonfiction_comics_verse_and_contemporary_stories(self):
        books = {book["id"]: book for book in BOOK_CATALOG}
        self.assertGreaterEqual(sum("graphic_novel" in b["styles"] for b in books.values()), 6)
        self.assertGreaterEqual(sum("verse" in b["styles"] for b in books.values()), 5)
        for book_id in (
            "the-watcher", "who-was-marie-curie", "who-was-albert-einstein",
            "what-is-nasa", "where-is-our-solar-system", "how-we-got-to-the-moon",
            "the-boy-who-harnessed-the-wind", "the-mona-lisa-vanishes",
        ):
            self.assertTrue({"science", "history"} & set(books[book_id]["interests"]))
        for age in (6, 10, 15):
            eligible = [book for book in books.values()
                        if book["age_min"] <= age and (book["age_max"] is None or age <= book["age_max"])]
            with self.subTest(age=age):
                self.assertTrue(any("fantasy" not in book["interests"] for book in eligible))
                self.assertTrue(any("puzzles" in book["themes"] for book in eligible))
                self.assertTrue(any("family" in book["themes"] for book in eligible))
        self.assertIn("family", books["harbor-me"]["themes"])
        self.assertIn("identity", books["american-born-chinese"]["themes"])
