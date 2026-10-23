"""Add reduced random pouches without editing any established item identity."""
from django.db import migrations


POUCHES = (
    ("pouch-small-v2", "Small Coin Pouch (1 Coin)", "👛", "money-purse", "common", 1),
    ("pouch-rupee-v2", "Loose Rupee (2 Coins)", "💎", "rupee", "common", 2),
    ("pouch-medium-v2", "Medium Coin Pouch (3 Coins)", "💰", "bronze-coin-stack", "uncommon", 3),
    ("pouch-large-v2", "Large Coin Pouch (10 Coins)", "💎", "silver-coin-stack", "rare", 10),
    ("pouch-gold-v2", "Gold Stack (20 Coins)", "🪙", "gold-coin-stack", "epic", 20),
    ("pouch-treasure-v2", "Treasure Hoard (50 Coins)", "🏆", "large-gold-coin-stack", "legendary", 50),
    ("pouch-mega-v2", "Mega Hoard (100 Coins)", "💎", "large-gold-coin-stack", "legendary", 100),
)


def validate_reserved_pouch(item, rarity, coins):
    metadata = item.metadata
    if (
        item.item_type != "coin_pouch" or item.rarity != rarity or item.coin_value != coins
        or not isinstance(metadata, dict) or type(metadata.get("coins")) is not int
        or metadata["coins"] != coins or metadata.get("no_random_drop") is not True
    ):
        raise ValueError("Reserved random Coin pouch identity conflicts with the payout policy.")


def add_random_pouches(apps, schema_editor):
    ItemDefinition = apps.get_model("rpg", "ItemDefinition")
    reserved = {item.slug: item for item in ItemDefinition.objects.filter(
        slug__in=[row[0] for row in POUCHES],
    )}
    # Check every reserved name, even without its original source: startup
    # YAML would otherwise overwrite a pre-existing custom/owned promise.
    # Validate all collisions before making the first additive write.
    for slug, _name, _icon, _sprite, rarity, coins in POUCHES:
        if slug in reserved:
            validate_reserved_pouch(reserved[slug], rarity, coins)
    for slug, name, icon, sprite, rarity, coins in POUCHES:
        # An empty installation gets the complete catalog from startup YAML.
        # Upgrade only installed source identities; do not prepopulate an
        # otherwise empty catalog (including synthetic fixture databases).
        if not ItemDefinition.objects.filter(slug=slug.removesuffix("-v2"), item_type="coin_pouch").exists():
            continue
        item, _created = ItemDefinition.objects.get_or_create(slug=slug, defaults={
            "name": name, "icon": icon, "sprite_key": sprite,
            "item_type": "coin_pouch", "rarity": rarity, "coin_value": coins,
            "metadata": {"coins": coins, "no_random_drop": True},
        })
        # A concurrent catalog insert must not turn a conflict into adoption.
        # RunPython is atomic, so a late collision rolls back earlier inserts.
        validate_reserved_pouch(item, rarity, coins)


class Migration(migrations.Migration):
    dependencies = [("rpg", "0039_merge_editorial_and_retirement")]
    # A rollback must not delete pouches a child already owns or was promised.
    operations = [migrations.RunPython(add_random_pouches, migrations.RunPython.noop)]
