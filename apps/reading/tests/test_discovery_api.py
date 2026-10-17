from datetime import date
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from config.tests.factories import make_family

from apps.reading.catalog import BOOK_CATALOG
from apps.reading.models import (
    ReadingBook, ReadingDailyReward, ReadingDiscoveryFeedback,
    ReadingFamilySuggestion, ReadingRewardCredit, ReadingSession,
)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingDiscoveryAPITests(TestCase):
    feedback_url = "/api/reading/discovery-feedback/"
    suggestions_url = "/api/reading-family-suggestions/"
    recommendations_url = "/api/reading/recommendations/"

    def setUp(self):
        family = make_family(
            "Discovery family",
            parents=[{"username": "discovery-parent", "display_name": "Parent Morgan"},
                     {"username": "discovery-coparent", "display_name": "Parent Sam"}],
            children=[{"username": "discovery-child", "date_of_birth": date(2016, 1, 1)},
                      {"username": "discovery-sibling"}],
        )
        other = make_family(
            "Other discovery family",
            parents=[{"username": "outside-parent", "display_name": "Private outside name"}],
            children=[{"username": "outside-child"}],
        )
        self.parent, self.coparent = family.parents
        self.child, self.sibling = family.children
        self.outside_parent, self.outside_child = other.parents[0], other.children[0]
        self.catalog_entry = next(entry for entry in BOOK_CATALOG if entry["id"] == "the-wild-robot")
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def test_discovery_feedback_and_family_suggestions_require_authentication(self):
        self.client.force_authenticate(None)
        for url in (self.feedback_url, self.suggestions_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)
                self.assertEqual(self.client.post(url, {}, format="json").status_code, 401)

    def feedback(self, **extra):
        return self.client.post(self.feedback_url, {
            "catalog_id": "the-wild-robot", "choice": "not_interested", **extra,
        }, format="json")

    def suggest(self, **extra):
        return self.client.post(self.suggestions_url, {
            "catalog_id": "the-wild-robot", "message": "The robot learns from the animals!",
            "client_request_id": str(uuid4()), "user_id": self.child.id, **extra,
        }, format="json")

    def saved_suggestion(self, *, user=None, author=None, **extra):
        author = author or self.parent
        return ReadingFamilySuggestion.objects.create(
            user=user or self.child, suggested_by=author, author_name=author.display_name,
            catalog_id="the-wild-robot", client_request_id=uuid4(), create_payload={}, **extra,
        )

    def test_feedback_is_idempotent_can_change_and_clear_without_making_reading_history(self):
        for _ in range(2):
            response = self.feedback()
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data, {"catalog_id": "the-wild-robot", "choice": "not_interested"})
        self.assertEqual(ReadingDiscoveryFeedback.objects.filter(user=self.child).count(), 1)
        response = self.feedback(choice="already_read")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ReadingDiscoveryFeedback.objects.get(user=self.child).choice, "already_read")
        listing = self.client.get(self.feedback_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["results"], [{"catalog_id": "the-wild-robot", "choice": "already_read"}])
        for _ in range(2):
            response = self.feedback(choice="")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["choice"], "")
        self.assertFalse(ReadingDiscoveryFeedback.objects.exists())
        self.assertFalse(ReadingBook.objects.exists())
        self.assertFalse(ReadingSession.objects.exists())

    def test_feedback_is_reader_scoped_for_reads_writes_and_recommendations(self):
        ReadingDiscoveryFeedback.objects.create(user=self.sibling, catalog_id="the-wild-robot", choice="already_read")
        self.assertEqual(self.client.get(self.feedback_url).data["results"], [])
        for target in (self.sibling, self.outside_child):
            with self.subTest(target=target.id):
                self.assertIn(self.feedback(user_id=target.id).status_code, (400, 404))
                self.assertIn(self.client.get(self.feedback_url, {"user_id": target.id}).status_code, (400, 404))
        self.assertEqual(self.feedback().status_code, 200)
        response = self.client.get(self.recommendations_url, {"q": "The Wild Robot"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("the-wild-robot", {entry["id"] for entry in response.data["results"]})
        self.assertEqual(ReadingDiscoveryFeedback.objects.filter(user=self.sibling).count(), 1)

    def test_parent_feedback_requires_explicit_same_family_child(self):
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(self.feedback_url).status_code, 400)
        self.assertEqual(self.feedback().status_code, 400)
        for target in (self.parent, self.outside_child):
            self.assertEqual(self.client.get(self.feedback_url, {"user_id": target.id}).status_code, 404)
            self.assertEqual(self.feedback(user_id=target.id).status_code, 404)
        self.assertEqual(self.feedback(user_id=self.child.id).status_code, 200)
        self.assertEqual(self.client.get(self.feedback_url, {"user_id": self.sibling.id}).data["results"], [])

    def test_feedback_rejects_unknown_catalog_choices_and_fields(self):
        for invalid in (
            {"catalog_id": "unknown-title"}, {"choice": "loved"}, {"choice": None},
            {"catalog_id": []}, {"user": self.sibling.id}, {"reward": 100},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.feedback(**invalid).status_code, 400)
        self.assertFalse(ReadingDiscoveryFeedback.objects.exists())

    def test_family_suggestions_are_parent_authored_invitations(self):
        self.assertEqual(self.suggest().status_code, 403)
        self.client.force_authenticate(self.parent)
        response = self.suggest()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["suggested_by"], {"id": self.parent.id, "display_name": self.parent.display_name})
        self.assertEqual(response.data["catalog_entry"]["id"], "the-wild-robot")
        self.assertEqual(response.data["status"], "pending")
        self.assertFalse(response.data["on_shelf"])
        self.assertFalse(ReadingBook.objects.exists())
        self.client.force_authenticate(self.child)
        listing = self.client.get(self.suggestions_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["id"] for row in listing.data["results"]], [response.data["id"]])

    def test_parent_family_suggestions_require_selected_child_for_lists_and_creates(self):
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(self.suggestions_url).status_code, 400)
        missing_target = self.client.post(self.suggestions_url, {
            "catalog_id": "the-wild-robot", "client_request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(missing_target.status_code, 400)
        for target in (self.parent, self.outside_child):
            self.assertEqual(self.suggest(user_id=target.id).status_code, 404)
            self.assertEqual(self.client.get(self.suggestions_url, {"user_id": target.id}).status_code, 404)
        self.assertEqual(self.suggest(user_id=self.sibling.id).status_code, 201)

    def test_family_suggestions_retries_remain_same_record_after_dismissal(self):
        self.client.force_authenticate(self.parent)
        request_id = str(uuid4())
        first = self.suggest(client_request_id=request_id, message="  A family favorite  ")
        self.assertEqual(first.status_code, 201, first.data)
        retry = self.suggest(client_request_id=request_id, message="A family favorite")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["id"], first.data["id"])
        self.client.force_authenticate(self.child)
        dismissed = self.client.patch(f"{self.suggestions_url}{first.data['id']}/", {"status": "dismissed"}, format="json")
        self.assertEqual(dismissed.status_code, 200, dismissed.data)
        self.client.force_authenticate(self.parent)
        retry = self.suggest(client_request_id=request_id, message="A family favorite")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["status"], "dismissed")
        self.assertEqual(ReadingFamilySuggestion.objects.count(), 1)

    def test_family_suggestion_uuid_reuse_rejects_changed_message_catalog_and_parent(self):
        self.client.force_authenticate(self.parent)
        request_id = str(uuid4())
        first = self.suggest(client_request_id=request_id)
        self.assertEqual(first.status_code, 201, first.data)
        other_catalog_id = next(entry["id"] for entry in BOOK_CATALOG if entry["id"] != "the-wild-robot")
        for changes in ({"message": "Different words"}, {"catalog_id": other_catalog_id}):
            with self.subTest(changes=changes):
                self.assertEqual(self.suggest(client_request_id=request_id, **changes).status_code, 400)
        self.client.force_authenticate(self.coparent)
        self.assertEqual(self.suggest(client_request_id=request_id).status_code, 400)
        self.assertEqual(ReadingFamilySuggestion.objects.count(), 1)
        # The UUID belongs to the target reader, so a distinct sibling is safe.
        self.assertEqual(self.suggest(client_request_id=request_id, user_id=self.sibling.id).status_code, 201)

    def test_family_suggestions_reject_unknown_fields_bad_requests_and_long_messages(self):
        self.client.force_authenticate(self.parent)
        for invalid in (
            {"catalog_id": "not-a-catalog-book"}, {"message": "x" * 501},
            {"client_request_id": "invalid"}, {"suggested_by": self.coparent.id},
            {"author_name": "Impersonated"}, {"status": "dismissed"}, {"user": self.sibling.id},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.suggest(**invalid).status_code, 400)
        self.assertFalse(ReadingFamilySuggestion.objects.exists())

    def test_suggestions_allow_dismissal_only_and_preserve_immutable_details(self):
        suggestion = self.saved_suggestion(message="Original message")
        detail_url = f"{self.suggestions_url}{suggestion.id}/"
        for fields in (
            {"message": "Changed"}, {"catalog_id": "eragon"}, {"user_id": self.sibling.id},
            {"suggested_by": self.coparent.id}, {"client_request_id": str(uuid4())}, {"status": "pending"},
        ):
            with self.subTest(fields=fields):
                self.assertEqual(self.client.patch(detail_url, fields, format="json").status_code, 400)
        self.assertEqual(self.client.delete(detail_url).status_code, 405)
        for _ in range(2):
            response = self.client.patch(detail_url, {"status": "dismissed"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.message, "Original message")
        self.assertEqual(suggestion.status, "dismissed")

    def test_suggestions_never_leak_sibling_other_family_or_inconsistent_author_rows(self):
        own = self.saved_suggestion()
        sibling = self.saved_suggestion(user=self.sibling)
        outside = self.saved_suggestion(user=self.outside_child, author=self.outside_parent)
        malformed = self.saved_suggestion(author=self.outside_parent, message="Private foreign note")
        listing = self.client.get(self.suggestions_url)
        self.assertEqual({row["id"] for row in listing.data["results"]}, {own.id})
        self.assertNotIn("Private foreign", str(listing.data))
        for inaccessible in (sibling, outside, malformed):
            detail_url = f"{self.suggestions_url}{inaccessible.id}/"
            self.assertEqual(self.client.get(detail_url).status_code, 404)
            self.assertEqual(self.client.patch(detail_url, {"status": "dismissed"}, format="json").status_code, 404)
        self.client.force_authenticate(self.parent)
        listing = self.client.get(self.suggestions_url, {"user_id": self.child.id})
        self.assertEqual({row["id"] for row in listing.data["results"]}, {own.id})
        self.assertEqual(self.client.get(f"{self.suggestions_url}{outside.id}/").status_code, 404)

    def test_author_attribution_survives_rename_and_parent_removal(self):
        suggestion = self.saved_suggestion()
        saved_name = self.parent.display_name
        self.parent.display_name = "A new display name"
        self.parent.save(update_fields=["display_name"])
        detail_url = f"{self.suggestions_url}{suggestion.id}/"
        self.assertEqual(self.client.get(detail_url).data["suggested_by"]["display_name"], saved_name)
        self.parent.delete()
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["suggested_by"], {"id": None, "display_name": saved_name})

    def test_suggestion_on_shelf_and_book_metadata_use_verified_title_author(self):
        suggestion = self.saved_suggestion()
        detail_url = f"{self.suggestions_url}{suggestion.id}/"
        for title, author, recognized in (
            ("  THE WILD   ROBOT ", " peter brown ", True),
            ("The Wild Robot", "", True),
            ("The Wild Robot", "Different author", False),
            ("An unknown personal book", "Peter Brown", False),
        ):
            with self.subTest(title=title, author=author):
                book = ReadingBook.objects.create(
                    user=self.child, title=title, author=author,
                    client_request_id=uuid4(), create_payload={},
                )
                response = self.client.get(f"/api/reading-books/{book.id}/")
                self.assertEqual(response.status_code, 200, response.data)
                if recognized:
                    self.assertEqual(response.data["catalog_entry"]["id"], "the-wild-robot")
                    for field in ("isbn", "page_count", "formats", "moods", "styles", "themes", "series", "cover_url"):
                        self.assertIn(field, response.data["catalog_entry"])
                else:
                    self.assertIsNone(response.data["catalog_entry"])
                self.assertEqual(self.client.get(detail_url).data["on_shelf"], recognized)
                book.delete()

    def test_discovery_reads_feedback_and_suggestions_never_award_or_log_reading(self):
        from apps.achievements.models import SkillProgress
        from apps.activity.models import ActivityEvent
        from apps.rewards.models import CoinLedger

        tracked = (ReadingBook, ReadingSession, ReadingDailyReward, ReadingRewardCredit, SkillProgress, CoinLedger, ActivityEvent)
        before = {model: model.objects.count() for model in tracked}
        self.assertEqual(self.feedback(choice="already_read").status_code, 200)
        self.client.force_authenticate(self.parent)
        suggested = self.suggest()
        self.assertEqual(suggested.status_code, 201, suggested.data)
        self.client.force_authenticate(self.child)
        for _ in range(2):
            self.assertEqual(self.client.get(self.feedback_url).status_code, 200)
            self.assertEqual(self.client.get(self.suggestions_url).status_code, 200)
            self.assertEqual(self.client.get(self.recommendations_url).status_code, 200)
        self.assertEqual(self.client.patch(f"{self.suggestions_url}{suggested.data['id']}/", {"status": "dismissed"}, format="json").status_code, 200)
        self.assertEqual({model: model.objects.count() for model in tracked}, before)

    def test_recommendations_validate_filters_and_use_book_format_without_renderer_collision(self):
        for invalid in (
            {"interest": "romance"}, {"mood": "angry"}, {"style": "invented"},
            {"book_format": "hardback"}, {"length": "tiny"}, {"theme": "invented"},
            {"similar_to": "unknown-book"}, {"rotation": "1.5"}, {"rotation": "-1"},
            {"rotation": "1001"}, {"rotation": "true"}, {"q": "x" * 161},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.get(self.recommendations_url, invalid).status_code, 400)
        response = self.client.get(self.recommendations_url, {"book_format": "print"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["results"])
        self.assertTrue(all("print" in entry["formats"] for entry in response.data["results"]))
        self.assertIn("total", response.data)
        self.assertIn("has_more", response.data)
        rotated = self.client.get(self.recommendations_url, {"rotation": 1000})
        self.assertEqual(rotated.status_code, 200, rotated.data)
        self.assertEqual(rotated.data["rotation"], 1000)
        similar = self.client.get(self.recommendations_url, {"similar_to": "the-wild-robot"})
        self.assertEqual(similar.status_code, 200, similar.data)
        self.assertTrue(similar.data["results"])
        self.assertTrue(all(entry["reason_kind"] == "similar" for entry in similar.data["results"]))

    def test_recommendations_cannot_be_retargeted_and_do_not_use_reading_notes(self):
        for target in (self.sibling, self.outside_child):
            self.assertIn(self.client.get(self.recommendations_url, {"user_id": target.id}).status_code, (400, 404))
        book = ReadingBook.objects.create(
            user=self.child, title="A personal book", interests=["science"],
            client_request_id=uuid4(), create_payload={},
        )
        log = ReadingSession.objects.create(
            user=self.child, book=book, occurred_on=date.today(), reflection="Private hidden words",
            reaction="liked", client_request_id=uuid4(), create_payload={},
        )
        expected = self.client.get(self.recommendations_url).data
        log.reflection = "Completely different private text about dragons"
        log.save(update_fields=["reflection"])
        actual = self.client.get(self.recommendations_url).data
        self.assertEqual(actual, expected)
        self.assertNotIn("private", str(actual).lower())
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(self.recommendations_url).status_code, 400)
        self.assertEqual(self.client.get(self.recommendations_url, {"user_id": self.outside_child.id}).status_code, 404)
