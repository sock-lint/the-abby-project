# Companion families and growth

Every pet species is a creature family with the same four lifecycle IDs:
`egg`, `baby`, `middle`, and `grown`. The ordered vocabulary, labels and growth
thresholds live in `shared/catalog/companion-lifecycle.json`, shared by Django
and React. Family-specific form names are presentation: Base Chick still uses
Chick, Fledgling and Bird after hatching. A species slug and compatible potion
identify one ownership path; stages never create four separate species.

| Stage | Saved authority | Existing interaction |
| --- | --- | --- |
| Egg | Species-linked egg `ItemDefinition` and owned inventory quantity | Choose an egg and compatible potion in Hatching |
| Baby | Owned `UserPet`, below 50 saved growth, not evolved | Existing care, activation and growth |
| Middle | Owned `UserPet`, at least 50 saved growth, not evolved | Same care; no additional award or ownership |
| Grown | Confirmed `evolved_to_mount` or owned `UserMount` | Existing activation, expeditions and eligible breeding |

An egg remains in inventory until the existing explicit hatch action consumes
one egg and one potion and creates a baby at zero growth. It is not an active
companion, incubation timer or new pet row. Multiple eggs are inventory
quantities; a hatched species/potion pair retains the existing unique ownership
constraint. Breeding creates another species-linked egg and potion through the
existing compatible output rules.

Existing pets retain their IDs, names, growth, feeding dates, activation,
evolution, mounts and expedition history. The lifecycle is a read-only
projection, requiring no data migration or backfill. An old unevolved row at
100 growth remains Middle until evolution is confirmed. Stage reads, art loads,
preview controls and local greetings award no XP, Coins, food or growth.

## API and consumers

Species, catalog and codex responses expose ordered `lifecycle_stages`. Pet and
mount responses expose server-derived `lifecycle_stage`; the feed and passive
growth receipts use the same projection. Egg item responses expose
`lifecycle_stage: "egg"` and `pet_species_slug`, resolving the typed species
first and retained legacy metadata when necessary. Other items expose null.
Neither a client stage value nor an artwork name changes saved state.

The compatible `evolution_stage` field retains `chick`, `fledgling`, `bird`, or
null for other identities. It continues selecting the existing exact Bird
renderer and its supplied transitions. New consumers use the generic lifecycle
for progress, while presentation adapters retain their own exact artwork IDs.
REST, MCP item/pet shapes, inventory, Hatching, collection details, owned pet
previews, Today and ceremonies must preserve this distinction. Shared raw API
fixtures exercise the actual producer and React consumer together.

## Adding creatures and forthcoming artwork

1. Author the family once in `content/rpg/initial/pet_species.yaml` or a namespaced
   content pack. The existing loader creates its matching egg with a typed
   `pet_species` FK. Do not separately author a second egg in `items.yaml`.
   `egg_name`, `egg_icon` and `egg_sprite_key` can name supplied egg artwork;
   the default remains the generic egg. Reloads preserve owned inventory.
2. Keep the generic stage IDs. Add exact family form names to `family_forms` in
   the shared lifecycle file when supplied. Match species slug, sprite identity
   and potion variants; family labels do not imply availability or asset fit.
3. Receive the reviewed private runtime bundle for Egg, Baby, Middle and Grown,
   with exact family/stage IDs, manifests, hashes, portraits and supported
   animations. Keep purchased originals, models, renders and receipts outside
   Git. Pin and verify the release through the existing private asset importer.
4. Register only verified presentation bindings in the matching portrait/model
   adapter. Use each supplied rig and declared motion unchanged. Missing stage
   artwork keeps a labelled egg or that same family's sprite/icon fallback;
   another family's Bird art is never a substitute. Existing bird motion aliases
   remain compatible until a reviewed family adapter replaces them.
5. Expand `shared/catalog/asset-support.json` only after the actual species and
   potion appearances pass the normal asset, renderer, CI and independent
   review gates. Catalog labels and owned portraits alone do not enable new
   drops, rewards, shop offers, hatching or breeding. No new creatures are
   enabled by this lifecycle preparation.
6. Check egg inventory identity and quantity, baby hatch consumption, 49→50
   growth, confirmed 100 evolution, reload, saved legacy pets, family isolation,
   missing assets and reduced motion. Run producer/consumer fixtures, pet/RPG
   checks, frontend coverage and web/native builds. Add real device acceptance
   for new art; desktop viewport checks do not establish phone performance.

The current private Bird release supplies the three post-hatch forms. No new
egg or creature asset, public delivery, runtime release, or production change
is claimed by the lifecycle code. The neutral pedestal egg in Hatching remains
decorative until an exact family egg binding is supplied and accepted.
