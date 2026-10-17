from django.db import migrations, models


SUPPORTED_TIERS = {
    "chick": "common", "meshtint-bee": "common", "meshtint-mushroom": "common",
    "meshtint-potted-plant": "common", "meshtint-sunflower": "common",
    "meshtint-bat": "uncommon", "meshtint-spider": "uncommon",
    "meshtint-snake": "uncommon", "meshtint-hermit-crab": "uncommon",
    "meshtint-blossom": "uncommon", "meshtint-ghost": "rare",
    "meshtint-wolf": "rare", "meshtint-bomb": "rare",
    "meshtint-shadow": "epic", "meshtint-dragon": "legendary",
}


def populate_acquisition_rarity(apps, schema_editor):
    Species = apps.get_model("pets", "PetSpecies")
    Item = apps.get_model("rpg", "ItemDefinition")
    alias = schema_editor.connection.alias
    # Preserve retained species' authored egg rarity. Only canonical typed eggs
    # can define the tier; an arbitrary alias in a saved inventory cannot.
    for species in Species.objects.using(alias).all().iterator():
        egg = Item.objects.using(alias).filter(
            slug=f"{species.slug}-egg", item_type="egg", pet_species_id=species.pk,
        ).first()
        if egg is not None:
            Species.objects.using(alias).filter(pk=species.pk).update(rarity=egg.rarity)
    # Existing supported rows must agree with their eggs immediately after the
    # schema change, even before the next idempotent content reload.
    for slug, rarity in SUPPORTED_TIERS.items():
        sprite_key = "cute-chick" if slug == "chick" else slug
        supported = Species.objects.using(alias).filter(slug=slug, sprite_key=sprite_key)
        supported.update(rarity=rarity)
        Item.objects.using(alias).filter(
            slug=f"{slug}-egg", item_type="egg", pet_species_id__in=supported.values("pk"),
        ).update(rarity=rarity)


class Migration(migrations.Migration):
    dependencies = [("pets", "0008_mountexpedition"), ("rpg", "0006_backfill_item_refs")]

    operations = [
        migrations.AddField(
            model_name="petspecies", name="rarity",
            field=models.CharField(
                choices=[("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"), ("epic", "Epic"), ("legendary", "Legendary")],
                default="common", max_length=20,
            ),
        ),
        migrations.RunPython(populate_acquisition_rarity, migrations.RunPython.noop),
    ]
