# apps/chores/

Recurring household tasks with a submit-then-approve workflow. User-facing label is "Chores" under Tasks; frontend page `/chores` redirects to the stable `/quests?tab=duties` route.

## Models
- `Chore` — family-scoped task definition. `recurrence` (daily / weekly / one_time), optional `due_date` for one-time chores, `reward_amount` (money), `coin_reward`, `xp_reward` (pool split across `ChoreSkillTag` rows). `assigned_to` nullable FK — null means available to all children. REST writes and proposal approval reject deadlines on recurring chores; switching away from one-time clears its deadline.
- `ChoreCompletion` — inherits `ApprovalWorkflowModel`. Statuses: `pending → approved` or `pending → rejected`. Snapshots `reward_amount_snapshot` + `coin_reward_snapshot` at submission time. Unique constraint: one active (non-rejected) completion per chore per user per period. `completed_date` identifies that period (Monday for weekly), not the submission date. Read-only `timing_snapshot` v1 preserves the household timezone, actual submission timestamp/day, recurrence, covered period, deadline and on-time/late comparison. Legacy rows keep null snapshots; review or schedule edits never invent or rewrite them.
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
- **Submission timing**: the current period and availability use the family's local date. Daily periods end on that day; weekly periods run Monday–Sunday inclusive. One-time chores optionally have a deadline and no period bounds. Submission on or before the deadline is on time; after it is late; no deadline has no timeliness classification. A child cannot backdate. These labels do not change awards, review or repeat eligibility.
- **Reviewed history**: `/api/chore-completions/?status=reviewed&user_id=<child>` returns normal paginated approved/rejected rows, scoped to the requesting family (or child themselves). Malformed IDs return 400; foreign, non-child or inaccessible IDs return 404. Pending rows stay in the review queue. Read-only `current_due_date` follows the current chore deadline, including null after clearing it; it never replaces `timing_snapshot.due_on`.
- **Withdraw**: owner-only `POST /api/chore-completions/<id>/withdraw/` hard-deletes a pending row.
- **`Chore.save()` defense-in-depth**: auto-attaches to default family when `family_id` is None.
- **`pending_parent_review`**: when True, the chore can't be completed — used for parent-proposed chores that haven't been finalized yet.
- **First challenge credit**: approval locks the child before the completion and before saving `decided_at`, using the same account lock as automatic enrollment. A concurrent first challenge read therefore cannot exclude that accepted approval from its initial window. PostgreSQL approval/read interleavings for chores and homework are covered by `tests/test_approval_concurrency.py`.

## Key entry points

Personal parent requests use `X-Abby-Space: personal` and exact self-assigned
chores. Create/update force self assignment and zero money. Completion invokes
the existing locked approval/award service in the same submission transaction,
with a zero money snapshot even for older money-bearing chores. Parent personal
availability excludes shared and child chores; children still submit pending
completions. The account role and Family management permissions do not change.
Personal catalog/detail, dashboard, next-action rewards and submission audit
project zero cash even when a legacy Family chore retains a money reward;
stored Family configuration and historical completion snapshots stay intact.
Personal lists retain all own published chores for editing, including inactive,
off-week and completed one-time chores. These retained rows are unavailable and
stay out of dashboard actions; completion eligibility still comes from the
existing service. Today annotations use the current household day for one-time
and daily chores, and the current Monday period for weekly chores. Older saved
completion statuses remain in completion history without inflating today's count.
`?pending=true` remains pending-only.
- `services.py` — `ChoreService` (all business logic).
- `models.py` — `Chore.WeekSchedule`, `ChoreCompletion.Status`.
