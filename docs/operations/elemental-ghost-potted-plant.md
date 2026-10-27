# Fire and Ice Ghost and Potted Plant

The owner accepted all twelve Fire/Ice appearances shown by application revision
`330c1de42b4ecbac3c3414f8ff341c586d61d478` and then authorized exact runtime
publication, guaranteed challenge activation, and PR #342 through merge,
deployment and live verification. [Artwork acceptance is recorded on the
PR](https://github.com/sock-lint/the-abby-project/pull/342#issuecomment-6452891577);
no repeat artwork approval or regeneration is needed. This change adds the
accepted runtime and four acquisition paths while preserving existing families,
saved identities and rewards. Pet stats remain deferred.

## Canonical delivery and verification

The canonical release is `abby-elemental-ghost-potted-plant` **1.0.0**.
The application independently verified its complete runtime through the
established Abby GET-only reader on October 27, 2026, at 21:10 UTC:

- Version index:
  `s3://abby-assets-releases/releases/versions/abby-elemental-ghost-potted-plant/1.0.0.json`
  — **174 bytes**, SHA-256
  `737b7e90c70ed64af4b9f483bfd2a2af09a72a4ae7ddd8faa76d666321ad6955`.
- Manifest:
  `s3://abby-assets-releases/releases/abby-elemental-ghost-potted-plant/1.0.0/6e1f2cb2f67503c63e3ab8a27135b6f7579f894e0d62b814bfa89df3a45ae9e9/manifest.json`
  — **292,313 bytes**, SHA-256
  `6e1f2cb2f67503c63e3ab8a27135b6f7579f894e0d62b814bfa89df3a45ae9e9`.
- Runtime: **154 files / 51,889,149 bytes** — 138 GLBs and 16 transparent
  256px PNGs: twelve stage portraits and four Baby-only acquisition images.
- Canonical total: **156 objects / 52,181,636 bytes**. Every downloaded object
  matched its SHA-256 and size; all 154 runtime payloads were byte-identical to
  the owner-approved candidate. All 156 anonymous requests returned HTTP 403.
- Fresh standard single-family import and verification passed. All fourteen
  prior canonical releases, their 2,333 payloads and seven supplemental portraits
  remained unchanged. Code-package integrity pins also remained unchanged.

The private application readback receipt has SHA-256
`263501577570df96c7fc88bc85e5c3d7287da70c307915b84c59b51ac1c5c8d8`;
its canonical summary has SHA-256
`174570bc528ffc1e425afa31bce68723637157ef1d6721434a243ab85ea5dcb8`.
These are application receiving proofs, not publisher execution proofs. The
scoped publisher, permanent-coordinator claims and manifest-last ordering are
not observable through the application reader; their operator receipt has not
been returned. Do not report those checks as passed from runtime GET results.
There are no unresolved application readback/access holds in the verified
inventory. The earlier 20:53 UTC `NoSuchKey` / HTTP 404 metadata probes remain
historical evidence from before canonical delivery appeared.

`frontend/assets.lock.json` adds only this exact fifteenth pin, retaining every
previous family/version/digest. Use normal `npm run assets:import` and
`npm run assets:verify`; ordinary application and canonical browser checks use
active-lock defaults without an evaluation root or injected staged release.
The separate `assets.ghost-potted-plant.evaluation.lock.json` and loopback review
route preserve the earlier private review; they are not normal runtime delivery.
Keep payloads, source archives, previews and evidence outside Git. The verified
canonical importer stages runtime files only into its dedicated ignored trees.

Reuse exact contracts **1.4.0**, avatar-runtime **1.3.0** and release-tools
**1.6.0** tarballs with their existing SHA-256/npm integrity pins. Canonical
runtime delivery does not publish new code packages or authorize an upgrade.
The separate asset workshop remains **Prepare Fire and Ice assets**; this
application retains its GET-only reader.

## Active identities and guarantees

`shared/catalog/elemental-ghost-potted-plant.json` records the exact accepted
release and presentation identities. Its activation metadata does not itself
authorize acquisition: the positive `shared/catalog/asset-support.json` policy
and ordinary initial content activate the four pairs and guarantees together.
The resulting policy contains **fifteen Base species, ten elemental species,
35 exact species/potion pairs and twenty elemental guarantees**; five species
remain Base only. All prior runtime families and saved data remain supported.

The two compatibility updates and four challenges load from `content/rpg/initial`
through default `loadrpgcontent`. The historical
`content/rpg/prepared/elemental-ghost-potted-plant` pack remains unregistered so
it cannot duplicate those offers. Explicit unsupported compatibility must still
fail atomically under a narrowed policy. Scoped synthetic policy overrides are
test inputs, not an application acquisition bypass.

| Species and sprite | Natural egg | Baby → Middle → Grown | Existing rarity |
| --- | --- | --- | --- |
| `meshtint-ghost` | `meshtint-ghost-egg` | Ghost → Spook → Phantom | Rare |
| `meshtint-potted-plant` | `meshtint-potted-plant-egg` | Seed → Sprout → Flower Pot Monster | Common |

Existing eggs retain their IDs, metadata, rarity and authored coin value 3.
There are no elemental eggs or additional potion definitions. Potion
presentation starts during incubation and persists through confirmed hatching
and growth. Baby Seed remains a bulb without a pot. Existing global Base,
Fire and Ice potion identities and artwork remain unchanged.

| Challenge | Qualifying accomplishments | Guaranteed bundle |
| --- | --- | --- |
| Ember Wisp | 20 | Natural Ghost Egg + existing Fire potion |
| Frost Wisp | 20 | Natural Ghost Egg + existing Ice potion |
| Ember Sprout | 5 | Natural Seed Egg + existing Fire potion |
| Frost Sprout | 5 | Natural Seed Egg + existing Ice potion |

All four have a 180-day window, pay once, and author zero Coins/XP. Wisp follows
the Rare Wolf target; Sprout follows Common Chick/Bee pacing. Existing
server-owned rules count approved chores/homework, completed projects or
milestones, eligible creations and earned daily reading receipts. Daily source
limits, accepted-promise snapshots and payout deduplication remain unchanged.
Browsing, artwork playback and greetings earn no progress. Existing accepted
promises retain their frozen rewards when ordinary content reloads.

Baby-only challenge images retain the exact presentation handles
`review-ghost-fire-acquisition-icon`, `review-ghost-ice-acquisition-icon`,
`review-potted-plant-fire-acquisition-icon` and
`review-potted-plant-ice-acquisition-icon`, each variant `icon`. Exact system
collection identity is required; a same-name parent challenge cannot obtain
this binding. Image identity is separate from quest names, slugs and numeric IDs.

## Presentation and expedition behavior

Keep `appearance_bindings` v1: explicit species + potion + lifecycle stage +
logical motion selects native variant/action, portrait and root-motion bindings.
Appearance IDs stay separate from native `source-*` motion IDs. The accepted
runtime preserves all 138 exact bindings: Ghost has 12/12/12 takes and Potted
Plant 11/12/10 per element for Baby/Middle/Grown. Every default is
`source-idle` / action `idle` / clip `Idle`.

Plant Middle additionally retains `source-idle-02` / action `idle-02` / clip
`Idle 02`. Ghost Middle uses `source-slash-left-attack` and
`source-slash-right-attack`; Grown uses the differently ordered
`source-left-slash-attack` and `source-right-slash-attack`. Do not normalize
these literal IDs, action names, clip case, timing, loop/root policies or bounds.
The candidate-to-Base audit preserved geometry, UVs, rig/skin, animation and
nonimage buffers across the 69 exact Base sources. Native materials remain
OPAQUE, including Ghost. Base/Fire/Ice instances retain independent materials,
textures, mutation and disposal. There are no aliases, authored transition
payloads or invented Evolve takes: eight descriptive growth edges retain the
same element's destination idle after app-confirmed growth. Both earlier
Fire/Ice Bird evolutions remain supported.

Child presentation still requires exact species + potion ownership and limits
forms/names to server-confirmed reached stages. Missing stable reads unlock
nothing; Baby challenge images do not disclose future forms. Parent/staff
behavior is unchanged. Missing or unsupported artwork fails explicitly without
a Base substitution or CSS recolor, while care and claim controls remain usable.
Natural egg identity, incubation deadlines, saved hatch replays and growth remain
server-owned. Portraits and model filenames grant no ownership or progression.

No expedition service change is required. Base/Fire/Ice share the existing
account/species allowance, including pending/unclaimed trips and claimed trips
started that local day. Ghost and Potted Plant retain separate species
allowances while sharing the two-starts-per-child family-local-day cap. Frozen
loot, sibling/family scoping, return/claim behavior and care rewards remain intact.

## Review evidence and remaining release gates

The immutable private review index is pinned by SHA-256
`12e87df4f4066b008767d3b281b1c8b12a8e965f227d39aaeec5735aaeffbb76`
(4,994 bytes); its URI remains in the receiving descriptor. The application
verified that index, all six artifacts, safe archives and all 1,039 declared
workspace/authoring members. The inspected offline Node 22
`verify-candidate.mjs` passed without npm or network access. Historical
candidate `preparing` labels describe the earlier publication snapshot and do
not undo later owner approval or the verified canonical readback.

Artwork review used actual application components at `330c1de4`, tree
`444b450706596b78df76e81d37bccd4391318197`. The original private browser run
passed sixteen cases and failed one Ice Spook playback check; an unchanged
isolated Ice Ghost repeat passed its 36 takes. No source or timeout change
explains the initial failure, whose cause remains unverified. Across those runs
all 138 distinct bindings were observed. Twelve owned/Hatchery forms, exact
portraits/icons, reduced motion, missing-file recovery, both Bird evolutions and
24 material groups / 96 independent instances were covered. Do not call the
original full run wholly green or replace it with its isolated repeat.

All four hosted checks passed on that historical review revision: 6,232 backend
tests, 5,366 frontend tests, API fixtures 174 Django + 241 React, and PWA
261 browser passes with 81 skips. These results do not validate a later
activation revision. Canonical browser checks, local tests/builds, current-base
hosted checks and independent review must pass on the actual activation
revision. Record their results, actual tested source/merge revisions and current
scene/source drift in the PR and private evidence; do not reuse older check
counts as a current-head pass. The changed real API fixture contents and React
consumers must agree without changing their response contract.

Run focused quest/pet preparation and activation checks, shared expedition
races on disposable PostgreSQL/Redis, normal frontend coverage/lint and web/native
builds. Normal `config.settings` tests use the syncdb shortcut on PostgreSQL;
validate the real migration graph separately and distinguish both results.
SQLite skips are not passed races. Canonical browser acceptance uses ordinary
component defaults, covering incubation/hatch, all twelve forms and 138 motions,
portraits/icons, same-element destination idle/reload, reduced motion, material
isolation, persistence, missing-file recovery and both prior Bird evolutions.

Formal durable source backup/restoration remains pending separately from the
verified 184-member authoring delivery. Physical-phone/native-shell acceptance
also remains separately pending; desktop Chromium at 390×844 does not establish
it. Owner artwork acceptance and successful canonical transport cannot certify
either missing acceptance. Keep those statuses explicit.

The owner has authorized the application release tail, while MAIN owns merge
through ordinary exact-head/base hosted CI, independent review, conversation,
asset and fresh trusted-live gates. Record the actual GitHub squash commit,
finished healthy deployment and exact-served revision live receipt when each
exists. Merge alone is not deployment or live proof. No merge/deployment/live
completion is claimed by this receiving runbook.

## Rollback

Withdraw only the four new offers/acquisition pairs through a reviewed policy
and initial-content change. Keep canonical Ghost/Plant delivery and
loader/presentation identity support for saved companions and accepted rewards,
alongside all fourteen prior releases. Preserve natural eggs/potions, pending
incubation, frozen challenge rewards, frozen expedition promises/loot including
pending and unclaimed trips, saved history, care and claim controls. Never
blindly revert the release after promises exist, delete canonical objects or
saved pets, migrate identities, reroll or re-grant rewards.

The original private-only return to `2c21a861` and unset receiving digest was a
pre-activation review withdrawal, not a safe post-activation rollback. Preserve
its external archives, review evidence and source recovery. The original art
review baseline was PR #336's `1ab5101d`; the local integration merge head
`63119bb4dc93bcd4bd3c710b218acbd566062134` includes main `949273e2`.
Neither historical baseline is a substitute for the actual final merge,
deployment and live verification proof.
