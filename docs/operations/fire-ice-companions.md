# Fire and Ice companions

The owner approved Fire and Ice appearances for exact species `chick`
(`cute-chick`) and `meshtint-wolf`, four guaranteed ingredient challenges,
and a daily expedition allowance shared by each account's species. Pet stats
are deferred. The owner accepted the in-app previews and authorized publication and deployment.
The application integrates the verified private candidate, and its branch now
prepares acquisition activation. Publication and deployment have not completed.

## Delivery state

The branch acquisition registry enables Base, Fire and Ice only for exact
Chick and Wolf identities; every other prepared family remains Base only.
These code changes are not production activation until the guarded release
and application merge/deployment complete. All eight existing release pins
are preserved, with a ninth pin for
`abby-elemental-companions` 1.0.0 at manifest SHA-256
`fe271f2ef6909dec7cb6fb44dc70635bd7efbb9bf01a1f74052065fcce675048`.
Authored `available_potions` declares Base, Fire
and Ice compatibility; that declaration does not establish art availability.
Registered Chick/Wolf starts require the canonical ingredient slug, typed
potion FK and matching metadata, plus the exact art policy and authored pair.
Tests exercise all four real start/wait/claim paths under the checked-in
policy, including preserved claims after an explicit policy retirement.
Other prepared families still reject elemental starts without consumption.

New elemental challenges are entirely omitted until their exact egg, potion
and species/potion pair are available. They cannot materialize an egg-only
reward after an unavailable potion is filtered. Accepted occurrences and
legacy quests retain their frozen ingredients and continue to pay once after
catalog retirement. Pre-offer facts are not replayed after a pair becomes
available.

Hatchery reads the existing codex for authoritative per-species compatible
potions. An unknown or failed catalog read blocks a new start, while an already
accepted ready incubation can still be hatched. Selecting another egg clears
an incompatible potion. Missing Fire/Ice art uses an explicit placeholder;
neither Base 3D art nor a CSS recolor establishes an elemental appearance.

The read-only candidate index matched SHA-256
`fcf62e1254f81e69cd42b9b9e7b0b974218c52d922fa925b3c534c6061842674`.
All six envelope objects, 743 verification inventory files, 185 authoring
inventory files and 200 runtime payloads verified. The standard verifier
reports `candidate_for_review`; it does not establish publication. The exact
code-only packages are contracts 1.4.0, avatar-runtime 1.3.0 and release-tools
1.6.0; their handoff SHA-256 and npm SHA-512 integrities are preserved in the
vendor packages and npm lock. Models, PNGs, authoring sources and review
evidence stay private and outside Git.

Private adoption uses the existing importer's local `releaseRoot` with the
verified candidate and unchanged Base releases, including seven retained
supplemental portraits. It does not repoint the ordinary production reader
to `candidates/`: no canonical version index exists for this candidate.
Required private production builds must continue to fail on absent or changed
payloads. Public validation builds retain their optional-art fallbacks.

## Guaranteed acquisition

| Challenge | Target | Frozen item bundle |
| --- | --- | --- |
| Ember Nest | 5 accomplishments | Chick Egg + Fire Potion |
| Frost Nest | 5 accomplishments | Chick Egg + Ice Potion |
| Ember Trail | 20 accomplishments | Wolf Pup Egg + Fire Potion |
| Frost Trail | 20 accomplishments | Wolf Pup Egg + Ice Potion |

All four are nonrepeatable automatic collection goals with 180-day windows
and zero authored Coins/XP. Existing source and completion rewards remain
independent. Qualifying sources are approved chores/homework, completed
milestones/projects, eligible creations (first two per local day) and the
earned daily ten-minute Reading Adventure receipt. These count accomplishments,
not distinct or consecutive days. Matching goals advance together regardless
of pin, with one contribution per source per occurrence.

Fire and Ice potions are excluded from random drops, expeditions and random
consumable pools under the checked-in policy. The first release's
guarantee comes from the fixed bundles. A Base mount does not cause an egg in
an elemental bundle to be salvaged: the egg remains useful until all elemental
forms promised by that bundle already have grown ownership. Other bundles
retain their existing salvage behavior. The anonymous Progression Lab mirrors
whole-offer availability and this bundle-specific salvage.

## Shared expeditions

Every appearance of one species shares a single start per account per current
Django-local day. A trip started on Base occupies the same allowance as Fire
or Ice. Any active/unclaimed trip also blocks the species across midnight
until explicitly collected. Different species and different accounts remain
independent. Existing accepted overlapping trips keep their original timing,
loot and individually claimable receipts.

Starts acquire the existing account award lock before the mount lock, so two
different appearances cannot race the species check. Existing availability
fields use the same species scope; `active_expedition` continues to identify
only the exact mount's trip. An alternate appearance blocked by an unclaimed
trip returns unavailable with null availability time and wait. The UI explains
that the other appearance's trip must be collected. The Lab uses deterministic
species selection and the same daily/pending restrictions before its separate
hypothetical account-wide expedition quotas.

## Exact application presentation

`sharedElementalRelease` resolves the twelve exact stage appearances through
`appearance_bindings` v1. Chick remains Chick → Fledgling → Bird; Wolf remains
Wolf Pup → Wolf → Werewolf. Potion appearance remains separate from native
animation-take IDs such as `source-idle`. Each of the 178 declared takes loads
its own source rig, animation action, loop and root-travel policy. Existing
Base adapters remain exact and unchanged.

Live companions and Hatchery previews use the same exact bindings and twelve
declared `icon` portraits at every display size. Four challenge and two potion
images use typed mappings in `shared/catalog/elemental-bindings.json`; those
presentation IDs never establish acquisition availability. Unknown identities,
missing private files and failed models retain labelled fallback and controls.
Egg item identities and their natural appearance stay unchanged.

The four Bird transition bindings preload the confirmed destination idle,
play once, and support a direct Baby → Grown chain. Stale selections, retries
and unmounts cancel old work and dispose owned resources. Reduced motion
skips the transition and shows the confirmed destination immediately. Wolf
uses its confirmed stage's native idle, with no invented transition.
The static Bird and roster framing rules remain independent from selected
motion bounds. Local preview controls never change growth, ownership or rewards.

The private review verified all canonical models against their original native
data and replayed 1,092 sampled WebGL poses, including simultaneous
Base/Fire/Ice isolation. Current-application browser checks use the actual
components and imported payloads:

```sh
cd frontend
ABBY_ELEMENTAL_FULL_MOTIONS=1 npx playwright test e2e/elemental.pw.js
```

Missing private art explicitly skips that acceptance scope. The synthetic
unit/API tests and public CI do not substitute for the private browser run.
The visible Chick bands cross brow/body because of shared source UVs; exact-art
owner review retains that documented presentation decision. Real-phone
performance and acceptance remain pending, separately from desktop viewports.

## Activation and rollback

Keep PR #307 in draft until exact canonical publication is proved and the
normal MAIN merge/deployment gates can complete. Owner visual acceptance is
recorded; it does not make private candidate objects a canonical runtime release.
The branch positive registry prepares only the exact Chick/Wolf Fire/Ice pairs,
with provenance bound to the pinned 1.0.0 manifest. Whole-bundle challenge
gating, typed ingredient checks and random-pool exclusions remain in force.

Publication is held on the installed operator connection: its approved release
helper supports the legacy avatar bundle (at most 83 files), while this verified
asset pack has 200 runtime payloads. An approved asset-pack publisher/coordinator
route is required. Do not split or relabel the bundle to fit the legacy schema,
use read-only credentials for writes, substitute the candidates namespace for
the canonical version index, or merge code that requires an unpublished pin.
The operator must publish this exact immutable release through an approved route,
then verify the canonical index, manifest and every pinned file before MAIN
merges and the existing deployment pipeline builds the app. No publication,
application merge or deployment has been performed by this preparation.

The application rollback baseline before asset adoption is foundations commit
`bf0a0fbab74fc1968d4fd4d582449dfa223c5d8e`. A fresh rollback PR restores its
eight-release lock, compatible package set and presentation code together,
preserving unrelated later changes. Reimport and verify the old pins and
supplemental portraits, then rerun ordinary checks and independent review.
Close only new elemental offers/starts through the positive policy; preserve
saved elemental ownership, nicknames, growth, accepted incubation identities
and deadlines, frozen ingredient promises and pending expedition receipts.
Accepted claims still fulfill exactly once and shared species allowance stays
intact. Honest unavailable-art fallbacks keep care and claim controls usable.
No database restore, reward reversal, conversion to Base or mutable release
replacement is part of art rollback.

Required normal checks include backend PostgreSQL races, challenge payout and
replay/retirement tests, API producers/consumers, Lab parity, frontend coverage,
web/native builds and independent review. The shared-allowance wire example is
`contracts/api/fixtures/pets-shared-expedition-allowance.json`; it contains only
synthetic saved ownership and no elemental acquisition authorization.
