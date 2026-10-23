"""Guide responses under the child surprise rule, produced by Django."""
import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.pets.models import PetSpecies, PotionType, UserPet
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family

FUTURE = re.compile(r"\b(Fledgling|Bird)\b")


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class LorebookApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family(
            "Guide Fixture Family", family_id=61,
            parents=[{"id": 16, "username": "guide-fixture-parent"}],
            children=[{"id": 17, "username": "guide-fixture-child", "lorebook_flags": {"pets_trained": True}}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        chick, _ = PetSpecies.objects.get_or_create(slug="chick", defaults={"name": "Chick", "sprite_key": "cute-chick", "icon": "C"})
        base, _ = PotionType.objects.get_or_create(slug="base", defaults={"name": "Base"})
        UserPet.objects.create(user=self.child, species=chick, potion=base, growth_points=10)

    def test_a_baby_chick_child_reads_generic_later_forms(self):
        self.client.force_authenticate(self.child)
        body = self.assert_response_fixture(self.client.get("/api/lorebook/"), "lorebook-child-baby-chick.json")
        self.assertEqual(FUTURE.findall(str(body)), [])

    def test_parents_read_the_full_reference(self):
        self.client.force_authenticate(self.parent)
        body = self.assert_response_fixture(self.client.get("/api/lorebook/"), "lorebook-parent-reference.json")
        self.assertEqual(set(FUTURE.findall(str(body))), {"Fledgling", "Bird"})
