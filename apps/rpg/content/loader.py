"""RPG content pack loader.

Reads a content pack (directory of YAML files) and idempotently upserts
RPG catalog rows: skill categories/subjects/skills/prerequisites, badges,
potion types, pet species (auto-materializing eggs + potion items),
free-form items, drop-table entries, quest definitions + reward items,
and rewards.

Upserts only — never deletes. Safe to run repeatedly.

Entry points:
    ContentPack(path).load(stdout=None, dry_run=False, namespace="")

Used by:
- ``apps.rpg.management.commands.loadrpgcontent`` (CLI)
- ``apps.projects.management.commands.seed_data`` (dev seed)
- tests (``apps/rpg/tests/test_content_loader.py``)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import yaml
from django.db import transaction
from django.utils.text import slugify


# File names inside a pack (all optional).
FILES = {
    "skill_tree": "skill_tree.yaml",
    "badges": "badges.yaml",
    "potion_types": "potion_types.yaml",
    "pet_species": "pet_species.yaml",
    "items": "items.yaml",
    "drops": "drops.yaml",
    "quests": "quests.yaml",
    "rewards": "rewards.yaml",
}


class ContentPackError(ValueError):
    """Raised when a pack is malformed or references missing content."""


@dataclass
class LoadStats:
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def bump(self, kind: str, key: str) -> None:
        bucket = getattr(self, kind)
        bucket[key] = bucket.get(key, 0) + 1

    def as_lines(self) -> list[str]:
        lines = []
        for kind in ("created", "updated", "skipped"):
            bucket = getattr(self, kind)
            for key, count in sorted(bucket.items()):
                lines.append(f"  {kind:>8} {key}: {count}")
        return lines


class ContentPack:
    """Load an RPG content pack directory.

    ``path`` is a directory containing any subset of the FILES above.
    ``namespace`` prefixes every slug (useful for third-party packs).
    """

    def __init__(self, path: Path | str, namespace: str = ""):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ContentPackError(f"Pack directory not found: {self.path}")
        self.namespace = namespace
        self.stats = LoadStats()

    # ---- public API ----------------------------------------------------

    @transaction.atomic
    def load(self, stdout=None, dry_run: bool = False) -> LoadStats:
        """Parse, validate, and upsert every content file present.

        Wrapped in ``transaction.atomic`` so the savepoint below has an
        active outer transaction to nest inside. Without this wrapper,
        callers that aren't already inside a transaction (e.g. MCP tool
        handlers hitting ``load()`` directly) would see ``dry_run=True``
        silently leak writes — ``transaction.savepoint()`` is a no-op
        outside of an atomic block.
        """
        parsed = self._parse_all()

        write = _writer(stdout)
        if dry_run:
            write("[dry-run] parsed successfully; no changes committed")

        # Inner savepoint so the same code path handles both dry-run
        # (rollback) and commit. The outer @transaction.atomic commits
        # whatever's left after this savepoint is rolled back or released.
        sid = transaction.savepoint()
        try:
            self._load_skill_tree(parsed.get("skill_tree"), write)
            self._load_badges(parsed.get("badges"), write)
            self._load_potion_types(parsed.get("potion_types"), write)
            self._load_pet_species(parsed.get("pet_species"), write)
            self._load_items(parsed.get("items"), write)
            self._load_drops(parsed.get("drops"), write)
            self._load_quests(parsed.get("quests"), write)
            self._load_rewards(parsed.get("rewards"), write)

            if dry_run:
                transaction.savepoint_rollback(sid)
                write("[dry-run] rolled back")
            else:
                transaction.savepoint_commit(sid)
        except Exception:
            transaction.savepoint_rollback(sid)
            raise

        for line in self.stats.as_lines():
            write(line)
        return self.stats

    # ---- parsing -------------------------------------------------------

    def _parse_all(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, filename in FILES.items():
            filepath = self.path / filename
            if not filepath.exists():
                continue
            try:
                with filepath.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                raise ContentPackError(f"{filepath}: invalid YAML — {exc}") from exc
            if not isinstance(data, dict):
                raise ContentPackError(f"{filepath}: top level must be a mapping")
            out[key] = data
        return out

    # ---- namespace helper ----------------------------------------------

    def _ns(self, slug: str) -> str:
        """Apply namespace prefix to a slug."""
        if not self.namespace:
            return slug
        prefix = self.namespace
        if not prefix.endswith("-"):
            prefix = f"{prefix}-"
        return f"{prefix}{slug}"

    # ---- skill tree ----------------------------------------------------

    def _load_skill_tree(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.achievements.models import Skill, SkillPrerequisite, Subject
        from apps.achievements.models import SkillCategory

        # Categories
        cat_by_name: dict[str, Any] = {}
        for entry in data.get("categories", []) or []:
            name = entry["name"]
            defaults = {
                "icon": entry.get("icon", ""),
                "color": entry.get("color", "#888888"),
                "description": entry.get("description", ""),
            }
            obj, created = SkillCategory.objects.update_or_create(
                name=name, defaults=defaults,
            )
            cat_by_name[name] = obj
            self.stats.bump("created" if created else "updated", "skill_category")

        # Subjects (grouping tier between Category and Skill). Unique per category.
        subject_by_key: dict[str, Any] = {}
        for entry in data.get("subjects", []) or []:
            cat_name = entry["category"]
            if cat_name not in cat_by_name:
                raise ContentPackError(
                    f"subject {entry['name']!r} references unknown category {cat_name!r}"
                )
            defaults = {
                "icon": entry.get("icon", ""),
                "order": entry.get("order", 0),
                "description": entry.get("description", ""),
            }
            obj, created = Subject.objects.update_or_create(
                name=entry["name"], category=cat_by_name[cat_name],
                defaults=defaults,
            )
            subject_by_key[f"{cat_name}::{entry['name']}"] = obj
            self.stats.bump("created" if created else "updated", "subject")

        # Skills (category resolved by name; skill has composite unique (category, name))
        skill_by_key: dict[str, Any] = {}
        skill_prereqs: list[dict] = []
        for entry in data.get("skills", []) or []:
            cat_name = entry["category"]
            if cat_name not in cat_by_name:
                raise ContentPackError(
                    f"skill {entry['name']!r} references unknown category {cat_name!r}"
                )
            defaults = {
                "icon": entry.get("icon", ""),
                "level_names": entry.get("levels", {}),
                "is_locked_by_default": entry.get("locked", False),
                "order": entry.get("order", 0),
                "description": entry.get("description", ""),
            }
            subject_name = entry.get("subject")
            if subject_name:
                subject_key = f"{cat_name}::{subject_name}"
                subject = subject_by_key.get(subject_key)
                if not subject:
                    raise ContentPackError(
                        f"skill {entry['name']!r} references unknown subject "
                        f"{subject_name!r} in category {cat_name!r}"
                    )
                defaults["subject"] = subject
            obj, created = Skill.objects.update_or_create(
                name=entry["name"], category=cat_by_name[cat_name],
                defaults=defaults,
            )
            skill_by_key[f"{cat_name}::{entry['name']}"] = obj
            skill_by_key[entry["name"]] = obj  # allow unscoped lookups
            self.stats.bump("created" if created else "updated", "skill")
            for prereq in entry.get("prereqs", []) or []:
                skill_prereqs.append({
                    "category": cat_name,
                    "skill_name": entry["name"],
                    "requires": prereq,
                })

        # Prerequisites (after all skills exist)
        for p in skill_prereqs:
            skill = skill_by_key[f"{p['category']}::{p['skill_name']}"]
            req = p["requires"]
            # Accept: "Skill Name" (same category) or "Category::Skill Name"
            if isinstance(req, dict):
                name = req["skill"]
                level = int(req.get("level", 2))
            else:
                name = req
                level = 2
            if "::" in name:
                req_skill = skill_by_key.get(name)
            else:
                req_skill = skill_by_key.get(f"{p['category']}::{name}")
            if not req_skill:
                raise ContentPackError(
                    f"skill {p['skill_name']!r} references unknown prereq {name!r}"
                )
            _, created = SkillPrerequisite.objects.update_or_create(
                skill=skill, required_skill=req_skill,
                defaults={"required_level": level},
            )
            self.stats.bump("created" if created else "updated", "skill_prereq")

    # ---- badges --------------------------------------------------------

    def _load_badges(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.achievements.models import Badge

        for entry in data.get("badges", []) or []:
            defaults = {
                "description": entry.get("description", ""),
                "icon": entry.get("icon", ""),
                "criteria_type": entry["criteria_type"],
                "criteria_value": entry.get("criteria_value", {}),
                "xp_bonus": entry.get("xp_bonus", 0),
                "rarity": entry.get("rarity", "common"),
                "award_coins": bool(entry.get("award_coins", True)),
            }
            _, created = Badge.objects.update_or_create(
                name=entry["name"], defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", "badge")

    # ---- potion types + auto potion items -------------------------------

    def _load_potion_types(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.pets.models import PotionType
        from apps.rpg.models import ItemDefinition

        for entry in data.get("potions", []) or []:
            slug = self._ns(entry["slug"])
            defaults = {
                "name": entry["name"],
                "sprite_key": entry.get("sprite_key", ""),
                "color_hex": entry.get("color_hex", "#8B7355"),
                "rarity": entry.get("rarity", "common"),
                "description": entry.get("description", ""),
            }
            potion, created = PotionType.objects.update_or_create(
                slug=slug, defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", "potion_type")

            # Auto-materialize a potion ItemDefinition named "<Name> Potion".
            item_slug = self._ns(f"{entry['slug']}-potion")
            item_defaults = {
                "name": entry.get("item_name", f"{entry['name']} Potion"),
                "icon": entry.get("item_icon", "🧪"),
                "sprite_key": entry.get("sprite_key", ""),
                "item_type": ItemDefinition.ItemType.POTION,
                "rarity": entry.get("rarity", "common"),
                "coin_value": entry.get("coin_value", 2),
                "metadata": {
                    "variant": entry["slug"],
                    "color": entry.get("color_hex", "#8B7355"),
                },
                "potion_type": potion,
                "description": entry.get("description", ""),
            }
            _, item_created = ItemDefinition.objects.update_or_create(
                slug=item_slug, defaults=item_defaults,
            )
            self.stats.bump("created" if item_created else "updated", "potion_item")

    # ---- pet species + auto egg items + food FKs -------------------------

    def _load_pet_species(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.pets.models import PetSpecies, PotionType
        from apps.rpg.models import ItemDefinition

        # Preload potions by slug for available_potions M2M.
        potions_by_slug = {p.slug: p for p in PotionType.objects.all() if p.slug}

        for entry in data.get("species", []) or []:
            slug = self._ns(entry["slug"])
            defaults = {
                "name": entry["name"],
                "icon": entry.get("icon", ""),
                "sprite_key": entry.get("sprite_key", ""),
                "description": entry.get("description", ""),
                "food_preference": entry.get("food_preference", ""),
            }
            species, created = PetSpecies.objects.update_or_create(
                slug=slug, defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", "pet_species")

            # Wire up available potions. When YAML omits the list, default
            # to every potion currently in the catalog (matches pre-pack
            # behavior where any egg+potion combo was hatchable).
            raw_potions = entry.get("available_potions")
            if raw_potions is None:
                potion_objs = list(potions_by_slug.values())
            else:
                potion_objs = []
                for ps in raw_potions or []:
                    lookup = self._ns(ps)
                    potion = potions_by_slug.get(lookup) or potions_by_slug.get(ps)
                    if not potion:
                        raise ContentPackError(
                            f"pet species {entry['slug']!r} references unknown potion {ps!r}"
                        )
                    potion_objs.append(potion)
            species.available_potions.set(potion_objs)

            # Auto-materialize an egg ItemDefinition.
            # Eggs use the generic "big-egg" sprite by default so they read as
            # eggs in the inventory; the species sprite is reserved for the
            # hatched pet on Companions.jsx. YAML can override via egg_sprite_key.
            egg_slug = self._ns(f"{entry['slug']}-egg")
            egg_defaults = {
                "name": entry.get("egg_name", f"{entry['name']} Egg"),
                "icon": entry.get("egg_icon", "🥚"),
                "sprite_key": entry.get("egg_sprite_key", "big-egg"),
                "item_type": ItemDefinition.ItemType.EGG,
                "rarity": entry.get("egg_rarity", "common"),
                "coin_value": entry.get("egg_coin_value", 3),
                "metadata": {"species": entry["slug"]},
                "pet_species": species,
                "description": entry.get("description", ""),
            }
            _, egg_created = ItemDefinition.objects.update_or_create(
                slug=egg_slug, defaults=egg_defaults,
            )
            self.stats.bump("created" if egg_created else "updated", "egg_item")

    # ---- free-form items (food / cosmetics / coin_pouch / etc.) ----------

    def _load_items(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.pets.models import PetSpecies
        from apps.rpg.models import ItemDefinition

        species_by_slug: dict[str, Any] = {}

        def resolve_species(slug: str) -> Any:
            if slug in species_by_slug:
                return species_by_slug[slug]
            try:
                obj = PetSpecies.objects.get(slug=self._ns(slug))
            except PetSpecies.DoesNotExist:
                try:
                    obj = PetSpecies.objects.get(slug=slug)
                except PetSpecies.DoesNotExist as exc:
                    raise ContentPackError(
                        f"item references unknown pet species {slug!r}"
                    ) from exc
            species_by_slug[slug] = obj
            return obj

        for entry in data.get("items", []) or []:
            slug = self._ns(entry["slug"])
            item_type = entry["item_type"]
            defaults = {
                "name": entry["name"],
                "icon": entry.get("icon", ""),
                "sprite_key": entry.get("sprite_key", ""),
                "item_type": item_type,
                "rarity": entry.get("rarity", "common"),
                "coin_value": entry.get("coin_value", 0),
                "metadata": entry.get("metadata", {}),
                "description": entry.get("description", ""),
            }
            # Optional typed FKs
            if "food_species" in entry and entry["food_species"]:
                defaults["food_species"] = resolve_species(entry["food_species"])
            _, created = ItemDefinition.objects.update_or_create(
                slug=slug, defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", f"item_{item_type}")

    # ---- drop tables ---------------------------------------------------

    def _load_drops(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.rpg.constants import TriggerType
        from apps.rpg.models import DropTable, ItemDefinition

        valid_triggers = {t.value for t in TriggerType}

        def _require_trigger(trigger: str, source: str) -> str:
            if trigger not in valid_triggers:
                raise ContentPackError(
                    f"drops.{source} references unknown trigger_type {trigger!r}. "
                    f"Valid triggers: {sorted(valid_triggers)}"
                )
            return trigger

        # Support two shapes:
        #   rules: [{trigger: clock_out, item_slugs: [...], weight: 5, min_level: 0}]
        #   or a convenience macro:
        #   macros:
        #     - triggers: [clock_out, chore_complete]
        #       item_type: egg
        #       weight_by_rarity: {common: 10, uncommon: 5, ...}

        rules = data.get("rules", []) or []
        for rule in rules:
            triggers = rule.get("triggers") or [rule.get("trigger")]
            weight = int(rule.get("weight", 1))
            min_level = int(rule.get("min_level", 0))
            item_slugs = rule.get("item_slugs", []) or []
            for trigger in filter(None, triggers):
                _require_trigger(trigger, "rules")
                for raw_slug in item_slugs:
                    slug = self._ns(raw_slug)
                    try:
                        item = ItemDefinition.objects.get(slug=slug)
                    except ItemDefinition.DoesNotExist as exc:
                        raise ContentPackError(
                            f"drops.rules references unknown item slug {raw_slug!r}"
                        ) from exc
                    _, created = DropTable.objects.update_or_create(
                        trigger_type=trigger, item=item,
                        defaults={"weight": weight, "min_level": min_level},
                    )
                    self.stats.bump("created" if created else "updated", "drop")

        macros = data.get("macros", []) or []
        for macro in macros:
            triggers = macro.get("triggers") or []
            item_type = macro.get("item_type")
            item_type_prefix = macro.get("item_type_startswith")
            weight_by_rarity = macro.get("weight_by_rarity", {}) or {}
            flat_weight = macro.get("weight")
            min_level = int(macro.get("min_level", 0))

            for trigger in triggers:
                _require_trigger(trigger, "macros")

            qs = ItemDefinition.objects.all()
            if item_type:
                qs = qs.filter(item_type=item_type)
            if item_type_prefix:
                qs = qs.filter(item_type__startswith=item_type_prefix)
            # If this is a namespaced pack, only pick items from the same ns
            # (so a dragons-pack's macro doesn't sweep in the wolf eggs).
            if self.namespace:
                prefix = self.namespace
                if not prefix.endswith("-"):
                    prefix = f"{prefix}-"
                qs = qs.filter(slug__startswith=prefix)

            for trigger in triggers:
                for item in qs:
                    w = int(
                        weight_by_rarity.get(item.rarity, flat_weight or 1)
                    )
                    _, created = DropTable.objects.update_or_create(
                        trigger_type=trigger, item=item,
                        defaults={"weight": w, "min_level": min_level},
                    )
                    self.stats.bump("created" if created else "updated", "drop")

    # ---- quests --------------------------------------------------------

    def _load_quests(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.achievements.models import Badge, Skill, SkillCategory
        from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
        from apps.rpg.models import ItemDefinition

        for entry in data.get("quests", []) or []:
            defaults = {
                "description": entry.get("description", ""),
                "icon": entry.get("icon", "⚔️"),
                "sprite_key": entry.get("sprite_key", ""),
                "quest_type": entry["quest_type"],
                "target_value": int(entry["target_value"]),
                "duration_days": int(entry.get("duration_days", 7)),
                "trigger_filter": entry.get("trigger_filter", {}),
                "coin_reward": int(entry.get("coin_reward", 0)),
                "xp_reward": int(entry.get("xp_reward", 0)),
                "is_repeatable": bool(entry.get("is_repeatable", False)),
                "is_system": bool(entry.get("is_system", True)),
            }
            if "required_badge" in entry and entry["required_badge"]:
                try:
                    defaults["required_badge"] = Badge.objects.get(
                        name=entry["required_badge"]
                    )
                except Badge.DoesNotExist as exc:
                    raise ContentPackError(
                        f"quest {entry['name']!r} references unknown badge "
                        f"{entry['required_badge']!r}"
                    ) from exc
            quest, created = QuestDefinition.objects.update_or_create(
                name=entry["name"], defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", "quest")

            # Reward items (upsert, preserve existing rows)
            for reward in entry.get("reward_items", []) or []:
                item_slug = self._ns(reward["slug"])
                try:
                    item = ItemDefinition.objects.get(slug=item_slug)
                except ItemDefinition.DoesNotExist:
                    # Try without namespace (quest pack referencing core content)
                    try:
                        item = ItemDefinition.objects.get(slug=reward["slug"])
                    except ItemDefinition.DoesNotExist as exc:
                        raise ContentPackError(
                            f"quest {entry['name']!r} reward references "
                            f"unknown item {reward['slug']!r}"
                        ) from exc
                _, r_created = QuestRewardItem.objects.update_or_create(
                    quest_definition=quest, item=item,
                    defaults={"quantity": int(reward.get("quantity", 1))},
                )
                self.stats.bump("created" if r_created else "updated", "quest_reward")

            # Skill tags. Each entry is either "Category::Skill Name"
            # (disambiguated) or "Skill Name" (unique across categories).
            # Weight defaults to 1. Authored tags REPLACE existing rows so
            # a rename in YAML doesn't leave orphan tags pointing at the
            # old skill.
            skill_tags = entry.get("skill_tags")
            if skill_tags is not None:
                QuestSkillTag.objects.filter(quest_definition=quest).delete()
                for tag_entry in skill_tags or []:
                    if isinstance(tag_entry, str):
                        skill_ref = tag_entry
                        weight = 1
                    else:
                        skill_ref = tag_entry["skill"]
                        weight = int(tag_entry.get("weight", 1))
                    if "::" in skill_ref:
                        cat_name, skill_name = skill_ref.split("::", 1)
                        try:
                            skill = Skill.objects.get(
                                category__name=cat_name, name=skill_name,
                            )
                        except Skill.DoesNotExist as exc:
                            raise ContentPackError(
                                f"quest {entry['name']!r} skill_tag references "
                                f"unknown skill {skill_ref!r}"
                            ) from exc
                    else:
                        matches = list(Skill.objects.filter(name=skill_ref))
                        if not matches:
                            raise ContentPackError(
                                f"quest {entry['name']!r} skill_tag references "
                                f"unknown skill {skill_ref!r}"
                            )
                        if len(matches) > 1:
                            raise ContentPackError(
                                f"quest {entry['name']!r} skill_tag {skill_ref!r} "
                                f"matches {len(matches)} skills across categories — "
                                f"use 'Category::Skill Name' form"
                            )
                        skill = matches[0]
                    _, t_created = QuestSkillTag.objects.get_or_create(
                        quest_definition=quest, skill=skill,
                        defaults={"xp_weight": weight},
                    )
                    self.stats.bump(
                        "created" if t_created else "updated", "quest_skill_tag",
                    )

    # ---- rewards -------------------------------------------------------

    def _load_rewards(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.rewards.models import Reward
        from apps.rpg.models import ItemDefinition

        for entry in data.get("rewards", []) or []:
            defaults = {
                "description": entry.get("description", ""),
                "icon": entry.get("icon", ""),
                "cost_coins": int(entry["cost_coins"]),
                "rarity": entry.get("rarity", "common"),
                "stock": entry.get("stock"),
                "requires_parent_approval": bool(
                    entry.get("requires_parent_approval", True)
                ),
                "is_active": bool(entry.get("is_active", True)),
                "order": int(entry.get("order", 0)),
                "fulfillment_kind": entry.get(
                    "fulfillment_kind", Reward.FulfillmentKind.REAL_WORLD,
                ),
            }

            # Optional link to a loaded ItemDefinition. Accept either a
            # namespaced slug or a core slug — the loader just finished
            # upserting items for this pack, so the namespaced form is
            # usually what the author wants, but referencing an existing
            # core item (e.g. a cosmetic from initial/) should also work.
            raw_item_slug = entry.get("item_definition")
            if raw_item_slug:
                slug = self._ns(raw_item_slug)
                try:
                    defaults["item_definition"] = ItemDefinition.objects.get(
                        slug=slug,
                    )
                except ItemDefinition.DoesNotExist:
                    try:
                        defaults["item_definition"] = ItemDefinition.objects.get(
                            slug=raw_item_slug,
                        )
                    except ItemDefinition.DoesNotExist as exc:
                        raise ContentPackError(
                            f"reward {entry['name']!r} references unknown "
                            f"item_definition slug {raw_item_slug!r}"
                        ) from exc

            _, created = Reward.objects.update_or_create(
                name=entry["name"], defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", "reward")


def _writer(stdout) -> Callable[[str], None]:
    if stdout is None:
        return lambda msg: None
    if callable(stdout):
        return stdout
    return lambda msg: stdout.write(f"{msg}\n")


# Convenience function for call sites that just want the one-shot behavior.
def load_pack(
    path: Path | str, namespace: str = "", stdout=None, dry_run: bool = False,
) -> LoadStats:
    return ContentPack(path, namespace=namespace).load(
        stdout=stdout, dry_run=dry_run,
    )
