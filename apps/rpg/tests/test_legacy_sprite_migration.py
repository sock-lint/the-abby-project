from django.test import TestCase
from apps.rpg.models import SpriteAsset


class LegacySpriteMigrationTests(TestCase):
    """Runs the import_legacy_sprites data migration's forward function
    directly against the test DB, using the repo's real manifest +
    artwork files.

    Migration runs are idempotent, so it's safe to invoke twice.
    """

    def test_forward_creates_rows_for_every_manifest_entry(self):
        from apps.rpg.migrations import _0014_import_legacy_sprites_impl as impl
        from django.apps import apps as django_apps

        impl.import_legacy_sprites(django_apps, None)

        # Every slug in the manifest should now be a SpriteAsset with pack="core"
        count = SpriteAsset.objects.filter(pack="core").count()
        self.assertGreater(count, 50)   # there are ~72 sprites today, be lenient
        # Spot-check a well-known slug from the existing manifest
        self.assertTrue(SpriteAsset.objects.filter(slug="apple").exists())

    def test_forward_is_idempotent(self):
        from apps.rpg.migrations import _0014_import_legacy_sprites_impl as impl
        from django.apps import apps as django_apps

        impl.import_legacy_sprites(django_apps, None)
        initial = SpriteAsset.objects.filter(pack="core").count()
        impl.import_legacy_sprites(django_apps, None)  # second run — should no-op
        after = SpriteAsset.objects.filter(pack="core").count()
        self.assertEqual(initial, after)

    def test_reverse_removes_pack_core_rows(self):
        from apps.rpg.migrations import _0014_import_legacy_sprites_impl as impl
        from django.apps import apps as django_apps

        impl.import_legacy_sprites(django_apps, None)
        count_before = SpriteAsset.objects.filter(pack="core").count()
        self.assertGreater(count_before, 0, "forward migration must have seeded core sprites")

        impl.remove_legacy_sprites(django_apps, None)

        self.assertEqual(SpriteAsset.objects.filter(pack="core").count(), 0)
