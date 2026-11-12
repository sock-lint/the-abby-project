# apps/chronicle/

Age-aware lifelong journal: birthdays, chapter transitions (school years that don't expire at grade 12), parent-authored memories, child-authored journal entries, and "first" events. Tables drive the `/chronicle?tab=yearbook` Yearbook surface.

## Models
- `ChronicleEntry` (kinds: `birthday` / `chapter_start` / `chapter_end` / `first_ever` / `milestone` / `recap` / `manual` / `journal` / `daily_note` / `creation` / `grade`).
  - `is_private` is an access rule for journals and grades: authors see their own entries; parents see only explicitly shared journals and grades. Other children never see a sibling's entries.
  - Partial unique index on `(user, event_slug) where kind=first_ever` for emit-once semantics.
  - Partial unique index on `(user, occurred_on) where kind='journal'` — one journal entry per user per local day.
  - Optional `client_entry_id` UUID is unique per author and makes interrupted saves safe to retry.
  - Nullable one-to-one `daily_note_source` binds a historical `daily_note` to its retained wellbeing row. These notes are always author-only, read-only, and appear beside ordinary journals in Memories; a same-day shared journal never absorbs their private text.
  - `chapter_year` is the August-starting year (2025 = Aug 2025–Jul 2026) — named `chapter` not `school` because the same field keeps working post-HS.
- `ChronicleComment` stores author, body, creation time, and optional per-author unique `client_comment_id` UUID on a shared journal or grade entry.
- `GradeDailyCounter` inherits `DailyCounterModel`, keyed by author and actual save day; it counts captures and survives corrections or removal of individual grade entries.

## Services
- `ChronicleService` — idempotent writers (`record_first`, `record_birthday`, `record_chapter_start/end`, `freeze_recap`, `record_creation`) plus retry-safe `write_journal` / owner-only `update_journal` for journal entries.
- `GradeService` in `grade_services.py` owns retry-safe result capture and owner-only corrections. `award_verified_xp` is shared with journals and measures committed skill progress, rather than configured rewards.

Celery tasks: `chronicle-birthday-check` (00:20, grants the fixed `BIRTHDAY_COIN_GIFT` (200) once for a new birthday), `chronicle-chapter-transition` (00:25, Aug 1 opens / Jun 1 closes + freezes RECAP; grade-12 Jun 1 also emits a standalone `graduated_high_school` MILESTONE entry).

## Endpoints

Parent My space (`X-Abby-Space: personal`) reads only the parent's own history,
chapter summaries and shared-entry comments; a targeted child summary is
rejected. Journal creation/today/corrections remain bound to the authenticated
author and preserve existing private defaults, rewards and UUID retries for
parents too. Family can still read explicitly shared household journals/grades;
co-parents cannot read private entries or alter another author's sharing.
Academic grade capture and the Meadow projection remain child-only.

Manual memories owned by a parent are owner-only in both My space and Family,
including REST list/detail/edit/delete and shared MCP readers and entry actions.
Their `is_private` value does not enable co-parent access; manual memories have
no sharing action. Family parents retain normal read/edit/delete access to
child-owned manual memories. Journal and grade sharing rules remain separate.

- `ChronicleViewSet` at `/api/chronicle/` — `summary`, `pending-celebration`, `mark-viewed`, parent-only manual CRUD, self-scoped journal POST (exact UUID retries return the saved entry; unrelated second-of-day attempts return 409) + same-day text PATCH + historical sharing PATCH + today lookup GET.
- Journal action is `IsAuthenticated`, binds writes to `request.user` so `user_id` in body is ignored.
- `GET /api/chronicle/journal/today/` — returns today's local-day journal entry for `request.user`, or `204` when none yet.
- `GET /api/chronicle/meadow/` — child-only, self-scoped, read-only keepsake projection for the companion prototype; ignores account/chapter filters.
- `GET` / `POST /api/chronicle/grades/` — paginated result history and child-authored grade capture.
- `PATCH /api/chronicle/{id}/grade/` — owner-only corrections and sharing changes on any date, with no extra reward.
- `GET` / `POST /api/chronicle/entries/{id}/comments/` — conversations on shared journals and grades, available only to the author and parents in that family.

Event hooks call into `ChronicleService` from `GameLoopService`, `ExchangeService.approve`, `PetService.hatch_incubation`/`feed_pet`.

New `record_first` entries and graduation milestones evaluate the `chronicle`
and `badges` scopes under the account lock in the entry transaction. Turning
Point and Life Chronicler count both `first_ever` and `milestone`; other history
kinds, including private journals and grades, do not count. A payout failure
rolls back the new recognition entry for retry. Existing-entry replay does not
evaluate or backfill awards, and firsts without an explicit date use the active
Django local day. Regression coverage is in `tests/test_milestone_badges.py`.
If graduation recognition fails, the chapter task still completes later
children's transitions, then requests at most three Celery retries five minutes
apart. Its internal `transition_date` retains the original June 1 across midnight;
saved markers prevent successful children from being paid again. Other chapter
failures retain their existing error behavior.

Both birthday writers take the same account lock before saving a new annual
entry, then evaluate `chronicle` and `badges` in that transaction. Each new badge
receives its ordinary payout and one accomplishment drop; birthdays create no
extra activity or direct drop. Only the scheduled task grants the existing
birthday coin gift. Replaying an existing entry backfills neither badges nor
gifts. Award failure rolls back the entry and all rewards; the task finishes
later children before requesting up to three retries five minutes apart, retaining
the original `birthday_date` across midnight. Optional birthday notification
inserts use a savepoint so their failure cannot invalidate the gift or badge
awards. See `tests/test_birthday_badges.py` and the PostgreSQL competing-writer
checks in `tests/test_birthday_concurrency.py`.

## Gotchas

- **Age-aware Chronicle**: `User.date_of_birth` + `User.grade_entry_year` (both nullable) feed computed properties `age_years`, `current_grade`, `school_year_label` (Freshman/Sophomore/Junior/Senior through grade 12; `"Age {n} · YYYY-YY"` after). `ChronicleEntry.chapter_year` is the August-starting year — named `chapter` not `school` because the same field keeps working post-HS. `ChronicleService.record_first` uses a partial unique index on `(user, event_slug) where kind=first_ever` for emit-once semantics, returning `None` on duplicate. `CharacterProfile.unlocks` JSONField is scaffolded for future feature-pack gates (Driver's Ed, First Job, College Prep) — no UI, no readers in the current release. Future birthday gifts use `BIRTHDAY_COIN_GIFT` (default 200), independent of age. Saved birthday entries and their earlier gifts are never recalculated. Full-screen `BirthdayCelebrationModal` fires in a child's space or a parent's My space when `/api/chronicle/pending-celebration/` returns an unviewed BIRTHDAY entry; Family leaves it pending. Dismiss hits `POST /api/chronicle/{id}/mark-viewed/`. Graduation is a milestone inside the timeline, not a terminal state — the app keeps rolling chapters forever, labels flip to age-based after grade 12.

- **Journal sharing and read access**: new journal and grade entries default to `is_private=True`. This now gates read access, rather than merely rendering a lock chip. `apps/chronicle/access.py::visible_chronicle_entries` applies author/family scoping and hides private journals and grades from parents across REST list, summary, detail, mark-viewed, and MCP Chronicle readers. Historical `daily_note` entries are author-only regardless of their sharing flag. Authors retain their private journals. Other children cannot read even shared sibling entries. A parent cannot change the child's sharing setting. Existing private journal rows remain private; no data migration makes them public.

- **Journal creation and interrupted saves**:
  - Fixed XP destinations resolve the original Language Arts category and its Creative Writing/Vocabulary skill identities through `apps.achievements.source_identity`, including retained MCP rename/reparent identities. Retirement keeps those installed routes; unlock checks still apply. A genuinely missing or ambiguous destination retains the existing surviving-tag split, or an unavailable receipt when none resolve. Taxonomy edits never backfill or rewrite a saved receipt.
  - `POST /api/chronicle/journal/` accepts optional `title`, `summary`, `is_private` (default true), and `client_entry_id` UUID. At least a nonblank title or body is required; neither length nor sentiment determines rewards. `user_id` is ignored because the author is always `request.user`.
  - One journal entry per author per local day remains enforced by the partial unique constraint. A new submission returns 201. Repeating the same UUID and original normalized submission returns 200 with the same entry, without awarding again—even on another day or after later edits. Reusing that UUID with different original content/sharing returns 409. An unrelated second entry on the same day returns 409 with `{detail, existing}` so the form can preserve its draft and offer an edit.
  - `ChronicleEntrySerializer` exposes the `client_entry_id` model field and `reward_receipt`; the receipt is stored in entry metadata. `reward_receipt` contains `receipt_id`, `status`, `xp_awarded`, `skills`, and (when available) `awarded_at`. Positive XP is measured from persisted `SkillProgress` deltas in the award transaction, including boosts and earned badge bonuses; configured amounts or game-loop response dictionaries are not proof of a reward. Status `awarded` confirms XP; `not_eligible` confirms no XP changed; `unavailable` preserves the memory if reward processing fails or the skill catalog is unavailable. Legacy journals return an unavailable/zero receipt instead of inventing past awards.
  - The first journal save routes the configured 15 XP pool through Creative Writing and Vocabulary (weights 2:1), receives the existing flat 2-Coin daily writing acknowledgment if it has not already been paid by an older Today client, then invokes the journal RPG hook for streak/drop/quest behavior. Separate savepoints roll failed downstream work back while keeping the journal. Replay, text edits, sharing changes, and comments grant no additional journal reward. The receipt additionally exposes measured `coins_awarded` and `coin_status` (`awarded`, `already_received`, or `unavailable`); it does not claim verified drops. Existing receipts without coin proof serialize with zero/unavailable coin fields.
  - `GET /api/chronicle/journal/today/` and chapter/birthday lookups use `timezone.localdate()`.

- **Unified daily writing history**: Today opens the ordinary Journal capture flow and shows today's same saved journal. Migration `0008_daily_notes_in_journal` copies nonblank historical wellbeing lines, their original dates and creation times into separate private `daily_note` Chronicle entries, retaining source rows and payout timestamps. The migration is idempotent and issues no XP, coins, game hooks, badges, or Meadow keepsakes. Older clients may still write the wellbeing endpoint; it updates only its bound private history row and retains its original validation rules. Historical notes are not counted as rewarded journal entries or journal streak days. Reversing `0008` deletes every `daily_note` projection before the earlier schema returns, because earlier access rules would show them to parents; the retained wellbeing rows rebuild them on a later forward migration. Treat the release as forward-only: before redeploying an earlier commit, first run `migrate chronicle 0007`, then deploy the earlier commit promptly (until it serves, this code's journal and old-client note endpoints fail without the dropped column). A note whose wellbeing source row was deleted cannot be rebuilt after reversal.

- **Journal updates**: `PATCH /api/chronicle/{id}/journal/` accepts partial `title`, `summary`, and `is_private` fields. Only the owner may update a journal. Text edits stay restricted to the same local day and cannot erase all meaningful content. A sharing-only PATCH works on historical entries without rewriting their text or granting rewards. There is no journal DELETE endpoint. The frontend keeps earlier entries' text read-only while providing a separate sharing control and conversations for shared entries.

- **Meadow keepsakes**: `GET /api/chronicle/meadow/` returns `{schema_version: 1, keepsake_count, journal_xp_awarded, keepsakes}` for the authenticated child only; parents receive 403. Each of the newest 30 keepsakes has `{receipt_id, type: "memory_bloom", title: "Memory bloom", earned_at}`. Counts and XP cover all eligible history. Eligibility requires a durable journal receipt with its matching `journal:{entry_id}` identity, `status="awarded"`, and positive integer verified XP. Creation timestamp is the stable `earned_at`; collection order is creation time then entry ID, newest first. Journal titles/body, sharing flags, skill metadata, and family replies are never returned. Loading, edits, sharing, comments, and retrying a saved journal issue no extra keepsake or XP. The existing one-journal-per-day constraint controls the earning rate. Legacy rows without confirmed receipts, unavailable/zero awards, and non-journal captures do not invent keepsakes. This first slice is a projection, not a separate collectible ledger: administrative entry/account deletion removes its projected items, and only the latest 30 item details are available (the all-time count remains complete). Clients compare receipt IDs within the validated account and establish an initial history baseline before celebrating later additions.

- **Academic result capture**: `POST /api/chronicle/grades/` is child-only and ignores `user_id`; the authenticated child is the author. Required fields are `subject` and `assessment` (trimmed nonblank strings, maximum 80 each), `grade_format`, active grade value fields, and a stable `client_entry_id` UUID. Optional `reflection` is at most 4000 characters and is stored in `entry.summary`; optional `occurred_on` defaults to the local day and cannot be future-dated; `is_private` defaults to true. `entry.title` is derived from subject + ` · ` + assessment and truncated to 160; full subject/assessment remain in `metadata.grade`.
  - `percentage` requires score 0–100; `points` requires score ≥0 and possible >0, with extra credit allowed; `letter` accepts A+/A/A−/B+/B/B−/C+/C/C−/D+/D/D−/F/P/NP/I (ASCII hyphens in API values). Nonempty fields from another format are rejected; inactive null/blank fields are discarded. Decimal input supports 18 total digits, at most 6 decimal places, and is stored as a normalized decimal string without unnecessary zeros. Metadata includes only fields active for the selected format.
  - GET uses `{count, next, previous, results}` pagination and applies family/owner sharing access. Optional `user_id` must be a positive 64-bit integer; optional `chapter_year` must be 1–9999. Malformed filters return 400. Children remain self-scoped regardless of supplied user ID.
  - Creation returns 201; a replay of the same normalized original submission returns 200 with the current saved entry and its original receipt. Fingerprints include original result, reflection, date, and sharing. An omitted/default date is remembered for retries across midnight and later corrections. Reusing an author's UUID across entry kinds or for a different submission returns 409 without another entry's data. UUID uniqueness applies to all Chronicle kinds.
  - Partial owner-only `PATCH /api/chronicle/{id}/grade/` supports result/reflection/date corrections and sharing changes on historical entries. Unspecified fields remain unchanged. Switching format discards the previous format's values and requires a complete valid new result. The original UUID cannot be changed; original fingerprint and reward receipt remain unchanged. General parent update/delete remains limited to manual Chronicle entries.

- **Grade recognition**: the first grade capture per author per actual local save day uses a fixed 10 XP pool for `Life Skills::Time Management`, independent of grade value, result date, reflection length, or sharing. The shared achievements source resolver follows that exact original category/skill identity through MCP rename, reparenting and retirement; ambiguous identities fail closed and ordinary unlock checks still apply. Saved receipts are never rewritten or backfilled by taxonomy edits. Later same-day captures remain unlimited and return `daily_limit` receipts with 0 XP. Corrections, sharing changes, comments, and UUID replays do not increment the counter or issue another reward. `GradeDailyCounter` is incremented outside the award savepoint but inside the entry transaction, so a failed award preserves the grade and consumes that day's first attempt. Missing skill catalog or an award failure returns `unavailable`; locked skill progress returns `not_eligible`; positive committed deltas return `awarded`, including boosts. Receipts contain `reward_day` as the actual eligibility date. There is no new RPG trigger, direct coin reward, drop roll, or grade-value-based reward; the existing AwardService badge evaluation still runs for relevant skill XP.

- **Quarter and semester report cards**: the same grade POST/PATCH endpoints accept `report_card` instead of the individual result fields. It contains `period_type` (`quarter` or `semester`), `period_number` (1–4 or 1–2 respectively), `school_year` (starting year, 1–9998), and `subjects` (1–30 complete results with unique subject names). Each subject has `subject`, `grade_format`, and the active grade values described above; no assessment is needed. These are school-issued final grades entered as recorded, with no calculated average or GPA. One card becomes one `kind="grade"` Chronicle entry with `metadata.report_card`, one reflection, and one receipt; it shares the existing daily recognition cap with individual grades. Existing individual result payloads and metadata stay compatible. Child authorship, sharing, family replies, UUID retries, and owner-only historical corrections follow the same rules. A correction can partially update period/year fields, but `subjects` replaces the entire list and requires complete valid results. A correction cannot change an individual grade into a report card or vice versa.

  React exposes **Log a report card** beside **Log a grade**, a dedicated form with per-account recoverable drafts and immutable save retries, and a subject/result table in Grades and Yearbook detail. The school-year label spans the starting year and the following year. Report cards use their own correction form from both surfaces.

- **Concurrency boundary**: journal/grade capture serialize on the author before counter/progress rows; grade corrections lock the author before the entry. Comment sends serialize on the author (`FOR NO KEY UPDATE`) before locking the shared entry. The weaker author lock permits notification foreign-key checks during simultaneous parent/child replies. Shared XP writers also follow author-before-progress lock order. The verified receipt records the award committed at that moment. SQLite tests verify constraints and API behavior, but cannot exercise PostgreSQL row-lock interleavings.

- **Family replies**: `GET /api/chronicle/entries/{id}/comments/` returns an array in chronological order with `{id, entry, author, author_name, author_role, body, created_at, client_comment_id}`. POST accepts `{body, client_comment_id?}`; body is trimmed, nonblank, and at most 2000 characters. The entry must be a shared journal or grade and the caller its author or a parent in that family. A new reply returns 201; exact same-author UUID retries return the original reply with 200. Reusing a UUID for different text or another entry returns 400. A reply issues no rewards. Parent replies notify the child; child replies notify only that family's active parents, through the dedicated `journal_reply` type. Replays do not duplicate notifications. Notification text contains no journal title/body, grade values/reflection, or reply body, so later unsharing does not leave sensitive text in a bell/push payload. Journal links open `/chronicle?tab=journal`; grade links open `/chronicle?tab=grades`. Unsharing hides the conversation from parents without deleting it.

- **Frontend journal capture**: [`JournalEntryFormModal`](/frontend/src/pages/yearbook/JournalEntryFormModal.jsx) retains dictation through [`useSpeechDictation`](/frontend/src/hooks/useSpeechDictation.js), title autofill, one-daily-entry conflict handling, and the local-day edit lock. Draft recovery, stable submission IDs, explicit sharing controls, and verified receipt reactions belong to the phone-first capture loop. Journal rows retain the `🪶` timeline icon; `manual` entries use `🖋️`.

- **Journal badges**: `journal_entries_written` thresholds 1/10/50/100/365 and `journal_streak_days` thresholds 3/7/30/100 are checked in [`apps/achievements/criteria.py`](/apps/achievements/criteria.py), with content in [`content/rpg/initial/badges.yaml`](/content/rpg/initial/badges.yaml). The streak checker counts distinct `occurred_on` dates. Badges and progression are independent of whether an entry is shared.

## Tunable settings
- `BIRTHDAY_COIN_GIFT` (default `200`) — fixed Coins granted for a newly recorded birthday. `BIRTHDAY_COINS_PER_YEAR` remains a legacy compatibility setting and no longer controls future gifts.

## Key entry points
- `services.py` — `ChronicleService`, `JournalAlreadyExistsError`, `_autofill_journal_title`, `award_verified_xp`.
- `grade_services.py` / `grade_serializers.py` — `GradeService`, `GradeEntryWriteSerializer`, `GradeListQuerySerializer`.
- `access.py` — shared REST/MCP read policy.
- `tasks.py` — `chronicle-birthday-check`, `chronicle-chapter-transition`.
- Frontend: [`pages/yearbook/`](/frontend/src/pages/yearbook/) (timeline + ChapterCard + TimelineEntry + EntryDetailSheet + JournalEntryFormModal + ManualEntryFormModal).
