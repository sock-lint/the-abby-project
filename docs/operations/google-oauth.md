# Google OAuth registration

Prepared October 11, 2026; AI evidence updated October 17, 2026. The public pages are a reviewable draft until the
deployment owner approves their wording and publication. This runbook does not
claim Google approval or completed verification.

The [AI inventory and Google verification evidence](google-ai-disclosure.md)
records all runtime model calls, MCP exports, browser dictation and Google-data
flows, with official policy sources and unresolved operator evidence. Use it
alongside this registration checklist if Google asks about AI or third-party
processing; no verification message has been supplied, so confirm the actual
review in Verification Center rather than assume a separate AI certification.

## Application wiring

The Django application already handles Google's authorization-code flow with
PKCE and encrypted credentials. Set these private runtime variables in the
existing Coolify application, then deploy through the normal reviewed process:

| Variable | Value |
| --- | --- |
| `GOOGLE_CLIENT_ID` | The existing Google OAuth web client's ID |
| `GOOGLE_CLIENT_SECRET` | That client's secret; keep it out of source and logs |
| `GOOGLE_REDIRECT_URI` | `https://abby.bos.lol/api/auth/google/callback/` |

Compose passes them to Django and the Celery worker. Do not rotate an existing
client or create a replacement until its identity has been matched to the live
application. `GoogleAuthService.is_configured()` checks ID and secret presence;
also verify the redirect URI explicitly.

## Console checklist

Use the project's **Google Auth Platform** pages. The existing project under
review is `abby-project-493200`; match its web client to the deployed client
before changing any setting.

1. Enable the **Google Calendar API** in that project.
2. In **Clients**, use a **Web application** client with the exact authorized
   redirect `https://abby.bos.lol/api/auth/google/callback/`, including the final
   slash. This server flow does not require a browser JavaScript SDK origin.
3. In **Branding**, use **The Abby Project**, retain the owner's existing
   user-support and developer-contact emails, and configure the approved public
   home page `https://abby.bos.lol/about/` and privacy page
   `https://abby.bos.lol/privacy/`. Do not publish a personal support address in
   the repository. Add the authorized domain `bos.lol`.
4. Verify domain ownership in Google Search Console using an account that is
   an Owner or Editor of this Cloud project. Public links alone do not establish
   ownership.
5. In **Data Access**, declare the exact current scopes:
   `openid`, `https://www.googleapis.com/auth/userinfo.email`,
   `https://www.googleapis.com/auth/userinfo.profile`, and
   `https://www.googleapis.com/auth/calendar.events.owned`. Replace the older
   `calendar.events` declaration; the application now requests the narrower
   permission for the primary calendar and other calendars owned by the user.
   If the separate [Drive Picker](google-drive-picker.md) is configured, also
   declare `https://www.googleapis.com/auth/drive.file`; its separate browser
   grant does not add broad Drive access or a Gemini permission.
6. In **Audience**, choose the actual audience. For External / Testing, add
   intended Google accounts as test users. Testing and personally known limited
   users can have verification exceptions, warning screens, caps, and limited
   refresh-token lifetimes; consult Google's current rules. Do not equate
   switching to Production with verification.

The current code requests Calendar event permission during linking and every
Google sign-in, even when sync is off. An implementation that separates sign-in
scopes from opt-in Calendar authorization would require a separate reviewed
change and updated demonstrations. Do not describe the existing flow as
incremental authorization.

## Owner review before publication

- Confirm the privacy wording matches actual hosting, access, logging, backup,
  and retention practices. Server operators can administer stored data;
  encryption at rest does not make it inaccessible to operators. Adopt and
  enforce the stated Google-data access restrictions. A page alone cannot
  establish Limited Use compliance.
- Confirm actual AI recipients and provider-account restrictions. Selected
  Drive PDF text can go to Anthropic during import; saved imported text can
  later reach family OpenAI/Anthropic planning or authorized MCP clients. The
  public `/privacy/#ai` inventory discloses these paths, but publication does
  not establish timely consent, downstream provider terms or deletion. Follow
  the evidence/actions in [the AI disclosure record](google-ai-disclosure.md#submission-evidence-and-unresolved-operator-actions).
- Confirm the audience classification. Google's policy restricts Google
  Account OAuth in primarily child-directed apps; mixed-audience apps can
  provide optional Google integration when the app is usable without it.
  Password login keeps Abby's core features available without Google. Do not
  misrepresent the audience to obtain approval.
- Verify the Calendar family-boundary fixes and their regression checks are
  included in the approved release before demonstrating sync for multiple
  families. The proposed change scopes manual chore sync to the requesting
  child's family and assigned/shared duties, and checks project access for
  completed work sessions. Automatic chore sync and daily duty reminders use
  the chore's explicit family and exclude unapproved proposals. Previously
  created Calendar events are not removed
  automatically by that change. Review existing calendars and mappings for
  stale events, and remove unwanted events directly in Google Calendar.
- The requested `calendar.events.owned` scope supports writes to the user's
  existing primary calendar and other owned calendars. Read-only scopes cannot
  create or update events, and `calendar.app.created` would require changing
  the feature to use a separate app-created calendar. Calendars owned by
  someone else are outside the newly requested permission. Do not claim that
  the broader `calendar.events` scope is necessary for primary-calendar writes.
  Older grants may retain broader access: revoking at Google and reconnecting
  is required to remove those grants; deploying this change does not revoke
  them automatically.

## Verify the public pages and linking

After an approved release, anonymously load `/about/` and `/privacy/` with
JavaScript disabled. Confirm meaningful HTML, matching app identity, working
privacy and sign-in links, and no redirect to login. Inspect the actual content,
because Django's SPA fallback can return HTTP 200 for a nonexistent page.
Existing service workers must also allow these navigations to reach the server.

First-time account linking uses password sign-in → **Settings → Google account
→ Connect Google account**. Success says **Google account linked successfully.**
Sign out, then test **Sign in with Google** with that same Google identity.
Google sign-in does not create a family or match an unlinked account by email.

Calendar sync is off by default. With a permitted test account, enabling
**Enable calendar sync** allows deadline, chore, and work-session writes.
Confirm the corresponding event in the linked account's calendar and test
turning sync off. Avoid recording real private family information or tokens.

| Symptom | Check |
| --- | --- |
| Google button absent | Runtime ID/secret configuration and public config response |
| `redirect_uri_mismatch` | Exact web-client callback and runtime redirect |
| `access_denied` | Test-user list, Google consent choice, and Workspace controls |
| `No linked Google account found` | Link from Settings after password sign-in |
| `invalid_state` | Ten-minute state expiry, completed callback, and database availability |
| `token_exchange_failed` | Client/secret mismatch or provider availability; logs deliberately omit provider details |

## Google review remains separate

For public use that requires sensitive-scope verification, publish approved
branding and follow the project's **Verification Center** workflow. Prepare a
scope justification and an unlisted demonstration video showing the consent
screen, app name and client identity, first-time linking, Google sign-in,
Calendar opt-in, and the resulting app-created Calendar events. Explain why a
narrower scope does not meet the implemented feature. Provide reviewer access
instructions without exposing a real household's data. Domain verification,
branding review, and sensitive-scope review are distinct prerequisites; record
the actual console status rather than claiming approval from page deployment.
When Drive/AI is in review, also demonstrate the selected-file permission,
import notice and affirmative user action, reviewable draft, and any subsequent
assistant data flow. Removing sprite generation does not remove these text-AI
transfers or the Calendar permission review.

Official guidance, checked October 11, 2026:

- [OAuth production policy compliance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)
- [Sensitive-scope verification and exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)

Focused local validation:

```powershell
$env:SECRET_KEY = 'synthetic-test-key'
$env:DATABASE_URL = 'sqlite:///tmp_test.db'
$env:DJANGO_SETTINGS_MODULE = 'config.settings_test'
python manage.py test config.tests.test_public_pages config.tests.test_pwa_urls
python -m ruff check config/urls.py config/tests/test_public_pages.py
```


## Browser-bound return exchange

The server's Google authorization-code/PKCE flow and Calendar scopes are
unchanged. A separate browser proof now protects the return to Abby:

1. The browser generates a fresh random verifier with Web Crypto and stores it
   temporarily in sessionStorage, scoped to the API/client origin and captured
   Abby credential fingerprint. No DRF or Google token is stored with it.
2. `GET /api/auth/google/login/` (sign-in) or authenticated
   `GET /api/auth/google/` (linking, optionally `for_user=<child id>`) requires
   `code_challenge=<base64url SHA256(verifier)>` and
   `code_challenge_method=S256`. It returns `{authorization_url, state,
   expires_in: 600}`. Public `GET /api/auth/google/config/` returns
   `{configured}` without creating an authorization.
3. The callback atomically claims the hashed state once, exchanges Google's
   code outside database locks, and stages the encrypted result. It redirects
   to `/#google_exchange=<opaque ticket>&google_state=<state>`. Errors use
   allowlisted `google_error` values, never provider text. No GoogleAccount
   changes or DRF token issuance happen at callback time.
4. The browser removes the fragment before Sentry initialization and POSTs
   `{exchange_code, code_verifier}` to `/api/auth/google/exchange/`, with the
   exact initiating Abby token for authenticated flows. The server checks
   proof, expiry, fresh account/family/role state and revocations, then consumes
   the ticket atomically. A wrong proof does not consume the legitimate ticket.
   Login returns `{mode: "login", token, user}`; linking returns
   `{mode: "link", linked: true}`. Errors return HTTP 400 `{error, code}`.

The initial authorization expires after ten minutes; the return ticket expires
90 seconds after callback and never outlives that initial window. Replays fail.
The browser coalesces StrictMode completion and rejects results after account
switching or another authorization. It never automatically retries an uncertain
exchange POST: restart Google sign-in if the response was lost. A confirmed
link may already exist; review Settings before reconnecting. Legacy `?token=`
URLs are removed and never accepted as login credentials.

Logout/token revocation, password changes, deactivation/reactivation,
membership/role changes and Google unlink/relink fence pending authorizations.
Durable per-user invalidation timestamps also cover anonymous sign-ins whose
Google identity is unknown at initiation. User and family deletion remove
related pending authenticated flows; fresh checks prevent anonymous flows from
resurrecting deleted accounts. Application auth changes must use `User.save`,
normal token deletion and GoogleAuthService link/unlink; raw database updates
bypass model hooks and are not a supported revocation interface.

The locking order is ordered User rows (`NO KEY UPDATE`), initiating Token,
transaction, GoogleAccount. Password login/logout follow the same User/Token
order. Logout releases User before waiting for an in-flight push binding, then
revalidates its exact token under fresh User/Token locks. Exchange locks on
subordinate rows use NOWAIT so a concurrent legacy account cascade cannot
deadlock them. A changed authorization returns the safe
exchange error; competing ordinary auth mutations may return HTTP 409 and
roll back so they can be retried. Family IDs in the transaction are scalar
snapshots, not new Family foreign keys. Never hold these locks during a Google network request.

Transactions store only hashed state/tickets and encrypted provider material.
Claim, failure and successful consumption erase their previous encrypted
payload immediately. Celery Beat runs `prune_google_oauth_transactions` every
five minutes and erases at most 200 expired rows per run, including expired
90-second return payloads. A stopped worker or backlog can retain encrypted
expired material longer; expiry still rejects it immediately. Monitor the
existing Beat/worker health and expired-row backlog; operators may invoke the
same bounded task to drain it. Database backups can retain prior encrypted
rows under the operator's backup retention; this is not immediate backup
erasure. Invalidation rows live until user deletion. Initiation/exchange are
throttled at ten requests/minute and at most ten live transactions per caller.
Authenticated callers use their user ID. Anonymous callers use the transport
peer by default: forwarded headers cannot invent a new identity. Behind an
unconfigured reverse proxy, anonymous clients share that peer's bucket.
`GOOGLE_OAUTH_TRUSTED_PROXY_NETWORKS` may list explicitly verified proxy CIDRs;
only then does Google authorization walk X-Forwarded-For from right to left,
stopping at the first untrusted hop. Configure only proxies that replace or
append the actual transport caller, and include every trusted hop needed for
client attribution. Private address ranges receive no automatic trust. Missing,
malformed or oversized chains fall back to the transport peer. Other API
throttle contracts are unchanged.

A singleton database admission lock also limits **all retained transaction
rows to 1,000**, independent of IPs, headers, accounts and cache availability.
Spent and expired rows still count until bounded erasure removes them. At
capacity, initiation returns HTTP 503 `{error, code: "authorization_busy"}`
without storing another verifier. Completion of an existing flow is allowed.
An unavailable worker therefore stops new admission rather than allowing
unbounded retained rows. Monitor both the expired backlog and admission
capacity; do not raise the bound to conceal failed erasure.
OAuth error envelopes retain exception types and code coordinates but strip
request secrets, exception locals and provider messages. OAuth performance
traces are omitted.

Password login still rotates the user's one shared DRF token; Google sign-in
still reuses or creates that token. Logout revokes that shared credential, and
self password reset retains it as documented. Independent browser/device
sessions remain a separate migration. Drive's transient `drive.file` grant,
Picker referrer policy and upload workflows remain separate from sign-in and
Calendar credentials.

This return supports same-origin browser/PWA navigation. The client checks the
actual provider `redirect_uri` against its own origin, including when a dev
proxy hides a different backend origin. Packaged clients and cross-origin
returns fail with a useful message before leaving Abby; a native system-browser
return bridge and device acceptance remain separate work. No arbitrary return
URL is accepted.
