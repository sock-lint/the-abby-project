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
from django.db.models import Q


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
        self._created_taxonomy: dict[type, set[int]] = {}
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
        self._created_taxonomy.clear()
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
        finally:
            # A reused loader must not treat rows from an earlier load (or
            # rolled-back IDs reused later) as part of this source bootstrap.
            self._created_taxonomy.clear()

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

    def _source_reference_matches(self, model, **lookup):
        """Resolve exact current or preserved source identities, rejecting ties.

        A durable rename leaves dependent YAML unchanged. Include that source
        identity without preferring it over a conflicting new current name.
        The same catalog lock protects these reads and all following writes.
        """
        from apps.rpg.models import RPGContentOverride
        overrides = RPGContentOverride.objects.filter(model_label=model._meta.label_lower)
        for name, value in lookup.items():
            attname = model._meta.get_field(name).attname
            overrides = overrides.filter(**{f"source_lookup__{attname}": getattr(value, "pk", value)})
        if model._meta.app_label == "achievements":
            overrides = overrides.filter(values___authoring={"version": 1, "source": "mcp"})
        queryset = model.objects.all()
        if model._meta.label_lower == "quests.questdefinition":
            from apps.quests.queries import active_system_definitions
            queryset = active_system_definitions().filter(created_by__isnull=True)
        return list(queryset.filter(
            Q(**lookup) | Q(pk__in=overrides.values("object_id")),
        ).order_by("pk")[:2])

    def _qualified_skill_matches(self, reference):
        """Reject spellings shared by different category/skill pairs."""
        from apps.achievements.models import Skill, SkillCategory

        category_limit = SkillCategory._meta.get_field("name").max_length
        skill_limit = Skill._meta.get_field("name").max_length
        matches = {}
        for boundary in range(1, min(len(reference) - 1, category_limit + 1)):
            if reference[boundary:boundary + 2] != "::":
                continue
            category, name = reference[:boundary], reference[boundary + 2:]
            if not name or len(name) > skill_limit:
                continue
            categories = self._source_reference_matches(SkillCategory, name=category)
            if len(categories) > 1:
                return []
            if categories:
                for skill in self._source_reference_matches(Skill, category=categories[0], name=name):
                    matches[skill.pk] = skill
            if len(matches) > 1:
                break
        return list(matches.values())

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
                matches = self._qualified_skill_matches(reference)
            else:
                matches = self._source_reference_matches(Skill, name=reference)
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
                  "coin_reward", "xp_reward", "is_repeatable", "is_cooperative", "required_badge",
                  "prerequisite_quest", "required_skill", "required_skill_level")
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

    def _upsert_link(self, model, *, defaults, **lookup):
        """Retain ambiguous legacy links rather than guessing which row owns them."""
        matches = list(model.objects.select_for_update(no_key=True).filter(**lookup).order_by("pk")[:2])
        if len(matches) > 1:
            kind = model._meta.model_name
            message = f"Ambiguous {kind}: multiple rows match {lookup}; reconcile them before applying catalog changes."
            if self.pack_key:
                # A reviewed publication must apply its complete intended diff,
                # whereas the unkeyed deployment load must keep startup available.
                raise ContentPackError(message)
            self.stats.bump("skipped", f"ambiguous_{kind}")
            self.warnings.append(message)
            return None, False
        return model.objects.update_or_create(defaults=defaults, **lookup)

    def _upsert(self, model, *, defaults, entry=None, **lookup):
        """Only a pack's previously claimed stable IDs can update existing rows."""
        if model._meta.label_lower in {
            "achievements.skillcategory", "achievements.subject", "achievements.skill", "achievements.badge",
        }:
            from .authoring import preserved_authoring_entry
            override = preserved_authoring_entry(model._meta.label_lower, lookup, pack_key=self.pack_key, entry=entry)
            if override:
                self.stats.bump("skipped", "database_authored_" + model._meta.model_name)
                return model.objects.get(pk=override.object_id), False
        if model._meta.label_lower == "rpg.itemdefinition":
            from .workbench import preserved_loader_entry
            override = preserved_loader_entry(model._meta.label_lower, lookup, pack_key=self.pack_key, entry=entry)
            if override:
                self.stats.bump("skipped", "database_authored_item")
                return model.objects.get(pk=override.object_id), False
        if not self.pack_key:
            if model._meta.label_lower == "rpg.droptable":
                return self._upsert_link(model, defaults=defaults, **lookup)
            if model._meta.label_lower == "quests.questdefinition":
                # Bundled quests predate stable publication claims. Their
                # global scope is part of the lookup: a family's identically
                # named template must never be adopted or rewritten, even if
                # its legacy is_system flag is true.
                lookup = {**lookup, "is_system": defaults["is_system"], "created_by": None,
                          "superseded_by__isnull": True}
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
                            skip = ("deferred_active_legacy_quest_change",
                                    f"Left quest {quest.name!r} unchanged: {active} active legacy quest(s) retain its accepted {', '.join(changed)}; the bundled change applies once they end.")
                        else:
                            self.stats.bump("skipped", "protected_active_legacy_quests", active)
                if skip:
                    self.stats.bump("skipped", skip[0])
                    self.warnings.append(skip[1])
                    return None, False
            self._validate_taxonomy_links(model, model.objects.filter(**lookup).first(), {**lookup, **defaults})
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
            matches = model.objects.filter(**lookup).exclude(pk=obj.pk)
            if kind == "questdefinition":
                matches = matches.filter(superseded_by__isnull=True)
                if obj.superseded_by_id:
                    raise ContentPackError("This quest identity is a retained alias; reconcile its publication claim before editing.")
            if matches.exists():
                raise ContentPackError(f"{kind} display/natural key collides with existing content.")
            if kind == "questdefinition":
                self._protect_active_quest(obj, defaults, entry or {})
            self._validate_taxonomy_links(model, obj, {**lookup, **defaults})
            for field_name, value in {**lookup, **defaults}.items():
                setattr(obj, field_name, value)
            created = False
        else:
            if model.objects.filter(**lookup).exists():
                raise ContentPackError(f"Unowned {kind} collision: existing content must be explicitly migrated, never adopted by name.")
            self._validate_taxonomy_links(model, None, {**lookup, **defaults})
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
        if kind == "itemdefinition":
            from .workbench_validation import validate_item_runtime
            validate_item_runtime(obj)
        from .authoring import validate_source_identity
        validate_source_identity(obj)
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

    @staticmethod
    def _admit_reference(model, ids, retained=()):
        from django.core.exceptions import ValidationError
        from apps.achievements.taxonomy import validate_new_taxonomy_references
        try:
            validate_new_taxonomy_references(model, ids, retained_ids=retained)
        except ValidationError as error:
            raise ContentPackError("; ".join(error.messages)) from error

    def _validate_taxonomy_links(self, model, previous, values):
        """Source identity stays global; only newly introduced links are choices."""
        from apps.achievements.models import Skill, SkillCategory, Subject
        from apps.quests.models import QuestDefinition
        if model in (Subject, Skill):
            category = values.get("category")
            if category is not None:
                # Reconstruct a fresh archived graph atomically. Only a NEW
                # definition may link to a parent actually created by this
                # load; seeing an existing retired row in source is not enough.
                retained = ([previous.category_id] if previous else
                            self._created_taxonomy.get(SkillCategory, ()))
                self._admit_reference(SkillCategory, [category.pk], retained)
        if model is Skill and values.get("subject") is not None:
            retained = ([previous.subject_id] if previous else
                        self._created_taxonomy.get(Subject, ()))
            self._admit_reference(Subject, [values["subject"].pk], retained)
        if model is QuestDefinition:
            if values.get("required_skill") is not None:
                self._admit_reference(Skill, [values["required_skill"].pk], [previous.required_skill_id] if previous else ())
            category_id = (values.get("trigger_filter") or {}).get("skill_category_id")
            if category_id is not None:
                old_id = (previous.trigger_filter or {}).get("skill_category_id") if previous else None
                self._admit_reference(SkillCategory, [category_id], [old_id] if old_id else ())

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
        from apps.achievements.taxonomy import available_for_new_choices

        # Categories
        cat_by_name: dict[str, Any] = {}
        for entry in data.get("categories", []) or []:
            name = entry["name"]
            defaults = {
                "icon": entry.get("icon", ""),
                "color": entry.get("color", "#888888"),
                "description": entry.get("description", ""),
            }
            if "is_retired" in entry:
                defaults["is_retired"] = entry["is_retired"]
            obj, created = self._upsert(SkillCategory, entry=entry,
                name=name, defaults=defaults,
            )
            if created:
                self._created_taxonomy.setdefault(SkillCategory, set()).add(obj.pk)
            cat_by_name[name] = obj
            self.stats.bump("created" if created else "updated", "skill_category")

        # Subjects (grouping tier between Category and Skill). Unique per category.
        subject_by_key: dict[tuple[str, str], Any] = {}
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
            if "is_retired" in entry:
                defaults["is_retired"] = entry["is_retired"]
            obj, created = self._upsert(Subject, entry=entry,
                name=entry["name"], category=cat_by_name[cat_name],
                defaults=defaults,
            )
            if created:
                self._created_taxonomy.setdefault(Subject, set()).add(obj.pk)
            subject_by_key[cat_name, entry["name"]] = obj
            self.stats.bump("created" if created else "updated", "subject")

        # Skills (category resolved by name; skill has composite unique (category, name))
        skill_by_key: dict[tuple[str, str], Any] = {}
        skill_prereqs: list[dict] = []
        explicit_prereqs: dict[int, list[int]] = {}
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
            if "is_retired" in entry:
                defaults["is_retired"] = entry["is_retired"]
            subject_name = entry.get("subject")
            if subject_name:
                subject_key = (cat_name, subject_name)
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
            if created:
                self._created_taxonomy.setdefault(Skill, set()).add(obj.pk)
            skill_by_key[cat_name, entry["name"]] = obj
            self.stats.bump("created" if created else "updated", "skill")
            from .authoring import preserves_skill_prerequisites
            if preserves_skill_prerequisites(obj):
                # The direct editor saved the complete current relationship
                # set, including an explicitly empty set. YAML cannot re-add it.
                continue
            if self.pack_key and "prereqs" in entry:
                # Omission retains existing links. An explicit list replaces
                # only the relationships of this pack's own skill identity.
                explicit_prereqs[obj.pk] = []
            for prereq in entry.get("prereqs", []) or []:
                skill_prereqs.append({
                    "category": cat_name,
                    "skill_name": entry["name"],
                    "requires": prereq,
                })

        # Prerequisites (after all skills exist)
        qualified_skills = {}
        for (category, name), skill in skill_by_key.items():
            qualified_skills.setdefault(f"{category}::{name}", {})[skill.pk] = skill
        for p in skill_prereqs:
            skill = skill_by_key[p["category"], p["skill_name"]]
            req = p["requires"]
            # Accept: "Skill Name" (same category) or "Category::Skill Name"
            if isinstance(req, dict):
                name = req["skill"]
                level = int(req.get("level", 2))
            else:
                name = req
                level = 2
            if "::" in name:
                matches = qualified_skills.get(name, {})
                if len(matches) > 1:
                    raise ContentPackError(
                        f"skill {p['skill_name']!r} references ambiguous prereq {name!r}; "
                        "use an unambiguous category-qualified skill name."
                    )
                req_skill = next(iter(matches.values()), None)
            else:
                req_skill = skill_by_key.get((p["category"], name))
            if not req_skill:
                raise ContentPackError(
                    f"skill {p['skill_name']!r} references unknown prereq {name!r}"
                )
            retained = set(SkillPrerequisite.objects.filter(skill=skill).values_list("required_skill_id", flat=True))
            new_skills = self._created_taxonomy.get(Skill, ())
            if skill.pk in new_skills and req_skill.pk in new_skills and not available_for_new_choices(skill):
                # Archived prerequisite graphs may bootstrap together. An
                # active new skill still cannot choose an unavailable target.
                retained.add(req_skill.pk)
            self._admit_reference(Skill, [req_skill.pk], retained)
            _, created = SkillPrerequisite.objects.update_or_create(
                skill=skill, required_skill=req_skill,
                defaults={"required_level": level},
            )
            self.stats.bump("created" if created else "updated", "skill_prereq")
            if skill.pk in explicit_prereqs:
                explicit_prereqs[skill.pk].append(req_skill.pk)

        if explicit_prereqs:
            from apps.rpg.models import ContentPackEntry
            owned = set(ContentPackEntry.objects.filter(
                pack=self.pack_key, family=self.family, kind="skill",
                model_label=Skill._meta.label_lower, object_id__in=explicit_prereqs,
            ).values_list("object_id", flat=True))
            for skill_id in owned:
                removed, _ = SkillPrerequisite.objects.filter(skill_id=skill_id).exclude(
                    required_skill_id__in=explicit_prereqs[skill_id],
                ).delete()
                self.stats.bump("retired", "skill_prereq", removed)

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
                compatibility = (["base"], ["base", "fire", "ice"]) if slug == "meshtint-wolf" else (["base"],)
                if entry.get("available_potions") not in compatibility:
                    raise ContentPackError(f"Prepared companion {slug!r} requires explicit global Base compatibility; only Wolf may also author Fire and Ice")
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
                    drop, created = self._upsert(DropTable,
                        trigger_type=trigger, item=item,
                        defaults={"weight": weight, "min_level": min_level},
                    )
                    if drop is not None:
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
                    drop, created = self._upsert(DropTable,
                        trigger_type=trigger, item=item,
                        defaults={"weight": w, "min_level": min_level},
                    )
                    if drop is not None:
                        self.stats.bump("created" if created else "updated", "drop")

    # ---- quests --------------------------------------------------------

    def _load_quests(self, data: dict | None, write: Callable[[str], None]) -> None:
        if not data:
            return
        from apps.achievements.models import Badge
        from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
        from apps.rpg.models import ItemDefinition

        entries = list(data.get("quests", []) or [])
        # Resolve forward references in dependency order without creating
        # incomplete placeholder definitions in the runtime catalog.
        ordered, pending = [], entries[:]
        while pending:
            names = {entry["name"] for entry in pending}
            ready = [entry for entry in pending if not entry.get("prerequisite_quest") or entry["prerequisite_quest"] not in names]
            if not ready:
                raise ContentPackError("Challenge prerequisites cannot form a cycle.")
            ordered.extend(ready)
            pending = [entry for entry in pending if entry not in ready]
        for entry in ordered:
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
                "is_cooperative": bool(entry.get("is_cooperative", False)),
            }
            if "prerequisite_quest" in entry:
                reference = entry["prerequisite_quest"]
                matches = self._source_reference_matches(QuestDefinition, name=reference) if reference else []
                if reference and len(matches) != 1:
                    raise ContentPackError(f"Unknown or ambiguous global prerequisite_quest: {reference!r}.")
                defaults["prerequisite_quest"] = matches[0] if matches else None
            if "required_skill" in entry or "required_skill_level" in entry:
                tags = self._resolved_quest_skill_tags({"name": entry["name"], "skill_tags": [entry["required_skill"]]}) if entry.get("required_skill") else []
                defaults["required_skill"] = tags[0][0] if tags else None
                defaults["required_skill_level"] = entry.get("required_skill_level", 0)
            if "required_badge" in entry:
                defaults["required_badge"] = None
            if entry.get("required_badge") is not None:
                matches = self._source_reference_matches(Badge, name=entry["required_badge"])
                if len(matches) != 1:
                    raise ContentPackError(
                        f"quest {entry['name']!r} references unknown badge or ambiguous source "
                        f"{entry['required_badge']!r}"
                    )
                defaults["required_badge"] = matches[0]
            quest, created = self._upsert(QuestDefinition, entry=entry,
                name=entry["name"], defaults=defaults,
            )
            if quest is None:
                # Left unchanged by an unkeyed load; keep its links as well.
                continue
            from django.core.exceptions import ValidationError
            try:
                quest.clean()
            except ValidationError as error:
                raise ContentPackError("; ".join(error.messages)) from error
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
                link, r_created = self._upsert_link(QuestRewardItem,
                    quest_definition=quest, item=item,
                    defaults={"quantity": int(reward.get("quantity", 1))},
                )
                if link is not None:
                    self.stats.bump("created" if r_created else "updated", "quest_reward")

            if self.pack_key:
                removed, _ = QuestRewardItem.objects.filter(quest_definition=quest).exclude(item_id__in=desired_reward_ids).delete()
                self.stats.bump("retired", "quest_reward", removed)

            # Resolve once using the same identities checked by the active-promise guard.
            if entry.get("skill_tags") is not None:
                tags = self._resolved_quest_skill_tags(entry)
                from apps.achievements.models import Skill
                self._admit_reference(Skill, [skill.pk for skill, _ in tags],
                    QuestSkillTag.objects.filter(quest_definition=quest).values_list("skill_id", flat=True))
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
            family = self.family
            if family is None:
                from apps.families.models import Family
                family, _ = Family.objects.get_or_create(
                    slug="default-family", defaults={"name": "Default Family"},
                )
            reward_scope = {"family": family}
            if not self.pack_key:
                # Legacy seed offers have no stable ownership claim. A name
                # within the destination household cannot prove this is still
                # the bundled offer, or authorize resetting a parent's edits.
                # Seed missing offers only; reviewed, owned publications below
                # remain the explicit way to update authored shop content.
                _, created = Reward.objects.get_or_create(
                    name=entry["name"], **reward_scope, defaults=defaults,
                )
                self.stats.bump("created" if created else "skipped",
                                "reward" if created else "preserved_family_reward")
                continue
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
