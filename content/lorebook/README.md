# Lorebook Content

The Lorebook is the in-app mechanics explainer shared by parents and kids.
It is intentionally **YAML-authored, not model-authored**: copy and reward
channel notes live in [`entries.yaml`](entries.yaml), while the backend computes
per-user discovery state from existing activity data.

## Surfaces

- **Parents:** `/manage → Guide` shows every entry as reference material and
  expands the parent knobs panel by default.
- **Kids:** `/atlas?tab=lorebook` (also reachable at `/lorebook`) shows the same
  entries as a discovery codex. Entries stay locked until the child first
  encounters that subsystem.
- **First encounter:** the dashboard payload includes `newly_unlocked_lorebook`;
  the frontend shows one celebration sheet per unlocked entry and marks it seen
  via `PATCH /api/auth/me/ { lorebook_flags: { "<slug>_seen": true } }`.

## Entry schema

Each item in `entries:` must include:

| Field | Purpose |
|---|---|
| `slug` | Stable identifier; also used for `<slug>_seen` flags. |
| `title` / `icon` / `audience_title` / `summary` | Tile and detail-sheet copy. |
| `chapter` | One of the frontend chapter ids in `pages/lorebook/lorebook.constants.js`. |
| `kid_voice` | Short journal-voice explanation for children. |
| `mechanics` | Load-bearing rules, caps, gates, formulas, and exceptions. |
| `parent_knobs` | `settings`, `powers_badges`, and `content_sources` arrays for the Guide tab. |
| `economy` | Boolean reward-channel map used by the parent economy diagram. |

The required economy keys are:

- `money`
- `coins`
- `xp`
- `drops`
- `quest_progress`
- `streak_credit`

## Current core entries

The catalog ships 17 entries:

`duties`, `rituals`, `study`, `journal`, `creations`, `ventures`, `skills`,
`badges`, `chronicle`, `quests`, `pets`, `mounts`, `drops`, `streaks`, `coins`,
`money`, `cosmetics`.

Exchange, rewards, and trophies currently live inside the Coins/Money/Cosmetics
entries rather than as separate tiles. Splitting them later only requires adding
new YAML entries, frontend chapter placement, and unlock derivation.

## Unlock derivation

`apps/lorebook/services.py::compute_lorebook_unlocks` maps entries to existing
first-encounter signals. Examples:

- `study` unlocks from the first homework assignment or submission.
- `creations` unlocks from the first `Creation`.
- `pets` unlocks from the first `UserPet`.
- `streaks` unlocks once `CharacterProfile.login_streak >= 2`.
- Parents always receive `unlocked=true` for every entry (`parent_reference`).

When adding a new entry, update:

1. `entries.yaml`
2. `EXPECTED_ENTRY_SLUGS` and `compute_lorebook_unlocks` in `apps/lorebook/services.py`
3. Chapter placement in `frontend/src/pages/lorebook/lorebook.constants.js`
4. Tests in `apps/lorebook/tests/test_views.py` and the relevant frontend tests

## Validation

Targeted backend check:

```bash
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
 DJANGO_SETTINGS_MODULE=config.settings_test \
 python manage.py test apps.lorebook
```

Targeted frontend check:

```bash
cd frontend
npm run test:run -- GuideSection.test.jsx Lorebook.test.jsx FirstEncounterSheet.test.jsx Manage.test.jsx
```
