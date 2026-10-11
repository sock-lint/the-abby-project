# Shared API response fixtures

`fixtures/*.json` contains raw Django response bodies shared by the React tests
and Unity Editor API validation. Keep the files here rather than copying sample
payloads into each client. No production credentials or user data belong here.
The login token and all identities are synthetic and exist only in the test DB.

| Fixture | Endpoint / scenario |
| --- | --- |
| `auth-login-child.json` | `POST /api/auth/`, successful password login; flat user plus token |
| `auth-me-child.json` | `GET /api/auth/me/`, authenticated child identity |
| `habits-page-1.json` | `GET /api/habits/`, first 20 of 21 child-visible rituals |
| `habits-page-2.json` | `GET /api/habits/?page=2`, final ritual and null `next` |
| `habits-empty.json` | `GET /api/habits/`, no published rituals |
| `habit-positive-tap.json` | `POST /api/habits/9/log/`, persisted `direction: 1` tap and real game event |
| `habit-positive-tap-no-event.json` | Same tap with the optional game-loop result explicitly absent |
| `habit-positive-tap-limit.json` | Same-day repeat rejected with HTTP 400; no second tap persists |

`config/tests/test_api_contract_fixtures.py` seeds fixed family/user/habit/skill
IDs and a fixed clock, sends requests through the real Django views, then compares
the rendered JSON to these files. It also verifies token rotation, child/family
scope, pagination, persisted strength and XP, and duplicate-tap rejection. The
ordinary tap runs the real game loop with fixed random input; only the no-event
scenario replaces that optional service boundary with `None`. Date of birth and
school grade are unset to avoid date-dependent computed identity values.

`frontend/src/api/sharedContractFixtures.test.js` serves these same files with
MSW and exercises the real React API wrappers, token handling, list normalization
and HTTP error propagation. Unity's `ApiContractValidation.Run` reads the files
directly from this repository; run it from a complete checkout, not an isolated
copy of `unity/AbbyCamp`.

## Check for drift

From the repository root, with the normal backend test environment configured:

```sh
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures
```

For Docker-less checks, use a disposable SQLite `DATABASE_URL` such as
`sqlite:///:memory:` and a synthetic `SECRET_KEY`. Do not use a production DB.
From `frontend/`:

```sh
npm run test:run -- src/api/sharedContractFixtures.test.js
```

Run Unity with `-executeMethod AbbyCamp.Editor.ApiContractValidation.Run`, or use
**Abby Camp → Validate API Contracts** in the Editor. See the Unity README for
the pinned editor and batch-mode commands.

## Update an intentional API change

Review the server and both client consumers first. Regenerate only through the
backend suite so sample payloads cannot drift into invented shapes. In PowerShell,
after configuring the test environment:

```powershell
$env:UPDATE_API_CONTRACT_FIXTURES = '1'
try {
    python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures
} finally {
    Remove-Item Env:UPDATE_API_CONTRACT_FIXTURES
}
```

Review the JSON diff and adapt the React and Unity consumers/tests as needed.
Then rerun all three checks with regeneration disabled. CI compares snapshots
and refuses regeneration. An unexpected added, removed, renamed or retyped field
fails the backend comparison even if a client silently ignores it.
