# Fire and Ice Bee and Bat preparation

This preparation adopts the verified private `abby-elemental-bee-bat` 1.0.0
appearance contract for application review. Owner approval of these actual app
previews, canonical runtime publication, acquisition activation and MAIN's
merge/deployment gates remain separate. Pet stats are deferred.

## Exact receiving identity

The immutable review index is bound to SHA-256
`4b318aa3fa172da7406a1525e9a135265cdfcfccd2818f6243e972616dd8d5d4`
(4,614 bytes). The manifest SHA-256 is
`7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5`.
Its 146 runtime files total 31,484,079 bytes: 130 native GLBs, twelve transparent
stage portraits and four acquisition review images. The workspace ZIP is pinned
by `d2ffa8f55c5d85b50e901e02095c6ba96b0309ae7f703c20e4692f83e21553ef`;
the separate authoring ZIP is pinned by
`d95ba670da5e997b82f40edd0f7d0e694b15f1384e87a6c56e9896381379fb0c`.
Both archives and all previews stay outside Git.

Receiving uses the documented Abby GET-only reader. Verify the immutable index,
every declared artifact's size and digest, safe archive inventories, all runtime
payloads and `README-VERIFY.md` / `node verify-candidate.mjs` before review.
The historical workshop `preparing` status is a receiving snapshot; this batch
has no canonical publication receipt yet.

The three code tarballs equal the application's existing vendor packages and
package-lock integrity pins. No package repack or version change is required:

| Package | Version | SHA-256 |
| --- | --- | --- |
| contracts | 1.4.0 | `573ed16aee3d623f901cd3c70cdaa4c0ec77169acd2644bd5efa50ef916431c7` |
| avatar-runtime | 1.3.0 | `d3f5c79dc3bf5c9e94e3671bdf4d2723b0a499b0077870c8a235fa1369e8fbfd` |
| release-tools | 1.6.0 | `8d783ec82756f37ffb59d7bfc3edc26b9f67bc1dcc12af46cc881de6577deded` |

## Application contract

`shared/catalog/elemental-bee-bat.json` adopts the exact release, appearance,
portrait and review-image handles as presentation identities. Review-image IDs
remain explicitly named `review-...-acquisition-icon`; they register no quest,
reward, threshold or acquisition eligibility.

| Species and sprite | Existing egg | Baby → Middle → Grown |
| --- | --- | --- |
| `meshtint-bee` | `meshtint-bee-egg` | Bee → Bumble → Sting |
| `meshtint-bat` | `meshtint-bat-egg` | Bat → Vampire Bat → Bat Lord |

Fire/Ice prefixes are display labels. Base names, saved species/potion identities
and natural eggs remain unchanged. There are no elemental eggs or new potion
items. The existing global Fire/Ice potion artwork remains in its approved
release. Incubation, hatching and growth remain server-owned.

`appearance_bindings` v1 selects exact species + potion + lifecycle stage +
logical motion. Native variant/action, portrait and root-motion identities stay
separate. Each stage rests on `source-idle`; Bat Lord retains the literal
`source-spin-attack-attack` take. Bee's stage take counts are 11/10/12; Bat's are
10/10/12 for each element. No Evolve take is supplied: confirmed growth displays
the same element's destination idle. Existing Chick/Bird transitions remain intact.
Missing, mismatched or unsupported bindings retain explicit unavailable
presentation; no Base substitution or CSS recolor represents missing artwork.

## Private review path

All twelve active production pins in `frontend/assets.lock.json` remain intact.
The Bee/Bat pin is recorded only in
`frontend/assets.bee-bat.evaluation.lock.json`. The existing Crown pilot lock
and its independent canonical import command remain unchanged. Neither normal
asset import nor web/native builds consume the Bee/Bat evaluation lock. Keep candidate bytes outside the checkout
and every Vite source tree; the broad `avatar/shared` URL glob would otherwise
emit them even without active catalog offers.

The e2e-only review server accepts an explicit external runtime directory,
verifies its exact manifest and complete payload inventory, and exposes only
those immutable files on loopback. The real owned-companion, Hatchery, portrait
and catalog components receive that staged release explicitly. This does not
install candidate delivery into ordinary app sessions or production bundles.

After standard active asset import, run from `frontend/`:

```bash
ABBY_ELEMENTAL_EVALUATION_ROOT=/absolute/private/runtime-release-directory \
ABBY_ELEMENTAL_FULL_MOTIONS=1 \
  npx playwright test e2e/elemental.pw.js --output=/absolute/private/browser-results
```

The directory contains the manifest and its `objects/` payloads. It is the exact
family/version/digest directory from the verified workspace, not a source-pack
or authoring directory. Without that explicit input, the Bee/Bat browser scopes
report that acceptance is pending; public CI exercises synthetic fixtures.

Record the actual tested app revision and current scene/source drift with the
private evidence and PR. Check all twelve Live/Hatchery forms, all 130 native
takes, exact portraits/review icons, destination idle, Base/Fire/Ice material
isolation, repeated instances/disposal, saved-state reload, reduced motion,
missing-file recovery and existing Bird transitions. Desktop narrow viewports
and SwiftShader checks do not establish physical-phone acceptance or performance.

## Activation and rollback

The positive server policy remains 23 supported pairs: fifteen Base pairs and
Fire/Ice for Chick, Wolf, Dragon and Mushroom. Bee/Bat acquisition stays disabled.
Guaranteed challenge names, thresholds and bundles must be agreed in the app
before activation; the artwork workshop supplied no reward rules. Use the
existing server-owned qualifying accomplishment rules and accepted-promise
snapshots. Every appearance of a species must keep the existing shared daily
expedition allowance and pending/unclaimed-trip restriction. No reward, drop,
stat or expedition policy changes are part of this preparation.

After owner artwork acceptance, verify a separate canonical publication receipt
and fresh standard GET-only import before moving this exact pin into the active
lock and enabling the four receiving pairs/challenges. Keep the preparation PR
draft while those gates are outstanding. MAIN owns merge, deployment and exact
served-revision live checks under the repository process.

Rollback of this preparation removes its presentation descriptor/evaluation pin
and explicit fixture support through a normal PR. Preserve the twelve active
release pins, earlier elemental families, saved eggs, potions, companions,
incubations, challenge promises and expedition records. The starting application
baseline is `e2afb7fb4069c4cfb558652e6a402e0fb2524fa4`; record a newer approved
served baseline if MAIN advances before activation. No data cleanup or migration
is needed for this presentation-only preparation.
