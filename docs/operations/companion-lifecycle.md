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

## Prepared roster adoption

The active roster is 15 Base-only families: retained Chick plus the 14 exact
namespaced identities in `shared/catalog/companion-roster.json`. That file
records every supplied egg, portrait, stage, native default take and explicit
50/100 growth rule. `apps/pets/roster.py` and the renderer consume that same
mapping. Source stage order alone establishes no gameplay rule.

| Species slug | Baby → Middle → Grown | Egg source |
| --- | --- | --- |
| `meshtint-bat` | Bat → VampireBat → BatLord | 15A |
| `meshtint-bee` | Bee → Bumble → Sting | 09A |
| `meshtint-shadow` | Egglet → Shade → Shadow | 05A |
| `meshtint-ghost` | Ghost → Spook → Phantom | 01D |
| `meshtint-mushroom` | Mushroom → Fungi → Toadstool | 10A |
| `meshtint-potted-plant` | Seed → Sprout → FlowerPotMonster | 11B |
| `meshtint-spider` | Spider → SpiderToxin → SpiderKing | 17A |
| `meshtint-wolf` | WolfPup → Wolf → Werewolf | 08E |
| `meshtint-dragon` | DragonSpark → DragonFire → DragonInferno | 06A |
| `meshtint-snake` | Snakelet → Snake → SnakeNaga | 16A |
| `meshtint-hermit-crab` | Shell → Spike → HermitKing | 03C |
| `meshtint-blossom` | Bud → Bloom → Blossom | 12E |
| `meshtint-sunflower` | SunBlossom → SunflowerFairy → SunfloraPixie | 13A |
| `meshtint-bomb` | Bomb → PoisonBomb → SnowBomb | 18C |
| `chick` | Chick → Fledgling → Bird | Retained Normal Egg |

Registered eggs require their exact item slug, typed `pet_species` FK and
canonical `metadata.species` to agree. The loader applies the namespace once
and rejects occupied/conflicting species or egg identities before upserting.
Only the existing global Base potion is supported. Unknown identities fail
closed; retained metadata fallback never rescues a conflicting new identity.

Dummy's separate pinned release is private future training art. It has no
species, egg, inventory, companion, mount, drop, shop or breeding binding.
Training gameplay is unimplemented and Dummy does not count toward 15.

## Private intake and build

Both digest-pinned delivery indexes, all six referenced objects, and all 4,410
workspace inventory entries were verified before reading the handoffs. Both
exact `verify-handoff` invocations returned `ready`, `verified: true`.
Paid payloads, archives, screenshots and evidence stay ignored/private.
The adopted logical pins are recorded in `frontend/assets.lock.json`:

| Release | Version | Manifest SHA-256 |
| --- | --- | --- |
| Companion roster | 1.0.0 | `2945dfc7ce31d31ef4a4aee867680b821f93046c829b09867f675b50b0af0fe9` |
| Training Dummy | 1.0.0 | `bceff1c1cb2676a68c45693460a26826dd3d880e513d4db32690ca8ca956a31b` |

The corresponding delivery-index hashes are roster
`41a067248c117d233c862beb8be555bad6b6ffcc25f5c2110d5df496be45b328`
and Dummy `8c47ff035ae71c4dba5fb24738834691c5438b99a166e71ea13d3ef181c90a84`.

The existing Archer, Bird, pedestal/UI and catalog pins remain unchanged.
The existing private reader imports six releases and verifies 1,120 runtime
files. Seven retained Chick/Fledgling/Bird and Normal Egg portraits come from
the roster delivery's inventory-pinned supplemental paths, recorded in
`shared/catalog/companion-supplemental.json`; they are not invented release
assets. `assets:import` stages these atomically into the ignored
`frontend/src/companion/supplemental/`. A fresh offline import requires both
`ABBY_ASSETS_RELEASE_ROOT` for the six-release tree and
`ABBY_COMPANION_WORKSPACE` for the fully extracted roster verification workspace;
the release tree contains none of these seven portraits. The importer verifies
the workspace inventory and every listed file before selecting the exact seven
outputs. Alternatively, it fetches the pinned verification ZIP through the
application's existing GetObject-only reader, checking the index before locators,
ZIP bytes/hash and every inventory file.

Supplemental sources are checked before any installed release files change. If
neither a fully verified installed supplemental tree nor a workspace or configured
reader is available, import fails with instructions to supply the required source.
An existing supplemental tree whose pin and exact contents still verify can be
reused for a release rollback without a workspace or S3 access. Missing or invalid
supplementals require verified source bytes again. Unmanaged files are never
replaced.

Use `npm run assets:import`, `npm run assets:verify`, and the normal web/native
builds. Keep the existing least-privilege reader configuration; never copy
publisher/backup credentials. Prebuild and postbuild checks verify installed
and bundled bytes. A public build without private inputs retains labelled
DOM/icon fallbacks. Source packs and handoff workspaces are not public build
inputs. No deployment is part of adoption.

## Native renderer contract and limits

`sharedRosterRelease.js` resolves exact species/sprite/Base/stage identities;
`sharedRosterPlayback.js` loads the selected native take with its own rig,
then disposes replaced takes. It never transfers arbitrary animation tracks
onto one skeleton or preloads the 353,598,901-byte roster library. Stage
previews are local, clearly labelled, and do not change ownership or rewards.
The default egg preview is a portrait; 3D is opt-in. Missing assets/WebGL leave
care, hatching and expedition controls functional.

DragonFire has supplied flying idle/forward only; the app invents no walking
take. Native loop metadata, travel and below-ground held poses are preserved.
Egg Idle and Underground are authentic held poses, not failed animations.
Root-travelling egg rolls use an explicit once-only host policy and return to
rest; continuous root accumulation and seamless repeated travel are not
claimed. Static host framing uses each stage's native default bounds and keeps
that scale across its takes, preserving native rig, geometry and keys. Roster
cameras focus on the scaled native idle bounds center so elevated flying idles
remain in view; the native scene, joint tracks and source clearance keep their
supplied coordinates. Travel may leave this fixed view. These
preview scales establish no gameplay size rule. The documented SnakeNaga breath-attack-right-left strongest-four
weight reduction measured 24.28098063 mm over five source poses; this differs
from prepared-mesh→GLB error (maximum 0.963 mm) and egg native→reimport error
(maximum 0.9864 mm). Do not collapse these scopes into a fidelity claim.

The workshop tested its recorded Asset Lab runtime snapshots. Its source drift
report is retained; current application tests exercise the actual scene code
and exact staged releases separately. Browser/desktop checks do not establish
physical iPhone/Android performance, lifecycle or thermal acceptance. Those
remain rollout gates, along with the repository's exact public-delivery process.
The bare companion previews also do not establish acceptance of creature and
Woodland scenery overlap in populated scenes.

## Non-destructive catalog rollout and rollback

Keep the 17 legacy definitions and every saved owner, nickname, growth value,
mount, inventory stack, history row, award and promised reward. There is no
legacy-to-new crosswalk, destructive schema migration or cascading deletion.
The initial pack contains 32 species definitions; only 15 are new-acquisition
eligible. Existing food preferences remain attached to their original species;
new families use neutral food growth until deliberately authored otherwise.

Before an eventual operator rollout, preserve a real database backup and a
private saved-data baseline. **No production database was read or changed by
this adoption task.** The regression baseline is synthetic: all 17 legacy
pet/mount families, names/growth/caps, inventory, paid/frozen promises, pending
expedition loot, history, badges, XP, Coins and money. Tests compare it before
and after dry-run/apply/reload/repeat and redeem original promises exactly once.
An operator must capture the actual saved-data baseline before applying:

```sh
python manage.py loadrpgcontent --dry-run
python manage.py reconcile_companion_catalog --dry-run --json
```

The adoption includes a nullable, server-only `Quest.reward_items_snapshot`
column. Review `python manage.py migrate --plan` and exercise the migration
and these dry runs on a disposable restored database first. The schema change
adds the column without deleting or paying anything. New quest starts freeze
only currently eligible reward item IDs and quantities. Reconciliation reports
and freezes existing accepted quests' retained reward links once; dry-run
persists nothing. That cutover cannot reconstruct definition edits made before
the saved-data baseline, so inspect the retained links before rollout.

Existing automatic challenge snapshots and accepted legacy quest item promises
remain visible and payable after catalog retirement. Payout uses the saved
promise rather than reapplying today's acquisition filter. Existing salvage,
participant, locking and one-time-award rules still apply. Reads, schema
migration and promise backfill award no XP, Coins or inventory. New goals,
occurrences and quest starts continue excluding unavailable items.

Review the affected row IDs and resolve collisions without repointing owned
definitions. On the approved rollout, ordinary `loadrpgcontent` upserts new
families and transactionally reconciles stale offers. The explicit idempotent
`reconcile_companion_catalog --json` is also available. It deletes only stale
egg/potion `DropTable` configuration and deactivates corresponding digital/both
shop offers. It retains ItemDefinition/PetSpecies, real-world offers,
QuestRewardItem links, frozen redemption snapshots and pre-rolled loot.
YAML removal alone is insufficient. Never substitute `cleanup_rpg_catalog`
or `prune_pack_content`, which have different destructive scopes.

Each existing pool keeps its prior total egg weight: 10 for triggered drops
and expeditions, 5 for common mystery-box selection. The 15 approved eggs share
that category weight; non-egg weights and trigger rates remain unchanged.

Rollback code baseline is `80b4c5429cda14f8eac77b3318cd391acfbaf5eb` (lifecycle
preparation), based on main `6aefd26f9b516ff580cd98ee84bba5f191abfbbe`.
The pre-adoption release pins are Archer 1.0.2 `4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`,
Bird 1.0.0 `1c8bd52e4f2273b1849bebb498d21c0689e7b8d6191c1ee36e7a7bfeb09bd37a`,
catalog 1.0.0 `0201085bd500af510bbdbcb16ac3fa68d0588b3cc321a4943d57e64c3cbd4ad2`,
and pedestal/UI 1.0.1 `abc05d8f7919fc30e19e3c77f2f7f470463666c184c2bdcab70e3778c15f378d`.
Retain these exact artifacts and the private pre-adoption lock. An art or policy
rollback must retain the nullable quest snapshot column and promise-preserving
payout code; reverting those fixes would restore the retired-reward loss.
Reverting art or policy never deletes new saved ownership. Recreating retired configuration
requires the reviewed pre-rollout configuration snapshot; do not reset the
database or rewrite reward promises. No rollback or deployment was executed.

## Adding later families

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
   drops, rewards, shop offers, hatching or breeding.
6. Check egg inventory identity and quantity, baby hatch consumption, 49→50
   growth, confirmed 100 evolution, reload, saved legacy pets, family isolation,
   missing assets and reduced motion. Run producer/consumer fixtures, pet/RPG
   checks, frontend coverage and web/native builds. Add real device acceptance
   for new art; desktop viewport checks do not establish phone performance.

Do not change unrelated approved pins while adding a family. Keep the exact
family-stage bindings, on-demand playback and legacy preservation checks together.
