# Fire and Ice Ghost and Potted Plant preparation

The owner requested private Fire/Ice artwork and application preparation for
Ghost and Potted Plant after the canonical Snake/Hermit Crab release in PR #336.
This work prepares receiving identities, future guarantees and regression checks.
It does not accept artwork, add a runtime pin or activate new acquisition.
Pet stats remain deferred.

## Current boundary

`shared/catalog/elemental-ghost-potted-plant.json` is a receiving agreement, not
an acquisition policy. Its state is `awaiting_private_assets`, with
`acquisition_active: false`, `artwork_accepted: false` and a null manifest digest.
The release family is `abby-elemental-ghost-potted-plant`, version `1.0.0`.

Ordinary initial content and `shared/catalog/asset-support.json` remain unchanged:
fifteen Base families, eight accepted elemental families, **31 exact pairs and
16 elemental guarantees**. All fourteen canonical runtime pins and existing
code-package integrity values remain unchanged. A globally available potion,
new metadata, a synthetic fixture or an owned image cannot authorize either new
species/potion pair.

The unregistered pack is
`content/rpg/prepared/elemental-ghost-potted-plant`. Default `loadrpgcontent`
does not load it. Explicit loading under the current production policy rejects
its unsupported compatibility atomically. Tests may supply an explicit
synthetic positive policy for every exact Base/Fire/Ice identity to exercise
future authoring, rewards and care. Never use that override as an application
activation or artwork acceptance mechanism.

## Identities and guarantees

| Species and sprite | Natural egg | Baby → Middle → Grown | Existing rarity |
| --- | --- | --- | --- |
| `meshtint-ghost` | `meshtint-ghost-egg` | Ghost → Spook → Phantom | Rare |
| `meshtint-potted-plant` | `meshtint-potted-plant-egg` | Seed → Sprout → Flower Pot Monster | Common |

Existing eggs retain their IDs, metadata, rarity and authored coin value 3.
Base forms remain unchanged. Separate Fire/Ice lifecycle metadata preserves
these stage names; it grants no stage or ownership. There are no elemental eggs
or additional potion definitions. Potion presentation begins during incubation.

| Future challenge | Qualifying accomplishments | Guaranteed bundle |
| --- | --- | --- |
| Ember Wisp | 20 | Natural Ghost Egg + existing Fire potion |
| Frost Wisp | 20 | Natural Ghost Egg + existing Ice potion |
| Ember Sprout | 5 | Natural Seed Egg + existing Fire potion |
| Frost Sprout | 5 | Natural Seed Egg + existing Ice potion |

All four have a 180-day window, pay once, and author zero Coins/XP. Wisp follows
the existing Rare Wolf target; Sprout follows Common Chick/Bee pacing. Existing
server-owned qualifying-source rules count approved chores/homework, completed
projects/milestones, eligible creations and earned daily reading receipts.
Daily source limits, accepted-promise snapshots and payout deduplication remain
unchanged. Browsing, artwork playback and greetings earn no progress.

Receiving challenge images are Baby-only and retain these exact IDs:
`review-ghost-fire-acquisition-icon`, `review-ghost-ice-acquisition-icon`,
`review-potted-plant-fire-acquisition-icon` and
`review-potted-plant-ice-acquisition-icon`. The existing mapping requires the
system collection definition; parent-authored names cannot impersonate it.
Actual PNG resolution still requires the correct received release.

## Presentation and expedition preparation

The existing resolver, portrait registry, sprite unavailable-art guard and
challenge surprise rules recognize the exact receiving family. With a null
manifest digest and no matching lock, ordinary delivery returns unavailable.
It does not recolor a Base portrait or substitute another creature. Explicit
synthetic staging is test-only evidence of component routing, not artwork review.

The existing child rule remains exact species + potion ownership, limited to
server-confirmed reached stages. Missing stable reads unlock nothing. Future
form names and Baby challenge illustrations remain withheld until permitted;
parent/staff behavior is unchanged. Incubation, natural egg identity, accepted
hatch replay, reduced motion, care and claim controls retain their behavior.

Keep `appearance_bindings` v1 and explicit species/potion/stage/motion bindings.
Appearance IDs must remain separate from native `source-*` motion IDs. Audit all
native names, actions, roots and bounds when assets arrive. Current pinned Base
sources contain Ghost 12/12/12 takes and Potted Plant 11/12/10, with opaque
materials and `source-idle` defaults. That implies 138 Fire/Ice GLBs plus twelve
256px stage portraits and four 256px acquisition images; actual received
inventory remains authoritative. No native Evolve take exists in those sources;
confirmed stage changes retain the same element's destination idle. Reuse the
existing global potion images.

No expedition service change is required. Base/Fire/Ice already share the
account/species allowance, including pending/unclaimed trips and claimed trips
started that local day. Ghost and Potted Plant have separate species allowances
and share the existing two-expeditions-per-child family-local-day cap. Frozen
loot, sibling/family scoping, return/claim behavior and care rewards remain intact.

## Receiving and activation gates

The private asset lane is **Prepare Fire and Ice assets**; the application team
keeps the established GET-only reader. Return the immutable review index URI,
SHA-256 and size; actual manifest digest; every artifact hash/size; runtime
inventory; previews; source/package pins; reproducible authoring inputs; and
verification instructions/results. Formal backup/restoration evidence is
separate from authoring delivery. Keep all licensed source packs, GLBs, PNGs,
archives, previews and receipts outside Git and outside ordinary Vite asset globs
until the receiving/import boundary is established.

Reuse exact contracts 1.4.0, avatar-runtime 1.3.0 and release-tools 1.6.0 tarballs
with their existing recorded SHA-256/npm integrity pins. Runtime preparation
does not authorize new code-package publication or an upgrade.

After receipt, verify all envelope/artifact/runtime hashes and sizes, safe archive
paths and the offline verification workspace. Integrate only the exact immutable
private review pin, exercise actual application components and show all twelve
appearances to the owner. Check every native take, portraits/icons, incubation,
hatch, all stages, same-element destination idle, reduced motion, material
isolation, saved identity and missing-file recovery. Preserve all earlier Base
and elemental releases and both existing Bird evolutions. Record actual tested
app revision and scene/source drift. Synthetic tests and desktop screenshots do
not establish physical-phone/native-shell acceptance.

After owner artwork approval and explicit publication authorization, require
canonical publication/readback. Then add the exact fifteenth release pin and
four positive pairs and move the four guarantees into ordinary initial content
as one reviewed activation: **35 pairs, ten elemental species, twenty elemental
guarantees**. Keep the historical preparation pack unregistered to avoid duplicate
offers. Preserve all prior pins and accepted promises. MAIN owns eventual merge,
the existing deployment and trusted exact-served live verification, under the
ordinary hosted CI/review/conversation/asset/live gates. This preparation grants
no merge, publication or deployment approval.

## Validation and rollback

Focused backend checks are
`apps.quests.tests.test_elemental_ghost_potted_plant_preparation` and
`apps.pets.tests.test_ghost_potted_plant_preparation`. Run concurrency checks on
disposable PostgreSQL/Redis; do not count SQLite skips as passed races. Normal
`config.settings` tests use the repository's syncdb shortcut on PostgreSQL;
validate the real migration graph separately with `manage.py migrate` on the
disposable base database and report the two results distinctly. Frontend synthetic coverage lives in `ghostPlantElemental.test.js`,
`RpgSpriteGhostPlant.test.jsx`, `GhostPlantPreview.test.jsx` and
`HatcheryGhostPlantPreparation.test.jsx`, with the shared ceremony, lifecycle and
challenge-surprise checks. Run normal lint, full frontend coverage/build and
required hosted backend/API/PWA checks. No shared response shape or currently
published fixture changes in this preparation.

Before activation, rollback removes only the unused receiving metadata,
presentation registrations and unregistered pack. It must not alter any active
family, policy, pin, saved identity or reward. After future activation, use a
reviewed withdrawal of only these four new offers/acquisition pairs while keeping
canonical delivery and loader/presentation identity support for saved companions
and accepted rewards. Preserve pending incubation promises, frozen challenge
rewards, eggs, potions, care and expedition loot. Do not blindly revert an entire
release after saved promises exist, delete canonical objects, migrate identities,
reroll or re-grant rewards.
