# apps/habits/

Micro-behaviors distinct from chores — no parent approval, no dollar rewards, **no coin rewards**. User-facing label is "Rituals"; frontend page `/habits` redirects to `/quests?tab=rituals`.

## Models
- `Habit` — `habit_type` (positive / negative / both), `max_taps_per_day` (default 1, caps positive taps per local day; negative taps uncapped), `strength` (integer, decays toward 0 daily), `xp_reward` (pool split across `HabitSkillTag` rows). `pending_parent_review` gates tapping. Table preserved as `rpg_habit` (state-only migration).
- `HabitLog` — single `+1` or `-1` tap entry. `streak_at_time` snapshots current login streak. Table preserved as `rpg_habitlog`.
- `HabitSkillTag` — `(habit, skill, xp_weight)` fan-out table mirroring `ProjectSkillTag`.

## Services
- `HabitService`:
  - `log_tap(user, habit, direction)` — validates type compatibility, enforces daily positive-tap cap, updates `strength`, distributes skill XP via `AwardService.grant` (positive taps only), fires RPG game loop. Returns `{direction, xp_reward, new_strength}`.
  - `decay_all_habits(user, target_date)` — decays untapped habits toward 0 by `max(1, max_taps_per_day // 2)`. Called by Celery task.

## Endpoints
- `GET /api/habits/history/?days=14` — per-habit daily net taps (sum of `HabitLog.direction` per local day), zero-filled, keyed by habit id (string keys — JSON). Role-scoped through `HabitViewSet.get_queryset` (children get only their own habits' series). `days` clamped 1..30 via `config.viewsets.clamp_int_param`. Feeds the 14-day `HabitHistoryBars` mini-bars on each ritual card in `Habits.jsx`, which refetch on every confirmed tap so today's bar moves immediately.

## Celery task
- `decay_habit_strength_task` — runs daily at 00:05 local. Decays untapped habits for all active children.

## Gotchas
- **Optimistic taps**: the frontend mutates `strength` + `taps_today` immediately on click and rolls back if `logHabitTap` rejects.
- **Decay scaling**: high-frequency habits (`max_taps_per_day=4`) decay at `step=2` per missed day so they drift roughly twice as fast as daily habits.
- **No coins**: unlike chores and projects, habits intentionally award zero coins — they are behavior-building, not economic.

## Key entry points
- `services.py` — `HabitService` (all business logic).
- `tasks.py` — `decay_habit_strength_task`.
