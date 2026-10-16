from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, local
from time import monotonic, sleep
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, skipUnlessDBFeature

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.achievements.services import SkillService
from apps.achievements.tests import test_xp_concurrency as xp_helpers
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import CosmeticService
from config.tests.factories import make_family


class CharacterProgressionConcurrencyTests(TransactionTestCase):
    _worker = staticmethod(xp_helpers.XpConcurrencyTests._worker)

    def setUp(self):
        self.child = make_family(children=[{"username": "parallel-character-child"}]).children[0]
        category = SkillCategory.objects.create(name="Parallel character")
        self.skill = Skill.objects.create(name="Practice", category=category)
        self.other = Skill.objects.create(name="Persistence", category=category)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_skill_awards_update_one_aggregate_level(self):
        barrier = Barrier(2)

        def award(skill):
            barrier.wait(timeout=5)
            return SkillService.award_xp(self.child, skill, 60)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._worker, lambda skill=skill: award(skill)) for skill in (self.skill, self.other)]
            for future in futures:
                future.result(timeout=15)
        self.assertEqual(sum(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True)), 120)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).level, 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_cosmetic_and_xp_mutations_share_user_before_profile_order(self):
        cover = ItemDefinition.objects.create(
            slug="cover-hyrule", name="Hyrule cover", item_type="cosmetic_theme",
            metadata={"theme": "hyrule"},
        )
        UserInventory.objects.create(user=self.child, item=cover)
        actions = {
            "equip": lambda: CosmeticService.equip(self.child, cover.pk),
            "unequip": lambda: CosmeticService.unequip(self.child, "active_theme"),
            "starter": lambda: CosmeticService.grant_starter_cover(self.child),
        }
        for name, action in actions.items():
            with self.subTest(action=name):
                SkillProgress.objects.filter(user=self.child).delete()
                CharacterProfile.objects.filter(user=self.child).update(level=0, active_theme=None)
                self.child.theme = "vigil"
                self.child.save(update_fields=["theme"])
                held_profile = Event()
                release_cosmetic = Event()
                state = local()
                competitor_pid = []
                original_save = CharacterProfile.save

                def hold_after_profile_save(profile, *args, **kwargs):
                    value = original_save(profile, *args, **kwargs)
                    if getattr(state, "hold", False):
                        state.hold = False
                        held_profile.set()
                        if not release_cosmetic.wait(10):
                            raise TimeoutError("Cosmetic profile save was not released")
                    return value

                def held_cosmetic():
                    state.hold = True
                    return action()

                with patch.object(CharacterProfile, "save", hold_after_profile_save), ThreadPoolExecutor(max_workers=2) as pool:
                    cosmetic = pool.submit(self._worker, held_cosmetic)
                    try:
                        self.assertTrue(held_profile.wait(5))
                        award = pool.submit(self._worker, lambda: SkillService.award_xp(self.child, self.skill, 125), ready=competitor_pid)
                        deadline = monotonic() + 5
                        while monotonic() < deadline:
                            if award.done():
                                award.result()
                                break
                            if competitor_pid:
                                with connection.cursor() as cursor:
                                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [competitor_pid[0]])
                                    row = cursor.fetchone()
                                if row and row[0] == "Lock":
                                    break
                            sleep(0.01)
                        else:
                            self.fail("XP neither completed nor reached a lock")
                    finally:
                        release_cosmetic.set()
                    cosmetic.result(timeout=15)
                    award.result(timeout=15)
                self.assertEqual(CharacterProfile.objects.get(user=self.child).level, 1)
                self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 125)
