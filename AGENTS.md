# Agent instructions

Before changing code, read [CLAUDE.md](CLAUDE.md). It is the canonical source
for the stack, architecture, commands, authentication, family scoping, and
project conventions. These `AGENTS.md` files make that existing guidance
discoverable; keep detailed subsystem documentation in its current location.

## Read the guidance for the work you touch

| Area | Required reading |
| --- | --- |
| Django apps | The relevant `apps/<app>/CLAUDE.md`, when present; the root document contains the subsystem index |
| React | [frontend/CLAUDE.md](frontend/CLAUDE.md) |
| React pages | [frontend/src/pages/CLAUDE.md](frontend/src/pages/CLAUDE.md), plus the owning backend app's guidance for API behavior |
| UI primitives and styling | [frontend/src/components/README.md](frontend/src/components/README.md) |
| Unity | [unity/AbbyCamp/AGENTS.md](unity/AbbyCamp/AGENTS.md) and [unity/AbbyCamp/README.md](unity/AbbyCamp/README.md) |
| Shared API responses | [contracts/api/README.md](contracts/api/README.md) and the owning views/serializers |

Read any more specific `AGENTS.md` and `CLAUDE.md` files along the path to the
files you edit. A frontend feature may need backend subsystem guidance even
when its implementation touches only React.

## Cross-client changes

Django owns authorization, saved contributions, reward eligibility, XP,
coins, inventory, and progression. React and Unity present server-confirmed
state. Preserve family boundaries and private journal access across every
client; use the existing scoping helpers described in `CLAUDE.md`.

For an API change, update its shared response fixtures and the affected
backend, React, and Unity checks together. Fixtures are synthetic examples of
the real response body, not a replacement for endpoint or permission tests.
Keep real browser credentials out of fixtures, logs, navigation URLs, and
messages; fixture tokens must be synthetic.

## Validation

Use the applicable commands in the canonical documents, and report what ran
and any environment limitation. From `frontend/`, use `npm run lint`,
`npm run test:run` (or the CI coverage gate), and `npm run build` for affected
frontend work. Backend validation uses `python manage.py test` with the
settings/environment documented in `CLAUDE.md`, or the existing Docker command.
Unity and browser-bridge commands are in its scoped instructions.

Pull-request checks and Unity runner setup are documented in
[docs/operations/pr-validation.md](docs/operations/pr-validation.md).

Preserve existing local changes. Keep the implementation focused on the
requested behavior, and review the diff for unintended scene, asset, package,
or generated-file changes before finishing.
