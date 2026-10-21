"""Prepare the selected Voyager policy as an inactive private Workbench draft.

This explicit operator action never simulates, publishes, edits bundled content
or changes an accepted challenge. Normal Workbench preview and publication
checks remain authoritative after preparation.
"""
from django.db import transaction

from apps.achievements.models import Skill
from apps.pets.models import PetSpecies, PotionType
from apps.pets.roster import prepared_base_potion
from apps.quests.models import QuestDefinition
from apps.rpg.catalog_support import available_pet_variants, item_is_available
from apps.rpg.models import ItemDefinition

from .loader import ContentPackError
from .publication import _catalog_lock
from .workbench import create_draft, preview_draft, save_draft
from .workbench_validation import require_actor


CURRENT_COMPANION_DESCRIPTION = (
    "Complete 3 daily Reading Adventures within 14 days. Each Adventure needs ten newly logged reading or listening minutes "
    "in your family's day. Meet a Chick with an egg, a Base potion and two Birdseed."
)
PROPOSED_COMPANION_DESCRIPTION = (
    "Complete 3 daily Reading Adventures at your own pace, with no deadline. "
    "Each Adventure needs ten newly logged reading or listening minutes in your family's day. "
    "Meet a Chick with an egg, a Base potion and two Birdseed."
)

CURRENT_DESCRIPTION = (
    "Complete 20 daily Reading Adventures within 45 days. Ten newly logged reading or listening minutes "
    "counts once each family-local day. Celebrate your reading rhythm with the Bookworm title."
)
PROPOSED_DESCRIPTION = (
    "Unlock by completing Reading Companion and reaching Reading Comprehension level 1. "
    "Complete 20 daily Reading Adventures within 84 days after this challenge opens. "
    "Each Adventure needs ten newly logged reading or listening minutes and counts once each family-local day. "
    "Earn the Bookworm title."
)
READING_FILTER = {"allowed_triggers": ["reading_logged"]}


def _unique(queryset, label):
    rows = list(queryset.select_for_update(of=("self",))[:2])
    if len(rows) != 1:
        raise ContentPackError(f"Preparation requires one unique global {label}; resolve missing or ambiguous references first.")
    return rows[0]


def _expected(obj, fields, label):
    changed = [name for name, value in fields.items() if getattr(obj, name) != value]
    if changed:
        raise ContentPackError(f"{label} differs from the reviewed baseline: {', '.join(sorted(changed))}.")


@transaction.atomic
def prepare_reading_voyager(actor):
    """Resolve exact globals, preserve rewards and return a normal reviewed draft.

    Any validation, ownership or active-legacy failure rolls back private draft
    creation too. Production use is a separate explicit operator action, never a
    startup hook; the returned preview is not simulation or publication approval.
    """
    require_actor(actor)
    _catalog_lock()
    globals_only = QuestDefinition.objects.filter(is_system=True, created_by__isnull=True)
    voyager = _unique(globals_only.filter(name="Reading Voyager"), "Reading Voyager challenge")
    companion = _unique(globals_only.filter(name="Reading Companion"), "Reading Companion challenge")
    skill = _unique(Skill.objects.filter(category__name="Language Arts", name="Reading Comprehension"),
                    "Language Arts::Reading Comprehension skill")
    title = _unique(ItemDefinition.objects.filter(slug="title-bookworm"), "title-bookworm item")
    _expected(voyager, {
        "description": CURRENT_DESCRIPTION, "quest_type": "collection", "target_value": 20,
        "duration_days": 45, "trigger_filter": READING_FILTER, "coin_reward": 0, "xp_reward": 50,
        "is_repeatable": False, "required_badge_id": None, "prerequisite_quest_id": None,
        "required_skill_id": None, "required_skill_level": 0,
    }, "Reading Voyager")
    _expected(companion, {"quest_type": "collection", "target_value": 3, "duration_days": 14,
                          "description": CURRENT_COMPANION_DESCRIPTION, "trigger_filter": READING_FILTER, "is_repeatable": False,
                          "coin_reward": 0, "xp_reward": 20, "required_badge_id": None,
                          "prerequisite_quest_id": None, "required_skill_id": None, "required_skill_level": 0},
              "Reading Companion")
    companion_rewards = list(companion.reward_items.select_related(
        "item__pet_species", "item__potion_type", "item__food_species",
    ).order_by("item__slug"))
    if [(row.item.slug, row.quantity) for row in companion_rewards] != [
        ("base-potion", 1), ("chick-egg", 1), ("food-birdseed", 2),
    ] or any(not item_is_available(row.item) for row in companion_rewards):
        raise ContentPackError("Reading Companion item rewards differ from the reviewed Chick starter promise.")
    chick = _unique(PetSpecies.objects.filter(slug="chick"), "Chick starter species")
    base = _unique(PotionType.objects.filter(slug="base"), "Base starter potion")
    starter = {row.item.slug: row.item for row in companion_rewards}
    _expected(starter["chick-egg"], {
        "item_type": ItemDefinition.ItemType.EGG, "pet_species_id": chick.pk,
        "potion_type_id": None, "food_species_id": None, "metadata": {"species": "chick"},
    }, "Reading Companion Chick Egg starter reward")
    _expected(starter["base-potion"], {
        "item_type": ItemDefinition.ItemType.POTION, "potion_type_id": base.pk,
        "pet_species_id": None, "food_species_id": None,
    }, "Reading Companion Base Potion starter reward")
    if not prepared_base_potion(starter["base-potion"]):
        raise ContentPackError("Reading Companion Base Potion starter metadata differs from the reviewed binding.")
    # Potion color is presentation. Birdseed's typed preference and common
    # five-point base nourishment are part of this reviewed reward.
    _expected(starter["food-birdseed"], {
        "item_type": ItemDefinition.ItemType.FOOD, "food_species_id": chick.pk,
        "pet_species_id": None, "potion_type_id": None, "rarity": "common",
        "metadata": {"food_type": "birdseed", "growth": 5},
    }, "Reading Companion Birdseed starter reward")
    if not available_pet_variants(chick).filter(pk=base.pk).exists():
        raise ContentPackError("Reading Companion starter ingredients must still hatch the promised Chick with Base Potion.")
    if list(companion.skill_tags.order_by("skill_id").values_list("skill_id", "xp_weight")) != [(skill.pk, 1)]:
        raise ContentPackError("Reading Companion skill rewards differ from the reviewed one-weight Reading Comprehension promise.")
    if skill.is_locked_by_default:
        raise ContentPackError("Reading Comprehension differs from the reviewed unlocked skill baseline.")
    if title.item_type != ItemDefinition.ItemType.COSMETIC_TITLE or not item_is_available(title):
        raise ContentPackError("The Bookworm reward must remain an available cosmetic title.")
    _expected(title, {"rarity": "uncommon", "coin_value": 15, "metadata": {"text": "Bookworm"}},
              "Bookworm reward")
    if list(voyager.skill_tags.order_by("skill_id").values_list("skill_id", "xp_weight")) != [(skill.pk, 1)]:
        raise ContentPackError("Reading Voyager skill rewards differ from the reviewed one-weight Reading Comprehension promise.")
    if list(voyager.reward_items.order_by("item_id").values_list("item_id", "quantity")) != [(title.pk, 1)]:
        raise ContentPackError("Reading Voyager item rewards differ from the reviewed single Bookworm title promise.")

    draft = create_draft(actor, "Untimed Reading Companion and 84-day Voyager")
    draft = save_draft(actor, draft["id"], draft["revision"], [{
        "section": "quests", "object_id": companion.pk, "key": "reading-companion",
        "values": {"duration_days": None, "description": PROPOSED_COMPANION_DESCRIPTION},
    }, {
        "section": "quests", "object_id": voyager.pk, "key": "reading-voyager",
        "values": {"prerequisite_quest": companion.pk, "required_skill": skill.pk, "required_skill_level": 1,
                   "duration_days": 84, "description": PROPOSED_DESCRIPTION},
    }])
    reviewed = preview_draft(actor, draft["id"], draft["revision"])
    return {**reviewed, "policy_id": "reading-companion-untimed-voyager-milestones-84-days", "preparation_only": True,
            "resolved_ids": {"voyager": voyager.pk, "companion": companion.pk,
                             "reading_skill": skill.pk, "bookworm_title": title.pk}}
