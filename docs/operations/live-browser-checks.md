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

## Offline validation

Hosted PR validation runs `npm run test:live-config` with synthetic files and
processes; it does not run the deployed suite or receive production credentials.
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
