"""Pins the HMS / print_error decoder. Pure unit tests — no database.

Invariants this file exists to protect:

1. ``hms`` and ``print_error`` are two different namespaces with two
   different encodings. HMS renders as four hex groups from ``(attr, code)``;
   ``print_error`` renders as **two** groups from a single 32-bit int.
2. Severity comes from group 3 and module from the high byte of group 1;
   anything unmapped decodes to ``"unknown"`` rather than raising.
3. An AMS code we don't have text for is retried against its unit- and
   slot-normalised form, and the recovered message names the unit and slot —
   which is how ~250 real faults cover ~2000 published code strings.
4. ``07FF`` is the external spool holder, not AMS unit 255, so it is never
   unit-normalised and it reads as "(external spool)".
5. A total table miss still renders severity + module. The timeline never
   says "unknown error".
6. One malformed entry in the ``hms`` array never costs us the good ones —
   firmware ships odd rows and the listener must not die on them.
7. ``0x0300400C`` (decimal 50348044) is a **normal user cancel**: not
   blocking, not a crash.
8. ``summarize_failure`` prefers the ``print_error`` (the outcome) over the
   HMS array (the symptoms), and otherwise picks the most severe blocker.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.printing.hms import (
    DecodedAlert,
    describe,
    describe_all,
    describe_print_error,
    format_hms_code,
    format_print_error,
    module_of,
    severity_of,
    summarize_failure,
    wiki_url_for,
)
from apps.printing.hms_codes import CANCEL_PRINT_ERROR, WIKI_INDEX_URL

# --- Real code pairs used across the file ---------------------------------
# "0700_2000_0002_0001" — the AMS slot ran out. In the vendored table.
AMS_RANOUT = (0x07002000, 0x00020001)
# The same fault on AMS unit D, slot 3. NOT in the table; must normalise.
AMS_RANOUT_UNIT_D_SLOT_3 = (0x07032200, 0x00020001)
# "07FF_2000_0002_0001" — the external spool holder ran out.
EXTERNAL_SPOOL_RANOUT = (0x07FF2000, 0x00020001)
# "0300_0100_0001_0001" — heated bed fault. Severity 1 (fatal).
BED_HEATER_FAULT = (0x03000100, 0x00010001)
# "0300_1A00_0002_0002" — the nozzle is clogged. Not AMS, so no location suffix.
NOZZLE_CLOGGED = (0x03001A00, 0x00020002)
# "0700_5100_0003_0001" — AMS switched off. Severity 3 (common), not blocking.
AMS_DISABLED = (0x07005100, 0x00030001)
# Nothing in the table starts 0C00_9999.
UNKNOWN_LIDAR_CODE = (0x0C009999, 0x00010042)


class FormatTests(SimpleTestCase):
    def test_format_hms_code_renders_four_groups(self):
        self.assertEqual(format_hms_code(*AMS_RANOUT), "0700_2000_0002_0001")

    def test_format_hms_code_zero_pads_each_group(self):
        self.assertEqual(format_hms_code(0x00000001, 0x00000002), "0000_0001_0000_0002")

    def test_format_print_error_splits_eight_hex_digits_four_and_four(self):
        self.assertEqual(format_print_error(0x0300400C), "0300_400C")

    def test_format_print_error_zero_pads_a_small_value(self):
        # The '0' + hex() shortcut some integrations use only works while the
        # high nibble happens to be zero. Ours pads explicitly.
        self.assertEqual(format_print_error(0x1234), "0000_1234")


class BitFieldTests(SimpleTestCase):
    def test_severity_reads_group_three(self):
        self.assertEqual(severity_of(0x00010000), "fatal")
        self.assertEqual(severity_of(0x00020000), "serious")
        self.assertEqual(severity_of(0x00030000), "common")
        self.assertEqual(severity_of(0x00040000), "info")

    def test_unmapped_severity_is_unknown(self):
        self.assertEqual(severity_of(0x00090000), "unknown")
        self.assertEqual(severity_of(0), "unknown")

    def test_module_reads_the_high_byte_of_group_one(self):
        self.assertEqual(module_of(0x03000000), "Motion controller")
        self.assertEqual(module_of(0x07000000), "AMS")
        self.assertEqual(module_of(0x12000000), "AMS Lite")

    def test_unmapped_module_is_unknown(self):
        self.assertEqual(module_of(0xAB000000), "unknown")


class DescribeTests(SimpleTestCase):
    def test_an_exact_hit_returns_the_vendored_message(self):
        alert = describe(*NOZZLE_CLOGGED)
        self.assertEqual(alert.code, "0300_1A00_0002_0002")
        self.assertEqual(alert.message, "The nozzle is clogged.")
        self.assertEqual(alert.severity, "serious")
        self.assertEqual(alert.module, "Motion controller")
        self.assertTrue(alert.blocking)

    def test_an_exact_ams_hit_still_names_its_unit_and_slot(self):
        # Unit A / slot 1 is the canonical form the table is keyed on, but the
        # suffix is appended unconditionally so the timeline never leaves a
        # parent guessing which slot to open.
        alert = describe(*AMS_RANOUT)
        self.assertEqual(alert.code, "0700_2000_0002_0001")
        self.assertEqual(
            alert.message,
            "The AMS slot ran out of filament. Load a new spool and resume. "
            "(unit A, slot 1)",
        )
        self.assertEqual(alert.module, "AMS")

    def test_an_ams_miss_falls_back_to_the_unit_and_slot_normalised_entry(self):
        alert = describe(*AMS_RANOUT_UNIT_D_SLOT_3)
        self.assertEqual(alert.code, "0703_2200_0002_0001")
        self.assertEqual(
            alert.message,
            "The AMS slot ran out of filament. Load a new spool and resume. "
            "(unit D, slot 3)",
        )

    def test_the_external_spool_is_not_unit_normalised(self):
        alert = describe(*EXTERNAL_SPOOL_RANOUT)
        self.assertEqual(alert.code, "07FF_2000_0002_0001")
        self.assertIn("(external spool)", alert.message)
        self.assertNotIn("unit ", alert.message)

    def test_a_common_severity_alert_is_not_blocking(self):
        alert = describe(*AMS_DISABLED)
        self.assertEqual(alert.severity, "common")
        self.assertFalse(alert.blocking)

    def test_an_unknown_code_still_names_its_severity_and_module(self):
        alert = describe(*UNKNOWN_LIDAR_CODE)
        self.assertIn("Micro Lidar camera", alert.message)
        self.assertIn("fatal", alert.message)
        self.assertIn("0C00_9999_0001_0042", alert.message)
        self.assertNotIn("unknown error", alert.message.lower())
        self.assertEqual(alert.severity, "fatal")

    def test_the_raw_ints_survive_for_offline_table_extension(self):
        alert = describe(*AMS_RANOUT)
        self.assertEqual(alert.raw, {"attr": AMS_RANOUT[0], "raw_code": AMS_RANOUT[1]})

    def test_as_context_is_the_json_blob_the_timeline_row_stores(self):
        context = describe(*AMS_RANOUT).as_context()
        self.assertEqual(context["code"], "0700_2000_0002_0001")
        self.assertEqual(context["severity"], "serious")
        self.assertEqual(context["module"], "AMS")
        self.assertTrue(context["blocking"])
        self.assertIn("wiki_url", context)


class DescribeAllTests(SimpleTestCase):
    def test_decodes_every_entry_in_order(self):
        alerts = describe_all([
            {"attr": AMS_RANOUT[0], "code": AMS_RANOUT[1]},
            {"attr": BED_HEATER_FAULT[0], "code": BED_HEATER_FAULT[1]},
        ])
        self.assertEqual(
            [a.code for a in alerts],
            ["0700_2000_0002_0001", "0300_0100_0001_0001"],
        )

    def test_malformed_entries_are_skipped_without_losing_the_good_ones(self):
        alerts = describe_all([
            {"attr": AMS_RANOUT[0], "code": AMS_RANOUT[1]},
            "not a dict at all",
            {"attr": AMS_RANOUT[0]},                       # missing key
            {"attr": "not a number", "code": "nope"},      # unparseable strings
            None,
            {"attr": BED_HEATER_FAULT[0], "code": BED_HEATER_FAULT[1]},
        ])
        self.assertEqual(
            [a.code for a in alerts],
            ["0700_2000_0002_0001", "0300_0100_0001_0001"],
        )

    def test_numeric_strings_are_still_decoded(self):
        # Firmware has shipped both quoted and raw numbers for these fields.
        alerts = describe_all([{"attr": str(AMS_RANOUT[0]), "code": str(AMS_RANOUT[1])}])
        self.assertEqual([a.code for a in alerts], ["0700_2000_0002_0001"])

    def test_an_empty_or_missing_array_decodes_to_nothing(self):
        self.assertEqual(describe_all([]), [])
        self.assertEqual(describe_all(None), [])


class DescribePrintErrorTests(SimpleTestCase):
    def test_the_cancel_sentinel_is_the_decimal_we_think_it_is(self):
        # Pinned explicitly: a source we consulted printed the wrong hex for
        # this decimal, and getting it wrong makes every cancel read as a crash.
        self.assertEqual(50348044, 0x0300400C)
        self.assertEqual(CANCEL_PRINT_ERROR, 0x0300400C)

    def test_a_user_cancel_is_not_a_failure(self):
        alert = describe_print_error(50348044)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.code, "0300_400C")
        self.assertTrue(alert.cancelled)
        self.assertFalse(alert.blocking)
        self.assertEqual(alert.message, "The print was cancelled.")

    def test_any_other_non_zero_value_is_blocking(self):
        alert = describe_print_error(0x03004002)
        self.assertFalse(alert.cancelled)
        self.assertTrue(alert.blocking)
        self.assertEqual(alert.severity, "fatal")

    def test_an_unknown_print_error_still_names_its_module(self):
        alert = describe_print_error(0x05009999)
        self.assertIn("Main board", alert.message)
        self.assertIn("0500_9999", alert.message)

    def test_zero_means_no_error(self):
        self.assertIsNone(describe_print_error(0))

    def test_non_numeric_input_returns_none(self):
        self.assertIsNone(describe_print_error("banana"))
        self.assertIsNone(describe_print_error(None))
        self.assertIsNone(describe_print_error([]))

    def test_a_numeric_string_is_still_decoded(self):
        alert = describe_print_error("50348044")
        self.assertIsNotNone(alert)
        self.assertTrue(alert.cancelled)


class SummarizeFailureTests(SimpleTestCase):
    def test_the_print_error_wins_over_the_hms_array(self):
        # The hms entries are the symptoms; print_error is the outcome.
        hms_alerts = [describe(*BED_HEATER_FAULT)]
        print_error = describe_print_error(0x03004006)
        self.assertIs(summarize_failure(hms_alerts, print_error), print_error)

    def test_the_most_severe_blocking_alert_wins_without_a_print_error(self):
        serious = describe(*AMS_RANOUT)
        fatal = describe(*BED_HEATER_FAULT)
        self.assertIs(summarize_failure([serious, fatal]), fatal)

    def test_ties_go_to_the_earliest_alert_seen(self):
        first = describe(*AMS_RANOUT)
        second = describe(*EXTERNAL_SPOOL_RANOUT)
        self.assertEqual(first.severity, second.severity)
        self.assertIs(summarize_failure([first, second]), first)

    def test_non_blocking_alerts_never_explain_a_failure(self):
        self.assertIsNone(summarize_failure([describe(*AMS_DISABLED)]))

    def test_nothing_at_all_summarises_to_none(self):
        self.assertIsNone(summarize_failure([]))
        self.assertIsNone(summarize_failure(None))
        self.assertIsNone(summarize_failure(None, None))

    def test_an_unknown_severity_ranks_last_but_is_still_returned(self):
        odd = DecodedAlert(code="X", message="?", severity="unheard-of", blocking=True)
        self.assertIs(summarize_failure([odd]), odd)


class WikiUrlTests(SimpleTestCase):
    def test_a_known_model_gets_a_model_specific_page(self):
        self.assertEqual(
            wiki_url_for("0700_2000_0002_0001", "X1C"),
            "https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/0700_2000_0002_0001",
        )

    def test_model_lookup_is_case_and_whitespace_insensitive(self):
        self.assertEqual(
            wiki_url_for("0700_2000_0002_0001", "  a1 mini "),
            "https://wiki.bambulab.com/en/a1-mini/troubleshooting/hmscode/"
            "0700_2000_0002_0001",
        )

    def test_an_unknown_model_falls_back_to_the_code_index(self):
        self.assertEqual(wiki_url_for("0700_2000_0002_0001", "Widgetron 9000"),
                         WIKI_INDEX_URL)
        self.assertEqual(wiki_url_for("0700_2000_0002_0001"), WIKI_INDEX_URL)
