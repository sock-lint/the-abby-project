# Google OAuth registration

Prepared October 11, 2026. The public pages are a reviewable draft until the
deployment owner approves their wording and publication. This runbook does not
claim Google approval or completed verification.

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
   `https://www.googleapis.com/auth/calendar.events`.
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
- Review whether the requested scope is the narrowest suitable one. The current
  implementation writes to an existing primary calendar and maps app-created
  events; do not justify the scope with features the app does not implement.

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
| Google button absent | Runtime ID/secret configuration and login-init response |
| `redirect_uri_mismatch` | Exact web-client callback and runtime redirect |
| `access_denied` | Test-user list, Google consent choice, and Workspace controls |
| `No linked Google account found` | Link from Settings after password sign-in |
| `invalid_state` | Ten-minute OAuth state expiry and shared Redis cache |
| `exchange_failed` | Client/secret mismatch or Google exchange logs; redact credentials |

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
