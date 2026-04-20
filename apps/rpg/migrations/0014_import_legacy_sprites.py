from django.db import migrations

from ._0014_import_legacy_sprites_impl import (
    import_legacy_sprites,
    remove_legacy_sprites,
)


class Migration(migrations.Migration):
    dependencies = [
        ("rpg", "0013_sprite_asset_storage"),
    ]

    operations = [
        migrations.RunPython(import_legacy_sprites, remove_legacy_sprites),
    ]
