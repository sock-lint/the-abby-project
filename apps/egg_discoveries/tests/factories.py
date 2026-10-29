"""Synthetic supported pairs for native discovery tests; no production assets."""
from types import SimpleNamespace

from apps.pets.models import PetSpecies, PotionType
from apps.rpg.models import ItemDefinition


ASSET_POLICY = {
    "schema_version": 1,
    "potion_slugs": ["base"],
    "pets": [
        {"species_slug": slug, "sprite_key": slug, "potion_slugs": ["base"]}
        for slug in ("discovery-ordinary", "discovery-other", "discovery-rare")
    ],
}


def make_catalog():
    """Return .ordinary/.other/.rare, each with .key/.egg/.species/.potion."""
    base = PotionType.objects.create(slug="base", name="Base")
    potion = ItemDefinition.objects.create(
        slug="base-potion", name="Base Potion", item_type="potion", potion_type=base,
        icon="P", sprite_key="potion-brew-earthy", metadata={"variant": "base"},
    )
    food = ItemDefinition.objects.create(
        slug="discovery-food", name="Starter Food", item_type="food", rarity="common", icon="F",
    )
    pairs = []
    for slug, rarity in (("discovery-ordinary", "common"), ("discovery-other", "uncommon"), ("discovery-rare", "rare")):
        species = PetSpecies.objects.create(slug=slug, name=slug.replace("-", " ").title(), sprite_key=slug, rarity=rarity, icon="S")
        species.available_potions.add(base)
        egg = ItemDefinition.objects.create(
            slug=f"{slug}-egg", name=f"{species.name} Egg", item_type="egg", pet_species=species,
            metadata={"species": slug}, rarity=rarity, icon="E", sprite_key="big-egg",
        )
        pairs.append(SimpleNamespace(key=f"{egg.slug}:base", species=species, egg=egg, potion=potion, base=base, food=food))
    return SimpleNamespace(ordinary=pairs[0], other=pairs[1], rare=pairs[2], base=base, potion=potion, food=food)
