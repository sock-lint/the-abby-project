"""Backfill ItemDefinition.slug, pet_species, potion_type, food_species.

Reads the existing ``metadata["species"]``, ``metadata["variant"]``, and
``metadata["food_type"]`` strings (case-insensitive) and resolves them to
real FKs. This fixes the previous case-mismatch bug where eggs stored
``"wolf"`` while ``PetSpecies.name`` was ``"Wolf"``.

Also populates ``PetSpecies.available_potions`` based on the egg × potion
combos implied by the seed catalog (every egg in the table times every
potion in the table — matches the original behavior where any
egg+potion combo was hatchable).
"""

from django.db import migrations
from django.utils.text import slugify


EGG_TYPE = "egg"
POTION_TYPE = "potion"
FOOD_TYPE = "food"


def backfill_refs(apps, schema_editor):
    ItemDefinition = apps.get_model("rpg", "ItemDefinition")
    PetSpecies = apps.get_model("pets", "PetSpecies")
    PotionType = apps.get_model("pets", "PotionType")

    # Build case-insensitive lookup maps keyed by slug AND lowercase name.
    species_by_key = {}
    for s in PetSpecies.objects.all():
        if s.slug:
            species_by_key[s.slug.lower()] = s
        species_by_key[s.name.lower()] = s

    potions_by_key = {}
    for p in PotionType.objects.all():
        if p.slug:
            potions_by_key[p.slug.lower()] = p
        potions_by_key[p.name.lower()] = p

    # Also map by food_preference → species (for food item FK).
    species_by_food_pref = {
        s.food_preference.lower(): s
        for s in PetSpecies.objects.all()
        if s.food_preference
    }

    for item in ItemDefinition.objects.all():
        changed = False
        meta = item.metadata or {}

        # Backfill slug from name.
        if not item.slug:
            item.slug = slugify(item.name)
            changed = True

        if item.item_type == EGG_TYPE and not item.pet_species_id:
            key = str(meta.get("species", "")).strip().lower()
            species = species_by_key.get(key)
            if species:
                item.pet_species = species
                changed = True

        if item.item_type == POTION_TYPE and not item.potion_type_id:
            key = str(meta.get("variant", "")).strip().lower()
            potion = potions_by_key.get(key)
            if potion:
                item.potion_type = potion
                changed = True

        if item.item_type == FOOD_TYPE and not item.food_species_id:
            key = str(meta.get("food_type", "")).strip().lower()
            species = species_by_food_pref.get(key)
            if species:
                item.food_species = species
                changed = True

        if changed:
            item.save(update_fields=[
                "slug", "pet_species", "potion_type", "food_species",
            ])

    # Populate PetSpecies.available_potions = all potions (matches original
    # "any combo works" seed behavior). Authors can narrow this per-species
    # later via YAML packs.
    all_potions = list(PotionType.objects.all())
    if all_potions:
        for species in PetSpecies.objects.all():
            if species.available_potions.count() == 0:
                species.available_potions.set(all_potions)


def reverse_noop(apps, schema_editor):
    ItemDefinition = apps.get_model("rpg", "ItemDefinition")
    ItemDefinition.objects.all().update(
        slug=None, pet_species=None, potion_type=None, food_species=None,
    )
    # M2M cleanup: clear all available_potions sets.
    PetSpecies = apps.get_model("pets", "PetSpecies")
    for species in PetSpecies.objects.all():
        species.available_potions.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("rpg", "0005_content_slugs_and_refs"),
        ("pets", "0003_backfill_slugs"),
    ]

    operations = [
        migrations.RunPython(backfill_refs, reverse_noop),
    ]
