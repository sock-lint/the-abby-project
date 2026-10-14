# apps/wellbeing/

Soft daily writing surface: today's affirmation and one personal note on Today (child-only), with optional ideas and up to two extra thoughts. One short line is enough; writing about a hard day is welcome. No notifications, badge ladder, quest progress, streak credit or skipped-day penalties.

## Models
- `DailyWellbeingEntry` — one row per `(user, local-date)` (unique constraint), holds the rolled `affirmation_slug`, the `gratitude_lines` JSON list, and an idempotent `coin_paid_at` timestamp.

## Services
- `WellbeingService` — deterministic affirmation roll + `submit_gratitude` (validates length + idempotent first-of-day coin trickle).

## Endpoints
- `GET /api/wellbeing/today/` — idempotent (first call creates the row, returns the affirmation + saved lines + paid flag).
- `POST /api/wellbeing/today/gratitude/ {lines: [...]}` — both `IsAuthenticated`, **always self-scoped** (`user_id` in the body is ignored).

## Authoring workflow
- Edit `content/wellbeing/affirmations.yaml`.
- Run `python manage.py loadwellbeingcontent` — validates the YAML (slug uniqueness, non-empty text, list shape) and reports the loaded count. Run automatically by `seed_data` flows for the same fail-loud guarantee as `loadrpgcontent`.

## Gotchas

- **Wellbeing card** (`apps/wellbeing/` + [`frontend/src/pages/dashboard/WellbeingCard.jsx`](/frontend/src/pages/dashboard/WellbeingCard.jsx)): a gentle daily invitation to write about anything. It starts with one note, offers optional idea prompts that change only the placeholder, and reveals extra fields on request or when older saved lines exist. Renders after tasks and recent items, before Rewards & earnings, child-only (parents skip it). Profile stays focused on identity and personalization; Challenges lives under Tasks. The small first-of-day coin trickle (2c, configurable via `GRATITUDE_FIRST_OF_DAY_COINS`) recognizes a saved note; later edits do not repay and skipping a day has no penalty. Historical `gratitude_lines` fields and endpoints remain compatible.
  - **`DailyWellbeingEntry`** model — one row per `(user, local-date)` (unique constraint), holding the rolled `affirmation_slug`, the `gratitude_lines` JSON list, and an idempotent `coin_paid_at` timestamp. The slug-not-text storage is deliberate: editing the YAML re-resolves past entries to the new copy.
  - **Affirmation pool** authored as YAML at [`content/wellbeing/affirmations.yaml`](/content/wellbeing/affirmations.yaml). Roll is **deterministic per `(user_id, day.toordinal())`** via SHA-1 modulo pool size — refreshes on the same day always return the same affirmation so the kid can't slot-machine the prompt. Adding new entries shifts the mapping for **future** days only; historical rows snapshot the slug.
  - **`WellbeingService.submit_gratitude`** validates `1 <= len(cleaned) <= MAX_LINES (=3)` and `len(line) <= MAX_LINE_CHARS (=200)`, filters blanks before counting, and pays the trickle exactly once per local day via the `coin_paid_at` idempotency key. Subsequent same-day edits persist the new lines without re-paying. Coin payout uses `CoinLedger.Reason.ADJUSTMENT` (mixed-sign, deliberately NOT on the Lucky Coin whitelist — kindness shouldn't double-stack).
  - **Endpoints**: `GET /api/wellbeing/today/` (idempotent — first call creates the row, returns the affirmation + saved lines + paid flag), `POST /api/wellbeing/today/gratitude/ {lines: [...]}`. Both `IsAuthenticated`, **always self-scoped** — `user_id` in the body is ignored, the view binds writes to `request.user`. Pinned by `test_user_id_in_post_body_is_ignored_self_scoped` in [`tests/test_views.py`](tests/test_views.py).
  - **Authoring workflow**: edit `content/wellbeing/affirmations.yaml`, then `python manage.py loadwellbeingcontent` validates the YAML (slug uniqueness, non-empty text, list shape) and reports the loaded count. The command is run automatically by `seed_data` flows for the same fail-loud guarantee as `loadrpgcontent`.
  - **Frontend**: `WellbeingCard` uses a labeled `<TextAreaField>` and optional `<TextField>` extras, hydrated from `data.gratitude_lines`. Empty/whitespace-only notes cannot submit. The successful POST response confirms "Saved for today" without requiring another GET; edits show "Unsaved changes" and failed saves retain the draft. A saved note can retry an unconfirmed coin award without editing. First-payment success flashes the labeled `role="status"` "Daily note reward" chip for 3.2s. Tests in [`WellbeingCard.test.jsx`](/frontend/src/pages/dashboard/WellbeingCard.test.jsx) cover one-line saves, optional prompts/extras, preserved older notes, save failures and daily reward retry; ChildDashboard integration checks revisit/edit behavior. Backend tests retain validation, once-per-day rewards and self-scoped privacy coverage.

## Key entry points
- `services.py` — `WellbeingService`, `MAX_LINES`, `MAX_LINE_CHARS`, `GRATITUDE_FIRST_OF_DAY_COINS`.
- `content/wellbeing/affirmations.yaml` — affirmation pool.
- `management/commands/loadwellbeingcontent.py` — YAML loader.
