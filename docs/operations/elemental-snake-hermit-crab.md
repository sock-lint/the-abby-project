# Fire and Ice Snake and Hermit Crab preparation

The owner accepted all twelve Fire/Ice Snake and Hermit Crab appearances shown
at application revision `d4c34c5d` and authorized exact runtime publication,
guaranteed challenge activation, and PR #336 through the ordinary MAIN merge,
deployment and live verification process. No repeat artwork approval or
regeneration is needed. Canonical publication/readback and application activation
remain pending. Pet stats remain deferred. The six released elemental families
and saved data remain supported.

The established scoped publisher and permanent write coordinator are in
**Prepare Fire and Ice assets**. This application retains its GET-only reader;
the exact publication handoff is prepared for the owner to copy to that
workshop. The application's canonical version-index read returned `NoSuchKey` / HTTP 404 on
October 24 before publication. That is historical probe evidence, not a claim
about every possible partial object or coordinator reservation. A returned
canonical receipt and fresh readback must precede normal delivery/activation.

## Prepared identities and acquisition

`shared/catalog/elemental-snake-hermit-crab.json` records proposed receiving
handles agreed with the application and the exact verified candidate digest.
Preparation state is `private_evaluation`; `artwork_accepted` and
`acquisition_active` are false. A verified digest and ID agreement are not artwork
acceptance or canonical delivery. The later owner acceptance above supersedes
historical pending-artwork labels; these delivery flags stay inactive until
canonical readback. The positive server policy and registered
content packs remain the acquisition authority. Presentation metadata grants no
ownership, progress, stage access or reward eligibility.

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
the candidate `abby-elemental-snake-hermit-crab` 1.0.0. Its separate evaluation
lock is absent from ordinary delivery, so normal resolution fails closed. Missing artwork
uses explicit unavailable presentation while companion controls remain usable;
neither a Base substitution nor a CSS recolor represents the missing appearance.
All thirteen approved runtime pins remain unchanged.

Receiving must preserve `appearance_bindings` v1: exact species + potion +
lifecycle stage + logical motion selects explicit native variant/action,
portrait and root-motion bindings. Native `source-*` IDs remain distinct from
appearance identity. The synthetic unit fixture remains separate from the actual
received runtime and does not establish artwork acceptance.

The verified runtime has 218 native GLBs, twelve transparent stage portraits and
four Baby-only acquisition images: 234 files / 88,597,843 bytes. Native takes per
element are Snake 14/14/20 and Hermit Crab 20/19/22 for Baby/Middle/Grown. There
are 218 logical motion bindings, no aliases and no authored evolution payloads.
Every default is `source-idle`, action `idle`, clip `Idle`. Middle Snake retains
the literal `source-slither-foward-in-place` and `source-slither-foward-w-root`
IDs and their `Slither Foward ...` clips. Do not normalize those spellings.
Descriptive stage edges introduce no motion or progression behavior; confirmed
growth uses the same element's destination idle.

Children retain exact-pair ownership and reached-stage restrictions, including
the per-render stage clamp and future-name masking. The staged release and
permitted stages remain separate inputs. Prepared acquisition illustrations are
Baby-only; their image handles cannot reveal future forms or grant discovery.
The existing parent/staff discovery rules and Chick/Bird evolution remain intact.

## Receiving and artwork review

The immutable private index is 4,820 bytes, SHA-256
`a9ea11c65c8cbdbfabd59a4a3f381cab243877ce3d012d57bc1db315ba095187`.
The manifest is 458,013 bytes, SHA-256
`2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3`.
Its delivery inventory is bound to
`fe4fadc29fd1fb64622809a5ef7dc1f8868b84a251e0345fec60d2306ea099d6`.
The six declared artifacts total 165,735,874 bytes. Application GET-only reads
verified every hash/size; all seven envelope objects denied anonymous access.

The verification ZIP is 89,198,383 bytes, SHA-256
`10e370c92015e6a7a93b8074f4208b1b00a1d4791c6b5569bba0683fabb73e33`.
Its 813 inventoried members plus the inventory pass exact hash/size and safe
archive checks. The inspected offline `node verify-candidate.mjs` passes without
credentials or network configuration. Independent parsing verifies all 234
runtime files and all 218 bindings, with geometry, UVs, rigs, skinning, animation
buffers, durations, roots and bounds preserved against 109 pinned Base takes.
Embedded Base/Fire/Ice texture digest sets are disjoint.

The separate authoring ZIP is 75,255,808 bytes, SHA-256
`2e2b469f67f303e4f909eee2e934be6a28597969bc1e78bf6a794b173105031f`.
All 219 inventoried members verify. This received archive is not a permanent
source-backup receipt: formal `handoff.source_backup` remains `pending`.
Workshop `preparing` and provisional-ID labels are receiving evidence, separate
from application ID agreement, app rendering and later owner acceptance.
Keep licensed inputs, GLBs, PNGs, archives, previews and evidence outside Git.
Reuse the existing global potion artwork; no new potion images are supplied.

Reuse these exact reviewed code artifacts; runtime publication does not imply
new code-package publication:

| Package | Version | SHA-256 |
| --- | --- | --- |
| contracts | 1.4.0 | `573ed16aee3d623f901cd3c70cdaa4c0ec77169acd2644bd5efa50ef916431c7` |
| avatar-runtime | 1.3.0 | `d3f5c79dc3bf5c9e94e3671bdf4d2723b0a499b0077870c8a235fa1369e8fbfd` |
| release-tools | 1.6.0 | `8d783ec82756f37ffb59d7bfc3edc26b9f67bc1dcc12af46cc881de6577deded` |

All three tarballs, npm integrity values and their supplied package sources
match the application's existing checked-in versions. No package upgrade,
repack or separate code publication is needed.

Keep candidates outside Vite's broad `avatar/shared` globs and ordinary builds.
`frontend/assets.snake-hermit-crab.evaluation.lock.json` binds the private review
candidate without changing any of the thirteen approved pins. The e2e-only
server allowlists its exact digest and complete inventory, serves GET/HEAD only
on loopback and injects the staged release into the real application components.
Historical Bee/Bat and Crown evaluation locks remain separate. Image dispatch
uses exact family membership so a Snake candidate cannot replace Bee/Bat icons.

From `frontend/`, point at the externally extracted runtime directory containing
`manifest.json` and `objects/`:

```bash
ABBY_ELEMENTAL_EVALUATION_ROOT=/absolute/private/runtime-directory \
ABBY_ELEMENTAL_FULL_MOTIONS=1 \
  npx playwright test e2e/elemental.pw.js \
  --grep 'meshtint-(snake|hermit-crab)' --output=/absolute/private/browser-results
```

Use the existing approved releases for Base/material and Bird regression checks.
Public CI without art reports the private renderer scopes as explicit skips;
unit fixtures exercise routing and failure handling without asserting real art.

Independent image review inspected all twelve delivered portraits, all four
Baby-only acquisition images and three comparison sheets without a blocking
defect. The actual private app run at `d4c34c5d` then passed seventeen cases,
all twelve forms, all 218 native takes, 66 exact portraits/icons, both existing
elemental Bird evolutions and 18 material groups / 72 independent instances.
Its source-bound original previews are the appearances the owner accepted.
That private run remains separate from canonical delivery and the refreshed
application's final validation.
The workshop snapshot records `origin/main` at `b19820fc` with thirteen pins,
separately from an older eleven-pin primary checkout. Against application
preparation head `2ac2933f`, six snapshot files differ for the expected resolver,
portrait/access, status-message/test and lifecycle preparation. Scene, camera,
playback and material preparation remain unchanged. Record the final tested
application revision and subsequent drift with the actual browser results.

Record the actual app revision, source/scene drift and evidence for incubation,
hatch, all twelve stages, every native take, exact portraits/icons, destination
idle, reduced motion, material isolation, instance disposal, persistence and
missing-file recovery. If no Evolve take exists, retain the same element's
destination idle. Report desktop/browser checks separately from physical-phone
and native-shell acceptance; neither has been performed for this release.

## Later activation and rollback

Keep the PR draft through canonical readback and application activation checks.
Owner appearance acceptance and release authorization are recorded above;
obtain canonical publication through the scoped asset session. Verify the
canonical version index, manifest and all
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
