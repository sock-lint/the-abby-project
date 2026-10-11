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

## Worktree lifecycle

These rules are mandatory for agents working in this repository. See
[CLAUDE.md](CLAUDE.md#worktree-lifecycle) for verification and recovery details.

- Before creating a worktree, inspect this chat's attached artifacts and reuse
  a suitable active worktree. Create isolated checkouts through `create_worktree`
  and attach them to their owning chat; attach every PR created or continued.
- Record the PR URL, target branch, canonical checkout branch/path, and managed
  worktree identity/root in the owning chat. Confirm the exact PR's merge on
  GitHub before treating its work as merged.
- After a confirmed merge, archive every eligible managed worktree owned by this chat
  through `archive_worktree`. It saves a recoverable snapshot and removes the
  checkout. Do not substitute raw filesystem deletion or forced Git removal.
  Automatic cleanup after merge is an established user preference; do not ask
  for redundant approval to archive an eligible managed worktree.
- Before final handoff, audit owned worktrees and clean up eligible ones. Never
  remove a primary, currently active, pinned, shared, or another chat's worktree.
  Retain a PR-associated checkout whose PR identity is ambiguous or whose work
  remains unmerged; preserve additional work and needed ignored assets first.
  Record a concrete reason and next action for each retained checkout.
- Archive an owned managed worktree used only for verification or exploration
  once its purpose is complete, needed work is preserved, and no active follow-up
  needs it. Record that completion as the cleanup reason; lack of a PR alone
  must not leave a disposable checkout stranded.
- If an open PR is the reason to retain a worktree, create or update a heartbeat
  in its owning chat to watch that PR's merge and archive the eligible worktree
  afterwards. Stay quiet while nothing changes, and stop/delete that monitor
  after archival. A central chat cannot archive another chat's attachments;
  monitoring and cleanup must run in the owning chat.
- For an unmanaged worktree owned by this chat, the user's standing automatic
  cleanup request for this repository is authorization: do not ask again. Remove
  it only when clean, inactive, fully merged, and matched to a confirmed exact
  GitHub PR. Use normal `git worktree remove` on its verified absolute path,
  without `--force`. Retain unknown ownership or another chat's checkout with
  a concrete reason. Managed Codex worktrees always use `archive_worktree`.
- The final response must report archived worktrees and recoverable saved work,
  or identify retained worktrees with their reasons and any active merge monitor.

Repository instructions establish this workflow; they do not install a global
Git hook or a repository-wide timer. Configure the owner-chat monitor when needed.

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
