# Autonomous improvement loop

On October 12, 2026, the owner requested an Abby station that continuously
proposes and implements improvements to this passion project, and authorized
automatic merge after tests and independent review pass. The application has
no active users. This authorization covers repository improvements; deployment
still follows the existing [platform pipeline](platform-deployment.md).

The station controller lives in the homelab configuration. Its bounded queue
feeds separate proposer, implementer and reviewer sessions. Work can proceed
without routine owner approval when it fits this policy. Report actionable
failures and decisions that need the owner; keep unchanged status quiet.

## Proposals and implementation

- Read root and applicable subtree guidance before choosing work. Verify the
  current code, issues and open PRs; a historical backlog entry alone does not
  establish a missing feature. Avoid duplicate or conflicting work.
- Favor concrete correctness fixes, mobile usability, accessibility, clearer
  onboarding, performance and bounded features that support real-life projects,
  learning and household contributions. Explain the user benefit, affected
  paths, acceptance criteria and meaningful verification in each proposal.
- Keep each issue and PR small enough for independent review. Finish a coherent
  behavior rather than adding placeholder screens or speculative frameworks.
  Update existing documentation when the behavior it describes changes.
- Respect the current React/R3F/Capacitor stack and single-origin Django web
  deployment. Unity is retired. Keep accessible DOM controls and the public
  fallback when private models or WebGL are unavailable. Do not import or
  publish licensed source art, or claim native phone acceptance from a bundle
  build alone.
- Preserve family scoping, private journals, server-owned rewards and
  progression, approval requirements, append-only ledgers and anti-farming
  limits. Frontend presentation cannot award progress. Keep API responses and
  producer/consumer fixtures aligned, with permission and interaction tests.
  API responses remain network-only; do not revive private API offline caches.
- Use synthetic accounts, fixtures and isolated test services. Do not operate
  production data, payment services, printers, credentials or infrastructure
  from an improvement task. Changes to live deployment configuration or the
  station's authority and merge gates need a separate owner-directed task.

## Merge gate

An implementer opens a PR targeting `main`. A separate reviewer inspects the
current diff, repository rules and evidence, addresses blocking findings, and
records its result for the exact current head. A self-review or a stale review
does not satisfy this requirement. New commits require fresh review and checks.

Automatic merge requires all three [required PR checks](pr-validation.md):
`Frontend validation`, `Backend validation`, and `API fixtures`, plus successful
completion of every other triggered check, including applicable PWA checks.
Pending, missing, failed, cancelled or skipped required checks do not count as
success. Preserve strict branch protection, current-base validation and
resolved review threads. Never force or bypass a merge to keep the loop moving.
If checks or independent review cannot be verified, retain the PR for repair.

Merging to `main` can deploy immediately: Coolify's native automatic deployment
is enabled independently of GitHub Actions. A successful merge is not release
evidence. The deployment workflow verifies the finished commit and public
application/database health; record and surface deployment failures without
issuing an unreviewed rollback or changing production settings.

## Station checkouts

Station tooling creates isolated worktrees with a station task owner, branch,
base SHA and exact PR identity. It owns only its task checkouts. Never adopt,
reset, delete or archive a Codex chat's managed artifacts or another task's work.
Keep the station's primary repository checkout and protected branches intact.

After verifying the exact GitHub PR merged, preserve needed work and remove
only a clean, inactive owned task worktree. Clean up its eligible disposable
task branch afterward using the branch-verification rules in `AGENTS.md`.
Retain divergent/unmerged work with its reason and next action. A deleted remote
branch is not merge evidence. Station task records supply the ownership and
cleanup evidence that a Codex app chat would keep in its artifact inventory.
