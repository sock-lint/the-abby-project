# apps/timecards/

Time tracking (clock-in/out) and weekly timecard generation with parent approval.

## Models
- `TimeEntry` — statuses: `active`, `completed`, `voided`. Partial unique constraint: one active entry per user. Auto-computes `duration_minutes` on save when `clock_out` is set. `auto_clocked_out` flag for stale-entry cleanup. The API keeps the project fixed after clock-in; note edits cannot reassign an entry.
- `ClockOutDropReceipt` — unique `(user, occurred_on)` random drop opportunity, independent of the entry/project so deleting work cannot re-arm it. The day is the family's local **clock-out** date, including sessions begun the preceding day. Historical receipts preserve completed work dates with at least ten minutes during migration without awarding items, Coins or XP; past family timezone edits cannot be reconstructed.
- `Timecard` — inherits `ApprovalWorkflowModel`. Statuses: `pending`, `approved`, `paid`, `closed`, `disputed`. Unique on `(user, week_start)`. Aggregates `total_hours`, `hourly_earnings`, `bonus_earnings`, `total_earnings`.

An approved exactly-zero timecard can be marked complete by a parent through
`POST /api/timecards/{id}/close/`. It becomes `closed`, preserves its approval
audit, and records one completion activity without a payout or another reward.
Closed cards cannot reopen, regenerate earnings, or repeat approval effects.
Nonpositive totals never offer payment; negative totals cannot be closed.
Only positive approved totals are offered in Greenlight's payment selection.

## Services
- `TimeEntryService` — read helpers: `completed_entries`, `daily_minute_totals`, `distinct_days`, `current_streak`, `longest_streak_at_least`.
- `ClockService`:
  - Homework plans are ineligible for clock-in. A historical homework timer can close without hourly XP, Coins or game-loop credit. Weekly payable hours and project bonuses exclude marked and legacy-linked homework plans; open-week reconciliation corrects earlier hourly credits, while approved/paid/closed history keeps its existing settlement protection.
  - `clock_in(user, project)` — enforces one active entry, project assignment, workable status, quiet hours (10pm–7am). Auto-transitions project `active → in_progress`.
  - `clock_out(user, notes)` — locks the user before reading/closing the active entry, then atomically saves hourly XP (10/hr) + coins (`COINS_PER_HOUR` × hours) via `AwardService.grant`. Positive entries keep RPG streak and factual progress; zero-minute entries skip the game loop. A single random `CLOCK_OUT` drop opportunity is consumed when the day's cumulative completed non-homework work first reaches ten minutes. The isolated drop step derives eligibility from the saved entry and commits its receipt with the roll. Later/smaller closes set `drops_allowed=False`, so splitting a session cannot increase drop rolls. Hourly rounding and saved timecard durations retain their existing rules. A failed hourly award rolls back the close for a safe retry. A drop-step storage/notification failure rolls back its receipt and loot while preserving saved work/hourly awards; a later positive close can try the unspent opportunity. A legitimate random miss commits the receipt and never grants another roll that day.
  - `get_active_entry(user)` — returns current active entry with `select_related("project")`.
  - `auto_clock_out()` — closes entries older than `MAX_ENTRY_HOURS` (8h). Called by Celery every 30 min.
- `TimecardService`:
  - `generate_weekly_timecard(user, week_start)` — locks the user and weekly card, atomically aggregates completed entries and posts hourly credits. Pending/disputed weeks append per-project ledger corrections for added/edited/voided hours, including zeroing an existing empty week and repairing partial legacy credits; repeats add nothing. Approved/paid/closed cards or cards with a payout ledger row retain their totals and status. Uses an explicit `project.hourly_rate_override` (including zero), otherwise `user.hourly_rate`; amounts round to cents before aggregation.
  - `approve_timecard(timecard, parent, notes)` — locks the user then a fresh card, stamps via `finalize_decision`, evaluates badges with `time` scope. Approved/paid/closed cards and cards with a payout do not repeat approval effects.
  - `close_timecard(timecard, parent)` — requires a same-family parent, locks the child then a fresh card, and accepts only an approved $0.00 card without a payout. Closed-card retries return the original completion without another activity. Status and its `ActivityLogService` audit commit atomically; the original `decided_by`, `decided_at`, notes, money and rewards remain intact.
  - `dispute_timecard(timecard)` — locks the user and fresh card; paid/closed cards or cards with a payout cannot reopen.
  - `mark_paid(timecard, parent, payout_amount)` — validates a positive finite decimal amount with at most two decimal places, checks parent/same-family access, and locks the child before the timecard. A first payout requires an approved card (or a legacy paid card needing repair), its exact full total, and sufficient approved payable ledger balance through `apps.payments.greenlight.validate_payable`. The payout ledger row and paid status commit atomically; an existing payout makes retries safe even after a status change. A retry can repair a legacy paid card whose failed request never wrote its payout when its earned funds remain available. New Greenlight confirmations may associate a card and use the same lock/order and payout ledger authority; statement matching never creates a second debit. See `apps/payments/CLAUDE.md`.

## Celery tasks (`tasks.py`)
- `auto_clock_out_task` — every 30 min.
- `generate_weekly_timecards_task` — Sun 23:55 local.
- `send_weekly_email_summaries_task` — Sun 08:00.

## Constants
- `ClockService.QUIET_HOURS_START = 22`, `QUIET_HOURS_END = 7`.
- `ClockService.MAX_ENTRY_HOURS = 8` — >4h flagged for review, >8h auto-clocked out.
- `ClockService.DROP_MINUTES_PER_DAY = 10` — cumulative completed work needed for the one daily clock-out drop opportunity. Reporting helpers continue grouping work by clock-in date for their existing timecard/streak reports.

## Key entry points
- `services.py` — `ClockService`, `TimeEntryService`, `TimecardService`.
- `tasks.py` — Celery Beat scheduled tasks.
- `export.py` — CSV export for timecards.
