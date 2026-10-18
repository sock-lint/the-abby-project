# apps/wellbeing/

Affirmations and compatibility for the earlier daily-note API. Today now opens the ordinary Chronicle journal, so short and long reflections have one history in Memories → Journal. A few words about any kind of day count; skipping a day has no penalty.

## Models
- `DailyWellbeingEntry` — one row per `(user, local-date)`, holding the rolled `affirmation_slug`, the legacy `gratitude_lines` list, and `coin_paid_at`. The payout sentinel is shared by ordinary journals and legacy note saves.
- `ChronicleEntry.daily_note_source` — one-to-one source binding for the legacy note's private history row. Source rows are retained; private text never gets merged into a shared same-day journal.

## Services
- `WellbeingService.get_or_create_today` rolls a deterministic affirmation and creates today's row idempotently.
- `award_daily_writing_coins` recognizes a first save with the existing flat 2 Coins, shared across both writing endpoints. It commits ledger and sentinel in one savepoint and reports measured `coins_awarded` plus `coin_status` (`awarded`, `already_received`, `unavailable`). Failed payouts preserve writing and leave the allowance unpaid. Journal replays and edits never attempt a new award.
- `submit_gratitude` remains compatible for older clients: trim/filter blank lines, require 1–3 strings of at most 200 characters, save the lines, and project them to their bound private `daily_note` Chronicle row. Repeated old-client saves update that same history row; they never overwrite a normal journal or grant journal XP/game progress.
- All row creation and payout paths lock the author before the wellbeing row, including GET, to serialize competing endpoints safely on PostgreSQL.

## Endpoints
- `GET /api/wellbeing/today/` — idempotent, returning the affirmation, legacy saved lines, and shared paid flag.
- `POST /api/wellbeing/today/gratitude/ {lines: [...]}` — retained compatibility endpoint; returns the saved legacy entry and actual coin award.
- Both are `IsAuthenticated` and always self-scoped; body `user_id` is ignored.

## Historical notes and privacy

Chronicle migration `0008_daily_notes_in_journal` imports every nonblank source note into its own `daily_note` entry, preserving date, text, and creation time. It neither deletes source rows nor changes their payout timestamps. The pure data migration invokes no reward/game services. Imported notes carry unavailable/zero reward receipts, since a saved source timestamp does not prove historical XP or an exact coin amount.

Daily notes are read-only and author-only across REST and MCP, even if an invalid row has `is_private=False`. They have no sharing or comments flow and do not count toward journal badges, streaks, or Meadow keepsakes. New Today captures instead use the normal private-by-default journal with its established sharing controls and once-per-day writing XP/game rules.

## Authoring workflow
- Edit `content/wellbeing/affirmations.yaml`.
- Run `python manage.py loadwellbeingcontent` to validate unique slugs, nonempty text and list shape. `seed_data` runs the same validation.
- The affirmation roll is deterministic for `(user_id, local day)`; saved rows store the slug, and content edits re-resolve it to current copy.

## Key entry points
- `services.py` — `WellbeingService`, `MAX_LINES`, `MAX_LINE_CHARS`, `GRATITUDE_FIRST_OF_DAY_COINS`.
- `content/wellbeing/affirmations.yaml` — affirmation pool.
- `management/commands/loadwellbeingcontent.py` — YAML validator.
- Frontend: `pages/dashboard/WellbeingCard.jsx` opens the shared journal form.
