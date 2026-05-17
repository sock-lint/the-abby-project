# apps/wellbeing/

Finch-inspired soft surface: daily affirmation + 3 gratitude lines on the Sigil Frontispiece (child-only). The whole point of this surface is that it stays **soft** — no notifications, no badge ladder, no quest progress, no streak credit.

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

- **Wellbeing card** (`apps/wellbeing/` + [`frontend/src/pages/character/WellbeingCard.jsx`](/frontend/src/pages/character/WellbeingCard.jsx), added 2026-05-10): Finch-inspired soft surface on the Sigil Frontispiece — daily affirmation + 3 gratitude lines the kid types in. Renders between `SigilFrontispiece` and the cosmetic chapters on `/sigil`, child-only (parents skip it). The whole point of this surface is that it stays SOFT — **no notifications, no badge ladder, no quest progress, no streak credit**. The act of writing is its own reward; the small first-of-day coin trickle (2c, configurable via `GRATITUDE_FIRST_OF_DAY_COINS`) is recognition rather than motivation.
  - **`DailyWellbeingEntry`** model — one row per `(user, local-date)` (unique constraint), holding the rolled `affirmation_slug`, the `gratitude_lines` JSON list, and an idempotent `coin_paid_at` timestamp. The slug-not-text storage is deliberate: editing the YAML re-resolves past entries to the new copy.
  - **Affirmation pool** authored as YAML at [`content/wellbeing/affirmations.yaml`](/content/wellbeing/affirmations.yaml). Roll is **deterministic per `(user_id, day.toordinal())`** via SHA-1 modulo pool size — refreshes on the same day always return the same affirmation so the kid can't slot-machine the prompt. Adding new entries shifts the mapping for **future** days only; historical rows snapshot the slug.
  - **`WellbeingService.submit_gratitude`** validates `1 <= len(cleaned) <= MAX_LINES (=3)` and `len(line) <= MAX_LINE_CHARS (=200)`, filters blanks before counting, and pays the trickle exactly once per local day via the `coin_paid_at` idempotency key. Subsequent same-day edits persist the new lines without re-paying. Coin payout uses `CoinLedger.Reason.ADJUSTMENT` (mixed-sign, deliberately NOT on the Lucky Coin whitelist — kindness shouldn't double-stack).
  - **Endpoints**: `GET /api/wellbeing/today/` (idempotent — first call creates the row, returns the affirmation + saved lines + paid flag), `POST /api/wellbeing/today/gratitude/ {lines: [...]}`. Both `IsAuthenticated`, **always self-scoped** — `user_id` in the body is ignored, the view binds writes to `request.user`. Pinned by `test_user_id_in_post_body_is_ignored_self_scoped` in [`tests/test_views.py`](tests/test_views.py).
  - **Authoring workflow**: edit `content/wellbeing/affirmations.yaml`, then `python manage.py loadwellbeingcontent` validates the YAML (slug uniqueness, non-empty text, list shape) and reports the loaded count. The command is run automatically by `seed_data` flows for the same fail-loud guarantee as `loadrpgcontent`.
  - **Frontend**: `WellbeingCard` is a controlled-input component (`useState` lines + `useEffect`-rehydrate from `data.gratitude_lines`). Three `<TextField>` slots use `aria-label` rather than visible labels because the title + script copy already establish context. First-save success flashes a `role="status"` chip with `+2 coins` for 3.2s — the chip is queryable by role separately from the always-visible "first save today earns +2" hint copy. Tests in [`WellbeingCard.test.jsx`](/frontend/src/pages/character/WellbeingCard.test.jsx) cover affirmation render, POST round-trip, error toast on empty submit, and the "Update" label flip after first pay. Backend tests in [`tests/test_services.py`](tests/test_services.py) (8 cases) and [`tests/test_views.py`](tests/test_views.py) (7 cases).

## Key entry points
- `services.py` — `WellbeingService`, `MAX_LINES`, `MAX_LINE_CHARS`, `GRATITUDE_FIRST_OF_DAY_COINS`.
- `content/wellbeing/affirmations.yaml` — affirmation pool.
- `management/commands/loadwellbeingcontent.py` — YAML loader.
