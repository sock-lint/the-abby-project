# RPG Content Packs

Additive first-party and third-party content lives here, one sub-directory per pack:

```
content/rpg/packs/
  spring-2026/
    items.yaml
    drops.yaml
    quests.yaml
  halloween/
    items.yaml
    pet_species.yaml
    ...
```

## Loading a pack

```bash
python manage.py loadrpgcontent \
  --pack content/rpg/packs/spring-2026 \
  --namespace spring-2026-
```

Namespacing prefixes every slug so packs can't collide with each other or
with `content/rpg/initial/`. The MCP `load_content_pack` tool applies this
automatically.

The default `loadrpgcontent` command loads the initial seed followed by the
registered `reading-adventures` and `collector-reading-2026` packs, atomically.
Those bundled packs live in `content/rpg/bundled/`, baked into the image:
production bind-mounts this `packs/` directory from the host for MCP-authored
packs, so a default pack placed here would be missing at startup.
Explicit `--pack` retains single-pack behavior; `--dry-run` rolls back the whole
selected batch, including cross-pack dependencies.

## Authoring via MCP

Prefer the MCP content-pack tools when an LLM is authoring — they validate
YAML syntax, invoke the loader's dry-run mode for pre-flight checks, and
record `last_loaded_at` in a per-pack `.manifest.json`. See
`apps/mcp_server/tools/content_packs.py`.

## Authoring by hand

See `content/rpg/README.md` for the full YAML schema and
`content/rpg/initial/` for working examples of every file type.

## Rules

- **Never edit `content/rpg/initial/`** — that's load-bearing base content.
  Instead, ship a namespaced override in a pack.
- **Pack names** must match `^[a-z0-9][a-z0-9-]*$` and not be `initial` or
  `packs`.
- **Reserved files**: only `items.yaml`, `drops.yaml`, `quests.yaml`,
  `badges.yaml`, `pet_species.yaml`, `potion_types.yaml`, `skill_tree.yaml`,
  `rewards.yaml`, plus the auto-managed `.manifest.json`.


For rewards earned only through authored goals, set item metadata
`no_random_drop: true`. Drop macros, explicit random rules, new expedition loot
and random consumable grants exclude that item. Normal availability, owned-item
use/equipping and established expedition loot remain intact. This property is
not a shop restriction; omit shop offers separately when access should require
the authored goal. The collector reading pack uses this for its three cosmetics.
