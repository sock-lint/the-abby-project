"""Tests for the Family model."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family


User = get_user_model()


class FamilyModelTests(TestCase):
    def test_slug_auto_generates_from_name(self):
        family = Family.objects.create(name="The Sageb Family")
        self.assertEqual(family.slug, "the-sageb-family")

    def test_slug_collision_appends_suffix(self):
        Family.objects.create(name="House")
        b = Family.objects.create(name="House")
        self.assertEqual(b.slug, "house-2")

    def test_explicit_slug_preserved(self):
        family = Family.objects.create(name="Test", slug="custom-slug")
        self.assertEqual(family.slug, "custom-slug")

    def test_str_returns_name(self):
        family = Family.objects.create(name="Brown")
        self.assertEqual(str(family), "Brown")

    def test_parents_property_returns_only_parents(self):
        family = Family.objects.create(name="A")
        p = User.objects.create_user(username="p", role="parent", family=family, password="pw")
        User.objects.create_user(username="c", role="child", family=family, password="pw")
        self.assertEqual(list(family.parents), [p])

    def test_children_property_returns_only_children(self):
        family = Family.objects.create(name="A")
        User.objects.create_user(username="p", role="parent", family=family, password="pw")
        c = User.objects.create_user(username="c", role="child", family=family, password="pw")
        self.assertEqual(list(family.children), [c])
