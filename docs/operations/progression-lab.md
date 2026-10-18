# Progression Lab

Staff parents open **Manage → Admin → Progression lab** to forecast an
anonymous new child's progression. The workbench reads the currently loaded
global content and supported-acquisition policy. It creates no accounts,
inventory, awards, notifications or household records.

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

## Access, bounds and API

Both endpoints require an authenticated staff parent. A regular parent or
staff child cannot use them. No real-account selector is accepted.

- `GET /api/rpg/progression-lab/` returns defaults, input bounds, editable
  routine examples, catalog counts, rules fingerprint, coverage and audits.
- `POST /api/rpg/progression-lab/simulate/` takes an anonymous scenario with an
  optional nested `economy` object and
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
