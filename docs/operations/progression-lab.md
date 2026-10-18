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
- **Flows** separate average Coin/XP/item sources from item consumption.
  Private shop offers are excluded, so accumulated Coins do not establish
  purchasing balance or time to afford a particular family's reward.
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
money, birthdays, grades, consumable use/boosts, breeding, Perfect Day and
legacy/co-op campaigns are outside this first model. Unmodeled badge criteria
are listed individually. The workbench does not verify production deployment
or artwork delivery and does not inspect existing children's progress.

## Access, bounds and API

Both endpoints require an authenticated staff parent. A regular parent or
staff child cannot use them. No real-account selector is accepted.

- `GET /api/rpg/progression-lab/` returns defaults, input bounds, editable
  routine examples, catalog counts, rules fingerprint, coverage and audits.
- `POST /api/rpg/progression-lab/simulate/` takes a flat anonymous scenario and
  returns the normalized assumptions, milestone ranges, daily aggregates,
  source/consumption totals and example journey.

Individual bounds are 40 trials and 365 days, with bounded activity counts and
global catalog sizes. Their combination must also fit a 10,000-unit work
budget: trials multiplied by calendar days plus active visits multiplied by
requested daily activity/expedition sources. The server checks this before
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
