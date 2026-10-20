# Fire and Ice companion foundations

The owner approved Fire and Ice appearances for exact species `chick`
(`cute-chick`) and `meshtint-wolf`, four guaranteed ingredient challenges,
and a daily expedition allowance shared by each account's species. Pet stats
are deferred. This change prepares application behavior while the private
asset workshop prepares the appearances.

## Delivery state

The production art registry and all existing asset release pins remain Base
only for these species. Authored `available_potions` now declares Base, Fire
and Ice compatibility; that declaration does not establish art availability.
Registered Chick/Wolf starts require the canonical ingredient slug, typed
potion FK and matching metadata, plus the exact art policy and authored pair.
A scoped synthetic art policy exercises all four real start/wait/claim paths
in tests only.

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
consumable pools even under a supported synthetic policy. The first release's
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

## Remaining asset intake

Receive twelve stage appearances and matching portraits, plus both Bird
evolution transitions in each element. Chick remains Chick → Fledgling → Bird;
Wolf remains Wolf Pup → Wolf → Werewolf. Potion appearance must remain separate
from native animation-take IDs such as `source-idle`.

The receiving change must verify the immutable private release, exact file
inventory/digests, every supported motion, transition source/destination,
portraits, simultaneous Base/Fire/Ice instances, reduced motion and actual
renderer output. Add the exact appearance bindings to both live companions
and Hatchery previews, then update the production positive registry for only
the verified pairs. Existing release pins and saved
ownership must be preserved. Public delivery uses the existing separate
owner-approved intake process; this foundations PR does not publish assets.

Required normal checks include backend PostgreSQL races, challenge payout and
replay/retirement tests, API producers/consumers, Lab parity, frontend coverage,
web/native builds and independent review. The shared-allowance wire example is
`contracts/api/fixtures/pets-shared-expedition-allowance.json`; it contains only
synthetic saved ownership and no elemental acquisition authorization. Physical
phone performance and complete visual acceptance await the actual asset intake.
