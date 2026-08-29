"""What the AMS says, and what we are willing to claim from it.

Every test here is about a way the payload lies or stays silent, because that
is where a filament picker goes wrong — not in the happy path where a Bambu
spool reports a colour and a percentage.

Invariants pinned here:

1. RGBA is rendered as RGB, and alpha ``00`` (unread bay) is *not* black.
2. ``remain`` is ``None`` for a spool with no RFID tag, never ``-1`` or 0.
3. An empty bay produces no slot, and a removed spool stops producing one.
4. A partial ``ams`` delta does not blank the bays it didn't mention.
5. The external spool holder is reported even with no AMS attached.
6. Slots are named the way the printer labels them: A1..A4, then B1.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.printing.filament import (
    describe_trays,
    merge_ams,
    normalize_color,
)


def tray(tray_id, **fields):
    base = {
        "id": str(tray_id),
        "tray_type": "PLA",
        "tray_sub_brands": "PLA Basic",
        "tray_color": "00AE42FF",
        "tray_info_idx": "GFA00",
        "remain": 92,
        "tray_weight": "1000",
    }
    base.update(fields)
    return base


def empty_tray(tray_id):
    """What the AMS reports for a bay with nothing in it."""
    return {
        "id": str(tray_id), "tray_type": "", "tray_sub_brands": "",
        "tray_color": "00000000", "tray_info_idx": "", "remain": -1,
    }


def ams_block(*units):
    return {"ams": list(units), "ams_exist_bits": "1", "version": 3}


def unit(unit_id, trays):
    return {"id": str(unit_id), "humidity": "4", "temp": "26.4", "tray": trays}


class ColorTests(SimpleTestCase):
    def test_rgba_is_rendered_as_rgb(self):
        self.assertEqual(normalize_color("00AE42FF"), "#00AE42")

    def test_black_filament_is_black_not_missing(self):
        # 000000FF is real black PLA. Only the alpha byte says "unknown".
        self.assertEqual(normalize_color("000000FF"), "#000000")

    def test_a_transparent_alpha_means_the_bay_was_never_read(self):
        self.assertIsNone(normalize_color("00000000"))

    def test_junk_is_none_rather_than_a_broken_swatch(self):
        for value in ("", None, "nope", "#12", "GGGGGGFF"):
            self.assertIsNone(normalize_color(value), value)

    def test_a_six_digit_colour_is_accepted(self):
        self.assertEqual(normalize_color("ff8800"), "#FF8800")


class DescribeTests(SimpleTestCase):
    def test_a_bambu_spool_reports_everything(self):
        slots = describe_trays(ams_block(unit(0, [tray(0)])), None)
        self.assertEqual(len(slots), 1)
        slot = slots[0]
        self.assertEqual(slot.slot, "A1")
        self.assertEqual(slot.material, "PLA")
        self.assertEqual(slot.label, "PLA Basic")
        self.assertEqual(slot.hex, "#00AE42")
        self.assertEqual(slot.remain_percent, 92)
        self.assertFalse(slot.is_external)
        self.assertEqual(slot.filament_id, "GFA00")

    def test_a_third_party_spool_has_no_percentage(self):
        # The percentage is read off an RFID tag, so it does not exist for a
        # spool that has none. -1 must not reach the UI as a number.
        slots = describe_trays(
            ams_block(unit(0, [tray(0, remain=-1, tray_sub_brands="")])), None,
        )
        self.assertIsNone(slots[0].remain_percent)
        self.assertEqual(slots[0].display_name, "PLA")

    def test_an_out_of_range_percentage_is_refused(self):
        slots = describe_trays(ams_block(unit(0, [tray(0, remain=255)])), None)
        self.assertIsNone(slots[0].remain_percent)

    def test_an_empty_bay_produces_no_slot(self):
        slots = describe_trays(
            ams_block(unit(0, [tray(0), empty_tray(1), empty_tray(2), empty_tray(3)])),
            None,
        )
        self.assertEqual([s.slot for s in slots], ["A1"])

    def test_a_bay_with_only_a_colour_still_counts(self):
        # A tag half-read: no material yet, but there is plainly something in
        # there, and hiding it would be worse than naming it vaguely.
        slots = describe_trays(
            ams_block(unit(0, [tray(0, tray_type="", tray_sub_brands="")])), None,
        )
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].display_name, "Unknown filament")

    def test_slots_are_named_the_way_the_printer_labels_them(self):
        slots = describe_trays(
            ams_block(
                unit(0, [tray(0), tray(1), tray(2), tray(3)]),
                unit(1, [tray(0)]),
            ),
            None,
        )
        self.assertEqual([s.slot for s in slots], ["A1", "A2", "A3", "A4", "B1"])

    def test_the_external_spool_is_included_and_marked(self):
        slots = describe_trays(
            ams_block(unit(0, [tray(0)])),
            {"id": "254", "tray_type": "TPU", "tray_color": "FF8800FF", "remain": -1},
        )
        self.assertEqual([s.slot for s in slots], ["A1", "Ext"])
        self.assertTrue(slots[-1].is_external)
        self.assertEqual(slots[-1].material, "TPU")

    def test_a_printer_with_no_ams_still_reports_its_external_spool(self):
        # An A1 mini without AMS lite has vt_tray and nothing else. Returning
        # nothing here would make the picker useless on that machine.
        slots = describe_trays(
            None, {"id": "254", "tray_type": "PETG", "tray_color": "1E90FFFF"},
        )
        self.assertEqual([s.slot for s in slots], ["Ext"])

    def test_an_empty_external_holder_produces_no_slot(self):
        self.assertEqual(describe_trays(None, empty_tray(254)), [])

    def test_nothing_reported_yet_is_an_empty_list_not_an_error(self):
        self.assertEqual(describe_trays(None, None), [])
        self.assertEqual(describe_trays({}, {}), [])

    def test_a_malformed_block_does_not_raise(self):
        # One bad report must never take down ingest.
        self.assertEqual(describe_trays({"ams": "nonsense"}, None), [])
        self.assertEqual(describe_trays({"ams": [None, 7]}, None), [])
        self.assertEqual(describe_trays({"ams": [{"tray": "no"}]}, None), [])


class MergeTests(SimpleTestCase):
    def test_a_full_block_merges_to_itself(self):
        block = ams_block(unit(0, [tray(0), tray(1)]))
        self.assertEqual(merge_ams({}, block)["ams"], block["ams"])

    def test_a_partial_tray_delta_keeps_the_other_bays(self):
        # The trap this whole module exists for: assigning the delta would
        # blank three bays because the printer only mentioned one.
        previous = merge_ams({}, ams_block(unit(0, [
            tray(0, tray_color="00AE42FF"), tray(1, tray_color="FF0000FF"),
            tray(2, tray_color="0000FFFF"), tray(3, tray_color="FFFFFFFF"),
        ])))
        merged = merge_ams(previous, {"ams": [{"id": "0", "tray": [
            {"id": "1", "remain": 40},
        ]}]})

        slots = describe_trays(merged, None)
        self.assertEqual([s.slot for s in slots], ["A1", "A2", "A3", "A4"])
        self.assertEqual(slots[1].remain_percent, 40)
        # …and the untouched bay keeps every field, not just its id.
        self.assertEqual(slots[1].hex, "#FF0000")
        self.assertEqual(slots[2].hex, "#0000FF")

    def test_a_partial_delta_keeps_units_it_did_not_mention(self):
        previous = merge_ams({}, ams_block(unit(0, [tray(0)]), unit(1, [tray(0)])))
        merged = merge_ams(previous, {"ams": [{"id": "0", "tray": [
            {"id": "0", "remain": 10},
        ]}]})
        self.assertEqual([s.slot for s in describe_trays(merged, None)], ["A1", "B1"])

    def test_a_removed_spool_stops_being_reported(self):
        # Removal arrives as the tray with its fields blanked, not as an
        # absent entry — so the merge accumulates it and describe drops it.
        previous = merge_ams({}, ams_block(unit(0, [tray(0), tray(1)])))
        merged = merge_ams(previous, {"ams": [{"id": "0", "tray": [empty_tray(0)]}]})
        self.assertEqual([s.slot for s in describe_trays(merged, None)], ["A2"])

    def test_string_and_int_ids_are_matched_as_the_same_tray(self):
        # JSON types are not stable across firmware; ids must not fork.
        previous = merge_ams({}, {"ams": [{"id": 0, "tray": [{"id": 0,
                                                             "tray_type": "PLA",
                                                             "tray_color": "00AE42FF"}]}]})
        merged = merge_ams(previous, {"ams": [{"id": "0", "tray": [
            {"id": "0", "remain": 55},
        ]}]})
        slots = describe_trays(merged, None)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].remain_percent, 55)

    def test_junk_leaves_the_previous_state_alone(self):
        previous = merge_ams({}, ams_block(unit(0, [tray(0)])))
        self.assertEqual(merge_ams(previous, "nope"), previous)
        self.assertEqual(merge_ams(previous, {"ams": "nope"})["ams"],
                         previous["ams"])
