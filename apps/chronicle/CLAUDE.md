# apps/chronicle/

Age-aware lifelong journal: birthdays, chapter transitions (school years that don't expire at grade 12), parent-authored memories, child-authored journal entries, and "first" events. Tables drive the `/atlas?tab=yearbook` Yearbook surface.

## Models
- `ChronicleEntry` (kinds: `birthday` / `chapter_start` / `chapter_end` / `first_ever` / `milestone` / `recap` / `manual` / `journal` / `creation`).
  - `is_private` flag (true for journal entries — lock chip renders on parent timeline view, never on child's own).
  - Partial unique index on `(user, event_slug) where kind=first_ever` for emit-once semantics.
  - Partial unique index on `(user, occurred_on) where kind='journal'` — one journal entry per user per local day.
  - `chapter_year` is the August-starting year (2025 = Aug 2025–Jul 2026) — named `chapter` not `school` because the same field keeps working post-HS.

## Services
- `ChronicleService` — idempotent writers (`record_first`, `record_birthday`, `record_chapter_start/end`, `freeze_recap`, `record_creation`) plus non-idempotent `write_journal` / `update_journal` for child-authored journal entries.

Celery tasks: `chronicle-birthday-check` (00:20, grants `BIRTHDAY_COINS_PER_YEAR × age_years` coins), `chronicle-chapter-transition` (00:25, Aug 1 opens / Jun 1 closes + freezes RECAP; grade-12 Jun 1 also emits a standalone `graduated_high_school` MILESTONE entry).

## Endpoints
- `ChronicleViewSet` at `/api/chronicle/` — `summary`, `pending-celebration`, `mark-viewed`, parent-only manual CRUD, child-self-scoped journal POST (409 with existing row on second-of-day attempt) + same-day PATCH + today lookup GET.
- Journal action is `IsAuthenticated`, binds writes to `request.user` so `user_id` in body is ignored.
- `GET /api/chronicle/journal/today/` — returns today's journal entry for `request.user`, or `204` when none yet.

Event hooks call into `ChronicleService` from `GameLoopService`, `ExchangeService.approve`, `PetService.hatch_pet`/`feed_pet`.

## Gotchas

- **Age-aware Chronicle**: `User.date_of_birth` + `User.grade_entry_year` (both nullable) feed computed properties `age_years`, `current_grade`, `school_year_label` (Freshman/Sophomore/Junior/Senior through grade 12; `"Age {n} · YYYY-YY"` after). `ChronicleEntry.chapter_year` is the August-starting year — named `chapter` not `school` because the same field keeps working post-HS. `ChronicleService.record_first` uses a partial unique index on `(user, event_slug) where kind=first_ever` for emit-once semantics, returning `None` on duplicate. `CharacterProfile.unlocks` JSONField is scaffolded for future feature-pack gates (Driver's Ed, First Job, College Prep) — no UI, no readers in the current release. The birthday coin gift is tunable via `BIRTHDAY_COINS_PER_YEAR` (default 100 × age_years). Full-screen `BirthdayCelebrationModal` fires at App boot when `/api/chronicle/pending-celebration/` returns an unviewed BIRTHDAY entry; dismiss hits `POST /api/chronicle/{id}/mark-viewed/`. Graduation is a milestone inside the timeline, not a terminal state — the app keeps rolling chapters forever, labels flip to age-based after grade 12.

- **Journal entries** (`apps/chronicle/` + `frontend/src/pages/yearbook/`): child-authored `ChronicleEntry.Kind.JOURNAL` rows that appear inline on the Yearbook timeline. `is_private=True` on every journal entry; the flag drives a `<RuneBadge icon={<Lock>}>Private</RuneBadge>` chip on the **parent's** view of the timeline (and on the detail sheet header) — **never** on the child's own view, so journaling doesn't feel surveilled. **One entry per user per local day** — a partial `UniqueConstraint` on `(user, occurred_on) where kind='journal'` enforces this at the DB layer; the service pre-checks and raises `JournalAlreadyExistsError(entry)` carrying the existing row so the view can 409 with context. Route surface:
  - `POST /api/chronicle/journal/` (`IsAuthenticated`, self-scoped — `user_id` in body is ignored; the endpoint always writes to `request.user`). Returns `201` on create, `409 Conflict` with `{detail, existing: <entry>}` when today's entry already exists. Frontend [`JournalEntryFormModal.jsx`](/frontend/src/pages/yearbook/JournalEntryFormModal.jsx) catches 409 and flips to edit mode with the returned entry, merging any in-flight text after the existing body so the child's words don't vanish.
  - `PATCH /api/chronicle/{id}/journal/` — owner-only, same-local-day only. `ChronicleService.update_journal` raises `PermissionDenied` after midnight crosses, surfacing as 403 → a friendly toast in the modal ("that entry is locked now — part of your chronicle"). No DELETE endpoint by design — prevents delete-in-anger wiping a memory.
  - **Lock UI** (frontend, 2026-05): [`JournalEntryFormModal`](/frontend/src/pages/yearbook/JournalEntryFormModal.jsx) compares `entry.occurred_on` to today's local date (`new Date().toLocaleDateString('en-CA')`). Today's entry stays editable; **prior-day entries open in read-only mode** with a script chip ("part of your chronicle") and only a Close button — no textarea, no Save. The 403 path stays as the fallback for the day-rolls-over-while-modal-open race (an entry editable when the modal opened becomes locked at midnight). Pinned in [`JournalEntryFormModal.test.jsx`](/frontend/src/pages/yearbook/JournalEntryFormModal.test.jsx).
  - `GET /api/chronicle/journal/today/` — returns today's journal entry for `request.user`, or `204` when none yet. Used by [`QuickActionsSheet`](/frontend/src/components/layout/QuickActionsSheet.jsx) to pre-check so the row label can flip between *"Write in journal"* and *"Edit today's journal"* and open the modal in the matching mode without a round-trip to the 409 path for the common case.
  - **Title autofill**: `_autofill_journal_title(title, body, day)` uses the user's title if present, otherwise the first 60 chars of body + `"…"`, otherwise `"{Month D} entry"`. Platform-safe date format (no `%-d` / `%#d`).
  - **Rewards fire on every create** (one-per-day makes this trivial): `AwardService.grant` distributes 15 XP split 2:1 across `Creative Writing` + `Vocabulary` via a `_JournalTag` faux shim matching the `SkillService.distribute_tagged_xp` duck-type; `GameLoopService.on_task_completed(user, TriggerType.JOURNAL_ENTRY, {...})` fires so streak, drops, and quest progress all count. Both awards are wrapped in `try/except` so a downstream failure can't block the entry write. The prior "first-of-day gate" in `write_journal` is gone — the constraint makes it redundant.
  - **Badges**: new `journal_entries_written` ladder (1/10/50/100/365 → First Page / Scribe / Chronicler / Historian / A Year in Ink) and `journal_streak_days` ladder (3/7/30/100 → Three-Night Quill / Weekly Diarist / Lunar Scribe / Constellation). Criteria checkers in [`apps/achievements/criteria.py`](/apps/achievements/criteria.py); YAML entries in [`content/rpg/initial/badges.yaml`](/content/rpg/initial/badges.yaml). The `journal_streak_days` checker reduces to `set(occurred_on)` before counting consecutive runs — defensive against legacy rows; production rows can't dupe a day.
  - **Dictation**: [`useSpeechDictation`](/frontend/src/hooks/useSpeechDictation.js) wraps `window.SpeechRecognition || window.webkitSpeechRecognition` with `continuous + interimResults`. Final chunks arrive with a trailing space so appends concat naturally; interim state is exposed separately for a "Listening… " preview chip. `supported === false` on Firefox → mic button renders disabled with an explanatory `aria-label`. No server-side audio path — the transcript is typed into the textarea client-side before POST.
  - **Quick Actions row**: child-only "Write in journal" / "Edit today's journal" row at the top of the child's Quick Actions menu (royal tone, `PenTool` icon). Pre-fetches `GET /chronicle/journal/today/` so it knows whether to open the modal in create vs edit mode. Parent view has no journal entry point — journals are authored, not assigned.
  - **Timeline icon**: `🪶` (quill) in `KIND_ICON`, distinct from `manual`'s `🖋️` (parent-authored memory) so the two never collide visually.

## Tunable settings
- `BIRTHDAY_COINS_PER_YEAR` (default `100`) — coins granted on birthday, multiplied by `age_years`. Tunable without code change.

## Key entry points
- `services.py` — `ChronicleService`, `JournalAlreadyExistsError`, `_autofill_journal_title`.
- `tasks.py` — `chronicle-birthday-check`, `chronicle-chapter-transition`.
- Frontend: [`pages/yearbook/`](/frontend/src/pages/yearbook/) (timeline + ChapterCard + TimelineEntry + EntryDetailSheet + JournalEntryFormModal + ManualEntryFormModal).
