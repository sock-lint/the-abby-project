"""Pins the Forge's Celery tasks. Nothing here opens a socket.

Invariants this file exists to protect:

1. Enrichment runs *after* the child has already submitted, so it fills gaps
   rather than overwriting: a placeholder title is replaced, a title the
   child typed is not.
2. Thumbnails are copied into our own storage because model hosts rotate CDN
   URLs and a card that only ever pointed at the remote og:image goes blank
   weeks later.
3. Caching a thumbnail is best effort and defensive: an oversize body, a
   non-image content type, an HTTP error or a blocked (SSRF-guarded) URL all
   leave the remote URL standing instead of storing junk.
4. ``reconcile_stale_jobs`` is the backstop for a printer that simply
   vanished. The listener closes jobs on a ``gcode_state`` transition, which
   never arrives after a power cut — so a request would stick in ``printing``
   forever. Such a job closes as **unknown**, never ``failed``: we genuinely
   do not know whether it finished.

Outbound HTTP is patched at the SSRF-guarded wrapper
(``config.url_safety.safe_get``, which ``tasks.py`` imports inside the task
body), never at ``requests``.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.printing.constants import STALE_JOB_MINUTES
from apps.printing.metadata import LinkMetadata
from apps.printing.models import (
    PrintBudgetLedger,
    PrinterProfile,
    PrintJob,
    PrintJobEvent,
    PrintRequest,
)
from apps.printing.services import PrintRequestService
from apps.printing.tasks import (
    MAX_THUMBNAIL_BYTES,
    cache_request_thumbnail,
    enrich_request_metadata,
    reconcile_stale_jobs,
)
from config.tests.factories import make_family

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100


class FakeResponse:
    """The shape ``config.url_safety.safe_get`` hands back, minus the socket."""

    def __init__(self, content=b"", status_code=200, content_type="image/jpeg"):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class _Fixture(TestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )
        self.parent = self.household.parents[0]
        self.child = self.household.children[0]

    def submit(self, *, title="Untitled print", source_url="", **kwargs):
        return PrintRequestService.create_request(
            self.child,
            title=title,
            reason="because",
            color="red",
            source_kind=PrintRequest.SourceKind.MAKERWORLD,
            source_url=source_url,
            **kwargs,
        )


class EnrichRequestMetadataTests(_Fixture):
    def setUp(self):
        super().setUp()
        # The follow-on thumbnail task runs eagerly in tests; keep it offline.
        patcher = mock.patch(
            "config.url_safety.safe_get",
            side_effect=RuntimeError("no network in tests"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def scraped(self, **overrides):
        meta = LinkMetadata(
            title="Articulated Dragon",
            thumbnail_url="https://cdn.example.com/dragon.jpg",
            author="MakerWorld",
            source_kind=PrintRequest.SourceKind.MAKERWORLD,
        )
        for key, value in overrides.items():
            setattr(meta, key, value)
        return mock.patch(
            "apps.printing.metadata.fetch_link_metadata", return_value=meta,
        )

    def test_a_placeholder_title_is_replaced_by_the_scraped_one(self):
        request = self.submit(
            title="", source_url="https://makerworld.com/en/models/1",
        )
        self.assertEqual(request.title, "Untitled print")
        with self.scraped():
            enrich_request_metadata(request.pk)
        request.refresh_from_db()
        self.assertEqual(request.title, "Articulated Dragon")

    def test_a_title_the_child_typed_is_never_overwritten(self):
        request = self.submit(
            title="My dragon", source_url="https://makerworld.com/en/models/1",
        )
        with self.scraped():
            enrich_request_metadata(request.pk)
        request.refresh_from_db()
        self.assertEqual(request.title, "My dragon")

    def test_the_thumbnail_url_and_author_are_filled_in(self):
        request = self.submit(source_url="https://makerworld.com/en/models/1")
        with self.scraped():
            enrich_request_metadata(request.pk)
        request.refresh_from_db()
        self.assertEqual(request.thumbnail_url, "https://cdn.example.com/dragon.jpg")
        self.assertEqual(request.source_author, "MakerWorld")

    def test_an_author_the_submitter_supplied_is_not_overwritten(self):
        request = self.submit(
            source_url="https://makerworld.com/en/models/1",
            source_author="Someone Else",
        )
        with self.scraped():
            enrich_request_metadata(request.pk)
        request.refresh_from_db()
        self.assertEqual(request.source_author, "Someone Else")

    def test_the_source_kind_is_corrected_from_the_resolved_host(self):
        request = self.submit(source_url="https://www.printables.com/model/1-dragon")
        with self.scraped(source_kind=PrintRequest.SourceKind.PRINTABLES):
            enrich_request_metadata(request.pk)
        request.refresh_from_db()
        self.assertEqual(request.source_kind, PrintRequest.SourceKind.PRINTABLES)

    def test_a_request_with_no_link_is_skipped(self):
        request = self.submit(title="Hand modelled")
        self.assertEqual(enrich_request_metadata(request.pk), "no source url")

    def test_a_deleted_request_is_not_an_error(self):
        self.assertIn("gone", enrich_request_metadata(9999))


class CacheRequestThumbnailTests(_Fixture):
    def setUp(self):
        super().setUp()
        # A throwaway MEDIA_ROOT per test so a cached thumbnail never lands in
        # the working tree. Storage is already pinned to FileSystemStorage for
        # test runs in config/settings.py, so nothing reaches for Ceph.
        media_root = tempfile.mkdtemp(prefix="abby-printing-tests-")
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        overrider = override_settings(MEDIA_ROOT=media_root)
        overrider.enable()
        self.addCleanup(overrider.disable)

        self.request = self.submit(
            title="Dragon", source_url="https://makerworld.com/en/models/1",
        )
        self.request.thumbnail_url = "https://cdn.example.com/dragon.jpg"
        self.request.save(update_fields=["thumbnail_url"])

    def fetch_returns(self, response):
        return mock.patch("config.url_safety.safe_get", return_value=response)

    def test_a_small_image_is_copied_into_our_own_storage(self):
        with self.fetch_returns(FakeResponse(JPEG_BYTES)):
            result = cache_request_thumbnail(self.request.pk)
        self.assertIn("cached thumbnail", result)
        self.request.refresh_from_db()
        self.assertTrue(self.request.thumbnail)
        self.assertIn("dragon.jpg", self.request.thumbnail.name)
        self.assertEqual(self.request.thumbnail.read(), JPEG_BYTES)
        # The remote URL is kept as provenance, not replaced.
        self.assertEqual(
            self.request.thumbnail_url, "https://cdn.example.com/dragon.jpg",
        )

    def test_an_oversize_body_is_refused(self):
        huge = FakeResponse(b"\xff" * (MAX_THUMBNAIL_BYTES + 1))
        with self.fetch_returns(huge):
            result = cache_request_thumbnail(self.request.pk)
        self.assertEqual(result, "not a usable image")
        self.request.refresh_from_db()
        self.assertFalse(self.request.thumbnail)

    def test_a_non_image_response_is_refused(self):
        with self.fetch_returns(FakeResponse(b"<html>nope</html>",
                                             content_type="text/html")):
            result = cache_request_thumbnail(self.request.pk)
        self.assertEqual(result, "not an image")
        self.request.refresh_from_db()
        self.assertFalse(self.request.thumbnail)

    def test_an_empty_body_is_refused(self):
        with self.fetch_returns(FakeResponse(b"")):
            self.assertEqual(
                cache_request_thumbnail(self.request.pk), "not a usable image",
            )

    def test_an_http_error_leaves_the_remote_url_standing(self):
        with self.fetch_returns(FakeResponse(JPEG_BYTES, status_code=404)):
            self.assertEqual(cache_request_thumbnail(self.request.pk), "http 404")
        self.request.refresh_from_db()
        self.assertFalse(self.request.thumbnail)
        self.assertTrue(self.request.thumbnail_url)

    def test_a_blocked_url_is_reported_as_unsafe_not_as_a_crash(self):
        from config.url_safety import UnsafeURLError

        with mock.patch(
            "config.url_safety.safe_get",
            side_effect=UnsafeURLError("resolves to a private address"),
        ):
            self.assertEqual(cache_request_thumbnail(self.request.pk), "unsafe url")

    def test_a_transport_failure_is_soft(self):
        with mock.patch(
            "config.url_safety.safe_get", side_effect=RuntimeError("connection reset"),
        ):
            self.assertEqual(cache_request_thumbnail(self.request.pk), "fetch failed")

    def test_an_already_cached_thumbnail_is_not_refetched(self):
        with self.fetch_returns(FakeResponse(JPEG_BYTES)):
            cache_request_thumbnail(self.request.pk)
        with mock.patch("config.url_safety.safe_get") as safe_get:
            self.assertEqual(
                cache_request_thumbnail(self.request.pk), "nothing to cache",
            )
        safe_get.assert_not_called()

    def test_a_request_with_no_thumbnail_url_is_skipped(self):
        bare = self.submit(title="No picture")
        self.assertEqual(cache_request_thumbnail(bare.pk), "nothing to cache")


class ReconcileStaleJobsTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.printer = PrinterProfile.objects.create(
            family=self.household.family, name="Garage X1C",
            serial="00M09A000000001", host="192.168.1.50",
        )
        self.request = PrintRequestService.approve(
            self.submit(title="Dragon"),
            self.parent,
            estimated_grams=Decimal("100.00"),
        )
        self.request.status = PrintRequest.Status.PRINTING
        self.request.save(update_fields=["status"])

    def make_job(self, *, minutes_ago, request=None, last_report=True):
        when = timezone.now() - timedelta(minutes=minutes_ago)
        return PrintJob.objects.create(
            printer=self.printer,
            request=request,
            user=request.user if request else None,
            subtask_name="req-0001-dragon",
            normalized_name="req-0001-dragon",
            state=PrintJob.State.RUNNING,
            layer_num=50,
            total_layer_num=100,
            started_at=when,
            last_report_at=when if last_report else None,
        )

    def test_a_silent_job_is_closed_as_unknown_not_failed(self):
        job = self.make_job(minutes_ago=STALE_JOB_MINUTES + 10, request=self.request)
        self.assertIn("closed 1", reconcile_stale_jobs())
        job.refresh_from_db()
        self.assertEqual(job.state, PrintJob.State.UNKNOWN)
        self.assertIsNotNone(job.finished_at)
        self.assertIn("stopped reporting", job.failure_reason)

    def test_a_silent_job_closes_out_its_request_and_debits_the_budget(self):
        job = self.make_job(minutes_ago=STALE_JOB_MINUTES + 10, request=self.request)
        reconcile_stale_jobs()
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, PrintRequest.Status.FAILED)
        job.refresh_from_db()
        # Half the layers were laid down, so half the estimate is debited.
        self.assertEqual(job.grams_debited, Decimal("50.00"))
        entry = PrintBudgetLedger.objects.get(user=self.child)
        self.assertEqual(entry.reason, PrintBudgetLedger.Reason.PRINT_FAILED)

    def test_the_timeline_records_why_the_job_was_closed(self):
        job = self.make_job(minutes_ago=STALE_JOB_MINUTES + 10, request=self.request)
        reconcile_stale_jobs()
        event = job.events.filter(kind=PrintJobEvent.Kind.FAILED).get()
        self.assertEqual(event.context["reason"], "stale")
        self.assertEqual(event.context["cutoff_minutes"], STALE_JOB_MINUTES)

    def test_a_job_that_never_reported_at_all_is_still_closed(self):
        job = self.make_job(
            minutes_ago=STALE_JOB_MINUTES + 10, request=self.request,
            last_report=False,
        )
        reconcile_stale_jobs()
        job.refresh_from_db()
        self.assertEqual(job.state, PrintJob.State.UNKNOWN)

    def test_a_job_still_reporting_is_left_alone(self):
        job = self.make_job(minutes_ago=5, request=self.request)
        self.assertIn("closed 0", reconcile_stale_jobs())
        job.refresh_from_db()
        self.assertEqual(job.state, PrintJob.State.RUNNING)
        self.assertIsNone(job.finished_at)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, PrintRequest.Status.PRINTING)

    def test_an_unlinked_stale_job_closes_without_a_ledger_row(self):
        job = self.make_job(minutes_ago=STALE_JOB_MINUTES + 10)
        reconcile_stale_jobs()
        job.refresh_from_db()
        self.assertEqual(job.state, PrintJob.State.UNKNOWN)
        self.assertIsNone(job.grams_debited)
        self.assertFalse(PrintBudgetLedger.objects.exists())

    def test_an_already_closed_job_is_not_reprocessed(self):
        job = self.make_job(minutes_ago=STALE_JOB_MINUTES + 10, request=self.request)
        job.finished_at = timezone.now()
        job.state = PrintJob.State.FINISHED
        job.save(update_fields=["finished_at", "state"])
        self.assertIn("closed 0", reconcile_stale_jobs())
        job.refresh_from_db()
        self.assertEqual(job.state, PrintJob.State.FINISHED)
