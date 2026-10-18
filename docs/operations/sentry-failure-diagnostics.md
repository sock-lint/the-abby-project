# API and Calendar failure diagnostics

These fields help investigate recurring failures using synthetic reproductions
and sanitized collector reports. They do not establish an incident's cause or
prove that it has been fixed, deployed or resolved.

## Successful responses with a non-JSON body

The shared API client adds `extra.responseDiagnostics` to its existing terminal
non-JSON error event and the same summary to its existing retry breadcrumb.
Fetch normally follows redirects, so a requested API route alone cannot identify
the final response's route. Each summary contains only:

| Field | Meaning |
| --- | --- |
| `redirected` | Boolean indicating a followed redirect, or `null` when unavailable. |
| `originRelation` | `same_origin`, `cross_origin`, or `unknown`, relative to the actual requested URL. |
| `pathRelation` | `same_path`, `other_api_path`, `other_path`, or `unknown`. |
| `responseType` | `basic`, `cors`, `default`, `error`, `opaque`, `opaqueredirect`, or `unknown`. |
| `serviceWorkerControlled` | Boolean indicating page control, or `null` when unavailable. |

The summary adds no final URLs, path values, query strings, headers, HTML,
credentials or worker script locations. A controlling worker does not prove it
handled the response. A redirect does not identify who issued it. Cross-origin
and path categories describe relationships, not the HTML's source.

The existing retry limit, fresh retry URL, no-store policy, authentication,
cancellation, error reporting and user-facing error remain in place. Existing
telemetry fields are unchanged; these new bounded fields do not authorize export
of raw legacy event data. See the [Fetch response definition](https://fetch.spec.whatwg.org/#responses).

## Google Calendar event writes

The existing `_upsert_event` exception log adds `google_calendar_failure`, with
the code-owned `insert` or `update` operation, a verified HTTP status when
available, and a fixed `reason` category. Classification accepts only a direct
Google Calendar HTTP error for the matching operation and bounded, consistent
structured response data. Unrecognized, conflicting, malformed, foreign or
unavailable evidence remains `unknown`; a database failure cannot borrow a
provider classification.

The initial reason allowlist follows the documented Calendar 403 reasons:
`userRateLimitExceeded`, `rateLimitExceeded`, `quotaExceeded` and
`forbiddenForNonOrganizer`. Other reasons remain unknown. The new summary does
not include provider messages, response bodies, URIs, calendar/event/user IDs or
credentials. Existing exception monitoring and mapping behavior remain in place;
no provider write is retried and no account setting is changed. The
[Google Calendar error guide](https://developers.google.com/workspace/calendar/api/guides/errors)
defines these categories; it does not identify an individual incident's cause.

## Collector and verification boundary

The central collector may expose these fixed fields through a separately
reviewed sanitized supplement. The loop inbox schema and validator are unchanged;
do not insert additional fields into that inbox by hand. Historical events lack
the new fields and retain their unknown classifications. Any incident fix still
needs a failing reproduction, regression checks, review, hosted CI, deployment
and the central resolver's independent proof before Sentry resolution.
