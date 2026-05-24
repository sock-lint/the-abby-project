# apps/chores/

Recurring household tasks with a submit-then-approve workflow. User-facing label is "Duties"; frontend page `/chores` redirects to `/quests?tab=duties`.

## Models
- `Chore` — family-scoped task definition. `recurrence` (daily / weekly / one_time), `reward_amount` (money), `coin_reward`, `xp_reward` (pool split across `ChoreSkillTag` rows). `assigned_to` nullable FK — null means available to all children.
- `ChoreCompletion` — inherits `ApprovalWorkflowModel`. Statuses: `pending → approved` or `pending → rejected`. Snapshots `reward_amount_snapshot` + `coin_reward_snapshot` at submission time. Unique constraint: one active (non-rejected) completion per chore per user per day.
- `ChoreSkillTag` — `(chore, skill, xp_weight)` fan-out table mirroring `ProjectSkillTag`.

## Services
- `ChoreService`:
  - `is_active_this_week(chore, target_date)` — ISO week parity check for alternating schedules.
  - `get_available_chores(user, target_date)` — annotates each chore with `is_done_today` + `today_completion_status`.
  - `submit_completion(user, chore, notes)` — validates active/assigned/period constraints, creates pending completion, notifies parents.
  - `approve_completion(completion, parent, notes)` — race-guarded with `select_for_update`. Posts to `PaymentLedger` + `CoinLedger` + skill XP via `AwardService.grant`, fires RPG game loop (`TriggerType.CHORE_COMPLETE`).
  - `reject_completion(completion, parent, notes)` — race-guarded. Notes woven into rejection notification body.

## Exceptions
- `ChoreNotAvailableError` — raised on constraint violations (inactive, wrong assignment, duplicate, off-week).

## Gotchas
- **Shared-custody alternating weeks**: `Chore.week_schedule` is `every_week` or `alternating`; when alternating, `schedule_start_date` sets the reference "on" week. `is_active_this_week()` compares ISO week parity. Availability is computed on-the-fly — no pre-generated instances, no Celery.
- **Withdraw**: owner-only `POST /api/chore-completions/<id>/withdraw/` hard-deletes a pending row.
- **`Chore.save()` defense-in-depth**: auto-attaches to default family when `family_id` is None.
- **`pending_parent_review`**: when True, the chore can't be completed — used for parent-proposed chores that haven't been finalized yet.

## Key entry points
- `services.py` — `ChoreService` (all business logic).
- `models.py` — `Chore.WeekSchedule`, `ChoreCompletion.Status`.
