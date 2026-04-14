"""Backfill slugs on PetSpecies and PotionType from their names."""

from django.db import migrations
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    PetSpecies = apps.get_model("pets", "PetSpecies")
    PotionType = apps.get_model("pets", "PotionType")

    for species in PetSpecies.objects.all():
        if not species.slug:
            species.slug = slugify(species.name)
            species.save(update_fields=["slug"])

    for potion in PotionType.objects.all():
        if not potion.slug:
            potion.slug = slugify(potion.name)
            potion.save(update_fields=["slug"])


def reverse_noop(apps, schema_editor):
    # Null the slugs back out — they're nullable so this is safe.
    PetSpecies = apps.get_model("pets", "PetSpecies")
    PotionType = apps.get_model("pets", "PotionType")
    PetSpecies.objects.all().update(slug=None)
    PotionType.objects.all().update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ("pets", "0002_content_slugs_and_refs"),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, reverse_noop),
    ]
