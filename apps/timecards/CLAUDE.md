# apps/timecards/

Time tracking (clock-in/out) and weekly timecard generation with parent approval.

## Models
- `TimeEntry` — statuses: `active`, `completed`, `voided`. Partial unique constraint: one active entry per user. Auto-computes `duration_minutes` on save when `clock_out` is set. `auto_clocked_out` flag for stale-entry cleanup.
- `Timecard` — inherits `ApprovalWorkflowModel`. Statuses: `pending`, `approved`, `paid`, `disputed`. Unique on `(user, week_start)`. Aggregates `total_hours`, `hourly_earnings`, `bonus_earnings`, `total_earnings`.

## Services
- `TimeEntryService` — read helpers: `completed_entries`, `daily_minute_totals`, `distinct_days`, `current_streak`, `longest_streak_at_least`.
- `ClockService`:
  - `clock_in(user, project)` — enforces one active entry, project assignment, workable status, quiet hours (10pm–7am). Auto-transitions project `active → in_progress`.
  - `clock_out(user, notes)` — awards XP (10/hr) + coins (`COINS_PER_HOUR` × hours) via `AwardService.grant`, fires RPG game loop (`TriggerType.CLOCK_OUT`).
  - `get_active_entry(user)` — returns current active entry with `select_related("project")`.
  - `auto_clock_out()` — closes entries older than `MAX_ENTRY_HOURS` (8h). Called by Celery every 30 min.
- `TimecardService`:
  - `generate_weekly_timecard(user, week_start)` — aggregates completed entries, creates `PaymentLedger` hourly entries. Uses `project.hourly_rate_override` or `user.hourly_rate`.
  - `approve_timecard(timecard, parent, notes)` — stamps via `finalize_decision`, evaluates badges with `time` scope.
  - `mark_paid(timecard, parent, payout_amount)` — creates payout ledger entry (negative).

## Celery tasks (`tasks.py`)
- `auto_clock_out_task` — every 30 min.
- `generate_weekly_timecards_task` — Sun 23:55 local.
- `send_weekly_email_summaries_task` — Sun 08:00.

## Constants
- `ClockService.QUIET_HOURS_START = 22`, `QUIET_HOURS_END = 7`.
- `ClockService.MAX_ENTRY_HOURS = 8` — >4h flagged for review, >8h auto-clocked out.

## Key entry points
- `services.py` — `ClockService`, `TimeEntryService`, `TimecardService`.
- `tasks.py` — Celery Beat scheduled tasks.
- `export.py` — CSV export for timecards.
