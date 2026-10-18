# Progression Lab

Staff parents open **Manage → Admin → Progression lab** to forecast an
anonymous new child's progression. The workbench reads the currently loaded
global content and supported-acquisition policy. Forecasts create no accounts,
inventory, awards or notifications. The experiment notebook saves private
design evidence separately; its observation panel reads only your family's
recent-child Coin ledger aggregates.

## Save findings and act on them

Use the experiment notebook to name a hypothesis and capture the current
routine, candidate policy and explicit numeric targets. Coin experiments compare
the installed rules with a payout envelope or the 100-Coin commitment prototype.
Expedition-limit experiments preserve the selected Coin policy on both sides
and compare unlimited expeditions with shared per-child launch or item limits. Saved routine edits create a new
revision; imported reports never become trusted evidence.

Run control and candidate explicitly. The server generates both from one
detached catalog and matching seeds, then saves immutable reports, inputs,
criteria, rule/catalog/evaluator fingerprints and deployment source metadata.
Each forecast retains the existing 10,000-work-unit bound; a paired request
permits 20,000 combined units and is limited to five per minute. A notebook
holds at most 20 experiments, each with 20 comparisons and 100 decisions.
Each paired evidence record is limited to 4 MiB. Oversized daily traces are
stored losslessly as versioned columns and all daily row values; API reads and
downloads restore the original complete reports, including all calendar days.
Legacy saved reports remain readable. Results that still exceed the cap are rejected
without replacing an earlier comparison.

Choose up to six bounded criteria. Costs are whole cents; completion rates
range from 0 to 1. A day percentile describes only completing journeys, so
also set a minimum completion rate when most children must reach the reward.
Disabled purchasing, an empty content denominator or an unreached milestone
produces insufficient evidence, never a zero-day success. No targets means
unconfigured, not passing. Targets measure the candidate, with control values
and differences retained for comparison.

Record keep testing, revise, or ready for design with a reason, concrete next
action and review date. Ready for design requires fresh, passing simulation
criteria and grants no publication authority. Edits or changes to rules,
catalog or criterion evaluation make earlier evidence stale; rerun before
recording another decision. Earlier reports and decisions remain readable.
Records are private to their author and current family, including between
co-parents. There is no client-supplied result or decision-edit endpoint.

Use **Manage challenges and items** for content drafts, preview, simulation
and explicit publication through the existing workbench. Expedition policy
requires a reviewed code change. The [concrete reward proposal](progression-reward-proposal.md)
describes the opt-in 75/25 commitment allocation and 10/25/50 expedition table.
The separate payout envelope does not simulate that issuance policy.

## Observe the installed economy

The separate observations panel uses a fixed last-30-day period in the
family's current timezone. It includes currently active, nonstaff children
registered within the last 90 inclusive days, excludes provisioned live-check
families and accepts no household or child selectors. It reports ledger-active
children and child-days alongside all eligible child-days. A Coin transaction
is evidence of ledger activity, not retention or a visit without an award.

New expedition direct, expedition salvage and opened-pouch awards receive
internal typed attribution without changing their amounts, boosts or timing.
Historical rows are not rewritten. Mixed unclassified positive adjustments
remain unknown and make the measured automatic totals a lower bound. The
panel reconciles opening balance + credits - debits = closing balance;
activity events and overlapping reward receipts are never added to it.
No eligible children or ledger entries means insufficient evidence. More than
100 eligible children or 100,000 ledger rows returns a capacity state with
unavailable totals, rather than a partial or zero sample.

These observations measure today's installed uncapped rules. They cannot
validate a 100-Coin policy that has not been deployed, estimate family costs,
or establish content exhaustion/retention. They do not read journals, report
child identities or aggregate other households. A saved decision and review
date provide the manual follow-up; no notification, timer or automatic reward
change is installed.

**Save observation checkpoint** retains the server's current accounting report
against the saved experiment revision, with its period, cohort denominators,
coverage and installed-rule binding. Each experiment permits 20 immutable
checkpoints. Save a baseline before taking an action and another at review;
empty samples remain insufficient evidence. Checkpoints never accept posted
client totals, enroll users in a live treatment or imply that changing cohorts
form a causal test. The recent-child window does not establish annual retention.

## Make a forecast

Choose an editable example routine or enter activities per active day. The
scenario starts with zero XP, Coins, pets and inventory. Chore and habit reward
amounts are explicit assumptions about hypothetical parent-authored activities;
the workbench does not inspect a family's configured chores or habits.

Visits occur on the first configured number of days in each seven-day block.
The horizon is 30, 90, 180 or 365 calendar days. Each simulated child uses a
separate reproducible random seed; the first child's seed is the supplied
seed. The same scenario, loaded catalog, model rules and seed reproduce the
same report.

Run the simulation explicitly. Editing controls does not run it or change the
last result. Keep a report as a comparison baseline, change the routine, then
run again. A comparison describes those complete scenarios; changing their
activities changes their random draw sequence even with the same seed.
Download the JSON report to retain its assumptions, coverage, version bindings,
aggregate results and bounded example journey.

## Interpret the results

- **Completion rate** includes every simulated child, including children who
  never reach the milestone within the horizon.
- **P10, median and P90 days** describe only children who reach that milestone.
  A median day with a low completion rate is not a promise for most children.
  An unreached milestone has null dates, rather than a completion at day zero.
- **Modeled finite content** is the report's stated subset of supported
  badges, one-time challenges, cosmetic identities and companion growth
  milestones. It is not the number of activities left in the whole app.
- **Targets not completed** and gaps between discoveries are design indicators.
  Uncompleted targets include missed one-time challenge windows, which the
  report counts separately as expired opportunities. They are not all still
  available to that simulated child; expiration never counts as completion.
  Repeatable activities can keep paying after their initial novelty is gone.
  Neither measure predicts boredom or retention.
- **Flows** separate average Coin/XP/item sources from spending and consumption.
  When purchasing is enabled, the report separates earned Coins, exchanged
  Coins, spent Coins and the remaining balance. Private shop offers are never
  read: affordability applies to the anonymous offers entered in the scenario.
- The example journey belongs to one seed and explains that child's outcomes;
  it is not the median child. Its event count and truncation flag distinguish
  the bounded displayed history from the complete aggregate simulation.

Read the coverage and audit sections with every report. Unsupported mechanics
are explicit exclusions, not zero rewards or consumed content. A forecast
without the intended global catalog loaded is not an estimate of that catalog.

## Model boundary

The server uses the installed XP thresholds and weighted splitting, source
caps and direct rewards, level-gated eligible drop tables, companion pool
weights, automatic challenge matching, supported badge criteria, hatching,
food growth and expedition tier rules. Simulated state is held in memory.
The model never calls award writers inside a rolled-back transaction.

Companion care includes the installed incubation duration, currently 24 elapsed
hours. Each report records its `pet_incubation_policy`; that snapshot is bound
to its rules fingerprint. The duration is a server rule, not a scenario control.
New forecasts use the current setting. Existing report bodies retain their
original policy, and reports made before this policy was recorded remain
unrecorded rather than inheriting today's setting.

The first eligible egg and potion are consumed during an active care visit,
reserving the single unfinished incubation slot. This creates no pet or badge.
The deadline stays fixed for that egg. Time advances on inactive days too;
a ready egg continues to occupy the slot until the next active care visit
claims it. Visits are modeled at the same time each calendar day, so an egg
started on day 1 can hatch on day 2 under the 24-hour rule, or later if the
child does not visit. Claiming occurs before that visit's activities and
feeding. Only a claimed pet can grow, earn companion badges or become a mount.
Selecting no feeding still permits incubation and hatching.

The daily trace separates waiting eggs from ready, unclaimed eggs. Neither
counts as an owned companion or a completed finite target. The example journey
records incubation start, readiness and the actual hatch separately; readiness
alone grants no rewards. Food already saved in inventory can be used after a
claim, so subsequent growth timing still depends on that routine's food supply.

Hatching and confirmed evolution evaluate the same pet and badge scopes as
live care, including their existing Coins and XP. Reachability includes those
care events when a companion can be obtained, so badge-gated challenges and
finite targets follow the same path. The rules fingerprint includes the live
ownership/growth hooks; forecasts made before a hook changes are different
model evidence, even when the catalog itself is unchanged.

The initial model supports reading, approved synthetic chores, positive
synthetic habits, tracked project time, journal entries, creations and
movement. Activity skill tags and automatic companion-care choices are
reported assumptions. Expedition rewards are rolled at launch and claimed
at the next active visit after their return.

Homework, completed projects and milestones, private shops and parent goals,
weekly payment settlement, birthdays, grades, consumable use/boosts,
Perfect Day and legacy/co-op campaigns remain outside the model. Unmodeled badge criteria
are listed individually. The workbench does not verify production deployment
or artwork delivery and does not inspect existing children's progress.

## Purchasing and family costs

Enable purchasing to enter hypothetical real-world rewards and print requests.
Each offer has a Coin price, a planning estimate of its fulfillment cost,
lifetime stock and either a one-time purchase or a minimum interval between
purchases. Offers are ordered by priority. Saving for the highest-priority
eligible offer and buying whichever eligible offers are affordable are
different policies; compare both before interpreting a price as balanced.
The model attempts purchases after an active visit's rewards are collected.

First Coin affordability and first purchase are separate measurements. A
child can afford an offer but still wait because of a purchase policy, stock
or a family budget. Unreached dates remain null and their completion rates
include every trial. Once spending starts, affordability uses that child's
actual remaining Coin balance; it is not the income-only forecast for an
otherwise identical child who never buys anything.

The family-cost allowance is per child and resets in each actual calendar
month, using the scenario's fixed, editable start date. It covers the entered
fulfillment-cost estimates, independently of Coin prices. Costs are assumed
to occur immediately on purchase. A partial calendar month receives the full
entered allowance; it is not prorated. A forecast spanning a month boundary can
therefore use two monthly allowances. Stock does not automatically restock. A
trial is an alternative history of one new child, not an additional sibling;
do not sum trial costs into a family bill or multiply a child percentile into
a family percentile.

Printing uses the same pure whole-Coin quote as live print approvals:
`ceil(estimated_minutes / minutes_per_coin)`. A null rate disables Coin pricing
and makes the modeled print free in Coins. Separate monthly time and filament
allowances can constrain print purchases; null means unlimited and zero means
none. The simulation assumes immediate successful printing, using the entered
minutes and whole grams for resource usage. It does not predict queue times,
failed prints, measured running time, material prices or parent overrides.
The entered fulfillment cost is an independent estimate, not a conversion
from Coins to dollars.

Optional money assumptions cover approved synthetic chores and project time.
Hourly money follows the live per-entry calculation: round entry hours to two
decimal places, then multiply by the assumed hourly rate and round money to
cents. For example, 20 minutes at $8/hour produces $2.64 per entry. The model
assumes these earnings are approved and available immediately; actual weekly
timecard generation and approval delays remain outside the forecast.

An explicit money-to-Coins policy can cover a purchase shortfall from the
child's available earned money, subject to the installed exchange rate, the
$1 minimum and an optional monthly exchange allowance. It cannot create money,
cash out Coins or apply Coin boosts to an exchange. Money earned, money
exchanged, money still owed and estimated reward costs stay separate. An
exchange reduces money owed; it is not an additional family expense. The
report's combined obligation estimate adds remaining money owed to estimated
fulfillment costs within each trial before aggregating.

Digital shop fulfillment and purchased consumable effects remain excluded.
The simulation creates no actual reward offers, redemptions, print requests,
payments, exchanges or ledger rows. These assumptions never change live
earning rates, exchange settings, shop prices or printing policy.

## Compare expedition and pouch reward budgets

The optional `reward_budget.daily_coins` is a hypothetical shared allowance
per child per calendar simulation day. Null keeps installed uncapped rules;
zero removes Coin credits from the selected sources; a positive whole number
limits their combined credit. The 50, 100 and 150 Coin examples are experiment
settings, not validated balance recommendations. Every mount shares the same
allowance. Unused allowance expires each day, including inactive days.

The allowance covers direct expedition Coins, expedition duplicate-cosmetic
salvage and all opened Coin pouches, including pouches from activity drops.
Other sources, including parent-authored chore Coins, reading Coins, challenge
rewards and other drop salvage, stay outside this pool. It does not change
XP, expedition item slots, food, eggs or cosmetic draws. Consumable boosts
remain excluded from the model.

This experiment removes excess Coins from the hypothetical journey. Pouches
are still consumed; omitted value is neither saved in inventory nor deferred
for a later day. Expedition returns are processed before end-of-visit pouch
opening, so expedition rewards receive the shared allowance first. Raw Coins
describe requests within that journey, not an independently run uncapped
counterfactual: changes to lifetime Coin badges can affect later eligibility.
Only credited Coins enter wallets, lifetime earnings and purchasing.

Reports show raw, credited and omitted Coins by source, capped days, and
daily cumulative totals. Keep an uncapped report as the baseline, select a
budget, then rerun with the same routine, seeds, prices and purchasing policy.
Compare purchase timing and balances together with finite-content milestones;
reducing Coin income does not automatically extend item or companion content.
Saved routines and exported reports retain the budget. Older saved routines
without this field import with uncapped rewards.

These controls change no live rewards. This is not a proposed cap on claiming
already promised loot: a future live design must establish any reduced values
before new expedition commitments or pouch grants and preserve existing loot
and owned-item promises. Holding pouches unopened would delay liquidity while
retaining their value; that is a different experiment.

## Access, bounds and API

Both endpoints require an authenticated staff parent. A regular parent or
staff child cannot use them. No real-account selector is accepted.

- `GET /api/rpg/progression-lab/` returns defaults, input bounds, editable
  routine examples, catalog counts, rules fingerprint, coverage and audits.
- `POST /api/rpg/progression-lab/simulate/` takes an anonymous scenario with
  optional nested `economy`, `reward_budget`, `reward_commitment` and
  `expedition_budget` objects and
  returns the normalized assumptions, milestone ranges, daily aggregates,
  source/consumption totals and example journey.

Individual bounds are 40 trials and 365 days, with bounded activity counts and
global catalog sizes. Their combination must also fit a 10,000-unit work
budget: trials multiplied by calendar days plus active visits multiplied by
requested daily activity/expedition sources and enabled purchasing/offer
checks. The server checks this before
reading the catalog. The typical 90-day, 20-child routine fits; longer or busier
routines may need fewer trials (for example, ten for 180 days or five for
365 days with the typical routine). Oversized requests fail explicitly and
never silently reduce their sample size. Simulation requests are limited to
ten per minute per caller.
Reports bind the engine version, rules fingerprint, catalog fingerprint and
the deployment's `SOURCE_COMMIT` when supplied. A source commit of
`unavailable` is explicit; the fingerprints still identify the modeled input.

Backend tests compare selected calculations with real domain services on
disposable records, reject simulator writes and household reads, check seeded
repeatability and exercise permissions and input limits. Shared synthetic API
fixtures connect the producing endpoints to React consumers. Keep those checks
and coverage notes current when live progression rules change.


## Acting on reading and collection gaps

Default `loadrpgcontent` loads the initial seed, `reading-adventures` and
`collector-reading-2026` in one transaction. Explicit `--pack` loads only that
pack; dry runs roll back the complete default batch. The initial pack is unchanged.
Three daily Reading Adventures within 14 days grant a supported Chick egg, Base
potion and two Birdseed. A repeating five-in-seven-days goal provides care food;
a twenty-in-45-days goal offers the existing Bookworm title. These goals author
no Coins. Existing general quest/badge bonuses still apply and are modeled.

After Full Ark (15 species), three sequential chapters require 5, 10 and 20 new
daily Reading Adventures and grant a title, frame and title. These six new
finite quest/cosmetic targets require 35 reading days after the gate, with
365-day chapter windows. Their three recognition badges author no Coins or XP.
Only explicit reading goals consume daily awarded receipts; reading does not
advance unfiltered effort goals or daily effort bonuses. Saved source dates,
family ownership, corrections, deletion and retries preserve the daily limit.

## Promise-preserving commitment prototype

`reward_commitment: {"enabled": true}` selects the fixed 100-Coin design:
75 for new expedition commitments across all a child's mounts and 25 for random
activity pouches per day. It cannot be combined with a non-null payout envelope.
Short/standard/long tiers establish 10/25/50 direct Coins and 1/2/3 item slots.
Direct promises are reduced only before launch when allocation is low. Candidate
items must fit their full pouch value or worst positive duplicate salvage before
weighted selection; established promises are never rerolled or partially paid.

Reports separate commitments, payments, pending direct Coins, unopened/pending
pouches and contingent salvage. Authored pouches remain outside these allocations.
Empty trips/slots and filtered paths are explicit. Unavailable finite targets
are excluded paths, never extra content runway. Delayed claims can exceed 100
Coins per day; boosts and live concurrent reservation storage remain unmodeled.
This is not a live hard payout limit or a rollout-ready economy.

Saved experiments use `candidate_policy: "envelope"` (legacy/default) or
`"commitment100"` (requires `candidate_daily_coins: 100`). Their installed control
has both experiments disabled. Older clients omitting policy on an edit preserve
the stored policy. A notebook decision never changes content or live rewards.


## Compare shared expedition launch and item budgets

`expedition_budget: {"daily_launches": null, "daily_items": null}` leaves
expeditions unlimited. Independently set whole-number launches (0–15) and item
units (0–45) per child per calendar day. The UI supplies unlimited, 1/2/3-launch
and 3/6/9-item examples; custom values may combine both limits. These remain
Lab assumptions and do not alter live ExpeditionService, drops or content.
Routine presets preserve the selected limits and Coin policy. Legacy report
imports default missing limits to unlimited; malformed or incomplete objects
are rejected rather than silently changing an experiment.

Every mount shares the same daily capacity; unused capacity does not carry.
The launch limit applies to eligible idle mounts before launch. The item limit
applies before weighted loot selection, reserving one unit per item actually
promised. A whole Coin pouch or cosmetic counts as one unit, even if the
cosmetic is later salvaged. Full item values and previously frozen promises
remain payable. Direct Coin promises still follow the selected Coin rules:
after item capacity runs out, Coin-only or completely empty trips can still
launch. The report explicitly counts these outcomes. Automatic oldest-first
mount selection is a model assumption, not a simulated child preference.

Trip accounting separates requested opportunities, available mounts, launched
trips and launches prevented by the limit. Item accounting reconciles nominal
slots on launched trips = promised units + budget-withheld slots + slots with
no eligible item. New promises equal claimed plus pending units after subtracting
grandfathered claims/pending units. Mean totals reconcile; separate percentile
values can describe different journeys. Zero-direct-Coin and completely empty
trip percentages use summed counts, never a ratio of independent medians.
Saturated days (allowance fully used) differ from limited days (an opportunity
was actually withheld). No-mount days do not imply a binding limit.

Acquisition and challenge capacity use the limits too. Reports compare finite
targets with an unlimited-expedition denominator under the **same Coin policy**.
Targets losing their only modeled acquisition path are reported separately;
removing access cannot count as longer runway. Reached-rate and conditional
milestone dates still need to be read together.

In the notebook choose `candidate_policy: "expedition_limits"`, with
`candidate_daily_coins: null` and a complete `candidate_expedition_budget`
containing at least one non-null limit. Control configuration has unlimited
expeditions; candidate changes only those limits. Selected Coin and purchasing
rules are identical. Switching to this policy explicitly captures the current
Lab routine; use **Use current routine** for later changes. Coin-only candidates
require unlimited expedition limits to avoid confounded comparisons. New
criterion options cover launched trips, promised items, empty trips, first-grown
completion day and first-grown reached rate. All criteria still share the
six-target maximum, immutable evidence and freshness checks.

Account/family deletion traverses only primary keys and ownership foreign keys
when fencing and checking collected rows. Saved comparison and observation JSON
bodies are not decoded by ownership checks, including recursive parent checks.
Regression tests cover self deletion, parent-managed deletion, family closure
and a foreign comparison link that must continue to fail closed.
