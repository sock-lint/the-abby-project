"""Tests that /api/children/{id}/ serializes DOB + grade + computed labels."""
from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class ChildAgeFieldsEndpointTests(APITestCase):
    def setUp(self):
        self.parent = User.objects.create(username="mom", role=User.Role.PARENT)
        self.child = User.objects.create(username="kid", role=User.Role.CHILD)

    def test_patch_and_read_back(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/children/{self.child.id}/", {
            "date_of_birth": "2011-09-22",
            "grade_entry_year": 2025,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["date_of_birth"], "2011-09-22")
        self.assertEqual(resp.data["grade_entry_year"], 2025)
        # Computed read-only fields are present and non-null now that DOB+grade exist
        self.assertIsNotNone(resp.data["age_years"])
        self.assertIsNotNone(resp.data["school_year_label"])

    def test_get_child_includes_computed_labels(self):
        self.child.date_of_birth = date(2011, 9, 22)
        self.child.grade_entry_year = 2025
        self.child.save()
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/children/{self.child.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("age_years", resp.data)
        self.assertIn("current_grade", resp.data)
        self.assertIn("school_year_label", resp.data)

    def test_computed_fields_null_when_no_dob(self):
        """age_years and school_year_label are None when DOB is not set."""
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/children/{self.child.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["age_years"])
        self.assertIsNone(resp.data["school_year_label"])

    def test_computed_grade_null_when_no_grade_entry_year(self):
        """current_grade is None when grade_entry_year is not set."""
        self.child.date_of_birth = date(2011, 9, 22)
        self.child.save()
        self.client.force_authenticate(self.parent)
        resp = self.client.get(f"/api/children/{self.child.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["current_grade"])

    def test_patch_ignores_computed_fields(self):
        """PATCH ignores submitted computed fields — they are read-only."""
        self.client.force_authenticate(self.parent)
        resp = self.client.patch(f"/api/children/{self.child.id}/", {
            "age_years": 99,
            "current_grade": 99,
            "school_year_label": "FAKE",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        # Computed values are None since no DOB/grade_entry_year set — not "99"
        self.assertIsNone(resp.data["age_years"])
        self.assertIsNone(resp.data["current_grade"])
        self.assertIsNone(resp.data["school_year_label"])


class MeLorebookFlagsEndpointTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create(
            username="kid",
            role=User.Role.CHILD,
            lorebook_flags={"pets_seen": True},
        )

    def test_me_includes_lorebook_flags(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["lorebook_flags"], {"pets_seen": True})

    def test_patch_merges_lorebook_flags(self):
        self.client.force_authenticate(self.child)
        resp = self.client.patch("/api/auth/me/", {
            "lorebook_flags": {"quests_seen": True},
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(
            self.child.lorebook_flags,
            {"pets_seen": True, "quests_seen": True},
        )

    def test_patch_rejects_non_object_lorebook_flags(self):
        self.client.force_authenticate(self.child)
        resp = self.client.patch("/api/auth/me/", {
            "lorebook_flags": ["pets_seen"],
        }, format="json")
        self.assertEqual(resp.status_code, 400)
