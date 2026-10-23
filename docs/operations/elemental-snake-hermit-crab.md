# Fire and Ice Snake and Hermit Crab preparation

The owner requested private artwork preparation and parallel application work
for Snake and Hermit Crab. This change prepares receiving and gameplay contracts;
it does not activate acquisition or install a runtime release. Pet stats remain
deferred. The six released elemental families and saved data remain supported.

## Prepared identities and acquisition

`shared/catalog/elemental-snake-hermit-crab.json` records proposed receiving
handles. Its `manifest_sha256` is deliberately `null`, preparation state is
`awaiting_private_assets`, and `acquisition_active` is false. These fields
document preparation; the positive server policy and registered content packs
remain the acquisition authority. Presentation metadata grants no ownership,
progress, stage access or reward eligibility.

| Species and sprite | Existing egg | Baby → Middle → Grown |
| --- | --- | --- |
| `meshtint-snake` | `meshtint-snake-egg` | Snakelet → Snake → Snake Naga |
| `meshtint-hermit-crab` | `meshtint-hermit-crab-egg` | Shell → Spike → Hermit King |

Both existing species are Uncommon. Each proposed path requires ten qualifying
accomplishments within 180 days, pays once, and authors zero Coins/XP:

| Challenge | Guaranteed bundle |
| --- | --- |
| Ember Coil | `meshtint-snake-egg` + `fire-potion` |
| Frost Coil | `meshtint-snake-egg` + `ice-potion` |
| Ember Shore | `meshtint-hermit-crab-egg` + `fire-potion` |
| Frost Shore | `meshtint-hermit-crab-egg` + `ice-potion` |

These use the existing server-owned eligibility, daily source limits, accepted
promise snapshots and payout deduplication. Approved chores/homework, completed
projects/milestones, eligible creations and earned daily reading receipts count
under the existing rules. Browsing a challenge does not earn progress. Existing
activity rewards and completion hooks retain their behavior.

The two compatibility entries and four challenges live in the unregistered
`content/rpg/prepared/elemental-snake-hermit-crab` pack. Normal startup/default
`loadrpgcontent` does not load it. The current 27-pair policy rejects its full
compatibility update atomically. Tests exercise future activation only with an
explicit synthetic 31-pair policy. Do not run this prepared pack in production
before the receiving, artwork acceptance and canonical delivery gates below.

The loader retains existing elemental-family compatibility authoring and permits
an additional registered family only when the positive policy approves its exact
species, sprite and all three Base/Fire/Ice pairs. Identity-collision checks
remain in force. This does not change `asset-support.json`, the initial content,
default pack registration, potion drop pools or any inventory identity.

Base, Fire and Ice share each species' existing daily expedition allowance,
including pending and unclaimed trips. Snake and Hermit Crab retain independent
species allowances. No elemental egg or new potion identity is introduced;
potion presentation begins with incubation and persists through hatch/growth.

## Application presentation

The resolver, portrait registry and child challenge-art access rules recognize
the proposed release `abby-elemental-snake-hermit-crab` 1.0.0. With no accepted
digest or installed payloads, ordinary resolution fails closed. Missing artwork
uses explicit unavailable presentation while companion controls remain usable;
neither a Base substitution nor a CSS recolor represents the missing appearance.
All thirteen approved runtime pins remain unchanged.

Receiving must preserve `appearance_bindings` v1: exact species + potion +
lifecycle stage + logical motion selects explicit native variant/action,
portrait and root-motion bindings. Native `source-*` IDs remain distinct from
appearance identity. Actual inventories, aliases and take counts are unknown
until receiving; the synthetic test fixture is not an artwork receipt.

Children retain exact-pair ownership and reached-stage restrictions, including
the per-render stage clamp and future-name masking. The staged release and
permitted stages remain separate inputs. Prepared acquisition illustrations are
Baby-only; their image handles cannot reveal future forms or grant discovery.
The existing parent/staff discovery rules and Chick/Bird evolution remain intact.

## Receiving and artwork review

The owner will pass the separate copyable prompt to **Prepare Fire and Ice
assets**. It requests twelve logical appearances, twelve transparent stage
portraits, four Baby-only acquisition illustrations and every actual native take.
Reuse the existing global potion artwork. Keep licensed inputs, GLBs, PNGs,
authoring archives, previews and private evidence outside Git.

Receive an immutable review-index URI with its exact SHA-256 and size. Use the
established GET-only import to verify that index and every declared artifact,
safe archive inventory, manifest and payload. Run the provided `README-VERIFY.md`
and `node verify-candidate.mjs` workflow. Inspect the separate authoring archive
and record backup status separately from runtime verification.

Reuse these exact reviewed code artifacts; runtime publication does not imply
new code-package publication:

| Package | Version | SHA-256 |
| --- | --- | --- |
| contracts | 1.4.0 | `573ed16aee3d623f901cd3c70cdaa4c0ec77169acd2644bd5efa50ef916431c7` |
| avatar-runtime | 1.3.0 | `d3f5c79dc3bf5c9e94e3671bdf4d2723b0a499b0077870c8a235fa1369e8fbfd` |
| release-tools | 1.6.0 | `8d783ec82756f37ffb59d7bfc3edc26b9f67bc1dcc12af46cc881de6577deded` |

Keep candidates outside Vite's broad `avatar/shared` globs and ordinary builds.
After verification, add an explicitly isolated review path for the actual pack,
without replacing the approved delivery pins. Exercise the real application
components and present all stages for owner review before requesting publication
or activation. Do not reuse the earlier Bee/Bat inventory or pretend its review
server already supports this release.

Record the actual app revision, source/scene drift and evidence for incubation,
hatch, all twelve stages, every native take, exact portraits/icons, destination
idle, reduced motion, material isolation, instance disposal, persistence and
missing-file recovery. If no Evolve take exists, retain the same element's
destination idle. Report desktop/browser checks separately from physical-phone
and native-shell acceptance; neither has been performed for this pending art.

## Later activation and rollback

Keep the preparation PR draft while the exact artwork is pending. After actual
app review and explicit owner acceptance, obtain canonical publication through
the scoped asset session. Verify the canonical version index, manifest and all
payloads with the application's normal GET-only import before adding its pin.
Then update the accepted descriptor, positive support policy and registered
content together; test the full 31-pair catalog and default-loader acquisition.
Preserve every earlier release and accepted saved promise.

Refresh against current `main`, run required hosted PostgreSQL/Redis, frontend,
API fixture and applicable browser gates, and obtain independent review of the
exact final head. MAIN owns merge/deployment and trusted live verification of
the exact served squash revision. A private review pass is not publication,
deployment, phone acceptance or permission to bypass those gates.

The preparation rollback is its focused code/content revert; no new production
asset pin or acquisition offer exists to withdraw. At later activation, record
the then-current approved baseline and concrete revert before merge. A rollback
must retain saved eggs, potions, pets, incubation receipts, accepted challenge
promises and expedition rewards, while stopping new unsupported acquisition.
Do not delete data or repoint existing release pins. Production reconciliation
remains with MAIN and the established scoped operator process.
