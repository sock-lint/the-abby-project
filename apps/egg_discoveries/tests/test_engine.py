from django.test import SimpleTestCase

from apps.egg_discoveries.engine import ordinary_complete, rare_search_capacity


class AllocationTests(SimpleTestCase):
    def test_ordinary_needs_total_effort_and_two_meaningful_categories(self):
        rule = {"total_minutes": 240, "min_minutes_per_type": 90, "activity_types_required": 2}
        self.assertFalse(ordinary_complete({"reading": 240, "movement": 0, "practice": 0}, rule))
        self.assertFalse(ordinary_complete({"reading": 90, "movement": 90, "practice": 0}, rule))
        self.assertTrue(ordinary_complete({"reading": 150, "movement": 90, "practice": 0}, rule))
        self.assertTrue(ordinary_complete({"reading": 0, "movement": 90, "practice": 150}, rule))

    def test_rare_needs_two_categories_and_uses_all_three_without_stranding_work(self):
        rule = {"minutes_per_search": 60, "max_minutes_per_type_per_search": 30}
        self.assertEqual(rare_search_capacity({"reading": 300, "movement": 29, "practice": 0}, rule), 0)
        self.assertEqual(rare_search_capacity({"reading": 30, "movement": 60, "practice": 90}, rule), 3)
        self.assertEqual(rare_search_capacity({"reading": 30, "movement": 30, "practice": 60}, rule), 2)
        self.assertEqual(rare_search_capacity({"reading": 150, "movement": 150, "practice": 0}, rule), 5)
        self.assertEqual(rare_search_capacity({"reading": 100, "movement": 100, "practice": 100}, rule), 5)
        self.assertEqual(rare_search_capacity({"reading": 30, "movement": 15, "practice": 15}, rule), 1)
        self.assertEqual(rare_search_capacity({"reading": 31, "movement": 29, "practice": 0}, rule), 0)
