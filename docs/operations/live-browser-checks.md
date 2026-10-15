# Dedicated deployed browser checks

On October 13, 2026 the owner authorized dedicated test accounts and actual
browser checks against `https://abby.bos.lol`. This observer supplements the
existing local mock/fixture suite; it never supplies credentials to PR code or
replaces required CI and independent review.

## Provisioning and ownership

After this source is reviewed, merged, deployed and its serving version verified,
a trusted operator runs the command inside the deployed Django application:

```sh
python manage.py provision_live_test_family --credentials-file /absolute/private.json
```

The input must be a regular file owned by the invoking user with mode `0600`,
without a final symlink or additional hard links. It is bounded to 8 KiB.
Passwords enter only through the private file, never command arguments,
environment variables, source or logs.
Use separately generated strong passwords (16–256 characters, also satisfying
Django's configured validators) for these reserved nonstaff accounts:

```json
{
  "schemaVersion": 1,
  "baseUrl": "https://abby.bos.lol",
  "familySlug": "abby-live-checks",
  "parent": {"username": "abby_loop_parent", "password": "<private>"},
  "child": {"username": "abby_loop_child", "password": "<private>"}
}
```

The first run atomically creates a distinct `Abby Live Checks` family, one
parent, one child, their normal user-owned character profiles and a persisted
`LiveTestFamily` ownership receipt. It never reuses the default family, adopts
matching usernames/slugs, creates staff accounts or emits auth tokens. A
reserved identity that already exists without that receipt is a collision and
stops provisioning. Existing ownership with changed members, identities,
privileges, roles or primary parent also stops without repairing or adopting it.

Output contains only this predictable nonsecret receipt:

```json
{
  "schemaVersion": 1, "status": "created",
  "baseUrl": "https://abby.bos.lol", "familySlug": "abby-live-checks",
  "familyId": 123,
  "parent": {"id": 124, "username": "abby_loop_parent", "role": "parent"},
  "child": {"id": 125, "username": "abby_loop_child", "role": "child"}
}
```

The operator adds all three returned expected IDs to the same private JSON:
top-level `familyId`, `parent.id`, and `child.id`. These IDs are mandatory for
live checks and are verified again by repeated provisioning. An unchanged
repeat returns `status: verified` without changing password hashes or tokens.
The explicit `--rotate-passwords` option permits changes only to owned accounts
and revokes tokens only for accounts whose password changed. `status: updated`
also covers acknowledging newly authored lorebook introduction copy for the
dedicated child; these flags do not award progression and avoid product writes
to dismiss first-encounter panels during read checks.

There is no public fixture endpoint or admin registration for this ownership
record. Provisioning and rotation are operator actions, outside improvement
tasks. Do not include the private input file in a Git checkout or artifact.

## Trusted source and proof

The station installs a reviewed merged-main harness immutably under root-owned
`/opt/abby-live-checks/<sourceCommit>`. Its Node binary, dependencies and browser
runtime are inside the same sealed installation. The controller independently
validates the source pin and its merged-main provenance. It executes this fixed
source after later application releases, rather than giving credentials to the
new PR's code. The harness source commit can be an ancestor of the application
commit being checked.

The install's `frontend/.abby-live-source.json` is root-owned, mode `0644`:

```json
{"schemaVersion": 1, "sourceCommit": "<40-character-source-sha>"}
```

The separate root-owned `/etc/abby-live-checks/manifest.json` has exact keys
`schemaVersion`, `sourceCommit`, `installPath`, `nodePath`, and `browserPath`.
The controller owns installation verification; this sidecar identifies the
harness revision in its private report. Source changes require another reviewed
installation. No live credentials are passed through the child environment.

Before starting, the controller supplies a private fresh deployment-proof JSON
with exact fields `schemaVersion: 1`, `source: "coolify"`, `applicationUuid`,
`repository: "sock-lint/the-abby-project"`, `branch: "main"`, `deploymentUuid`,
`status: "finished"`, `commit`, `observedAt`, and `expiresAt`. The application
UUID is pinned to `lr5dn6lhga31vyk6u5qvhm4c`; commit must match the expected
40-character SHA, and evidence expires within five minutes of observation.
The proof is produced through read-only Coolify observation, not through
inference from a healthy login page or a pending deployment.

## Browser run and private receipt

From the trusted install's `frontend/` directory, the controller invokes the
pinned Node binary with:

```sh
node scripts/run-live-checks.mjs --credentials-file /absolute/private.json \
  --deployment-proof-file /absolute/proof.json --result-file /absolute/result.json \
  --expected-commit <40-character-application-sha>
```

The small serial Chromium suite has no API mocks. It checks the public shell,
performs actual parent and child UI sign-in, verifies returned user and family
IDs before allowing authenticated reads, exercises read workflows and verifies
the child is denied parent-only access. Only login and logout POSTs are allowed;
unexpected product writes or authenticated cross-origin requests fail the run.
Service workers are blocked for this observer so requests cannot bypass its
guard. The default local Playwright suite keeps its existing service-worker and
fixture behavior.

Before login and again after the journeys, `/health` must report `status: ok`,
`db: up`, the expected serving `commit`, the pinned `resourceUuid`, and
`Cache-Control: no-store`. Finished Coolify proof and serving identity must
agree. Browser timeouts and proof expiry fail closed. Cleanup logs out both
dedicated sessions; no user-generated project, journal, reward or assignment
records are created. Normal authenticated read effects such as `last_seen_at`
remain restricted to the owned fixture accounts.

There are two login and two logout POSTs per successful run. Abby's existing
auth throttle is 10 POSTs per minute per IP and includes logout. The controller
reuses a fresh receipt for the same exact scope/deployment before merge and
spaces separate browser starts at least 60 seconds apart. A post-merge cooldown
or pending deployment waits for another eligible tick before further work.

The wrapper holds an exclusive private credential lock, bounds the whole run to
180 seconds, and drains the runner, worker and browser descendants on timeout
or termination before releasing ownership. Retries are disabled. It writes only
a private mode-`0600` result with these allowlisted fields:

- `schemaVersion`, `status`, `checkedAt`, `expiresAt`, `baseUrl`;
- `sourceCommit`, `expectedCommit`, `deployedCommit`, `servedCommit`;
- `deployment` with source, application UUID, deployment UUID, repository,
  branch, status and observation time;
- `scope` with family slug, family ID, parent ID and child ID;
- boolean `checks`: deployment, health, publicShell, parent, child, isolation,
  cleanup; and categorical `failures`.

Receipt expiry is the earlier of proof expiry and five minutes after the check.
Reports contain no response bodies, error text, DOM, credentials, tokens or
ordinary-user content. Traces, screenshots, video, HAR, storage-state files,
public HTML/JSON reporters and browser console capture are disabled. The
controller verifies the exact report schema, scope, source, target, health and
freshness independently and re-observes deployment state before accepting it.

## Design and UX journeys

The reviewed harness also exercises the deployed `/__design` route without an
account. At a real 320-pixel viewport it checks all six cover palettes, enlarged
and long content, text/control/focus contrast, 44-pixel controls, changing the
browser's reduced-motion preference, keyboard dialog containment and restored
focus, local Task details, and attachment selection, replacement, removal,
preview failure and linked errors. Gallery saves and simulated upload failures
are synthetic local state; they do not submit domain records.

After verifying the dedicated identities, the parent journey follows the child's
Today card into Timeline, retains the verified child across Journal, Grades and
Timeline, and rejects an invalid local selection. Chronicle requests with an
explicit `user_id` are fenced to the designated accounts before forwarding.
Each initial Journal, Grades and Timeline read must finish successfully before
the journey continues; returning to a retained panel reuses that confirmed read.
An absent alert while a request is still loading does not establish success.
The child journey verifies self-scoped Memories, task filtered/true-empty states,
Movement's recorded-session/actual-XP summary and local image/model chooser
controls in the real forms. Project detail/back restoration is exercised when
the dedicated account already has a visible project; otherwise the journey
requires a successful empty response and the true-empty UI. It never creates a
project to manufacture coverage.

Task recovery is a bounded browser connectivity fault. The Tasks hub statically
loads its tab components online, then the already-authenticated browser briefly
goes offline for the first Habits mount. Visited panels remain mounted, so
reopening an already loaded Habits tab would not exercise a failed read. The
actual error and “Try again” flow must recover after restoring connectivity;
habit filtering runs afterwards. No API response is replaced, and connectivity
is restored in a `finally` block before cleanup. Loopback checks render the real
task hub and error controls so their retained-panel behavior and accessible names
are part of the harness regression tests.

PWA update protection uses an in-memory registration/event probe while native
service workers remain blocked. The real deployed `PwaStatusProvider`, new
project page and new-child dialog must protect local drafts, recheck work opened
during activation, handle a failed activation, and reload only after an explicit
retry or the existing fallback. The probe cannot register, install, activate or
contact a native worker; it never submits either form. This establishes deployed
UI behavior under controlled worker events, not native cache/install acceptance.
Actual replacement-worker/offline-cache behavior remains covered by the isolated
two-release browser tests. Server-confirmed saves, upload retries, approvals and
rewards remain outside this read-only observer.

All assertions run before their existing `publicShell`, `parent` or `child`
receipt flag becomes true. The seven-check receipt schema, private transport,
fixed failure categories, two logins/two logouts, mutation fence and time limits
are unchanged. A missing control or failed assertion fails the whole receipt;
arbitrary DOM, file content and account values never enter the report.
The receipt is a gate result, not a per-journey inventory: a pass cannot establish
that populated-project return or unmatched-search branches ran. Those checks
require existing dedicated-family data; keep this limitation in verification
reports rather than interpreting a true-empty check as populated coverage.

## Installing a reviewed harness revision

Installation is an explicitly authorized operator action. Source must come from
the exact GitHub-confirmed merged commit after hosted CI and independent review,
not a worktree, draft or uncommitted file. Verify the squash/rebase merge's tree
against the reviewed PR head, and record the PR, source SHA and checks. Keep the
previous immutable installation and manifest available for recovery.

Prepare a new `/opt/abby-live-checks/<sourceCommit>` containing these exact Git
archive paths, including all transitive live-helper imports:

- `frontend/package.json`, `frontend/package-lock.json`,
  `frontend/playwright.live.config.js`;
- `frontend/e2e/live-smoke/`;
- `frontend/scripts/run-live-checks.mjs`, `live-checks-contract.mjs`,
  `live-process-group.mjs`, `live-checks-contract.check.mjs`;
- `frontend/src/utils/contrast.js`.

Do not copy credentials, worker homes, `.env`, private art, browser profiles,
working-tree files or candidate-written pass receipts. If the archived lockfile
is byte-identical to the previous sealed installation's lockfile, its unchanged
root-owned `frontend/node_modules`, Node binary and matching `.browsers` runtime
may be copied into the new installation. Verify both source and destination
digests. A different lockfile requires a separately reviewed locked runtime
preparation; do not silently reuse incompatible dependencies or execute npm
lifecycle hooks as root.

Write the new root-owned `0644` `frontend/.abby-live-source.json` with only
`schemaVersion: 1` and the exact `sourceCommit`. Verify every staged file against
its Git archive/runtime source, root ownership, no group/world write permission,
regular files/directories, and symlinks whose resolved targets stay inside the
new installation. Check that the Node binary is executable and Chromium's
revision matches the locked Playwright package. Only then atomically replace
the root-owned `0644` `/etc/abby-live-checks/manifest.json` with its existing five
keys and paths inside the new immutable root. Never edit the previous tree or
change the credential file, observer wrapper, loop grants or failure holds.

Run the fixed observer against the freshly finished and served application
commit. Verify the returned `sourceCommit` is the newly installed revision and
that expected/deployed/served commits match the actual application release.
An installation or browser failure retains the evidence for repair; it does not
authorize a deployment retry, pin bypass, product write or fabricated pass.

## Offline validation

Hosted PR validation runs `npm run test:live-config` with synthetic files and
processes; it does not run the deployed suite or receive production credentials.
The ordinary `npm run test:pwa` gate also runs the design, family/task and PWA
helper checks against disposable loopback fixtures. Negative cases reject
unreadable controls, missing draft guards, false empty responses, unverified
identity and an unexpected file upload. The PWA fixture is a production-mode
build of the real providers and forms, with native worker methods trapped.
The existing frontend coverage/build, backend PostgreSQL and API-fixture gates
remain required. Locally, also run:

```sh
python manage.py test --settings=config.settings_test apps.families.tests.test_live_tests config.tests.test_middleware config.tests.test_migration_drift
```

These checks establish ownership/idempotence, collision and privilege refusal,
transaction rollback, private transport, migration compatibility, served-release
validation and harness confinement. They do not claim a production browser pass;
that requires the reviewed install, provisioned dedicated accounts and fresh
finished/serving release proof.
