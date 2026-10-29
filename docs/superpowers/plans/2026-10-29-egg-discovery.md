# Targeted egg discovery implementation plan

October 29, 2026. Status: implementation started in an isolated owner-chat
worktree. The first pull request implements a disabled-by-default preview.
It does not activate a production economy transition or publish new artwork.

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

## First pull request: working preview

The preview is disabled unless `EGG_DISCOVERY_ENABLED=True`. It must remain off
in production until the prospective acquisition transition below is reviewed.
The normal challenge, drop, shop, incubation, and expedition rules remain intact.
The preview is for isolated synthetic evaluation, not a claim that parallel egg
earning has already been removed.

### Server-owned state

Add `apps/egg_discoveries` with account-owned targets, source credits, immutable
search outcomes, making/practice sessions, and request receipts. Database
constraints permit one active discovery per account and one lifetime discovery
for an exact target. Freeze accepted rules, exact reward ingredients, season
window, and display identities. Protect ingredient identities needed to honor
accepted promises.

Derive preview offers from the supported-art policy and the real typed
egg/potion catalog. Common and Uncommon pairs use the ordinary recipe; Rare,
Epic, and Legendary pairs use the rare recipe. This is a preview mapping for
evaluation; it does not reclassify existing species or owned companions.
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
  preview is off; a metadata-only migration reserves surviving older UUIDs.
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

Show the preview above Tasks → Challenges and a compact chosen-egg card on
Today. Keep the old challenge experience available during the preview. Display
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

## Required validation for the first pull request

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

## Subsequent release: prospective acquisition transition

Before enabling the preview as the normal product, review a synthetic balance
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

The first PR must not silently enable this transition, mutate production
catalogs, change live settings, or rewrite existing reward promises.
