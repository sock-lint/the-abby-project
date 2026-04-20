"""Storage accessor for the sprite bucket.

Kept in its own module so model files stay clean, and so the S3 backend
can be swapped for FileSystemStorage in tests via override_settings
without touching model definitions.
"""
from django.core.files.storage import storages


def sprite_storage():
    """Return the storage backend dedicated to the sprite bucket.

    Resolves to ``STORAGES["sprites"]`` via Django's storage registry.
    Use this in ImageField's ``storage=`` argument so the field picks up
    the current dict at runtime — not at import time — which makes
    ``override_settings(STORAGES={...})`` work in tests.
    """
    return storages["sprites"]
