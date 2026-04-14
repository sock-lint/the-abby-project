# RPG Content Packs

This directory is the **single source of truth** for the RPG catalog —
pets, eggs, potions, items, drops, quests, badges, rewards, and the
skill tree. Before this existed, the same content was scattered across
hand-written Python lists in `apps/projects/management/commands/seed_data.py`
and one-off `get_or_create` calls in data migrations. Editing a pet used
to mean touching three files; now it's one YAML edit.

## How it works

- `content/rpg/initial/` is the canonical seed pack. Running
  `python manage.py loadrpgcontent` (which is also what `seed_data`
  calls internally) upserts everything in it idempotently.
- Every authored entity has a stable `slug` as its natural key. Running
  the loader twice in a row is a no-op.
- Pets and potions **fan out** — one entry in `pet_species.yaml` creates
  both the `PetSpecies` row **and** the matching egg `ItemDefinition`
  with a real FK linking them. Same for potions → potion items. Eggs and
  potions should never be authored directly in `items.yaml`.
- `metadata` JSONField is still used for genuinely free-form per-item
  data (border colors, title text, coin-pouch coin count). Cross-entity
  references (egg→species, potion→type, food→species) live in real FKs
  now. See `apps/rpg/migrations/0006_backfill_item_refs.py` for how
  pre-pack rows were migrated.

## Files

| File                  | What it authors                                             |
| --------------------- | ----------------------------------------------------------- |
| `skill_tree.yaml`     | SkillCategory + Skill + SkillPrerequisite                   |
| `badges.yaml`         | Badge                                                       |
| `potion_types.yaml`   | PotionType + auto-generated potion ItemDefinition per entry |
| `pet_species.yaml`    | PetSpecies + auto-generated egg ItemDefinition per entry    |
| `items.yaml`          | Food, cosmetics, coin pouches, quest scrolls                |
| `drops.yaml`          | DropTable rules & macros (trigger → item → weight)          |
| `quests.yaml`         | QuestDefinition + QuestRewardItem                           |
| `rewards.yaml`        | Reward (coin-shop items) — optional                         |

The loader tolerates any subset being present; missing files just skip
that section.

## Commands

```bash
# Load the initial pack (idempotent upsert)
python manage.py loadrpgcontent

# Preview what would change without committing
python manage.py loadrpgcontent --dry-run

# Load a third-party pack with a namespace prefix so slugs don't collide
python manage.py loadrpgcontent --pack content/rpg/packs/dragons --namespace dragons-
```

## Authoring workflow

1. Open the right YAML file.
2. Copy an existing entry.
3. Change slug + name + fields.
4. `python manage.py loadrpgcontent --dry-run` to validate.
5. `python manage.py loadrpgcontent` to apply.
6. Commit the YAML change.

Claude (via the `Edit` tool) can do all of this — no MCP tool plumbing
required. A prompt like *"add a water-themed koi pet that prefers fish
and drops from chores"* is sufficient; Claude edits `pet_species.yaml`
directly, runs the loader, and verifies.

## Third-party content

Open-licence icons & data we recommend:

- **[game-icons.net](https://game-icons.net)** — CC-BY-3.0, 4000+
  monochrome SVG icons. Perfect for `ItemDefinition.icon` and
  `PetSpecies.icon`. Attribution required.
- **[Kenney.nl](https://kenney.nl)** — CC0 asset packs with tile-style
  icons.
- **[OpenGameArt.org](https://opengameart.org)** — filter to CC0 / CC-BY.

Downloaded packs live under `content/rpg/packs/<pack-name>/` and are
loaded with `--namespace` so their slugs never collide with core
content. If you go this route:

1. Drop the pack's YAML files + `assets/` into
   `content/rpg/packs/<pack-name>/`.
2. Pick a short unique namespace (e.g. `dragons-`, `kenney-`).
3. `python manage.py loadrpgcontent --pack content/rpg/packs/<pack-name> --namespace <pack-name>-`.

Pack assets (SVG/PNG) must still be served from somewhere WhiteNoise can
see them — today `icon` is a short string and the frontend renders emoji
inline. Wiring a real asset pipeline is a future improvement.

## Extending the schema

Adding a new content type (e.g. an ItemSet, DailyQuest, etc.):

1. Add the model field / new model as usual.
2. Add a new method to `apps/rpg/content/loader.py` (e.g.
   `_load_item_sets`) that reads a new YAML key and does
   `update_or_create` on slug.
3. Register the filename in the `FILES` dict at the top of `loader.py`.
4. Call the new method from `ContentPack.load` in the correct
   dependency order.
5. Add a test in `apps/rpg/tests/test_content_loader.py`.
