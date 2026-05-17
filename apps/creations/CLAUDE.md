# apps/creations/

Child-authored "I made a thing" entries — past-tense, artifact-first. Required photo + optional audio + optional caption + child-picked primary skill + optional secondary skill from a creative-subset allow-list.

## Models
- `Creation` — owner, image (required), audio (optional), caption, primary_skill, secondary_skill, status (`LOGGED` / `PENDING` / `APPROVED` / `REJECTED`).
- `CreationBonusSkillTag` — parent-authored bonus XP fan-out for the approved-bonus path.
- `CreationDailyCounter` — concrete `DailyCounterModel` subclass; anti-farm gate that **survives `Creation.delete()`**.

## Services
- `CreationService` — `log_creation` (with first-2-per-day XP gate), `submit_for_bonus`, `approve_bonus` (default +15 XP), `reject_bonus`, `withdraw`, `today_status`.

## Endpoints
- `POST /api/creations/` (multipart, self-scoped — parent can optionally pass `user_id` to create on a child's behalf).
- `GET /api/creations/`.
- `DELETE /api/creations/{id}/` (owner or parent, blob-first).
- `POST /api/creations/{id}/submit/` (owner or parent).
- `POST /api/creations/{id}/withdraw/` (owner or parent — reverts `PENDING → LOGGED` on the existing row without unwinding baseline XP).
- `POST /api/creations/{id}/approve/` + `/reject/` (parent-only).
- `GET /api/creations/pending/` (parent-only, feeds `useParentDashboard`).
- `GET /api/creations/today_status/` (self-scoped — returns `{count, limit, remaining_with_xp}`).

## Gotchas

- **Creations**: child-authored "I made a thing" entries — past-tense, artifact-first. Required photo + optional audio + optional caption + child-picked primary skill + optional secondary skill from a creative-subset allow-list (`apps/creations/constants.CREATIVE_CATEGORY_NAMES` — 7 categories: Art & Crafts, Making & Fabrication, Music, Cooking, Creative Writing, Sewing & Textiles, Woodworking). **Fixed 10 XP baseline pool** — 100% to primary when solo, 70/30 split when both set. **Anti-farm gate:** first `DAILY_XP_LIMIT=2` Creations per user per local day fire XP + drop roll + game loop; third+ land silently in Sketchbook/Yearbook without XP. The counter lives in `CreationDailyCounter` (concrete subclass of `config.base_models.DailyCounterModel`, keyed on `(user, occurred_on)`) — it's incremented via `config.services.bump_daily_counter` BEFORE the Creation write and **survives `Creation.delete()`**, which is the whole point: a parent-cooperated create → delete → create cycle on the same day still skips the 3rd log's rewards. Pinned by `test_create_two_then_delete_one_then_create_still_skips_xp` in [`tests/test_services.py`](tests/test_services.py). **Parent bonus track:** child (or parent) taps "Submit for bonus" → `status=PENDING` → parent `approve_bonus` grants `DEFAULT_BONUS_XP=15` (tunable per-call) distributed via parent-authored `CreationBonusSkillTag` rows (falls back to the child's primary skill at weight 1 when no tags set). Rejection stamps `REJECTED` without reversing baseline XP — matches every other flow. Every `log_creation` emits a `ChronicleEntry.Kind.CREATION` via `ChronicleService.record_creation` (idempotent on `(user, related_object_type='creation', related_object_id)`). **Not `is_private`** — Creations are meant to be seen. Endpoints: `POST /api/creations/` (multipart, self-scoped — parent can optionally pass `user_id` to create on a child's behalf), `GET /api/creations/`, `DELETE /api/creations/{id}/` (owner or parent, blob-first), `POST /api/creations/{id}/submit/` (owner or parent), `POST /api/creations/{id}/withdraw/` (owner or parent — reverts `PENDING → LOGGED` on the existing row without unwinding baseline XP), `POST /api/creations/{id}/approve/` + `/reject/` (parent-only), `GET /api/creations/pending/` (parent-only, feeds `useParentDashboard`), `GET /api/creations/today_status/` (self-scoped — returns `{count, limit, remaining_with_xp}` so [`CreationLogModal`](/frontend/src/components/CreationLogModal.jsx) can show a moss/ember helper line above the form telling the kid whether the next log will earn XP). Frontend: `CreationLogModal` launched from a gold-toned `QuickActionsSheet` row (child-only); Creations appear in the Sketchbook filter pill with a `Palette` overlay + `Music` badge when audio is attached + pending chip + approved 🏅 ribbon; parent approval row in `ApprovalQueueList` grants the default +15 XP via `approveCreation(id, {})`. PortfolioView adds a `creations` section to the response + a `creations/<Category>/` folder in the ZIP export. Badge ladders: `creations_logged` (1/10/50/100/365 — Maker line), `creations_approved` (5/25/100 — Framed/Featured/Legacy), `creation_skill_breadth` one-shot (Polymath at 5 distinct creative skills). `TriggerType.CREATION_LOGGED` with `BASE_DROP_RATES` of 0.25 (between `habit_log` 0.15 and `homework_complete` 0.35). No `TRIGGER_DAMAGE` entry — Creations don't damage boss quests by design.

## Constants
- `apps/creations/constants.CREATIVE_CATEGORY_NAMES` — 7 categories: Art & Crafts, Making & Fabrication, Music, Cooking, Creative Writing, Sewing & Textiles, Woodworking.
- `DAILY_XP_LIMIT = 2` — first 2 Creations per user per local day earn XP/drops/quest credit.
- `DEFAULT_BONUS_XP = 15` — parent bonus track default.

## Key entry points
- `services.py` — `CreationService`, `DAILY_XP_LIMIT`, `DEFAULT_BONUS_XP`.
- `constants.py` — `CREATIVE_CATEGORY_NAMES`.
- `tests/test_services.py`.
