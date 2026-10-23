"""The owner's child surprise rule for Guide copy that names Chick's forms."""
import json
import re

from rest_framework.test import APITestCase

from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.projects.models import User

FUTURE = re.compile(r"\b(Fledgling|Bird)\b")


class GuideSurpriseTests(APITestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="surprise-child", password="pw", role="child")
        self.chick, _ = PetSpecies.objects.get_or_create(slug="chick", defaults={"name": "Chick", "sprite_key": "cute-chick", "icon": "C"})
        self.base, _ = PotionType.objects.get_or_create(slug="base", defaults={"name": "Base"})
        self.fire, _ = PotionType.objects.get_or_create(slug="fire", defaults={"name": "Fire"})

    def guide(self, user=None):
        self.client.force_authenticate(user or self.child)
        response = self.client.get("/api/lorebook/")
        self.assertEqual(response.status_code, 200)
        return {entry["slug"]: entry for entry in response.json()["entries"]}

    def names(self, entries, *slugs):
        text = json.dumps([entries[slug] for slug in slugs], ensure_ascii=False)
        return set(FUTURE.findall(text))

    def pet(self, potion=None, growth=10, evolved=False):
        return UserPet.objects.create(user=self.child, species=self.chick, potion=potion or self.base,
                                      growth_points=growth, evolved_to_mount=evolved)

    def test_a_child_without_chick_reads_generic_stages_everywhere(self):
        entries = self.guide()
        self.assertEqual(set(FUTURE.findall(json.dumps(list(entries.values()), ensure_ascii=False))), set())
        pets = entries["pets"]
        self.assertIn("For Chick, these forms are Chick, its middle form and its grown form.", pets["kid_voice"])
        self.assertEqual(pets["trial"]["payoff"], "Egg → Baby → Middle → Grown (Chick → middle form → grown form after hatching)")
        self.assertIn("Base Chick evolves to the owned grown appearance", entries["mounts"]["parent_knobs"]["content_sources"][0])
        self.assertIn("Every species follows Egg → Baby → Middle → Grown", pets["mechanics"][0])

    def test_a_baby_or_unevolved_chick_reveals_no_later_form(self):
        pet = self.pet()
        self.assertEqual(self.names(self.guide(), "pets", "mounts"), set())
        pet.growth_points = 100
        pet.save(update_fields=["growth_points"])
        self.assertEqual(self.names(self.guide(), "pets", "mounts"), {"Fledgling"})

    def test_a_middle_chick_reveals_fledgling_but_not_bird(self):
        self.pet(growth=65)
        entries = self.guide()
        self.assertEqual(self.names(entries, "pets", "mounts"), {"Fledgling"})
        self.assertIn("at 50 growth Chick becomes Fledgling.", entries["pets"]["trial"]["steps"][2])

    def test_a_confirmed_grown_chick_reveals_every_reached_form(self):
        pet = self.pet(growth=100, evolved=True)
        UserMount.objects.create(user=self.child, species=self.chick, potion=self.base)
        self.assertEqual(self.names(self.guide(), "pets", "mounts"), {"Fledgling", "Bird"})
        self.assertTrue(pet.evolved_to_mount)

    def test_another_appearance_or_legacy_potion_never_unlocks_base_forms(self):
        self.pet(potion=self.fire, growth=100, evolved=True)
        UserMount.objects.create(user=self.child, species=self.chick, potion=self.fire)
        legacy = PotionType.objects.create(slug=None, name="Legacy")
        self.pet(potion=legacy, growth=65)
        self.assertEqual(self.names(self.guide(), "pets", "mounts"), set())

    def test_parents_and_staff_children_keep_the_full_reference(self):
        parent = User.objects.create_user(username="surprise-parent", password="pw", role="parent")
        staff = User.objects.create_user(username="surprise-staff", password="pw", role="child", is_staff=True)
        for user in (parent, staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.names(self.guide(user), "pets", "mounts"), {"Fledgling", "Bird"})
