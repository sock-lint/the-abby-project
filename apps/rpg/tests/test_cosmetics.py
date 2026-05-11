from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import CosmeticService


class CosmeticServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cosmeticchild", password="testpass", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

        self.frame = ItemDefinition.objects.create(
            name="Bronze Frame",
            icon="🟫",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
            metadata={"border_color": "#CD7F32"},
        )
        self.title = ItemDefinition.objects.create(
            name="Apprentice",
            icon="🎓",
            item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
            metadata={"text": "Apprentice"},
        )
        self.theme = ItemDefinition.objects.create(
            slug="cover-sunlit",
            name="Sunlit Field",
            icon="☀️",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            coin_value=20,
            metadata={"theme": "sunlit"},
        )
        self.egg = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.COMMON,
        )

    def _give_item(self, item, qty=1):
        UserInventory.objects.create(user=self.user, item=item, quantity=qty)

    def test_equip_cosmetic_frame(self):
        self._give_item(self.frame)

        result = CosmeticService.equip(self.user, self.frame.pk)

        self.assertEqual(result["slot"], "active_frame")
        self.assertEqual(result["item_id"], self.frame.pk)
        self.assertEqual(result["item_name"], "Bronze Frame")

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.active_frame_id, self.frame.pk)

    def test_equip_item_not_owned(self):
        # User does not own the frame
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, self.frame.pk)
        self.assertIn("don't own", str(ctx.exception))

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_frame)

    def test_equip_non_cosmetic_raises(self):
        self._give_item(self.egg)

        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, self.egg.pk)
        self.assertIn("not a cosmetic", str(ctx.exception))

    def test_equip_unknown_item_raises(self):
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, 999999)
        self.assertIn("not found", str(ctx.exception))

    def test_unequip_clears_slot(self):
        self._give_item(self.frame)
        CosmeticService.equip(self.user, self.frame.pk)

        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.active_frame)

        result = CosmeticService.unequip(self.user, "active_frame")
        self.assertEqual(result["slot"], "active_frame")

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_frame)

    def test_unequip_invalid_slot_raises(self):
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.unequip(self.user, "active_bogus")
        self.assertIn("Invalid slot", str(ctx.exception))

    def test_list_owned_cosmetics(self):
        self._give_item(self.frame)
        self._give_item(self.title)
        self._give_item(self.theme)
        self._give_item(self.egg)  # Should NOT appear in results

        owned = CosmeticService.list_owned_cosmetics(self.user)

        self.assertIn("active_frame", owned)
        self.assertIn("active_title", owned)
        self.assertIn("active_theme", owned)
        self.assertIn("active_pet_accessory", owned)

        self.assertEqual(len(owned["active_frame"]), 1)
        self.assertEqual(owned["active_frame"][0].pk, self.frame.pk)

        self.assertEqual(len(owned["active_title"]), 1)
        self.assertEqual(owned["active_title"][0].pk, self.title.pk)

        self.assertEqual(len(owned["active_theme"]), 1)
        self.assertEqual(owned["active_theme"][0].pk, self.theme.pk)

        self.assertEqual(len(owned["active_pet_accessory"]), 0)


class JournalCoverEquipTests(TestCase):
    """Unification: equipping a ``cover-*`` cosmetic_theme also writes
    ``User.theme`` so the visible journal cover swaps.

    Pre-unification, ``CosmeticService.equip`` only wrote the FK on
    ``CharacterProfile.active_theme`` — the legacy ``User.theme``
    CharField that the frontend bootstrap actually reads stayed stale.
    Equipping a theme cosmetic was a silent no-op visually. Now the
    two writes happen atomically in the same transaction.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="coverkid", password="testpass", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

        # cover-vigil mirrors the YAML — metadata.theme="vigil" linking
        # to the real palette in frontend/src/themes.js.
        self.cover_vigil = ItemDefinition.objects.create(
            slug="cover-vigil",
            name="Night Vigil",
            icon="🕯️",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.RARE,
            coin_value=40,
            metadata={"theme": "vigil", "accent": "#7fe3f0"},
        )
        self.cover_hyrule = ItemDefinition.objects.create(
            slug="cover-hyrule",
            name="Hyrule Day",
            icon="📖",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
            metadata={"theme": "hyrule", "accent": "#157064"},
        )
        # Defensive: a cosmetic_theme item whose metadata lacks the
        # ``theme`` key. The 13 legacy ``theme-*`` items had this shape
        # before the 2026-05 cleanup retired them; this fixture pins the
        # guard so a future cosmetic author who forgets metadata.theme
        # gets a clear error rather than a silent fallback to Hyrule.
        self.malformed_cover = ItemDefinition.objects.create(
            slug="legacy-test-malformed",
            name="Malformed Cover",
            icon="❓",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            coin_value=20,
            metadata={"accent": "#0077BE"},
        )

    def _give(self, item, qty=1):
        UserInventory.objects.create(user=self.user, item=item, quantity=qty)

    def test_equipping_cover_cosmetic_updates_user_theme(self):
        """Equipping cover-vigil writes BOTH the FK and User.theme."""
        self._give(self.cover_vigil)
        # Pre-condition: user.theme is the default (legacy).
        self.assertNotEqual(self.user.theme, "vigil")

        result = CosmeticService.equip(self.user, self.cover_vigil.pk)

        self.assertEqual(result["slot"], "active_theme")

        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.profile.active_theme_id, self.cover_vigil.pk)
        self.assertEqual(self.user.theme, "vigil")

    def test_equipping_cosmetic_without_theme_metadata_raises(self):
        """Cosmetic_theme items without ``metadata.theme`` are rejected.

        Pre-unification, the 13 legacy ``theme-*`` items had this exact
        shape — equipping one was a silent no-op (applyTheme fell back to
        Hyrule). The cleanup retired them in 2026-05, but the guard stays
        as defense in depth against any future cosmetic_theme author who
        forgets to wire metadata.theme.
        """
        self._give(self.malformed_cover)

        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, self.malformed_cover.pk)
        self.assertIn("metadata.theme", str(ctx.exception))

        # No partial write: neither side of the dual-write should have landed.
        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertIsNone(self.profile.active_theme_id)

    def test_equipping_cover_with_unknown_theme_slug_raises(self):
        """metadata.theme that doesn't map to a real palette is rejected."""
        bogus = ItemDefinition.objects.create(
            slug="cover-bogus",
            name="Bogus Cover",
            icon="❓",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            metadata={"theme": "not-a-real-palette"},
        )
        self._give(bogus)

        with self.assertRaises(ValueError):
            CosmeticService.equip(self.user, bogus.pk)

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_theme_id)

    def test_equipping_frame_does_not_touch_user_theme(self):
        """The dual-write is scoped to ``active_theme`` only — equipping
        a frame must NOT clobber User.theme.
        """
        frame = ItemDefinition.objects.create(
            slug="frame-test",
            name="Test Frame",
            icon="🟫",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.COMMON,
        )
        self._give(frame)
        original_theme = self.user.theme

        CosmeticService.equip(self.user, frame.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, original_theme)


class StarterCoverGrantTests(TestCase):
    """``CosmeticService.grant_starter_cover`` is called from the three
    user-creation paths (FamilyService.create_family_with_parent,
    ChildViewSet.perform_create, ParentViewSet.perform_create). Tests
    cover idempotency + defensive behavior when seed data is missing.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="cardholder", password="testpass", role="child",
        )

    def test_grant_starter_cover_grants_hyrule_and_equips_it(self):
        cover = ItemDefinition.objects.create(
            slug="cover-hyrule",
            name="Hyrule Day",
            icon="📖",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            metadata={"theme": "hyrule"},
        )

        inv = CosmeticService.grant_starter_cover(self.user)

        self.assertIsNotNone(inv)
        self.assertEqual(inv.item_id, cover.pk)
        self.assertEqual(inv.quantity, 1)

        profile = CharacterProfile.objects.get(user=self.user)
        self.assertEqual(profile.active_theme_id, cover.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "hyrule")

    def test_grant_starter_cover_is_idempotent(self):
        ItemDefinition.objects.create(
            slug="cover-hyrule",
            name="Hyrule Day",
            icon="📖",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            metadata={"theme": "hyrule"},
        )

        CosmeticService.grant_starter_cover(self.user)
        CosmeticService.grant_starter_cover(self.user)

        # Only one inventory row per (user, item).
        self.assertEqual(
            UserInventory.objects.filter(user=self.user).count(), 1,
        )

    def test_grant_starter_cover_missing_item_returns_none(self):
        """Test fixtures that skip ``loadrpgcontent`` must not 500 on signup."""
        # No cover-hyrule row created.
        result = CosmeticService.grant_starter_cover(self.user)
        self.assertIsNone(result)

        # User can still exist and be saved.
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "cardholder")

    def test_grant_starter_cover_does_not_overwrite_existing_active_theme(self):
        """If the user already has an ``active_theme`` (e.g. from the
        backfill migration), grant_starter_cover leaves it alone — Hyrule
        is just added to the inventory.
        """
        hyrule = ItemDefinition.objects.create(
            slug="cover-hyrule", name="Hyrule Day", icon="📖",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            metadata={"theme": "hyrule"},
        )
        vigil = ItemDefinition.objects.create(
            slug="cover-vigil", name="Night Vigil", icon="🕯️",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.RARE,
            metadata={"theme": "vigil"},
        )
        # Simulate the post-migration state for an existing Vigil user.
        UserInventory.objects.create(user=self.user, item=vigil, quantity=1)
        profile, _ = CharacterProfile.objects.get_or_create(user=self.user)
        profile.active_theme = vigil
        profile.save()

        CosmeticService.grant_starter_cover(self.user)

        profile.refresh_from_db()
        self.assertEqual(profile.active_theme_id, vigil.pk)
        # Hyrule is now also in the inventory.
        self.assertTrue(
            UserInventory.objects.filter(user=self.user, item=hyrule).exists()
        )


class CosmeticListingFiltersMalformedCoversTests(TestCase):
    """Pin: ``list_owned_cosmetics`` + the catalog endpoint must drop any
    cosmetic_theme item whose ``metadata.theme`` doesn't resolve to a real
    palette in themes.js.

    The 13 retired ``theme-*`` items had this exact shape; cleanup_rpg_catalog
    removes them from the DB on next deploy, but until then the filter
    ensures the UI never advertises a cover the equip path would refuse.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="filterkid", password="testpass", role="child",
        )
        self.valid_cover = ItemDefinition.objects.create(
            slug="cover-vigil",
            name="Night Vigil",
            icon="🕯️",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.RARE,
            metadata={"theme": "vigil"},
        )
        self.legacy_cover = ItemDefinition.objects.create(
            slug="theme-ocean",
            name="Ocean Theme",
            icon="🌊",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            metadata={"accent": "#0077BE"},  # no theme key
        )
        self.frame = ItemDefinition.objects.create(
            slug="frame-test",
            name="Test Frame",
            icon="🟫",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.COMMON,
        )

    def test_is_valid_cosmetic_accepts_valid_cover(self):
        self.assertTrue(CosmeticService.is_valid_cosmetic(self.valid_cover))

    def test_is_valid_cosmetic_rejects_malformed_cover(self):
        self.assertFalse(CosmeticService.is_valid_cosmetic(self.legacy_cover))

    def test_is_valid_cosmetic_passes_other_cosmetic_types(self):
        """Only cosmetic_theme has a structural integrity check.

        Frames / titles / pet accessories don't carry metadata.theme;
        the filter must not accidentally drop them.
        """
        self.assertTrue(CosmeticService.is_valid_cosmetic(self.frame))

    def test_list_owned_cosmetics_excludes_malformed_covers(self):
        UserInventory.objects.create(user=self.user, item=self.valid_cover, quantity=1)
        UserInventory.objects.create(user=self.user, item=self.legacy_cover, quantity=1)

        owned = CosmeticService.list_owned_cosmetics(self.user)

        # Only the valid cover appears in the active_theme list.
        self.assertEqual(len(owned["active_theme"]), 1)
        self.assertEqual(owned["active_theme"][0].slug, "cover-vigil")


class SignupGrantsCoverTests(TestCase):
    """Integration: the three create-user paths all grant ``cover-hyrule``."""

    @classmethod
    def setUpTestData(cls):
        ItemDefinition.objects.create(
            slug="cover-hyrule",
            name="Hyrule Day",
            icon="📖",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.COMMON,
            metadata={"theme": "hyrule"},
        )

    def test_family_signup_grants_hyrule(self):
        from apps.families.services import FamilyService

        parent, _family, _token = FamilyService.create_family_with_parent(
            username="signupparent",
            password="t3stPass!secure",
            display_name="Founder",
            family_name="Test Family",
        )

        self.assertTrue(
            UserInventory.objects.filter(
                user=parent, item__slug="cover-hyrule",
            ).exists()
        )
        profile = CharacterProfile.objects.get(user=parent)
        self.assertEqual(profile.active_theme.slug, "cover-hyrule")
        parent.refresh_from_db()
        self.assertEqual(parent.theme, "hyrule")
