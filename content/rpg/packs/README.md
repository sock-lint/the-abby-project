# RPG Content Packs

Third-party content lives under this directory, one sub-directory per pack:

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
