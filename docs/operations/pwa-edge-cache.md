# PWA worker delivery and edge cache policy

This document records the October 10 diagnosis and the release safeguards
added after the October 16 recurrence. Provider policy is managed separately
through the homelab's fixed-zone `cloudflare-abby-delivery` Swamp model; a
source file alone is not proof that a rule is installed.

## October 10 observations

On October 10, 2026, around 13:09 Phoenix time (20:09 UTC), unauthenticated
requests to `https://abby.bos.lol` showed the following. The direct Django
container and local HTTP Traefik router were also probed with the same Host.

| Resource | Django and local HTTP proxy | Public response |
| --- | --- | --- |
| `/sw.js` | `Cache-Control: no-cache` | `max-age=14400`, `CF-Cache-Status: REVALIDATED`, no Age |
| `/push-sw.js` | No Cache-Control | `max-age=14400`, `HIT`, Age increasing from 2788 to 2955 seconds |
| `/static/assets/index-ndmBM9MX.js` | `max-age=60, public` | `public, max-age=14400`, `REVALIDATED` |
| `/` and `/index.html` | SPA revalidation policy | `no-cache`, `DYNAMIC` |

GET, HEAD, and conditional 304 requests carried the same script policies at
each layer. A unique query-string request for `/sw.js` returned `MISS` with the
same four-hour header. Script bytes matched across Django, Traefik, and the
public endpoint:

```text
sw.js       26b6b86685ca53dae0ace3d845cbeb5b8fa2eb9a38be96512c4f20fe05add812
push-sw.js  314626026e2a3f9c1f0dc65013170bcd099c795ca60faa3ed61b871a75ff7a20
```

The header rewrite occurs downstream of Django and the local HTTP proxy.
WhiteNoise handles `/static/`, so it does not set headers on the root worker.
There is no tracked Cloudflare configuration or proxy header override in this
repository. `/registerSW.js` currently returns 404 because the production build
does not emit it; the route remains available for builds that do.

Cloudflare's default Browser Cache TTL is four hours and can raise a shorter
origin TTL. This is consistent with the observed rewrite. The exact zone
setting or matching rule is **unverified**: no connected Cloudflare plugin was
available and the dashboard was signed out during this investigation.
[Cloudflare TTL documentation](https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/)

`max-age=14400` is a browser-facing lifetime, not proof of a four-hour edge
freshness interval. The repeated `REVALIDATED` responses show `/sw.js` being
validated at the edge; increasing `HIT` Age shows `/push-sw.js` being served from
stored edge content. [Cache response meanings](https://developers.cloudflare.com/cache/concepts/cache-responses/)
Cloudflare may store and always revalidate an origin `no-cache` response when
Origin Cache Control is enabled. [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)

Default service-worker `updateViaCache: 'imports'` bypasses the browser HTTP
cache for the main worker's update check but permits it for imported scripts.
The unversioned push import therefore has the clearest stale-script risk; these
observations do not establish that every main-worker update waits four hours.
[Chrome service-worker update documentation](https://developer.chrome.com/blog/fresher-sw)

## Origin and provider policy

The origin now gives all four stable PWA script routes:

```http
Cache-Control: no-cache, max-age=0, must-revalidate
Cloudflare-CDN-Cache-Control: no-store
```

The policy is applied after Django's static view returns, including HEAD and
304 responses. The Cloudflare-specific header separates edge storage from
browser caching, but an overriding provider rule can still take precedence.
[CDN header precedence](https://developers.cloudflare.com/cache/concepts/cdn-cache-control/)
Icons, manifests, hashed assets, API routes, and service-worker CacheStorage
behavior are outside this origin change.

Two **individual rule bodies** are supplied in `infra/cloudflare/`:

| File | Zone entry-point phase | Effect |
| --- | --- | --- |
| `pwa-cache-bypass.rule.json` | `http_request_cache_settings` | Makes the four scripts ineligible for edge caching |
| `pwa-cache-headers.rule.json` | `http_response_headers_transform` | Sets the browser revalidation header and removes Expires |

Both match only `abby.bos.lol` and the exact `/sw.js`, `/push-sw.js`, `/privacy-sw.js`, and
`/registerSW.js` paths. Query strings are covered because the expression uses
`uri.path`. The separate response transform is deliberate: changing response
headers alone does not change Cloudflare's earlier edge-cache decision.
[Transform limitations](https://developers.cloudflare.com/rules/transform/response-header-modification/)

## Applying or repairing the scoped provider policy

1. Inspect the `bos.lol` Browser Cache TTL, matching Cache Rules, legacy Page
   Rules, Cache Response Rules, response transforms, and Worker routes. Record
   the responsible override and the current rule IDs/order for rollback.
2. Add or update the narrow exception in each relevant zone phase. Place it
   after conflicting broader rules and confirm the effective settings for each
   script with Cloudflare Trace. Later matching Cache Rules win conflicts.
   [Rule priority](https://developers.cloudflare.com/cache/how-to/cache-rules/order/)
3. The JSON files are single-rule request bodies for an existing phase ruleset,
   not full ruleset replacements. The individual add endpoint is
   `POST /zones/{zone_id}/rulesets/{ruleset_id}/rules` and appends by default.
   Preserve other rules; do not PUT these files as an entire ruleset. If the
   phase has no entry-point ruleset, create the equivalent rule in the dashboard.
   [Individual add API](https://developers.cloudflare.com/ruleset-engine/rulesets-api/add-rule/),
   [header action schema](https://developers.cloudflare.com/rules/transform/response-header-modification/reference/parameters/)
4. Deploy the tested origin change through the normal release process only
   when authorized. If a purge is needed, scope it to these script URLs.

After application, repeat GET, HEAD, query-string, and Last-Modified conditional
requests against the direct origin and public endpoint. Existing scripts should
return JavaScript with the revalidation header on both 200 and 304; the public
edge should return `DYNAMIC` or `BYPASS` without increasing cache Age, rather
than HIT, REVALIDATED, or a four-hour max-age. Compare body SHA-256 hashes.
An un-emitted registration script should remain 404. Also verify an ordinary
hashed asset retains its intended caching policy and the SPA still loads.

Existing browser HTTP cache entries cannot be remotely purged and may retain
their old lifetime until expiration. Do not promise immediate recovery for
previously cached imported scripts. Rule removal and restoration of any edited
rules use the recorded IDs/order; reverting the origin commit restores its
previous headers.

## Local validation

```sh
python manage.py test config.tests.test_pwa_urls config.tests.test_pwa_delivery config.tests.test_middleware --noinput --verbosity=2
```

The route-only suite uses synthetic build files and no database setup. It
checks script bodies and MIME types, both headers on GET/HEAD/query/304
responses, missing-script 404s, and unchanged manifest/icon headers. A focused
pull-request workflow runs these checks with Python 3.12 and production settings;
it contains no build, deployment, or provider-write step.


## CI/CD release gate

After Coolify finishes the exact current-main commit, the existing deployment
helper requires `/health` to advertise SHA-256 and byte length for `/sw.js`,
`/push-sw.js`, and `/privacy-sw.js` from that serving image. These public hashes
contain no credentials or private asset data. Missing or unreadable runtime files
omit the entire manifest; ordinary container liveness remains available, but the
release cannot pass. Each read is bounded to 2 MiB and rejects symlinks.

The helper fetches those exact URLs with no query string, credentials, redirects,
or ambient proxy. Each response must be HTTP 200 JavaScript, match both the
runtime hash and byte count, require browser revalidation (or no-store), and
have no positive Age or cache lifetime. Cloudflare `HIT`, `REVALIDATED`, `MISS`,
`STALE`, and similar storage states fail; `DYNAMIC` or `BYPASS` are accepted.
A final health read must still identify the same build and manifest. Invalid
public delivery may recover within the existing two-minute verification window;
a finished container alone never establishes release success.

Prevention belongs in the narrow provider bypass and the origin response policy.
A purge is recovery for an existing edge entry, not the normal proof of a valid
release. The Cloudflare token stays in the operator's encrypted homelab vault;
the app deployment job needs no new provider secret or broad cache permissions.
The station's trusted native live gate can use the same anonymous manifest proof
after ordinary deployments and asset rebuilds, including rebuilds at the same
commit. That observer update must be installed after this manifest is deployed.

The existing real-browser A-to-B release test remains responsible for worker
activation, offline behavior and unsaved-draft protection. Header/hash checks
complement that browser test; they do not authorize forcing a reload over edits.
