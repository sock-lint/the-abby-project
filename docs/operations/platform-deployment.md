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

The [CI/CD workflow](../../.github/workflows/ci-cd.yml) checks that its SHA is
still current `main`, runs the full frontend coverage gate and PostgreSQL backend
tests, builds/publishes a public validation image, and scans it for fixable HIGH
and CRITICAL vulnerabilities before invoking Coolify. The validation image
checks the public checkout; Coolify performs the actual production build using
its preserved private build inputs. Its separate native build can still fail
even when the public image passes. The shared runner's frontend test process is
bounded to four workers. GHCR credentials use a unique directory under each
job's runner temporary directory and are removed afterwards, leaving other
repositories' Docker credentials alone.

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

## Release verification and limits

Only pushes/manual dispatches on `main` can deploy. Per-ref workflow concurrency
supersedes older Actions runs; a non-main manual dispatch cannot cancel main's
run. The helper checks GitHub's current-main SHA immediately before queuing the
native deployment and while polling it. A stale run does not queue a deployment.
A monitored deployment resolving to another SHA, or superseded during polling,
fails and requests cancellation when it is still active.

An existing active deployment for the same application and expected SHA is
reused. An unresolved native `HEAD` deployment can also be monitored, with the
same exact-SHA success requirement. Preview deployments are excluded. This
avoids redundant webhook builds and accounts for the installed API's duplicate
response bug, which can name a UUID that has no queue row; the helper resolves
that initial 404 only through this application's active deployment history.

Coolify 4.1.2's native deploy API does not accept an immutable commit argument.
The application resolves its configured `HEAD` on the server, so the GitHub
check and server fetch cannot be atomic. Do not describe this as commit pinning:
the helper accepts success only when the finished deployment's resolved commit
equals the workflow SHA. Its bounded polling allows 20 minutes for Coolify, then
two minutes for `https://abby.bos.lol/health` to confirm both `status: ok` and
`db: up`. The Actions deployment job has a 30-minute limit. Signals, timeout,
and mismatches attempt cancellation of the monitored deployment UUID; a forced
runner exit or an already finished deployment can prevent cancellation. Inspect
that exact deployment in Coolify when cancellation cannot be confirmed.

Coolify's existing automatic deployment remains enabled. Its native webhooks are
outside Actions concurrency and latest-main guards, and are not evidence that
the GitHub validation pipeline passed. The workflow preserves this setting and
the application's private build configuration. Public health plus the exact
finished Coolify commit is the workflow's release evidence; an operator can
independently compare running containers' `SOURCE_COMMIT` when investigating
runtime/version drift.

Do not re-enable stale queued workflows or use an old manual dispatch to roll
back production. Select a deliberate current-main change, validate it, and
deploy it through the normal pipeline. For build/health failures, inspect the
exact native deployment and application in Coolify; do not substitute a raw
Compose stack or overwrite its private environment.

## Local guard tests

The deployment helper uses only Python's standard library. These checks use
synthetic API responses and never contact production:

```powershell
python -m unittest discover -s scripts/operations -p test_deploy_coolify.py -v
```

They cover stale/nonmatching commits and application targets, exact successful
completion, supersession/timeout/interruption cancellation, public health and
database failure, restricted HTTP URLs, redirect refusal, and credential/error
response isolation.
