# Isolated avatar staging

Use a separate Coolify application and the reviewed task branch. The base
`docker-compose.staging.yml` has no public route. Protected hosting opts into
`docker-compose.staging-cloudflare.yml`, which extends that same recipe.
Keep automatic and preview deployments disabled.
The existing main-branch application is production and is not a staging target.

The staging recipe uses an isolated PostgreSQL volume and Redis service. It
passes an explicit runtime environment, uses a distinct `abby_staging` database
and role, disables signup, discards outgoing email, and has no printer listener,
periodic scheduler, production storage credentials or host content mounts.
Do not copy the production environment or restore production data into it.
This reduced stack supports avatar/API acceptance; it does not establish
background-job or whole-application parity.

Configure `STAGING_DATABASE_PASSWORD`, `STAGING_SECRET_KEY`, `STAGING_HOSTNAME`,
`STAGING_ORIGIN` and `STAGING_POSTGRES_VOLUME` on that application, with both
build-time and runtime flags enabled. Coolify evaluates the entire Compose
file even for its build command,
so those interpolation values must exist at both stages. Each Docker `RUN`
explicitly scopes its secret mounts; the staging signing/database keys never
enter dependency installation or Vite. Generate fresh random secret values;
use a password containing only URL-safe characters for the database URL.
`STAGING_HOSTNAME` is a hostname without a scheme and `STAGING_ORIGIN` includes
the scheme. Use HTTPS for native device testing. The same seven dedicated
read-only shared-asset build secrets described in
[shared-avatar-assets.md](shared-avatar-assets.md) supply Archer. Enable
BuildKit secret mode and use a fresh build when verifying reader credentials.
Do not copy unrelated production build inputs. Public CI images remain free
of purchased artwork.

## Protected HTTPS origin

Before publishing the staging hostname, protect the whole hostname with
Cloudflare Access, including health, API and static asset paths. Enable the
tunnel route's Access JWT enforcement (`originRequest.access.required`, the
correct team name and application audience) as well. An edge Access policy
alone does not protect a directly reachable origin.

Use Coolify raw Compose mode and preserve the repository so the extended base
file remains available. On the staging application only, set
`is_raw_compose_deployment_enabled=true` and
`is_preserve_repository_enabled=true`, and select
`/docker-compose.staging-cloudflare.yml`. Keep BuildKit secret mode enabled,
automatic/preview deployment disabled and automatic network connection disabled.
Coolify 4.1.2 normal Compose mode injects its shared runtime `.env` into every
service, including Redis. Raw mode is required to keep signing and database
credentials scoped to the explicit service environments. The opt-in recipe
declares only the eight build secrets needed for the shared reader and disabled
signup. It supplies no runtime secrets mounts. Preserve Coolify's generated
`SOURCE_COMMIT`; do not replace it with an operator-maintained commit setting.
The environment map intentionally inherits this value through a null entry.
A `${SOURCE_COMMIT:-unknown}` default makes Coolify's pre-build parser register
an `unknown` user setting, which suppresses the generated runtime commit. When
migrating that earlier recipe, verify and remove only that automatically created
`unknown` row; do not replace it with a manually maintained SHA.

For the approved `abby-staging.bos.lol` hostname, remove the old LAN hostname
from the staging application's domain metadata rather than retaining an alias.
Set
`STAGING_HOSTNAME=abby-staging.bos.lol` and
`STAGING_ORIGIN=https://abby-staging.bos.lol`, keeping the existing flags and
`is_literal=false`. The tunnel sends this exact hostname to host loopback
HTTP port 80; Cloudflare terminates public HTTPS. The opt-in recipe explicitly
defines one HTTP router for that exact Host and all paths, forwarding to Django
port 8000. Only Django joins the external `coolify` proxy network; PostgreSQL
and Redis remain on the private application network. No host port is published.
Do not add another HTTP, HTTPS or LAN alias.
The protected recipe uses the private-only `abby-staging-db` and
`abby-staging-redis` network aliases in its database, cache and broker URLs.
Generic `db` or `redis` names can resolve to another service on Django's joined
proxy network. After deployment, resolve the configured aliases from inside
Django and compare them with the exact staging PostgreSQL/Redis private IPs.
Never supply another project's credentials to work around an alias collision.

Before migrating the existing application to raw mode, record its exact Compose
project and PostgreSQL volume, and save a private `pg_dump --format=custom`
recovery file with mode 0600, a hash and a successful `pg_restore --list` check.
Set `STAGING_POSTGRES_VOLUME` to the verified existing volume. The opt-in recipe
requires that external volume and cannot silently create a different database.
The current native application's volume uses `staging-postgres` with a hyphen;
the source volume key uses an underscore. Preserve the same Compose project
and service identities, stop the old staging services before starting their
replacements, and verify no second PostgreSQL process mounts that volume.
Keep the four synthetic identities and saved avatar choices intact.

The staging Compose labels restrict every routed path to the verified
`10.0.1.1/32` transport peer. On this host, cloudflared uses host networking
and connects to `127.0.0.1:80`; Docker's IPv4 proxy reaches Traefik from that
gateway. Direct LAN IPv4 has a different peer, and the native IPv6 proxy
uses a different IPv6 gateway. This restriction trusts privileged processes
on the host as well as cloudflared. Recheck the actual socket peer after a
proxy, network or host change; do not widen the rule to a Docker subnet.

Keep the default IP strategy. A forwarded-header depth or excluded-IP rule
could let a client-supplied header select the allowed address. After the
peer gate, staging sets canonical forwarded HTTPS, host and port headers
and removes `Forwarded`. Django already uses forwarded HTTPS and host.
Keep global proxy trust unchanged, and do not copy `CF-Connecting-IP` into
authorization or throttling state. The explicit router puts the origin gate
before the header middleware. Inspect the finished router and actual service
environment names; source recipe tests cannot detect a hosting platform's
additional runtime environment injection.

Before accepting the new route, check the whole boundary:

- Anonymous public requests, including a paid asset URL, must hit Access.
- The allowed Access identity must reach the app and complete Abby login,
  avatar selection and saved-profile reload in an HTTPS secure context.
- Direct LAN IPv4 and reachable IPv6 requests with the canonical Host must
  return 403, including attempts with forged forwarded IP, Cloudflare IP
  and Access assertion headers. No published container port may bypass Traefik.
- The former LAN hostname must not return Abby health JSON or the actual pinned
  asset bytes. The shared proxy's unrelated error-page fallback can return 200;
  check content type, GLB magic and the expected hash rather than status alone.
- Record the deployment commit, generated router and middleware definitions,
  the distinct staging application identity and the preserved database state.
  PostgreSQL must receive only its own database credentials, Redis no app
  secrets, and Django no reader credentials or unrelated production keys.
  Header configuration and a browser pass do not establish physical-phone
  or native Access readiness.

The app migrates its fresh database and loads the authored content catalog.
Provision the four synthetic identities once with
`scripts/operations/provision_avatar_staging.py` through `manage.py shell` stdin.
Provide four distinct random passwords of at least 24 characters through
`ABBY_STAGING_PARENT_PASSWORD`, `ABBY_STAGING_CHILD_PASSWORD`,
`ABBY_STAGING_OTHER_PARENT_PASSWORD`, and `ABBY_STAGING_OTHER_CHILD_PASSWORD`.
Keep those values in local operator secrets; never put them in command
arguments, repository files, build layers or logs. The script refuses a
populated user table and refuses database settings outside the staging recipe.
It creates `stage-parent`, `stage-child`, `stage-other-parent` and
`stage-other-child` in two synthetic families without emitting tokens.

Acceptance must record the finished deployment's exact commit, the matching
public `/health` commit, and the distinct staging application/container identity.
The existing health middleware deliberately exposes `resourceUuid` only for the
canonical production application; its absence on staging is expected. Do not
weaken the production observer's target checks to use it against staging.

On the actual staging Profile page, verify authentication, default appearance,
saved choices after reload/login, equipment add/remove, complete Jump playback,
pause/reduced motion and graceful error handling. Verify another family cannot
read or change those choices. Desktop browser checks do not establish phone
performance or native installation readiness; real device acceptance remains
separate.

The effective recipe isolation check uses synthetic configuration only:

```sh
python -m unittest discover -s scripts/operations -p test_staging_recipe.py -v
```
