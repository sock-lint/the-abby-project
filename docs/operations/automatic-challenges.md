# Automatic challenges

Challenges describe a goal within a period. Matching saved activity advances
every eligible goal in the background. Pinning changes which goal is featured
on Today; it neither enrolls the child nor determines whether their work counts.
Badges remain permanent recognition of milestones, skills and sustained effort.
A single activity can count toward a daily bonus, a challenge and a badge.

## Activity, periods and rewards

Use the original activity date to assign progress to a period. Parent approval
confirms a submitted chore or homework contribution; approving last week's work
does not move it into this week's goal. Late approval may finish its original
period. Work outside the goal's window does not count.

Parent-created `this_week` goals use Monday through Sunday in the family's
timezone, with the next Monday as the exclusive end boundary. A repeating weekly
goal creates a separate occurrence for the next week. Completing a goal early
does not start another paid occurrence in the same week. The period, target,
reward and activity rule are frozen on each occurrence. Changes to a future goal
must not rewrite earlier earned progress or promised rewards. Explicit midweek
weekly creation includes already saved matching work from that week and may
complete immediately; the parent form explains this before saving.

Catalog goals use the stored trigger filters, not their names, artwork or reward
skill tags. A coding theme does not restrict contributions to coding unless the
filter explicitly does so. Nonrepeatable catalog goals have one enrollment-based
window. Repeatable catalog goals use successive windows of their stored duration;
they do not restart each time the child completes or pins them. An already active
legacy challenge retains its original dates, target, progress and reward promise.
New automatic enrollment omits reward-only badge-earned/Perfect-Day definitions;
those saved legacy instances remain readable. Default goals count effort events,
so bonus awards do not recursively complete more goals. Expedition returns count
only when the goal explicitly includes that trigger.

Built-in catalog challenges retain the existing source eligibility limits:
only the first planned homework assignment and first two logged creations per
local day count. The source service freezes that eligibility when it saves the
record. Replaying a source, deleting an earlier record, or retrying progress does
not turn an ineligible record into eligible catalog credit. Additional valid
records remain saved and can count toward an explicit parent-created goal.

These eligibility counters use the active Django timezone (default
America/Phoenix), preserving their existing day boundary. Goal periods and the
automatic daily bonus use the family's timezone. Movement goal progress continues
for every valid session after its separate first-three-session XP/drop limit.

Movement distance is a separate optional measurement from minutes. Store a
decimal distance with `distance_unit: mi|km`, normalize it to metres, and sum
actual distance for distance goals. An older session without distance does not
gain invented mileage. Running-specific goals match the selected movement type;
other movement does not count. Each valid session can advance measurable goals
even after the existing daily movement XP/drop limit has been reached.

Saved source identities make contribution retries idempotent. Pinning, reading
and reopening a page award nothing. Completion awards each
occurrence once and returns a receipt containing the actual Coins and skill XP;
the configured reward preview is not proof of payment. Daily Coins remain
Lucky Coin eligible; goal Coins retain the existing unboosted quest policy.
Before completion, a correction removes or replaces the source contribution. A paid occurrence never
rearms because its source was changed or deleted.

## Daily bonus

The daily bonus is one small automatic award per child per family-local day.
It qualifies on approved work or a completed project/milestone, or ten cumulative
minutes of logged project work or movement. Multiple short sessions accumulate.
It is created and evaluated while activity is saved, so opening Today and the
nightly task are not prerequisites.

The base reward is 10 Coins and 20 skill XP. XP uses explicit source skill tags
where available, with an explicit Persistence skill fallback for untagged
work. If neither is available, the receipt must report zero skill XP.
The receipt describes what was actually awarded, including an applicable boost.
Completing another qualifying activity that day does not grant a second bonus.

## Upgrade and recovery

Apply the additive migrations normally. Do not delete or rewrite `Quest`,
`QuestParticipant`, `DailyChallenge`, catalog definitions, inventory or ledgers.
Existing selected active challenges become the initial pin. Historical daily
reward values of zero retain their already-claimed meaning; nonzero values retain
the original reward promise. Schema migration and the first list/read must not
award completed historical work or create retroactive bonus payouts. The
scheduled bounded settlement may finish genuinely completed legacy bonuses with unpaid reward promises; it must
not award unfinished legacy rows or historical days without earned work.

Do not backfill all historical activities through the full RPG game loop: that
would rerun streaks, drops and unrelated rewards. A progress repair uses durable
source/contribution identities and touches only missing challenge state. Keep
new progress unavailable until its migration and server implementation are
deployed together. If a reward failure occurs, retain the durable source fact
as pending for inspection and an idempotent retry; never fabricate a
successful receipt or discard saved activity to release a gate.

## Validation

The producer in `config/tests/test_challenge_api_contract_fixtures.py` sends real
parent goal, child list/pin and movement requests with synthetic accounts and a
fixed clock. Its shared JSON bodies are consumed through the React API client in
`frontend/src/api/challengeContractFixtures.test.js`. They cover an unpinned goal
completing alongside another goal, cumulative distance, a daily bonus, actual
reward receipts, boost amounts and family-scoped rejections.

Reproduce against disposable test data:

```sh
SECRET_KEY=challenge-contract-test-only DATABASE_URL=sqlite:///:memory: \
  .venv/bin/python manage.py test --settings=config.settings_test \
  config.tests.test_challenge_api_contract_fixtures --verbosity=2
cd frontend
npm run test:run -- src/api/challengeContractFixtures.test.js
```

For an intentional contract change, set `UPDATE_API_CONTRACT_FIXTURES=1` only on
the local producer command, review the generated JSON, then rerun with that
variable absent. CI refuses fixture regeneration. Fixtures are raw server
responses, not hand-authored examples or permission-test replacements.

Run the affected goal/period/movement tests, migration-preservation check and
lorebook parity checks locally. Required hosted PR checks remain `Frontend
validation`, `Backend validation` and `API fixtures` as described in
[PR validation](pr-validation.md). PostgreSQL transaction tests are required for
concurrent contributions, completion/payout locking and recurrence; SQLite
contract checks do not verify those locks.
