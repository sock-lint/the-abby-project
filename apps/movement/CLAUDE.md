# apps/movement/

Self-reported physical activity sessions. No approval flow — child logs a session and earns XP immediately. First `DAILY_REWARD_LIMIT` sessions per local day fire XP + drop roll + game loop; subsequent sessions write the row but skip rewards.

## Models
- `MovementType` — catalog of sessionable activities (seeded with ~10 rows covering Sports + Body Work). `default_intensity` (low / medium / high), parent-extensible via `created_by` FK. `MovementTypeSkillTag` provides default skill fan-out.
- `MovementTypeSkillTag` — `(movement_type, skill, xp_weight)` mirroring `ChoreSkillTag`.
- `MovementSession` — child-logged row. `duration_minutes` (capped to `MAX_DURATION_MINUTES=240`), `intensity`, `occurred_on` (local-day bucket), `xp_awarded` (0 if over daily cap).
- `MovementDailyCounter` — inherits `DailyCounterModel`. Anti-farm gate that survives session deletes.

## Services
- `MovementSessionService`:
  - `log_session(user, movement_type, duration_minutes, intensity, notes, occurred_on)` — bumps daily counter, writes session, distributes XP if under daily cap, fires RPG game loop (`TriggerType.MOVEMENT_LOGGED`).
  - `compute_xp_pool(duration_minutes, intensity)` — `floor(minutes / 10) × XP_PER_10_MIN × intensity_mult`. Under 10 min = 0 XP.

## Constants
- `DAILY_REWARD_LIMIT = 3` — sessions per local day that earn rewards.
- `INTENSITY_MULTIPLIER` — low 0.5×, medium 1.0×, high 1.5×.
- `XP_PER_10_MIN = 5`, `MAX_DURATION_MINUTES = 240`, `MIN_DURATION_MINUTES = 1`.

## Exceptions
- `MovementSessionError`, `MovementTypeError`.

## Key entry points
- `services.py` — `MovementSessionService`.
- `models.py` — `MovementType`, `MovementSession`, `MovementDailyCounter`.
