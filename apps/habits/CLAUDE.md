# apps/habits/

Micro-behaviors distinct from chores — no parent approval, no dollar rewards, **no coin rewards**. User-facing label is "Habits" under Tasks; frontend page `/habits` redirects to the stable `/quests?tab=rituals` route.

## Models
- `Habit` — `habit_type` (positive / negative / both), `max_taps_per_day` (default 1, caps positive taps per local day; negative taps uncapped), `strength` (integer, decays toward 0 daily), `last_decay_date` (last completed family-local day evaluated), `xp_reward` (pool split across `HabitSkillTag` rows). `pending_parent_review` gates tapping. Table preserved as `rpg_habit` (state-only migration).
- `HabitLog` — single `+1` or `-1` tap entry. `streak_at_time` snapshots current login streak. Table preserved as `rpg_habitlog`.
- `HabitSkillTag` — `(habit, skill, xp_weight)` fan-out table mirroring `ProjectSkillTag`.

## Starter routine
- Every existing child receives the published positive **Brush your teeth** starter through migration `0007`; new children receive it atomically with creation in `ChildViewSet`. It starts with `max_taps_per_day=2` and the normal 5-XP setting. The two check-ins support a morning/evening routine without imposing time windows.
- `defaults.ensure_starter_habits` is called only at onboarding or explicit seeding, never on reads. Nullable, read-only `Habit.starter_key` identifies the starter as `brush_teeth`, with database uniqueness per child. Parents can rename, customize, pause or delete it normally; it cannot be reassigned to another child. Paused habits cannot be tapped.
- Existing published positive **Brush teeth** / **Brush your teeth** habits with two taps per day are adopted without changing their name, rewards, logs or paused state. Pending child proposals are never auto-published. A starter with a saved key survives later parent customization; repeat installation leaves it untouched.

## Services
- `HabitService`:
  - `log_tap(user, habit, direction)` — validates type compatibility, enforces daily positive-tap cap, updates `strength`, distributes skill XP via `AwardService.grant` (positive taps only), fires RPG game loop. Every accepted positive tap evaluates habit and meta badges, including habits configured with zero XP; badge bonuses and loot share the tap transaction. Returns `{direction, xp_reward, new_strength}`.
  - `decay_all_habits(user, target_date)` — decays untapped habits toward 0 by `max(1, max_taps_per_day // 2)`. Called by Celery task.

## Endpoints
- `GET /api/habits/history/?days=14` — per-habit daily net taps (sum of `HabitLog.direction` per local day), zero-filled, keyed by habit id (string keys — JSON). Role-scoped through `HabitViewSet.get_queryset` (children get only their own habits' series). `days` clamped 1..30 via `config.viewsets.clamp_int_param`. Feeds the 14-day `HabitHistoryBars` mini-bars on each ritual card in `Habits.jsx`, which refetch on every confirmed tap so today's bar moves immediately.

## Celery task
- `decay_habit_strength_task` — runs daily at 00:05 in the configured scheduler timezone. Evaluates the previous calendar day in each child's family timezone, preserving taps from that completed day. Strength and `last_decay_date` commit together under a habit lock; repeat or older deliveries cannot decay it again. Tapped and zero-strength days also advance the guard.

## Gotchas
- **Proposal ownership**: child create requests omit `user`; the write serializer treats it as read-only and the view saves the authenticated child as owner and creator. Parent create requests still require an explicit `user`.
- **Parent targets**: habit creation, reassignment and approval resolve `user` only within the authenticated actor's family. Existing same-family child, self and co-parent targets remain supported; starter habits still cannot be reassigned. Manual write serializers must receive request context; absent actor/family context admits no target. Foreign and missing target IDs return the same validation error before habit, tag or notification writes.
- **Optimistic taps**: the frontend mutates `strength` + `taps_today` immediately on click and rolls back if `logHabitTap` rejects.
- **Decay scaling**: high-frequency habits (`max_taps_per_day=4`) decay at `step=2` per missed day so they drift roughly twice as fast as daily habits.
- **No coins**: unlike chores and projects, habits intentionally award zero coins — they are behavior-building, not economic.

## Key entry points
- `services.py` — `HabitService` (all business logic).
- `tasks.py` — `decay_habit_strength_task`.
