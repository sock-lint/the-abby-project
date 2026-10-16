# DigitalOcean App Platform migration

The owner prefers App Platform for Abby's production hosting. The target is a
managed web service, background workers, PostgreSQL, Valkey, and Spaces. Keep
Django, React, OAuth discovery, and `/mcp` on one HTTPS origin.

This document and the [staging example](../../.do/app-platform-staging.example.yaml)
prepare an isolated bootstrap deployment. They do not establish production
readiness. The current [Coolify deployment](platform-deployment.md) remains
canonical until the migration criteria below pass. Provider capabilities and
prices were checked against DigitalOcean's documentation on October 16, 2026.

## Target services and initial budget

| Component | App Platform mapping | Initial monthly estimate |
| --- | --- | --- |
| Django, React, and MCP | One 2 GiB web service, port 8000 | $25 |
| Celery tasks | One 2 GiB worker; initially concurrency 2 | $25 |
| Celery Beat | One 512 MiB worker, after singleton coordination is implemented | $5 |
| Printer listener | One 512 MiB worker, after transport and replacement checks | $5 |
| PostgreSQL | Isolated managed PostgreSQL 16 cluster | About $15 plus storage |
| Cache, broker, and results | Isolated managed Valkey cluster, TLS required | From $15 |
| Private uploads and public sprites | Separate Spaces buckets and permissions | $5 base subscription |
| Release setup | One `PRE_DEPLOY` job | Billed while running |

Budget approximately **$95–120/month** for this small, single-instance target,
including some room for registry/storage charges. Sizing is provisional until
staging memory, task duration, database connections, and upload behavior are
measured. These starting database plans do not provide high availability.
Redundant application/database infrastructure needs a separate estimate.
The bootstrap example omits Beat and printer tracking, so it costs less and
does not exercise their behavior.

Sources: [App Platform component pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/),
[PostgreSQL pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/),
[Valkey pricing](https://docs.digitalocean.com/products/databases/valkey/details/pricing/),
[Spaces pricing](https://www.digitalocean.com/pricing/spaces-object-storage).
PostgreSQL plan/standby availability is changing for new accounts in October
2026; verify the chosen account's available plan before budgeting failover.

## Build once and deploy the same image

Use the existing Dockerfile with BuildKit in a trusted build environment, then
deploy a private container image by immutable digest. Reuse that exact digest
for the web service, task worker, and release job. Set `SOURCE_COMMIT` to the
full Git commit represented by that image and record the commit-to-digest
binding outside the image's self-reported health response.

App Platform supports [private registry images](https://docs.digitalocean.com/products/app-platform/how-to/deploy-from-container-images/).
Its [Dockerfile build reference](https://docs.digitalocean.com/products/app-platform/reference/dockerfile/)
documents build arguments, but does not document an interface for Abby's
BuildKit secret mounts. Preserve secret mounts in the external build rather
than converting asset-reader keys into Docker build arguments. The existing
public GHCR validation image has fallback artwork and cannot prove delivery of
the private production assets.

The first staging build can use the public fallback with synthetic data. Before
evaluating real artwork, preserve existing artifact acceptance records and
verify that the approved delivery scope covers the new target. Use the scoped
operator release connection for any actual release writes. Private source packs
and purchased originals stay outside Git and the runtime image. Keep automatic
image deployments off so publication cannot skip validation and release gates.

## Bootstrap the isolated staging app

The example spec has explicit `REPLACE_` values and zero-filled identity/digest
placeholders. Copy it to a private location, populate it using the account's
secret controls, and validate the populated spec before creating resources.
Never commit or paste the populated file into a chat or a review.

1. Select the DigitalOcean team/project and an App Platform region with
   colocated PostgreSQL, Valkey, registry access, and Spaces availability.
   Provision a new staging database, queue/cache, buckets, signing key, and
   least-privilege storage credentials. Use synthetic families only.
2. Build and publish a staging image, record its source commit and digest, and
   replace the image/digest/commit placeholders identically across components.
3. Set database and storage credentials privately. Install the provider's
   PostgreSQL CA in the private staging image at a read-only path accessible to
   all three components. Set that path in the URL's `sslrootcert` parameter and
   retain `sslmode=verify-full`; use `rediss://` with certificate
   verification for Valkey. Keep cache on database 0 and broker/results on
   database 1. Preserve the managed queue's `noeviction` policy and verify
   memory alerts; evicting queue keys can lose tasks.
4. Set the exact staging hostname/origin, OAuth/MCP origin, and bucket CORS.
   Protect the staging origin through an approved access control before adding
   any identities. Leave public parent signup, email delivery, planning AI,
   Google integrations, and printer connections disconnected.
5. Run the fresh-database `PRE_DEPLOY` job: `migrate --noinput`, then
   `loadrpgcontent`. The example runs neither `seed_data` nor
   `backfill_accounts_history`: the latter assumes an existing migration table
   and is for legacy database history. Review it separately when rehearsing a
   restored production database. Existing Compose-only staging provisioning
   helpers deliberately reject this topology; do not bypass their guards.
6. Validate schema locally with
   `doctl apps spec validate --schema-only /private/path/app.yaml`, capturing
   stdout/stderr only to a private mode-0600 file. This command prints a
   normalized spec, including populated secret values; do not run it against
   secrets in a shared terminal, CI log, or chat tool output. Then perform
   account-aware validation in the chosen account. Schema validation cannot
   prove registry access, pricing, network access, or runtime behavior.

No credentials or paid resources are provisioned by this repository change.
Creating a staging app needs the owner's configured account access and an
approved resource scope/budget. Authentication is performed by the owner;
tokens must not be sent in chat.

## Changes required before feature-complete staging

| Dependency | Current behavior | Required outcome |
| --- | --- | --- |
| Editable content packs | MCP writes YAML drafts and load manifests under `content/rpg/packs` | Durable storage with validated read/write/delete behavior, multi-process visibility, restart survival, and export/recovery; immutable base content remains protected |
| Source sprite authoring | `register_sprite_assets` writes a source manifest and frontend PNGs | Explicit offline authoring workflow or durable replacement; preserve supported authoring behavior rather than silently accepting ephemeral writes |
| Celery Beat | PostgreSQL `DatabaseScheduler` with no leader lease | One active scheduler during rolling replacement, restart, connection failure, and recovery; one configured instance alone is insufficient proof |
| Printer observation | LAN or Bambu cloud transport; Redis per-printer coordination | Owner-selected transport reachable from the cloud; prove coordinated replacement and saved-job reattachment without duplicate printer connections |
| Managed Valkey | Current deployments use plain Redis URLs | Verify TLS, cache, Celery broker/results, Lua locks, pub/sub, reconnects, and queue memory policy with the installed client versions |
| Release setup | Compose runs setup inside web startup | A serialized release job, backwards-compatible migrations, and failure checks that prevent traffic promotion |
| Deployment identity | Health and trusted observer bind to a pinned Coolify resource | Independent App Platform app/deployment/image/commit evidence, before/after browser checks, and preservation of current merge/live gates |

App Platform's ordinary container filesystem is
[ephemeral](https://docs.digitalocean.com/products/app-platform/how-to/store-data/).
Setting S3 media storage does not fix source-tree pack/sprite writes. In
particular, do not use bootstrap staging for valuable authoring work.

[NFS mounts](https://docs.digitalocean.com/products/app-platform/how-to/mount-nfs-shares/)
are a private-preview option as of this review, requiring account approval.
They are limited to specific regions, force mounted components to UID/GID 65534,
and need seeding and backup design. The existing image runs as UID 1000. Do not
make this preview a production dependency without explicit evaluation; durable
PostgreSQL/object-storage authoring is the default migration direction.

App Platform supports [workers](https://docs.digitalocean.com/products/app-platform/how-to/manage-workers/)
and [pre-deploy jobs](https://docs.digitalocean.com/products/app-platform/how-to/manage-jobs/).
Its rolling replacement behavior means scheduler exclusivity needs application
coordination. Native scheduled jobs have a minimum interval of 15 minutes and
must not replace Beat without checking the application's timing requirements.
The printer listener already has Redis coordination; its actual handover still
needs testing with the chosen managed backend and transport.

## Acceptance and production cutover

First prove health, HTTPS/origin handling, parent/child authentication, two-family
isolation, OAuth discovery and `/mcp`, uploads, public sprite rendering, and one
complete background task on synthetic staging. Redeploy the same app and prove
that saved data and uploads survive. Then complete durable authoring and
scheduler/printer replacement checks before claiming feature parity. Exercise
the private asset renderer against the approved artifact separately; a fallback
build cannot establish that acceptance.

Rehearse a private database and object-storage restore. Preserve the production
`SECRET_KEY` at cutover: it encrypts saved Google OAuth credentials, printer
credentials, and family AI keys. Staging uses a different key and credentials.
Inventory every database, private upload bucket, public sprite bucket, content
draft, asset release, origin/callback URL, and worker before the final transfer.
Keep private media presigned; keep only intended public sprites publicly readable.

The scoped station deployment observer, release helper, and loop currently
expect Coolify identity and permissions. Their provider migration is separate
operator/station work; app code must not bypass, impersonate, or disable those
gates. A self-reported commit and a green `/health` are insufficient deployment
proof. Require hosted CI, independent review, exact deployment/image identity,
trusted live checks, and the existing release reservation/hold handling on the
new target before moving the production domain.

Schedule the final transfer with writes and existing Beat/listener stopped,
verify the restored data and approved assets, then promote the new target and
run the trusted live journeys. Keep a verified recovery point. Once the new
target accepts writes, reverting DNS to the old database loses those new writes;
rollback then requires reconciliation rather than a blind DNS change.
