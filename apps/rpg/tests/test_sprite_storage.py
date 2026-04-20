from django.test import TestCase, override_settings
from apps.rpg.storage import sprite_storage


class SpriteStorageHelperTests(TestCase):
    def test_returns_a_storage_instance(self):
        storage = sprite_storage()
        # All Django storages expose .save / .url / .delete. Any one is fine
        # as a smoke check that we got a storage-like object, not None.
        self.assertTrue(hasattr(storage, "save"))
        self.assertTrue(hasattr(storage, "url"))
        self.assertTrue(hasattr(storage, "delete"))

    def test_default_is_filesystem_in_tests(self):
        from django.core.files.storage import FileSystemStorage
        # The test-mode block in settings.py keeps sprite_storage pinned to
        # FileSystem so SimpleUploadedFile tests don't reach for Ceph.
        self.assertIsInstance(sprite_storage(), FileSystemStorage)
