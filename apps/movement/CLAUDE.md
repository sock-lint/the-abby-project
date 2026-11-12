# apps/movement/

Self-reported physical activity sessions. No approval flow — child logs a session and earns XP immediately. First `DAILY_REWARD_LIMIT` sessions per local day fire XP + drop roll + game loop; subsequent sessions still advance automatic measurable goals while skipping the separate movement XP/drop award path.

## Models
- `MovementType` — catalog of sessionable activities (seeded with ~10 rows covering Sports + Body Work). `default_intensity` (low / medium / high), parent-extensible via `created_by` FK. `MovementTypeSkillTag` provides default skill fan-out.
- `MovementTypeSkillTag` — `(movement_type, skill, xp_weight)` mirroring `ChoreSkillTag`.
- `MovementSession` — child-logged row. `duration_minutes` (capped to `MAX_DURATION_MINUTES=240`), `intensity`, `occurred_on` (local-day bucket), `xp_awarded` (0 if over daily cap), nullable decimal `distance_meters`, display `distance_unit` (`mi|km`), and optional `client_request_id` UUID. Older rows retain null distance.
- `MovementDailyCounter` — inherits `DailyCounterModel`. Anti-farm gate that survives session deletes.

## Services

Parents can log their own activity in My space with `X-Abby-Space: personal`.
Lists/deletions are self-scoped and a nonself `user_id` is rejected before
logging or rewards. Family keeps the existing explicit child logging flow.
Parent sessions use the same XP limits, measured distances and automatic
challenge activity pipeline; the space hint changes no account role.

- `MovementSessionService`:
  - `log_session(user, movement_type, duration_minutes, intensity, notes, occurred_at, distance, distance_unit, client_request_id)` — validates a positive measured distance, normalizes it to metres, buckets the saved session in the family timezone, preserves the daily XP/drop cap, and records automatic challenge activity independently of that cap (`TriggerType.MOVEMENT_SESSION`). Identical UUID retries return the saved session and original challenge receipts; changed details are rejected.
  - `compute_xp_pool(duration_minutes, intensity)` — `floor(minutes / 10) × XP_PER_10_MIN × intensity_mult`. Under 10 min = 0 XP.

## Challenge progress and distance

`POST /api/movement-sessions/` accepts optional decimal-string `distance` (up to
three fractional digits) and `distance_unit`. One mile is exactly 1609.344 metres;
distance never substitutes for duration or guesses the distance of an older
session. The read response exposes normalized metres, display-unit distance
rounded to the accepted three fractional digits with trailing zeros removed,
request UUID and `challenge_receipts` wrapping all matching goal deltas plus an
optional automatic daily bonus. Deletion voids the source contribution for unpaid
goals; it never resets the movement reward counter or rearms a paid occurrence.
See [automatic challenge operations](../../docs/operations/automatic-challenges.md).

Deleting an activity type returns HTTP 409 when sessions or saved challenge goals
reference it, preserving those records and goal promises. The existing `error`
response names the blocking kind; shared types never expose a family's private
goal names, children or goal counts in that message.

## Constants
- `DAILY_REWARD_LIMIT = 3` — sessions per family-local day that earn movement XP and a drop roll; automatic goal progress has no three-session cap.
- `INTENSITY_MULTIPLIER` — low 0.5×, medium 1.0×, high 1.5×.
- `XP_PER_10_MIN = 5`, `MAX_DURATION_MINUTES = 240`, `MIN_DURATION_MINUTES = 1`.

## Exceptions
- `MovementSessionError`, `MovementTypeError`.

## Key entry points
- `services.py` — `MovementSessionService`.
- `models.py` — `MovementType`, `MovementSession`, `MovementDailyCounter`.
