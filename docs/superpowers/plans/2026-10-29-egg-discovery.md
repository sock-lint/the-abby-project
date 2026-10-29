# Targeted egg discovery implementation plan

October 29, 2026. Status: the owner expanded PR #359 to include the prospective
egg-source transition in the chat's isolated worktree, refreshed from main.
The release setting stays off
by default; this work makes its activation switch all new egg sources together.
It does not change production settings or publish artwork.

## Product decisions

- Choose one exact supported egg and potion appearance to pursue. Selecting a
  different target pauses the previous one without losing progress or searches.
- Earning stays connected to real-world activity. There are no minigames,
  parent-assigned difficulty scores, custom project reward values, daily
  attendance requirements, or consecutive-day requirements.
- Reading/listening, movement, and making/practice are the three activity types.
  Making/practice uses a simple session name and duration, without a project.
- Ordinary discoveries require 240 minutes total, including at least 90 minutes
  in each of two types. The remaining 60 minutes can use any type.
- Rare discoveries become eligible after two distinct creature families have
  hatched. Existing evolved pets and retained completed incubation evidence
  count; additional potion appearances of one family do not count twice.
- Each rare search requires 60 balanced minutes, with at most half supplied by
  one type. Two or three types can be combined; partial minutes are retained.
  Searches 1–4 independently have a 20% success chance. Search 5 guarantees the
  selected egg. One hour is the earliest search; five hours of balanced
  qualifying activity is the maximum. About 41% reach that guarantee and mean
  required effort is approximately 3 hours 22 minutes. These are candidate
  balance values, not measured household outcomes.
- Only starting a seasonal discovery is date-limited. Accepted discoveries can
  resume and finish after their window closes, using their accepted rules.
- Completing the collection is acceptable. Do not manufacture endless content
  by continually increasing requirements or duplicating equivalent tasks.

## Implementation scope

Discovery is disabled unless `EGG_DISCOVERY_ENABLED=True`. Enabling also applies
the prospective acquisition transition below; it is independent of whether an
account currently has a chosen target. Accepted promises and owned supplies
retain their rules. Activation follows normal review and release gates.

### Server-owned state

Add `apps/egg_discoveries` with account-owned targets, source credits, immutable
search outcomes, making/practice sessions, and request receipts. Database
constraints permit one active discovery per account and one lifetime discovery
for an exact target. Freeze accepted rules, exact reward ingredients, season
window, and display identities. Protect ingredient identities needed to honor
accepted promises.

Derive offers from the supported-art policy and the real typed
egg/potion catalog. Common and Uncommon pairs use the ordinary recipe; Rare,
Epic, and Legendary pairs use the rare recipe. This does not reclassify existing
species or owned companions.
Owned, incubating, already rewarded, unavailable, or incompatible pairs cannot
create another fresh reward. Paused accepted discoveries retain their terms.

Rewards are one exact egg, one compatible potion, and two supported common
foods, saved at acceptance. Grant through the existing inventory service once
in the progress transaction. Do not call quest completion or its accomplishment
loot pipeline. Existing inventory badge rules remain authoritative; their
indirect rewards must be included in the later economy audit.

If the saved supplies cannot be delivered, retain the activity and any winning
search without blocking normal source rewards. Expose pending delivery and an
explicit retry through selecting the saved target. Reads and duplicate request
replays do not retry delivery, and a saved winning search never rolls again.

### Activity credit

- Reading: credit a genuinely new session's full recorded minutes, independently
  from the existing daily reward's ten-minute cap.
- Movement: credit new recorded minutes independently from the three-session
  daily XP/drop allowance.
- Making/practice: save a required UUID, activity name and 1–240 minutes. It
  contributes discovery progress without introducing another XP, Coin or
  random-drop source.
- Only newly saved current-family-day sessions qualify. No old history scan,
  backdated credit, editing top-up, or retroactive transfer to another target.
- Retain source UUID tombstones after deleting a source record. Saving a UUID
  again cannot advance another target or reroll a search. Splitting sessions
  changes neither the total credited minutes nor the number of searches.
- Reading also respects its existing native reward-credit UUIDs from before
  this feature. Movement retains zero-credit request identities even while the
  mode is off; a metadata-only migration reserves surviving older UUIDs.
  Identities deleted before any durable receipt existed cannot be reconstructed.
- Keep surplus progress with its accepted target. A success cannot send the
  unused portion of the same saved source into the next selected discovery.

For three activity types, calculate rare search capacity as the lesser of total
minutes divided by 60 and minutes outside the largest type divided by 30, both
rounded down. Persist only newly reached search outcomes. Greedy irreversible
pairing would make source order affect eligibility; separately rounding each
type to 30-minute blocks would penalize a varied 100/100/100-minute routine.
Test both cases explicitly. Existing searches never reroll.

### API and child experience

Authenticated self-scoped endpoints:

- `GET /api/egg-discoveries/`: enabled state, supported offers, saved discoveries,
  the active target, authoritative requirements, progress, outcomes and receipts.
- `POST /api/egg-discoveries/select/`: select or resume an offer using a request UUID.
- `POST /api/egg-discoveries/<id>/pause/`: pause without erasing accepted state.
- `POST /api/egg-discoveries/practice/`: record making/practice with a request UUID.

Reject another account selector; a parent uses their own My space. Recheck active
membership under the existing family-then-account locking convention. A retry
with the same UUID and payload recovers the saved operation without another
selection, source credit, roll or reward; changed payloads conflict.

Show discovery above Tasks → Challenges and a compact chosen-egg card on
Today. Collapse earlier system egg promises and keep other goals separate. Display
server-confirmed requirements, category progress, saved searches and a clear
guarantee. Show egg artwork only, preserving exact-pair creature surprises until
hatching. Completion links to the existing Hatchery; incubation remains a
separate explicit action with its normal accepted wait.

Fence client reads and writes by account, credential and workspace. Preserve
the UUID for uncertain identical retries. A possible write is never retried
automatically. Switching identity discards its local draft and pending state.

### Seasonal support

Support reviewed exact-offer start windows through `EGG_DISCOVERY_SEASONS`,
using inclusive family-local dates. The first version publishes no invented
seasonal roster or dates. Freeze the selected window at acceptance; later
configuration edits or season closure do not revoke an accepted discovery.
Tests exercise entering, resuming and finishing across a window boundary.

## Required validation

- Pure allocation tests: ordinary total and variety thresholds; rare capacity,
  source splitting/order, surplus and five-search maximum.
- Native service/API tests: ownership/family isolation, one active target,
  pause/resume, eligibility, season snapshots, duplicate UUIDs, every search
  outcome, exact once-only inventory rewards, disabled behavior and read purity.
- Real source tests: full reading minutes, movement beyond the XP allowance,
  historical and zero-minute logs, deletion/recreation, normal reward preservation.
- PostgreSQL tests: concurrent selections, duplicate source writes, final searches,
  one grant, rollback and lock order. SQLite does not certify these checks.
- Shared raw API fixtures and React consumers for authoritative saved progress
  and award receipts, included in the required hosted fixture gate.
- React interaction tests: actual mutation requests, saved retry UUIDs, scope
  changes, loading/errors, pause/resume, practice, search/guarantee and egg-only art.
- Lint, affected native suites, web build, full frontend coverage and native
  staging build; all required hosted PR checks and independent Claude review.

## Prospective acquisition transition

Before enabling the release, review a synthetic balance
comparison and an explicit transition of every acquisition source:

1. Stop new enrollment in overlapping system egg challenges for participants in
   the new mode. Keep parent goals and unrelated bonuses separate.
2. Reconcile new random egg grants, expeditions, shops, mystery containers and
   inventory-badge effects with the selected discovery policy. Include all
   indirect Coins, food, badges and collection effects in pacing estimates.
3. Preserve every accepted challenge occurrence and legacy campaign, existing
   inventory, pre-rolled expedition loot and paid shop redemption promise.
   Define how retained work is presented without recreating an unfocused list.
   Account for the deployment boundary while older writers may still be serving
   requests; historical UUID reservation is not proof about already deleted or
   concurrently unrecorded pre-deployment activity.
4. Choose exact ordinary/rare rosters, starter treatment and returning seasonal
   offers using supported assets. Do not invent a new species, public asset
   release or license clearance through gameplay configuration.
5. Compare occasional, regular, weekend-heavy and high-activity synthetic
   routines, including bad-luck outcomes and a completed collection. Verify
   that 20%/five searches and the ordinary recipe remain the desired pacing.
6. Update in-app acquisition hints, guidance and any progression forecasts so
   new offers describe the actual released rules. Complete review, hosted CI,
   normal merge ownership and trusted deployment checks before activation.

The PR must not silently activate production, mutate production catalogs or
rewrite existing reward promises.

### Implemented transition contract

- `EGG_DISCOVERY_ENABLED` controls discovery and the prospective source policy
  together. The policy is global, independent of whether a child has selected
  an egg. Pausing or selecting nothing cannot reopen competing egg sources.
- New ordinary/accomplishment drops, Mystery Box draws, expedition pre-rolls,
  digital/combined shop requests and development grants exclude eggs. Potions,
  food, other items, activity rewards and parent-authored goals remain separate.
  Existing unopened boxes have no frozen item outcome and use the current pool;
  an empty pool consumes no box. Existing pouch values are not repriced.
- New system egg challenges stop enrolling. Accepted cycle zero, already saved
  recurring windows, campaigns and eligible explicit saved retries keep their
  rewards. Later unaccepted recurring egg windows stop opening. Canonical
  definition identity and history remain available to the earlier controls.
- A new non-egg system offer may meet a retired egg-bundle prerequisite through
  actual hatching/ownership of every exact typed pair that bundle promised.
  This keeps Reading Voyager reachable. It fabricates no completion, reward
  or history; accepted gate snapshots and retries retain their original terms.
- Owned eggs/potions, active incubations, pre-rolled expedition loot and paid
  shop redemptions remain fulfillable. No balances, inventories, reward prices,
  saved loot or accepted requirements are rewritten.
- Earlier system egg promises move into a closed **Earlier egg rewards**
  section. The selected discovery leads Today; changing an egg is an explicit
  disclosure action. Acquisition hints use the current mode and exact supported
  offers, including earlier accepted rewards.
- There is no free starter egg. All ten supported ordinary species are choices,
  including Chick; hatching two distinct species opens rare choices. Existing
  orphan eggs do not block a full discovery package, which can leave a surplus
  egg. Each exact appearance can still be discovered only once.
- The installed policy has 35 exact supported pairs: 24 ordinary and 11 rare.
  Rarity is the higher of the species/potion authored tiers; Common/Uncommon
  use ordinary rules and Rare/Epic/Legendary use rare rules. There is no new
  artwork or seasonal roster. Exact seasonal windows remain optional; a window
  restricts only new starts and never shortens an accepted discovery.
- The Lab filters prospective egg sources but does not model discovery or its
  indirect badge/care effects. Its page and report explicitly mark companion,
  mount and collection timelines unavailable in discovery mode. Captured
  catalog/rules bindings include the mode; old experiments cannot masquerade
  as forecasts under the new policy.

### Bounded effort and economy comparison

These are requirement calculations for a newly selected eligible egg, not
observed household retention or an old-economy drop forecast. There are no
attendance, consecutive-day, project or parent difficulty requirements.

| Routine | Ordinary egg | Rare egg after unlock |
| --- | --- | --- |
| 15 minutes reading + 15 movement each activity day | 8 activity days | First search after 2 days; guaranteed by 10 |
| 30 minutes reading + 30 movement each activity day | 4 activity days | First search after 1 day; guaranteed by 5 |
| One weekend with 150 making + 90 movement minutes | Earns an egg that weekend | Supports 3 searches; 48.8% cumulative chance, with 2 searches left to guarantee |
| Reading only, however long | Variety still needed | Variety still needed; no extra rolls |

A rare egg requires 1/2/3/4/5 searches with probabilities
20% / 16% / 12.8% / 10.24% / 40.96%. Mean effort is 3.3616 balanced hours;
maximum is five balanced hours. Recorded unbalanced effort and session overshoot
can make total logged time higher. A large source stays with its accepted
target even if it contains more time than necessary; it cannot auto-select and
fund another egg. This preserves the same no-carry rule as smaller logs.

With the current 24/11 roster, earning every discovery consumes at least 107
and at most 151 qualifying balanced hours, before session overshoot, uneven
activity or seasonal availability; expected rare-search effort yields about
133 hours overall. Each exact package adds one egg, one compatible potion and
two common foods: 35 eggs, 35 potions and 70 food units across the whole roster.
Incubation remains one at a time with its accepted elapsed wait. Collection is
finite and completable; no requirements increase as content runs out.

Discovery itself authors zero Coins/XP and causes no quest/accomplishment drop.
Native inventory, hatch, skill and collection badge evaluation remains active;
each newly earned badge can add its authored XP/Coins and an accomplishment
draw. That draw now excludes eggs, so the chain cannot fund another creature.
Two common foods contribute their actual native growth (including preference),
not a promised instant evolution. Reading, movement, check-in and ordinary
bonuses keep their existing caps and receipts. Earlier accepted rewards remain
a finite transition overlap; household inventories and completion histories
make its size variable. No fixed combined Coin/XP or retention forecast is
claimed by the effort table.

### Activation and rollback boundary

1. Merge only after refreshed exact-head hosted tests and independent review.
   Keep `EGG_DISCOVERY_ENABLED=False` during the schema/code rollout.
2. Deploy the reviewed revision to every HTTP, MCP and background writer,
   apply migrations, and drain older processes before activating. Mixed old
   writers can still grant eggs or fail to reserve source UUIDs; the database
   cannot reconstruct a request they saved and deleted before a receipt existed.
3. Run `python manage.py check_egg_discovery_rollout --json` through the normal
   approved environment. It checks the installed global roster, supplies and
   start windows without reading households or granting rewards. At least two
   ordinary species must be startable. A passing catalog check is not proof
   of deployment, writer drain, required CI or trusted live verification.
4. Set the release setting consistently across writers using the authorized
   deployment route, then perform normal trusted release verification. This
   implementation session does not mutate production settings or deploy.
5. Setting the mode back off restores prospective legacy acquisition and hides
   discovery. Saved discovery progress, UUID credits, searches and receipts
   remain intact for resumption; activity logged while off does not backfill.
   Roll back the setting with the current schema/code rather than removing the
   schema or running old writers against active discoveries.
