"""Pins the deterministic-matching contract.

The invariants this file exists to protect:

1. A minted slug always embeds the request's primary key, so it is unique by
   construction and stable across re-prints.
2. Every ``subtask_name`` shape firmware has been observed to emit for the
   same plate normalises to the same key — with or without an extension,
   with a plate suffix, with a copy suffix, with a directory prefix, in any
   separator or case.
3. Matching is an equality check, never a fuzzy score. A name that isn't a
   slug matches nothing.
4. A request in another family can never absorb a print.
5. Rejected and cancelled requests never absorb a print.
"""
from __future__ import annotations

from django.test import TestCase

from config.tests.factories import make_family

from apps.printing.matching import (
    find_request,
    mint_slug,
    normalize_subtask_name,
    plate_filename_for,
    request_id_from_name,
)
from apps.printing.models import PrintRequest


class MintSlugTests(TestCase):
    def test_slug_embeds_zero_padded_id_and_slugified_title(self):
        self.assertEqual(mint_slug(42, "Articulated Dragon"), "req-0042-articulated-dragon")

    def test_slug_survives_punctuation_and_case(self):
        self.assertEqual(mint_slug(7, "Baby Yoda!! (v2)"), "req-0007-baby-yoda-v2")

    def test_untitleable_title_still_produces_an_id_bearing_slug(self):
        # Emoji-only / CJK titles slugify to nothing. The id half is what
        # actually identifies the request, so the slug must still be usable.
        self.assertEqual(mint_slug(3, "🐉🐉🐉"), "req-0003-print")

    def test_long_titles_are_truncated_without_a_trailing_hyphen(self):
        slug = mint_slug(1, "a" * 200)
        self.assertTrue(slug.startswith("req-0001-"))
        self.assertFalse(slug.endswith("-"))
        self.assertLessEqual(len(slug), 80)

    def test_ids_beyond_the_pad_width_are_not_truncated(self):
        self.assertEqual(mint_slug(123456, "Thing"), "req-123456-thing")

    def test_plate_filename_appends_the_3mf_extension(self):
        self.assertEqual(plate_filename_for("req-0042-dragon"), "req-0042-dragon.3mf")


class NormalizeSubtaskNameTests(TestCase):
    """Every shape below is one the printer has been seen to report."""

    def test_bare_name_is_already_normal(self):
        self.assertEqual(normalize_subtask_name("req-0042-dragon"), "req-0042-dragon")

    def test_strips_3mf(self):
        self.assertEqual(normalize_subtask_name("req-0042-dragon.3mf"), "req-0042-dragon")

    def test_strips_stacked_gcode_3mf(self):
        self.assertEqual(
            normalize_subtask_name("req-0042-dragon.gcode.3mf"), "req-0042-dragon",
        )

    def test_strips_bare_gcode(self):
        self.assertEqual(
            normalize_subtask_name("req-0042-dragon.gcode"), "req-0042-dragon",
        )

    def test_strips_stl(self):
        self.assertEqual(normalize_subtask_name("req-0042-dragon.stl"), "req-0042-dragon")

    def test_strips_a_leading_directory(self):
        self.assertEqual(
            normalize_subtask_name("/cache/req-0042-dragon.3mf"), "req-0042-dragon",
        )

    def test_strips_a_windows_directory(self):
        self.assertEqual(
            normalize_subtask_name(r"C:\\plates\\req-0042-dragon.3mf"), "req-0042-dragon",
        )

    def test_strips_studios_single_plate_suffix(self):
        for raw in (
            "req-0042-dragon_plate_1",
            "req-0042-dragon-plate-1",
            "req-0042-dragon plate 2",
            "req-0042-dragon_plate1",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_subtask_name(raw), "req-0042-dragon")

    def test_strips_a_file_picker_copy_suffix(self):
        self.assertEqual(normalize_subtask_name("req-0042-dragon(1)"), "req-0042-dragon")
        self.assertEqual(
            normalize_subtask_name("req-0042-dragon (2).3mf"), "req-0042-dragon",
        )

    def test_unifies_case_and_separators(self):
        self.assertEqual(
            normalize_subtask_name("REQ_0042_Dragon.3MF"), "req-0042-dragon",
        )

    def test_empty_input_is_empty_not_a_wildcard(self):
        self.assertEqual(normalize_subtask_name(""), "")
        self.assertEqual(normalize_subtask_name(None), "")
        self.assertEqual(normalize_subtask_name("   "), "")

    def test_all_observed_shapes_of_one_plate_collapse_to_one_key(self):
        variants = [
            "req-0042-dragon",
            "req-0042-dragon.3mf",
            "req-0042-dragon.gcode.3mf",
            "/data/req-0042-dragon.3mf",
            "req-0042-dragon_plate_1",
            "REQ-0042-DRAGON (1).3mf",
        ]
        keys = {normalize_subtask_name(v) for v in variants}
        self.assertEqual(keys, {"req-0042-dragon"})


class RequestIdFromNameTests(TestCase):
    def test_extracts_the_id_from_a_padded_slug(self):
        self.assertEqual(request_id_from_name("req-0042-dragon"), 42)

    def test_extracts_the_id_from_an_unpadded_slug(self):
        self.assertEqual(request_id_from_name("req-42-dragon"), 42)

    def test_extracts_from_a_bare_prefix(self):
        self.assertEqual(request_id_from_name("req-0042"), 42)

    def test_returns_none_for_a_non_slug(self):
        self.assertIsNone(request_id_from_name("clamshell-parts-box"))
        self.assertIsNone(request_id_from_name(""))


class FindRequestTests(TestCase):
    def setUp(self):
        self.alpha = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_kid"}],
        )
        self.beta = make_family(
            "Beta",
            parents=[{"username": "beta_parent"}],
            children=[{"username": "beta_kid"}],
        )
        self.request = PrintRequest.objects.create(
            user=self.alpha.children[0],
            title="Dragon",
            reason="It is cool",
            color="red",
            status=PrintRequest.Status.APPROVED,
        )
        self.request.slug = mint_slug(self.request.pk, self.request.title)
        self.request.plate_filename = plate_filename_for(self.request.slug)
        self.request.save(update_fields=["slug", "plate_filename"])

    def test_exact_slug_matches(self):
        found = find_request(self.request.slug, family=self.alpha.family)
        self.assertEqual(found, self.request)

    def test_matches_through_normalisation_of_the_reported_name(self):
        reported = f"{self.request.plate_filename}"
        found = find_request(
            normalize_subtask_name(reported), family=self.alpha.family,
        )
        self.assertEqual(found, self.request)

    def test_id_prefix_still_matches_when_the_title_half_was_retyped(self):
        found = find_request(
            f"req-{self.request.pk:04d}-something-else", family=self.alpha.family,
        )
        self.assertEqual(found, self.request)

    def test_unrelated_name_matches_nothing(self):
        self.assertIsNone(
            find_request("clamshell-parts-box", family=self.alpha.family),
        )

    def test_empty_name_matches_nothing(self):
        self.assertIsNone(find_request("", family=self.alpha.family))

    def test_another_familys_printer_cannot_bind_to_this_request(self):
        self.assertIsNone(
            find_request(self.request.slug, family=self.beta.family),
        )

    def test_rejected_requests_never_absorb_a_print(self):
        self.request.status = PrintRequest.Status.REJECTED
        self.request.save(update_fields=["status"])
        self.assertIsNone(find_request(self.request.slug, family=self.alpha.family))

    def test_cancelled_requests_never_absorb_a_print(self):
        self.request.status = PrintRequest.Status.CANCELLED
        self.request.save(update_fields=["status"])
        self.assertIsNone(find_request(self.request.slug, family=self.alpha.family))

    def test_failed_requests_rebind_so_a_reprint_needs_no_re_approval(self):
        self.request.status = PrintRequest.Status.FAILED
        self.request.save(update_fields=["status"])
        self.assertEqual(
            find_request(self.request.slug, family=self.alpha.family), self.request,
        )

    def test_pending_requests_do_not_bind(self):
        # A plate can't legitimately be printing before it was approved, and
        # binding one would skip the budget check entirely.
        pending = PrintRequest.objects.create(
            user=self.alpha.children[0],
            title="Not yet",
            reason="soon",
            color="blue",
            status=PrintRequest.Status.PENDING,
            slug="req-9999-not-yet",
        )
        self.assertIsNone(find_request(pending.slug, family=self.alpha.family))

    def test_blank_slugs_do_not_collide(self):
        # Many pending requests sit at slug="" — the partial unique constraint
        # allows that, and an empty normalised name must not match any of them.
        PrintRequest.objects.create(
            user=self.alpha.children[0], title="A", reason="r", color="c",
        )
        PrintRequest.objects.create(
            user=self.alpha.children[0], title="B", reason="r", color="c",
        )
        self.assertIsNone(find_request("", family=self.alpha.family))
