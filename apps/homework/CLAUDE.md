# apps/homework/

One-off homework assignments with a submit→approve workflow requiring proof photos, a shareable link, or both. Homework pays **no money and no coins** — positioned as school duty, not work-for-hire. Rewards come from XP (via `HomeworkSkillTag`), RPG drops, streak credit, and quest progress.

## Models
- `HomeworkAssignment` (one-off task; `assigned_to` FK required; `due_date`; `effort_level` 1-5; optional `project` FK to AI-planned long-form).
- `HomeworkSubmission` (submit→approve with proof photos; inherits `ApprovalWorkflowModel`). Read-only `timing_snapshot` v1 freezes the household timezone, actual submitted timestamp/day, original deadline and saved timeliness. Older rows remain null; their stored timeliness remains available without claiming to know the original deadline.
- `HomeworkProof` (optional image uploads; a submission requires at least one image or `proof_url`).
- `HomeworkTemplate` (reusable assignment configs).
- `HomeworkSkillTag` (XP distribution; `xp_amount` fixed-per-tag pattern).
- `HomeworkDailyCounter` (anti-farm gate; concrete `DailyCounterModel` subclass).

## Services
- `HomeworkService` — `create_assignment`, `submit_completion`, `approve_submission`, `plan_assignment` (AI), `get_timeliness`, `can_self_plan`.

New submissions and previews count both the household-local day before the due
date and the due date itself as `on_time`. Two or more days before is `early`;
after the due date is `late` (or `beyond_cutoff` past the configured late cutoff).
Previously saved labels and timing snapshots retain their original evidence.

## Submission proof links

`POST /api/homework/{id}/submit/` accepts optional `proof_url` alongside image
uploads. One valid link can satisfy the proof requirement without photos; both
can be included. `HomeworkSubmission.proof_url` is a bounded 2048-character
HTTP(S) URL, blank for existing/photo-only submissions. The service validates it
locally, rejects embedded credentials and control characters, and preserves
sharing queries and fragments. It never fetches, previews, checks permissions
on, or downloads the linked document. Photo rows remain image-only for portfolio
and cleanup compatibility. The link is readable through the existing scoped
submission serializer and MCP reads; activity records do not include the URL.

Homework, Today review details and reviewed history show the saved external
link alongside photos. Parent approval still confirms the submitted work;
submission, withdrawal and family/assignee permissions use the existing guards.

## Endpoints
- `/api/homework/ai-settings/` (parent-only `GET`/`PUT`/`DELETE`; current family's planner settings).
- `/api/homework/` (CRUD + `submit` + `save-template` + `plan`).
- `/api/homework-submissions/` (read-only + `approve` / `reject` / `withdraw`).
- `/api/homework-proofs/{id}/` (destroy-only — owner or parent — deletes a single proof image without voiding the submission).
- `/api/homework-templates/` (CRUD + `create-assignment`).
- `/api/homework/dashboard/`.

`/api/homework-submissions/?status=reviewed&user_id=<child>` returns normal
paginated approved/rejected history for a child in the requesting household.
Children can read only their own history; inaccessible or malformed child IDs
return 404. Results use stable newest-first ordering, including tied timestamps.
The current assignment must also remain in the household. The read-only
`current_due_date` is explicitly the assignment's current deadline, separate
from the original deadline in a saved snapshot. Assignment cards expose saved
timing only from a submission by the assignment's matching child. Parent review
and later deadline/timezone edits do not recalculate submission timeliness.
Child dashboard due-today/upcoming/overdue buckets use the same household-local
day as submission timing and Today task urgency. This does not change reward
quota, Perfect Day or streak accounting days.

MCP tools: `list_homework`, `get_homework`, `create_homework`, `submit_homework`, `list_homework_submissions`, `approve_homework_submission`, `reject_homework_submission`.

## Gotchas

- **Legacy template skill IDs:** cloning accepts saved positive integer IDs and
  their canonical ASCII decimal strings (`"1"`), normalizing them before current
  existence/retirement admission. The saved template JSON and XP amounts stay
  unchanged. Padded, signed, float, boolean, malformed and oversized IDs fail
  before an assignment is saved. New template/assignment inputs remain strict;
  this compatibility rule does not exempt retired taxonomy from new work.
  Template updates may resend an exact saved canonical string or change it to
  the equivalent integer while retaining that same reference, including a
  retired skill. Strings for newly selected IDs remain invalid; malformed old
  tags may be removed and never grant a retirement exemption.

- **Homework plans are schoolwork:** the linked `Project` stores the assignment's
  steps and materials, and stays accessible through its detail URL. Its
  server-owned `is_homework_plan` identity includes older assignment links and
  persists for new plans even if the assignment is later removed. It is excluded
  from the ordinary project list and dashboard, cannot accept clock-ins, and
  cannot award project or milestone payments or rewards. Complete schoolwork
  through the original homework proof/submission/approval flow. Project detail
  returns `homework_assignment_id` only when the linked assignment matches the
  project's assigned child and family, so clients can return to Homework safely.

- **Child dashboard:** `pending` is a separate assignment section for submissions awaiting approval, regardless of due date. These assignments appear only once and retain the Withdraw action after their due date passes. Rejected or withdrawn overdue work returns to `overdue`; approved past-due work remains in history.

- **Homework**: one-off homework assignments with a submit-then-approve workflow requiring proof photos, a shareable link, or both. Both parents and children can create assignments. **`assigned_to` is required on the model FK but optional on `HomeworkAssignmentWriteSerializer`** so two callers stay clean: children omit it (the viewset's `perform_create` auto-sets `assigned_to=request.user`), parents must pass `assigned_to: <child_id>` (the viewset raises `serializers.ValidationError` → 400 otherwise — without that guard the service hits a NOT NULL FK and 500s). The parent quick-action ("Create homework for a kid") navigates to `/quests?tab=study&new=1`; [`pages/Homework/index.jsx`](/frontend/src/pages/Homework/index.jsx) reads `?new=1` once on mount via `useSearchParams`, calls `openCreate()`, and clears the param so refresh doesn't re-trigger. The frontend [`HomeworkFormModal`](/frontend/src/pages/Homework/HomeworkFormModal.jsx) also short-circuits before submit when `isParent && !form.assigned_to` so a parent who skips the (HTML-required) child select still gets a friendly error instead of bouncing off the backend. **Homework pays no money and no coins** — it's positioned as school duty, not work-for-hire. Rewards come from XP (via `HomeworkSkillTag`), RPG drops, streak credit, and quest progress. `effort_level` is a 1-5 hint that scales the per-tag XP pool on approval via `EFFORT_XP_FACTOR` (1: 0.6x, 2: 0.8x, 3: 1.0x, 4: 1.4x, 5: 1.8x — default 3 keeps existing assignments at parity, 5 is roughly 3x the XP of 1). Children may set their own. The factor multiplies the pool BEFORE distribution so each tag's proportional split is preserved. Pinned by `EffortLevelXpScalingTests`. `HomeworkTemplate` stores reusable assignment configs (title/description/subject/effort_level/skill_tags). **On creation:** `HomeworkService.create_assignment` fires `GameLoopService.on_task_completed(child, "homework_created", ...)` ONLY for the first create per child per local day — subsequent creates skip that reward loop call. Every saved assignment still records a challenge fact for explicit parent goals. The first-of-day check is gated on a `HomeworkDailyCounter` row (locked read-modify-write via `config.services.bump_daily_counter`); the counter row is independent of the assignment, so it survives both soft-delete (`is_active=False`) and hard-delete — a parent-cooperated `create → delete → create` cycle on the same day still skips the second loop call. This closes streak credit, drop, and built-in catalog quest-progress farming through this trigger; explicit parent goals can count all valid matching assignments. Mirrors the same pattern used by `CreationDailyCounter` and `MovementDailyCounter`; all three concretes inherit from `config.base_models.DailyCounterModel`. Planner-style badges (`HOMEWORK_PLANNED_AHEAD`) are evaluated immediately on create regardless so logging early pays off fast. **On submission:** `submit_completion` records the `Timeliness` label (early/on_time/late/beyond_cutoff via `HomeworkService.get_timeliness`), attaches proof photos and/or a shareable link, notifies parents, and saves timing evidence — no AI calls or currency snapshots. **On approval:** `approve_submission` distributes XP via skill tags, evaluates badges (including `HOMEWORK_ON_TIME_COUNT`), and fires `GameLoopService.on_task_completed(child, "homework_complete", {"on_time": bool})` so quests with `trigger_filter.on_time=true` can count only early/on-time submissions. **On delete:** `HomeworkAssignmentViewSet.perform_destroy` soft-deletes (`is_active=False`) so submission history is preserved. **RPG side effects from create are NOT reversed** — but the first-of-day gate preserves the source limit for streaks/drops/built-in quests; awarded XP/badges still don't unwind (matches every other approval flow). The anti-farm gate is pinned by `test_game_loop_fires_only_for_first_create_today`, `test_create_then_soft_delete_then_create_still_skips_second_loop`, and `test_create_then_hard_delete_then_create_still_skips_second_loop` in [`tests/test_services.py`](tests/test_services.py). **AI-planned long-form homework:** `HomeworkAssignment.project` (nullable FK to `Project`) links to a full project generated via Claude + MCP `create_project` tool use for complex multi-step assignments. `POST /api/homework/{id}/plan/` triggers AI planning. **Long-lead self-serve gate** (2026-04-25): parents can always plan; children can plan their own assignments only when the due date is at least `settings.HOMEWORK_SELF_PLAN_LEAD_DAYS` (default 3) days out. The "planning ahead" virtue earns autonomy; short-lead / urgent assignments stay parent-only because the conversation matters more than the AI plan when a child has waited too long. The gate is centralized in `HomeworkService.can_self_plan(user, assignment)` and surfaced to the frontend via the `can_plan` field on `HomeworkAssignmentSerializer` so the "Plan it out" button hides itself when self-serve isn't allowed. Routes: `/api/homework/` (CRUD + `submit` + `save-template` + `plan`), `/api/homework-submissions/` (read-only + `approve`/`reject`/`withdraw`), `/api/homework-proofs/{id}/` (destroy-only — owner or parent — deletes a single proof image without voiding the submission), `/api/homework-templates/` (CRUD + `create-assignment`), `/api/homework/dashboard/`. **Withdraw** (2026-05): owner-only `POST /api/homework-submissions/<id>/withdraw/` hard-deletes a pending submission **and** runs blob-first cleanup on every attached `HomeworkProof` image (Ceph DELETE before the row delete, matching the `ProjectPhotoViewSet.destroy` invariant). 400s once the submission has been approved. Frontend page: `/homework` (redirects to `/quests?tab=study`). Portfolio integration: approved homework proofs appear alongside project photos with filter tabs. MCP tools: `list_homework`, `get_homework`, `create_homework`, `submit_homework`, `list_homework_submissions`, `approve_homework_submission`, `reject_homework_submission`. **Scholar track content** (`content/rpg/initial/`): `Planner` / `Punctual` badges in `badges.yaml`, Scholar-themed cosmetics (`title-bookworm`, `title-scholar`, `frame-scholar`, `theme-library`) in `items.yaml`, and `Scholar's Week` / `On-Time Streak` / `Midnight Oil` quests in `quests.yaml`.

## Tunable settings
- `HOMEWORK_LATE_CUTOFF_DAYS` (default `3`) — past this many days late, a submission's `Timeliness` flips from `late` to `beyond_cutoff`. Homework pays no money/coins, so this only affects the submission label and the `on_time` quest filter — not any reward value.
- `HOMEWORK_SELF_PLAN_LEAD_DAYS` (default `3`) — how many days out an assignment's `due_date` must be for a child to self-trigger AI planning on their own assignments. Parents bypass this gate. Tuned so "planning ahead" earns autonomy while panic-mode (`due_date - today < N`) still requires a parent conversation. Read by `HomeworkService.can_self_plan`.

## Family planning AI settings

Parents configure homework and project planning in Settings → Planning AI. The optional
`HomeworkAISettings` row belongs to one `Family` and selects `openai` or
`anthropic` plus an explicit model ID. The settings endpoint derives the family
only from the authenticated parent and returns `{provider, model, has_api_key}`;
it never returns a saved key or ciphertext. `PUT` accepts `provider`, `model`
and an optional write-only `api_key`. An omitted/empty key preserves a key only
for the same provider; selecting another provider requires a replacement key.
`DELETE` or `provider="default"` removes the connection and disables new AI
homework and project drafts. The existing wire sentinel (`provider="default"`, empty model,
`has_api_key=false`) means disconnected; there is no deployment fallback.
Existing linked projects remain available. Updates lock the family row to
serialize co-parent saves.

`ai_settings.py` encrypts credentials with Fernet using a distinct HKDF domain
derived from Django `SECRET_KEY`. Rotating that secret requires entering saved
planning API keys again. Keep credentials out of logs, exceptions, localStorage,
fixtures and API read responses. Decryption/provider failures return a safe
message and never silently switch to another provider. Planning looks up the
assignment child's family at call time, preserving existing assignment and
lead-time permission gates. Children can use the configured planner when those
gates allow it but cannot inspect or edit its credentials. A missing family
connection stops before any provider request and asks a parent to connect OpenAI
or Claude in Settings → Planning AI. A connected planner always uses an
8192-token output budget through `config.llm.complete_json`. Planning never uses
the deployment-wide AI configuration. Those deployment settings
continue to serve project idea suggestions and ingestion enrichment. Family keys
serve homework planning and the reviewed project plan assistant. The existing
homework settings endpoint, model and encryption domain remain compatible.

`tests/test_ai_settings.py` covers credential storage, validation, family/role
boundaries, settings removal and provider/model selection in the real planning
service. All provider calls use mocks and synthetic test keys.

## Automatic challenge planning credit

Assignment creation takes the child's shared award/challenge row lock before
saving its timestamp. A concurrent first challenge read therefore cannot
initialize enrollment after that accepted plan and exclude its first credit.
The PostgreSQL interleaving regression is in
`apps/quests/tests/test_goal_concurrency.py`.

Approval uses the same child-first lock order before locking the submission and
stamping `decided_at`. The initial catalog read cannot cut over after accepted
homework and lose its completion credit. PostgreSQL chore/homework approval
interleavings are covered in `apps/chores/tests/test_approval_concurrency.py`.

Built-in catalog challenges count the first planned assignment per local day,
using the existing `HomeworkDailyCounter` gate. The source service freezes the
private challenge-fact eligibility at save time; deleting an assignment or
retrying its fact cannot release another catalog-credit slot. Explicit parent
planning goals may count every valid matching saved assignment. Approved
homework completion remains a separate trigger with its existing approval and
timeliness rules. Source quota days use the active Django timezone (default
America/Phoenix); family-local challenge windows do not reset those counters.

## Key entry points
- `services.py` — `HomeworkService`, `EFFORT_XP_FACTOR`, `get_timeliness`, `can_self_plan`.
- `models.py` — `HomeworkAssignment`, `HomeworkSubmission`, `HomeworkProof`, `HomeworkDailyCounter`.
- `tests/test_services.py` — anti-farm gate, effort scaling, AI planning gate.
