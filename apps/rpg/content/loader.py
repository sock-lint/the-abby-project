"""RPG content pack loader.

Reads a content pack (directory of YAML files) and idempotently upserts
RPG catalog rows: skill categories/subjects/skills/prerequisites, badges,
potion types, pet species (auto-materializing eggs + potion items),
free-form items, drop-table entries, quest definitions + reward items,
and rewards.

Definitions are upserted only. Unsupported companion acquisition configuration
is reconciled after loading; saved identities, ownership and promises remain.

Entry points:
    ContentPack(path).load(stdout=None, dry_run=False, namespace="")

Used by:
- ``apps.rpg.management.commands.loadrpgcontent`` (CLI)
- ``apps.projects.management.commands.seed_data`` (dev seed)
- tests (``apps/rpg/tests/test_content_loader.py``)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from django.db import transaction


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
    retired: dict[str, int] = field(default_factory=dict)

    def bump(self, kind: str, key: str, amount: int = 1) -> None:
        bucket = getattr(self, kind)
        if amount:
            bucket[key] = bucket.get(key, 0) + amount

    def as_lines(self) -> list[str]:
        lines = []
        for kind in ("created", "updated", "skipped", "retired"):
            bucket = getattr(self, kind)
            for key, count in sorted(bucket.items()):
                lines.append(f"  {kind:>8} {key}: {count}")
        return lines


class ContentPack:
    """Load an RPG content pack directory.

    ``path`` is a directory containing any subset of the FILES above.
    ``namespace`` prefixes every slug (useful for third-party packs).
    """

    def __init__(self, path: Path | str, namespace: str = "", *, pack_key=None, family=None, parsed_content=None):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ContentPackError(f"Pack directory not found: {self.path}")
        self.namespace = namespace
        self.stats = LoadStats()
        self.parsed_content = parsed_content
        self.pack_key = pack_key
        self.family = family
        self.seen_entries = set()
        # Unkeyed (deploy-time) loads report entries they leave unchanged
        # here instead of failing: they run before gunicorn starts.
        self.warnings: list[str] = []

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
        # A baseline reload and a reviewed publication share one catalog lock.
        # Otherwise a loader could read "no override", wait on an upsert, and
        # overwrite an override that committed during that wait.
        from .publication import _catalog_lock
        _catalog_lock()
        parsed = self.parsed_content if self.parsed_content is not None else self._parse_all()
        from .validation import validate_content
        validate_content(parsed, strict=self.pack_key is not None)

        write = _writer(stdout)
        if dry_run:
            write("[dry-run] parsed successfully; no changes committed")

        # Inner savepoint so the same code path handles both dry-run
        # (rollback) and commit. The outer @transaction.atomic commits
        # whatever's left after this savepoint is rolled back or released.
        sid = transaction.savepoint()
        try:
            # Freeze accepted pre-cutover item links before authored quest
            # upserts can change quantities; the dry-run savepoint rolls back.
            from apps.quests.reward_items import freeze_legacy_quest_promises
            if self.pack_key:
                from apps.rpg.models import ContentPackEntry
                definition_ids = ContentPackEntry.objects.filter(pack=self.pack_key,
                    model_label="quests.questdefinition").values_list("object_id", flat=True)
                frozen = freeze_legacy_quest_promises(definition_ids=definition_ids)
                self.stats.bump("skipped", "accepted_promises_preserved", len(frozen))
            else:
                freeze_legacy_quest_promises()
            self._load_skill_tree(parsed.get("skill_tree"), write)
            self._load_badges(parsed.get("badges"), write)
            self._load_potion_types(parsed.get("potion_types"), write)
            self._load_pet_species(parsed.get("pet_species"), write)
            self._load_items(parsed.get("items"), write)
            self._load_drops(parsed.get("drops"), write)
            self._load_quests(parsed.get("quests"), write)
            self._load_rewards(parsed.get("rewards"), write)
            if self.pack_key:
                self._reconcile_owned_offers()
            else:
                from apps.rpg.companion_catalog import reconcile_companion_offers
                reconciled = reconcile_companion_offers()
                self.stats.bump("retired", "companion_drop", reconciled["drops_removed"])
                self.stats.bump("retired", "companion_shop_offer", reconciled["rewards_deactivated"])

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
        for warning in self.warnings:
            write(f"  warning: {warning}")
        return self.stats

    def _reconcile_owned_offers(self):
        from django.apps import apps
        from apps.rpg.models import ContentPackEntry
        for claim in ContentPackEntry.objects.filter(pack=self.pack_key):
            if (claim.kind, claim.key) in self.seen_entries:
                continue
            model = apps.get_model(claim.model_label)
            if claim.kind == "reward":
                obj = model.objects.filter(pk=claim.object_id, family=self.family).first()
                if obj and obj.is_active:
                    obj.is_active = False
                    obj.save(update_fields=["is_active"])
                    self.stats.bump("retired", "shop_offer")
            elif claim.kind == "droptable":
                model.objects.filter(pk=claim.object_id).delete()
                claim.delete()
                self.stats.bump("retired", "drop")
            else:
                # Definitions can own saved inventory, achievements or promises.
                # Retaining is explicit in the reviewed plan; never cascade-delete them.
                self.stats.bump("skipped", f"retained_{claim.kind}")

    def _resolved_quest_skill_tags(self, entry):
        from apps.achievements.models import Skill
        resolved = []
        seen = set()
        for tag in entry.get("skill_tags") or []:
            reference = tag if isinstance(tag, str) else tag["skill"]
            weight = 1 if isinstance(tag, str) else int(tag.get("weight", 1))
            if not isinstance(reference, str) or not reference:
                raise ContentPackError("Quest skill references must be nonempty names.")
            if "::" in reference:
                category, name = reference.split("::", 1)
                matches = list(Skill.objects.filter(category__name=category, name=name))
            else:
                matches = list(Skill.objects.filter(name=reference))
            if len(matches) != 1:
                raise ContentPackError(f"quest {entry['name']!r} skill_tag references unknown or ambiguous skill {reference!r}; use Category::Skill Name.")
            skill = matches[0]
            if skill.pk in seen:
                raise ContentPackError("Quest skill tags must reference different skills.")
            seen.add(skill.pk)
            resolved.append((skill, weight))
        return resolved

    def _protect_active_quest(self, quest, defaults, entry):
        active, changed = self._active_quest_changes(quest, defaults, entry)
        if changed:
            raise ContentPackError(f"Cannot change {', '.join(changed)} while {active} active legacy quest(s) retain these rules and rewards. Author a new stable entry/version with a distinct name for future content.")
        self.stats.bump("skipped", "protected_active_legacy_quests", active)

    def _active_quest_changes(self, quest, defaults, entry):
        """Return (active legacy quest count, accepted fields this load would change)."""
        from apps.quests.models import Quest
        active = list(Quest.objects.select_for_update(of=("self",)).filter(
            definition=quest, status=Quest.Status.ACTIVE).values_list("pk", flat=True))
        if not active:
            return 0, []
        fields =("quest_type", "target_value", "duration_days", "trigger_filter",
                  "coin_reward", "xp_reward", "is_repeatable", "required_badge")
        changed = []
        for field_name in fields:
            if field_name not in defaults:
                continue
            old, proposed = getattr(quest, field_name), defaults[field_name]
            if getattr(old, "pk", old) != getattr(proposed, "pk", proposed):
                changed.append(field_name)
        if entry.get("skill_tags") is not None:
            current_tags = sorted(quest.skill_tags.values_list("skill_id", "xp_weight"))
            proposed_tags = sorted((skill.pk, weight) for skill, weight in self._resolved_quest_skill_tags(entry))
            if current_tags != proposed_tags:
                changed.append("skill_tags")
        return len(active), changed

    def _upsert(self, model, *, defaults, entry=None, **lookup):
        """Only a pack's previously claimed stable IDs can update existing rows."""
        if model._meta.label_lower == "rpg.itemdefinition":
            from .workbench import preserved_loader_entry
            override = preserved_loader_entry(model._meta.label_lower, lookup, pack_key=self.pack_key, entry=entry)
            if override:
                self.stats.bump("skipped", "database_authored_item")
                return model.objects.get(pk=override.object_id), False
        if not self.pack_key:
            if model._meta.label_lower == "quests.questdefinition":
                # Bundled quests predate stable publication claims. Their
                # global scope is part of the lookup: a family's identically
                # named template must never be adopted or rewritten, even if
                # its legacy is_system flag is true.
                lookup = {**lookup, "is_system": defaults["is_system"], "created_by": None}
                # This load runs before gunicorn on every container start, so
                # a quest it cannot safely update is left unchanged and
                # reported. Failing here would keep the whole app down.
                matches = list(model.objects.select_for_update(no_key=True).filter(**lookup)[:2])
                skip = None
                if len(matches) > 1:
                    skip = ("ambiguous_global_quest",
                            f"Left global quest {lookup['name']!r} unchanged: more than one definition matches; reconcile them to apply bundled changes.")
                elif matches:
                    from apps.rpg.models import ContentPackEntry
                    quest = matches[0]
                    owner = ContentPackEntry.objects.filter(
                        model_label=model._meta.label_lower, object_id=quest.pk).first()
                    if owner:
                        skip = ("pack_owned_quest",
                                f"Left quest {quest.name!r} unchanged: it is owned by {owner.pack}.")
                    else:
                        active, changed = self._active_quest_changes(quest, defaults, entry or {})
                        if changed:
                            skip = ("protected_active_legacy_quest",
                                    f"Left quest {quest.name!r} unchanged: {active} active legacy quest(s) retain its accepted {', '.join(changed)}; the bundled change applies once they end.")
                        else:
                            self.stats.bump("skipped", "protected_active_legacy_quests", active)
                if skip:
                    self.stats.bump("skipped", skip[0])
                    self.warnings.append(skip[1])
                    return None, False
            return model.objects.update_or_create(defaults=defaults, **lookup)
        import json
        from django.core.exceptions import ValidationError
        from apps.rpg.models import ContentPackEntry
        kind = model._meta.model_name
        def stable_value(value):
            if not hasattr(value, "_meta"):
                return value
            owner = ContentPackEntry.objects.filter(model_label=value._meta.label_lower, object_id=value.pk).first()
            return f"{owner.pack}/{owner.kind}/{owner.key}" if owner else value.pk
        identity = {key: stable_value(value) for key, value in lookup.items()}
        stable_id = (entry or {}).get("id") if kind in {"badge", "questdefinition", "reward"} else None
        key = str(stable_id) if stable_id else json.dumps(identity, sort_keys=True, separators=(",", ":"))
        if kind == "reward":
            key = f"family:{self.family.pk}:{key}"
        if len(key) > 200:
            raise ContentPackError("Entry identity exceeds 200 characters; supply a short stable id.")
        self.seen_entries.add((kind, key))
        claim = ContentPackEntry.objects.filter(pack=self.pack_key, kind=kind, key=key).first()
        if claim:
            if claim.model_label != model._meta.label_lower:
                raise ContentPackError("Pack identity changed model type.")
            try:
                obj = model.objects.select_for_update(no_key=True).get(pk=claim.object_id)
            except model.DoesNotExist:
                raise ContentPackError(f"Owned {kind} {key} is missing; reconcile its publication history.") from None
            # Prevent a stable ID rename from colliding with someone else's natural key.
            if model.objects.filter(**lookup).exclude(pk=obj.pk).exists():
                raise ContentPackError(f"{kind} display/natural key collides with existing content.")
            if kind == "questdefinition":
                self._protect_active_quest(obj, defaults, entry or {})
            for field_name, value in {**lookup, **defaults}.items():
                setattr(obj, field_name, value)
            created = False
        else:
            if model.objects.filter(**lookup).exists():
                raise ContentPackError(f"Unowned {kind} collision: existing content must be explicitly migrated, never adopted by name.")
            obj = model(**lookup, **defaults)
            created = True
        if kind == "reward":
            from apps.rewards.availability import reward_is_available
            if obj.fulfillment_kind != "real_world" and obj.item_definition_id is None:
                raise ContentPackError("Digital shop rewards require an item_definition.")
            if obj.is_active and not reward_is_available(obj):
                raise ContentPackError("Shop item is unavailable for new acquisition; retain it as an inactive offer.")
        # Icons are optional presentation in pack schemas; provide a generic fallback.
        if hasattr(obj, "icon") and not obj.icon:
            obj.icon = "🎁"
        try:
            # Empty parameter objects are valid for parameterless badge criteria;
            # their schema was checked before loading (JSONField.blank is False).
            obj.full_clean(exclude=["criteria_value"] if kind == "badge" else None)
        except ValidationError as error:
            raise ContentPackError(f"{kind}: {'; '.join(error.messages)}") from error
        obj.save()
        if not claim:
            ContentPackEntry.objects.create(pack=self.pack_key, family=self.family, kind=kind, key=key,
                model_label=model._meta.label_lower, object_id=obj.pk)
        return obj, created

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
        if prefix == "meshtint-" and slug.startswith(prefix):
            return slug
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
            obj, created = self._upsert(SkillCategory, entry=entry,
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
            obj, created = self._upsert(Subject, entry=entry,
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
            obj, created = self._upsert(Skill, entry=entry,
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
            _, created = self._upsert(Badge, entry=entry,
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
            if slug.startswith("meshtint-"):
                raise ContentPackError("Prepared companions reuse global Base; namespaced potion definitions are forbidden")
            defaults = {
                "name": entry["name"],
                "sprite_key": entry.get("sprite_key", ""),
                "color_hex": entry.get("color_hex", "#8B7355"),
                "rarity": entry.get("rarity", "common"),
                "description": entry.get("description", ""),
            }
            potion, created = self._upsert(PotionType, entry=entry,
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
            _, item_created = self._upsert(ItemDefinition, entry=entry,
                slug=item_slug, defaults=item_defaults,
            )
            self.stats.bump("created" if item_created else "updated", "potion_item")

    # ---- pet species + auto egg items + food FKs -------------------------

    def _load_pet_species(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.pets.models import PetSpecies, PotionType
        from apps.rpg.models import ItemDefinition
        from apps.pets.roster import FAMILIES
        from apps.rpg.companion_catalog import CompanionCatalogCollision, check_prepared_identity_collisions

        try:
            check_prepared_identity_collisions()
        except CompanionCatalogCollision as exc:
            raise ContentPackError(str(exc)) from exc

        entries = data.get("species", []) or []
        normalized = set()
        names = set()
        for entry in entries:
            slug = self._ns(entry["slug"])
            if slug in normalized:
                raise ContentPackError(f"duplicate normalized pet species slug {slug!r}")
            normalized.add(slug)
            name = entry["name"].casefold()
            if name in names:
                raise ContentPackError(f"pet species display-name collision for {slug!r}")
            names.add(name)
            collision = PetSpecies.objects.filter(name__iexact=entry["name"]).exclude(slug=slug).first()
            if collision:
                raise ContentPackError(f"pet species id={collision.pk} display-name collision for {slug!r}; retain the existing identity")
            if slug.startswith("meshtint-"):
                family = FAMILIES.get(slug)
                if family is None:
                    raise ContentPackError(f"Unknown prepared companion identity {slug!r}")
                if entry.get("available_potions") != ["base"]:
                    raise ContentPackError(f"Prepared companion {slug!r} requires explicit global Base only")
                if entry["name"] != family["name"] or entry.get("sprite_key") != family["sprite_key"]:
                    raise ContentPackError(f"Prepared companion identity collision for {slug!r}")
                existing = PetSpecies.objects.filter(slug=slug).first()
                if existing and (existing.name != family["name"] or existing.sprite_key != family["sprite_key"]):
                    raise ContentPackError(f"Prepared companion id={existing.pk} database identity collision for {slug!r}")
                egg = ItemDefinition.objects.filter(slug=family["egg"]["item_slug"]).first()
                if egg:
                    metadata = egg.metadata if isinstance(egg.metadata, dict) else {}
                    if (existing is None or egg.item_type != "egg" or egg.pet_species_id != existing.pk
                            or metadata.get("species") != slug):
                        raise ContentPackError(f"Prepared egg id={egg.pk} identity collision for {slug!r}")

        # Preload potions by slug for available_potions M2M.
        potions_by_slug = {p.slug: p for p in PotionType.objects.all() if p.slug}

        for entry in entries:
            slug = self._ns(entry["slug"])
            defaults = {
                "name": entry["name"],
                "icon": entry.get("icon", ""),
                "sprite_key": entry.get("sprite_key", ""),
                "description": entry.get("description", ""),
                "food_preference": entry.get("food_preference", ""),
                "rarity": entry.get("egg_rarity", "common"),
            }
            species, created = self._upsert(PetSpecies, entry=entry,
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
                    lookup = ps if slug in FAMILIES else self._ns(ps)
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
                "metadata": {"species": species.slug},
                "pet_species": species,
                "description": entry.get("description", ""),
            }
            _, egg_created = self._upsert(ItemDefinition, entry=entry,
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
            from .workbench import preserved_loader_entry
            if preserved_loader_entry("rpg.itemdefinition", {"slug": slug}, pack_key=self.pack_key, entry=entry):
                self.stats.bump("skipped", "database_authored_item")
                continue
            item_type = entry["item_type"]
            if slug.startswith("meshtint-") and item_type in {"egg", "potion"}:
                raise ContentPackError("Prepared eggs must be generated from species; reuse the global Base potion")
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
            _, created = self._upsert(ItemDefinition, entry=entry,
                slug=slug, defaults=defaults,
            )
            self.stats.bump("created" if created else "updated", f"item_{item_type}")

    # ---- drop tables ---------------------------------------------------

    def _load_drops(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.rpg.constants import TriggerType
        from apps.rpg.models import DropTable, ItemDefinition
        from apps.rpg.catalog_support import item_is_available

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
                    if item.item_type in {"egg", "potion"} and not item_is_available(item):
                        continue
                    if isinstance(item.metadata, dict) and item.metadata.get("no_random_drop") is True:
                        continue
                    _, created = self._upsert(DropTable,
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
                    if item.item_type in {"egg", "potion"} and not item_is_available(item):
                        continue
                    # Earned-only cosmetics must not enter global macros on a
                    # later seed reload, before their chapter is completed.
                    if isinstance(item.metadata, dict) and item.metadata.get("no_random_drop") is True:
                        continue
                    w = int(
                        weight_by_rarity.get(item.rarity, 0) if weight_by_rarity else (flat_weight or 1)
                    )
                    _, created = self._upsert(DropTable,
                        trigger_type=trigger, item=item,
                        defaults={"weight": w, "min_level": min_level},
                    )
                    self.stats.bump("created" if created else "updated", "drop")

    # ---- quests --------------------------------------------------------

    def _load_quests(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.achievements.models import Badge
        from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
        from apps.rpg.models import ItemDefinition

        for entry in data.get("quests", []) or []:
            from .workbench import preserved_loader_entry
            if preserved_loader_entry("quests.questdefinition", {"name": entry["name"]}, pack_key=self.pack_key, entry=entry):
                self.stats.bump("skipped", "database_authored_quest")
                continue
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
            quest, created = self._upsert(QuestDefinition, entry=entry,
                name=entry["name"], defaults=defaults,
            )
            if quest is None:
                # Left unchanged by an unkeyed load; keep its links as well.
                continue
            self.stats.bump("created" if created else "updated", "quest")

            # Reconcile future links after freezing accepted promises above.
            desired_reward_ids = []
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
                desired_reward_ids.append(item.pk)
                _, r_created = QuestRewardItem.objects.update_or_create(
                    quest_definition=quest, item=item,
                    defaults={"quantity": int(reward.get("quantity", 1))},
                )
                self.stats.bump("created" if r_created else "updated", "quest_reward")

            if self.pack_key:
                removed, _ = QuestRewardItem.objects.filter(quest_definition=quest).exclude(item_id__in=desired_reward_ids).delete()
                self.stats.bump("retired", "quest_reward", removed)

            # Resolve once using the same identities checked by the active-promise guard.
            if entry.get("skill_tags") is not None:
                tags = self._resolved_quest_skill_tags(entry)
                QuestSkillTag.objects.filter(quest_definition=quest).delete()
                for skill, weight in tags:
                    _, created = QuestSkillTag.objects.get_or_create(
                        quest_definition=quest, skill=skill, defaults={"xp_weight": weight})
                    self.stats.bump("created" if created else "updated", "quest_skill_tag")

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

            if self.pack_key and self.family is None:
                raise ContentPackError("Shop rewards require an explicit destination family.")
            reward_scope = {"family": self.family} if self.family is not None else {}
            _, created = self._upsert(Reward, entry=entry,
                name=entry["name"], **reward_scope, defaults=defaults,
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
