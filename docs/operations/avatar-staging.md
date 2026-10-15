# Isolated avatar staging

Use a separate Coolify application, the reviewed task branch, and
`/docker-compose.staging.yml`. Keep automatic and preview deployments disabled.
The existing main-branch application is production and is not a staging target.

The staging recipe creates its own PostgreSQL volume and Redis service. It
passes an explicit runtime environment, uses a distinct `abby_staging` database
and role, disables signup, discards outgoing email, and has no printer listener,
periodic scheduler, production storage credentials or host content mounts.
Do not copy the production environment or restore production data into it.
This reduced stack supports avatar/API acceptance; it does not establish
background-job or whole-application parity.

Configure `STAGING_DATABASE_PASSWORD`, `STAGING_SECRET_KEY`, `STAGING_HOSTNAME`
and `STAGING_ORIGIN` on that application, with both build-time and runtime flags
enabled. Coolify evaluates the entire Compose file even for its build command,
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
