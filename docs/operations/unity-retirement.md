# Unity retirement and React replacement

The owner authorized immediate retirement on October 12, 2026 because no one
is using the application. React remains the product UI, with optional R3F
companion presentation and Capacitor development packaging. The
[roadmap](../superpowers/plans/2026-10-12-r3f-capacitor.md) records later native
session, integration, device and distribution gates.

## Active client and release changes

Unity build/deploy/readiness/browser-bridge jobs are removed from active
workflows. React lint, coverage, web/native staging builds and real Django/React
response fixture checks replace the licensed editor dependency. Shared fixture
bodies are retained; no reward or ownership contracts change.

GitHub's strict `main` status-check protection was updated to require
`Frontend validation` and `API fixtures` from GitHub Actions. The retired Unity
and browser-bridge requirements were removed; other protections were preserved.
GitHub's automatic merged-branch deletion remains enabled.

`UNITY_WEB_RELEASE_ENABLED` and `UNITY_VALIDATION_RUNNER_ENABLED` were set to
`false` so the old workflow on `main` cannot rebuild/redeploy the retired client
before this PR merges. The last main deployment was already complete. Other
application release flags, private input pointers and signing/deployment
credentials were preserved.

React `/play/*` bookmarks and Django `/play`, `/play/` and nested links resolve
to the pet collection. Django drops obsolete query parameters. `/profile` and
`/pets` aliases lead to existing `/sigil` and `/bestiary` routes. Meadow links
stay in React. These repository redirects become live with the platform release.

## Hosted service retirement

The separate Coolify resource `abby-unity-web`
(`k137wrcpgc4l0i234jf2adm2`, server ID 0) was stopped on October 12, 2026 through
the installed `App\Actions\Service\StopService` action. Before stopping it,
the Docker daemon identity and exact resource name were checked, along with
its single `unity-web` application and absence of databases. Network deletion
and Docker cleanup were disabled. The resource, configuration, image archives
and private assets remain available for recovery.

Verification found no running container for that resource. The main public
`/health` returned `status=ok`, `db=up`; `/play/` returned the React shell without
`createUnityInstance`. Until the new platform release, the old React bundle
does not yet contain the new bookmark redirect. No unrelated application,
database, printer listener, VM or backup was stopped or removed.

The retained [hosting](../unity-web-hosting.md),
[release](unity-web-release.md) and [runner](unity-pr-validation.md) documents
are historical recovery references, not active operating instructions. Do not
dispatch old Unity release workflows or restart the resource as part of normal
application deployment.

## Source and purchased art

The `unity/AbbyCamp` reference tree is retained. Original Meshtint sources,
licensed scene, import records and purchase/license evidence remain private
and unmodified. The [asset review](../../content/rpg/react-three-fiber-assets.md)
governs conversion, exact identity bindings and runtime delivery. Converted
GLB outputs are ignored private build inputs; public source checkouts retain
working 2D controls and artwork fallback.

Deleting Unity reference source, old images, private archives or the runner VM
is separate storage cleanup. Retirement does not require discarding recovery
material. React profile/pet actions remain server-backed, and greetings/3D
animation never create rewards.
