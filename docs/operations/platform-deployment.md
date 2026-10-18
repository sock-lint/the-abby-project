# Platform deployment

Production is the native Coolify Docker Compose application
`lr5dn6lhga31vyk6u5qvhm4c` on the Coolify LXC (119). It builds
`sock-lint/the-abby-project`, branch `main`, with its existing application
configuration, private build inputs, runtime variables, and persistent volumes.
GitHub Actions does not copy Compose files, change application settings, or
install the public GHCR image into production. The retired SSH deployment to
`192.168.4.67:/opt/the-abby-project` is no longer used.

## Runner and pipeline

The `deploy-platform` runner belongs to this repository on VM 110
(`gha-runner-01`, `192.168.4.150`). It is separate from the licensed Unity runner
described in [PR validation](pr-validation.md). Its service account needs Git,
Docker access, Trivy, and access to the Coolify API and public health endpoint.
Actions installs Node 22 and Python 3.12 for the corresponding jobs. No
production SSH identity is needed.

Production `frontend-test` uses the separate `abby-frontend` runner on the same
CI VM, so frontend and backend tests can run concurrently. Its dedicated
`abby-frontend` service account has private work, tool and dependency caches
under `/var/lib/abby-frontend-runner`, no sudo or Docker membership, and a
systemd sandbox that hides other users' home directories. The service is capped
at six CPUs and 12 GiB RAM; Vitest retains its four-worker limit. This runner
has only the frontend label. Backend tests, image build, vulnerability scan and
deployment remain on `deploy-platform`; do not add that label to the frontend
runner because backend services bind fixed PostgreSQL/Redis host ports.

The [CI/CD workflow](../../.github/workflows/ci-cd.yml) checks that its SHA is
still current `main`, runs the full frontend coverage gate and PostgreSQL backend
tests, builds/publishes a public validation image, and scans it for fixable HIGH
and CRITICAL vulnerabilities before invoking Coolify. The validation image
checks the public checkout; Coolify performs the actual production build using
its preserved private build inputs. Its separate native build can still fail
even when the public image passes. GHCR credentials use a unique directory under each
job's runner temporary directory and are removed afterwards, leaving other
repositories' Docker credentials alone.

Backend tests run real PostgreSQL 16 with the disposable data directory on a
1 GiB tmpfs. This preserves PostgreSQL transaction and locking checks while
avoiding disk-sync stalls on the shared runner's storage. The explicit size
limit caps this temporary filesystem's allocation. Actions removes the service
container and its test data after the job; production uses its native persistent
Compose volumes.

## Integration configuration

Set these GitHub Actions values through the repository's secret/variable
settings; never put a real token in source, command arguments, or logs.

| Type | Name | Purpose |
| --- | --- | --- |
| Secret | `COOLIFY_API_URL` | Trusted API base URL ending in `/api/v1` |
| Secret | `COOLIFY_API_TOKEN` | Team-bound token with only `read` and `deploy` abilities |
| Variable | `COOLIFY_APPLICATION_UUID` | `lr5dn6lhga31vyk6u5qvhm4c` |

Use HTTPS when the existing API allowlist permits that route. The current
instance allows the private LAN, while the public Cloudflare route does not
meet its IP allowlist. The private API address is
`http://192.168.4.76:8000/api/v1`; this route relies on the trusted LAN and
instance allowlist. The helper rejects public HTTP addresses and HTTP hostnames.
It never follows authenticated redirects. Do not broaden the API allowlist or
grant `write`, `root`, or `read:sensitive` to work around a connectivity failure.

The token belongs to the existing application's team. Coolify 4.1.2 supports
team-level abilities, not a token restricted to one application; the helper
restricts all application/deployment requests to the configured UUID and verifies
its repository and branch. Use a dedicated expiring token for this integration,
rotate it before expiry, and revoke it if exposed. GitHub's built-in token uses
read-only repository access for the latest-main check; the build/scan jobs grant
only their required package write/read permissions.

See Coolify's [API token documentation](https://coolify.io/docs/core/security/credentials/api-tokens),
[deployment endpoint](https://coolify.io/docs/api/endpoints/deployments/deploy-by-tag-or-uuid),
and [deployment status endpoint](https://coolify.io/docs/api/endpoints/deployments/get-deployment-by-uuid).
The request/response behavior was also checked against the installed 4.1.2
controller. This integration does not print deployment logs, application
configuration, or error response bodies, which may contain private values.

## Sentry configuration and verification

Backend and browser error reporting use separate settings. Select the existing
Abby projects in the self-hosted Sentry instance at `https://logs.neato.digital`
and copy each project's DSN from its client-key settings. Do not substitute an
authentication token for a DSN or assume both clients use the same project.

In the existing production Coolify application's **Environment Variables**, set:

| Setting | Value | Required scope |
| --- | --- | --- |
| `SENTRY_DSN` | Backend project's DSN | Runtime |
| `SENTRY_ENVIRONMENT` | `production` | Runtime |
| `VITE_SENTRY_DSN` | Browser project's DSN | Build time |
| `VITE_SENTRY_ENVIRONMENT` | `production` | Build time |

Optional `SENTRY_RELEASE` and `VITE_SENTRY_RELEASE` can identify the same deployed
commit. The independent `*_TRACES_SAMPLE_RATE` settings control performance
tracing, not whether errors are captured. Empty DSNs intentionally disable
reporting for that client.

The production Compose build forwards the public `VITE_SENTRY_*` settings as
build arguments. Existing scoped BuildKit mounts take precedence when Coolify
supplies those settings as build secrets. Changing browser settings requires a
new image build and deployment; restarting an old image preserves its old
configuration. GitHub's optional Sentry secrets configure only its public
validation image, not Coolify's separate production build.

The optional source-map upload token belongs in the existing BuildKit secret
`SENTRY_AUTH_TOKEN`, never a build argument or `VITE_*` value. Keep a verification
API token outside Git and application configuration. For readback, use
`project:read` and `event:read` permissions and authenticated requests to the
self-hosted instance.

After the gated deployment, verify both sending clients and receiver ingestion:

1. Confirm `/health` identifies the expected served commit. Open the deployed
   website in a fresh browser context so an old PWA bundle cannot mask the new
   browser configuration.
2. Produce one clearly named synthetic browser exception and one synthetic
   exception in the deployed Django process. Backend verification must use its
   initialized SDK and runtime settings, not a separately configured local SDK.
   Use synthetic messages with no family, journal or authentication data.
3. Record each event ID and retrieve it from
   `/api/0/projects/<organization>/<project>/events/<event-id>/`. Check the
   expected project, message, platform and environment before recording success.

An SDK event ID, an accepted envelope, passing mocked unit tests, a healthy
Sentry endpoint or successful source-map upload alone does not prove an event
was processed and stored. Missing receiver access leaves delivery unverified.

## Release verification and limits

Only pushes/manual dispatches on `main` can deploy. Per-ref workflow concurrency
supersedes older Actions runs; a non-main manual dispatch cannot cancel main's
run. The helper checks GitHub's current-main SHA immediately before queuing the
native deployment and while polling it. A stale run does not queue a deployment.
A monitored deployment resolving to another SHA, or superseded during polling,
fails and requests cancellation when it is still active.

One existing active deployment for the same application and expected SHA is
reused. An unresolved native `HEAD` deployment can also be monitored, with the
same exact-SHA success requirement. Preview deployments are excluded. Multiple
active deployments, or an active deployment for another resolved SHA, stop the
helper before it queues more work.

Temporary connection failures and HTTP 408, 429, 500, 502, 503 and 504 responses
to observational GETs allow four retries, with 2, 4, 8 and 16 seconds of backoff.
This applies to Coolify, GitHub's current-main check and public health. A short
outage no longer immediately cancels an otherwise progressing native deployment.
Authorization/configuration failures, redirects and invalid Coolify/GitHub GET
responses fail without those retries. During public health verification only,
invalid JSON (including a brief HTTP 200 plaintext `ok` proxy response) remains
unproven readiness until the next poll or the health deadline. It can never
establish serving identity or success. Requests retain their 30-second connection/read timeout;
the helper checks one monotonic deployment deadline before and after reads and
caps backoff to the remaining time. A single in-flight request can finish after
that deadline, but cannot authorize another deployment or success afterwards.

The deployment POST is sent at most once. A lost connection, temporary server
error or malformed response can follow server-side acceptance, so the helper
does not replay it. It captures the application's last 50 deployment UUIDs
before POST, then allows up to 60 seconds within the deployment deadline to
identify one new, compatible, non-preview row in this application's history.
A new finished row must already prove the exact expected SHA; an old finished
row cannot prove acceptance. The same reconciliation handles the installed API's
duplicate response bug, which can return a UUID without a queue row. Missing or
ambiguous evidence fails with an instruction to inspect that application's
queue, without queuing a replacement or cancelling an unidentified deployment.
After an uncertain result, inspect Coolify before rerunning the workflow.

Coolify 4.1.2's native deploy API does not accept an immutable commit argument.
The application resolves its configured `HEAD` on the server, so the GitHub
check and server fetch cannot be atomic. Do not describe this as commit pinning:
the helper accepts success only when the finished deployment's resolved commit
equals the workflow SHA. One 20-minute budget covers application checks,
reconciliation, retries, native deployment and public verification. After Coolify
finishes, up to two minutes of that remaining budget allow
`https://abby.bos.lol/health` to confirm `status: ok`, `db: up`, the exact workflow
`commit`, and the configured application `resourceUuid`. Current main is checked
again after the health read before success. That same verification window also
checks the three canonical unqueried worker URLs (`/sw.js`, `/push-sw.js`,
`/privacy-sw.js`) anonymously, with redirects and ambient proxies disabled.
`/health.pwaScripts` describes the SHA-256 and byte length of those files in the
actual serving production image; the public validation image cannot supply this
proof because its build inputs differ. JavaScript MIME, exact bytes, zero cache
age, browser revalidation and an edge bypass (`DYNAMIC` or `BYPASS` when
Cloudflare reports a status) are required. HTML, stale bytes, positive cache TTLs,
missing fingerprints, and edge hits fail release verification. A final health
read must retain the same commit and fingerprints. No cache-busting URL is used.
The helper never cancels an already finished deployment for a worker-delivery
failure; the deployment job fails with the release still unverified. See
[PWA delivery policy](pwa-edge-cache.md). The Actions deployment job has a
30-minute limit. Signals, deadline, exhausted read retries and mismatches attempt
cancellation of the known monitored deployment UUID. A forced runner exit, an
interruption before an uncertain POST can be reconciled, or an already finished
deployment can prevent cancellation. Inspect that exact application/deployment
in Coolify when cancellation or the request outcome cannot be confirmed.
If a deployment response contradicts the expected application/resource UUID,
deployment UUID or non-preview identity, earlier cancellation eligibility is
revoked. The helper fails without cancelling that contradictory target; inspect
the application's queue instead. A proved own deployment resolving to the wrong
commit still receives cancellation while active.

Coolify's existing automatic deployment remains enabled. Its native webhooks are
outside Actions concurrency and latest-main guards, and are not evidence that
the GitHub validation pipeline passed. The workflow preserves this setting and
the application's private build configuration. The workflow accepts public
health and serving identity only alongside the exact finished Coolify commit
as its release evidence.

`/health` additionally exposes `commit` only for a full lowercase 40-character
hexadecimal `SOURCE_COMMIT`, and `resourceUuid` only when runtime
`COOLIFY_RESOURCE_UUID` matches Abby's pinned application UUID. Missing or
invalid values are omitted, including on degraded health responses. Every
health response uses `Cache-Control: no-store` so the identity describes the
container serving the request. Coolify injects these existing runtime values;
no Docker build argument or private environment change is needed.

The separately authorized [live browser observer](live-browser-checks.md)
requires that public serving identity to match fresh finished-deployment proof
both before login and after its browser journeys. Those browser journeys are an
additional station gate beyond the deployment workflow's public identity and
status/database checks. Operators can also compare running containers'
`SOURCE_COMMIT` when investigating runtime/version drift.

Do not re-enable stale queued workflows or use an old manual dispatch to roll
back production. Select a deliberate current-main change, validate it, and
deploy it through the normal pipeline. For build/health failures, inspect the
exact native deployment and application in Coolify; do not substitute a raw
Compose stack or overwrite its private environment.

## Local guard tests

The [Deployment guard regression checks](../../.github/workflows/deployment-guards.yml)
workflow runs these synthetic checks and the executable PHP/Bash helper-command
tests on relevant pull requests and main changes. It requires PHP and Bash, so
missing tooling cannot turn skipped helper tests into a pass. It uses no
production connection or private assets.

The deployment helper uses only Python's standard library. These checks use
synthetic API responses and never contact production:

```powershell
python -m unittest discover -s scripts/operations -p test_deploy_coolify.py -v
```

They cover stale/nonmatching commits and application targets, exact successful
completion, temporary Coolify/GitHub/health failures, bounded retry exhaustion,
deadline/supersession during backoff, uncertain POST reconciliation without
replay, old/ambiguous/preview/cross-application history, interruption cancellation,
serving identity and database failure, temporary/plaintext and persistently
invalid public health responses, restricted HTTP URLs, redirect refusal,
and credential/error response isolation.

The version-specific, pinned Coolify image correction and its source guards,
startup ordering checks, activation and rollback procedure are documented in
[the Coolify helper correction](../../scripts/operations/coolify_helper/README.md).
Its custom image override is a deliberate platform upgrade hold: remove or
rebase it after reviewing a later official release, rather than running the
updater against the pinned local image.
