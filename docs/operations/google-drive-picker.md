# Google Drive file picker

Parents can choose Drive files in **Add Resource** on a project or its step.
Django verifies the selected file and fills the resource title, type, and link.
The parent can edit these fields before choosing **Add Resource**. A resource
link retains Google's sharing permissions; Abby does not make the file public
or grant family members access to it.

In **Auto-fill from Source → PDF**, **Import PDF from Google Drive** copies a
selected PDF into the existing import workflow. The parent reviews its plan
before creating a project. School worksheets use this same project review flow;
this version does not create homework assignments automatically. PDF text may
be sent to the configured AI import provider, as disclosed before selection and
in `/privacy/#drive`. Files must be genuine, downloadable PDFs of at most 25 MB.
Google Docs exports, folders, and shortcuts are not supported for PDF import.

## Runtime setup

Use one Google Cloud project for the existing OAuth web client, Picker API key,
and app ID:

1. Enable **Google Picker API** and **Google Drive API**.
2. Add each journal origin to the OAuth client's authorized JavaScript origins.
   Local development uses `http://localhost:3000`; production uses its HTTPS origin.
3. Create a browser API key. Restrict websites to the journal origins and
   `https://docs.google.com/*`; restrict APIs to Google Picker API and Drive API.
4. Add `https://www.googleapis.com/auth/drive.file` to the OAuth consent
   configuration. Existing Calendar scopes remain unchanged.
5. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_PICKER_API_KEY`, and
   `GOOGLE_PICKER_APP_ID` in the deployment. The app ID is the **numeric Cloud
   project number**, not the project name or OAuth client ID. Compose passes
   these runtime values to Django; no frontend rebuild-only secret is needed.

The OAuth client and app ID must belong to the same Cloud project. Existing
Calendar/sign-in credentials remain separate from Drive selection. No new Drive
refresh token or client secret is sent to the browser. The API key, client ID,
and project number are public browser configuration.

The journal SPA sends `Cross-Origin-Opener-Policy: same-origin-allow-popups` so
Google's authorization popup can communicate with its opener. It also sends
`Referrer-Policy: strict-origin-when-cross-origin` so website-restricted Picker
keys can verify the journal's public origin. Cross-site referrers omit private
SPA paths and query strings. Reverse proxies must preserve both headers,
including on 304 responses. API and admin responses keep their existing policies.
Users must allow popups; an unavailable configuration or blocked SDK leaves
manual links and uploads available.

See Google's [Picker setup](https://developers.google.com/workspace/drive/picker/guides/web-picker-sample),
[selected-file scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
and [authorization library guidance](https://developers.google.com/identity/oauth2/web/guides/load-3p-authorization-library).

## Authorization and API behavior

The button preloads the SDK before enabling the user action, then opens Google
Identity Services directly from the click. It requests `drive.file` with
`include_granted_scopes: false` and verifies that the scope was granted. The
access token stays in memory until the selected operation completes, is
cancelled, or the Abby session changes. It never enters browser drafts,
GoogleAccount, database rows, Abby navigation URLs, or Celery messages. Sign-in/Calendar token
handling is unchanged.

- `GET /api/auth/google/drive/config/` returns public `{configured, client_id, api_key,
  app_id}` without requiring sign-in. Missing configuration returns false and
  empty values. Client secrets are never returned.
- `POST /api/auth/google/drive/file/` accepts `{file_id, access_token,
  resource_key?}` from a parent. It returns verified `{id, title, url, mime_type,
  resource_type}` with an existing resource type (`doc`, `image`, `video`, or
  `link`). The file ID and optional link-sharing resource key are validated;
  the canonical Google link is constructed by Django.
- `POST /api/projects/ingest/google-drive/` accepts the same parent-only selection.
  It verifies the remote MIME type, download permission, size, and PDF header,
  streams at most 25 MB from Google's fixed API host without following redirects,
  and saves a copied PDF plus its canonical source URL. Its response and
  review/commit behavior match normal PDF ingestion. Only the owning parent can
  access the staged job; normal family-scoped resource/project rules still apply.

The picker temporarily owns focus and Escape above an open resource form. The
underlying sheet's fields are retained and its dismiss actions are disabled
until the external interaction finishes. Returning restores the sheet's focus.

Unlinking Google does not remove copied PDFs or saved links. Discarding an import
uses the existing soft-discard behavior and retains its file; deployment
operators must handle file and backup retention through their existing policy.

## Validation

Backend tests in `apps/google_integration/tests/test_drive.py` and
`apps/ingestion/tests/test_google_drive.py` cover permissions, canonical metadata,
resource keys, invalid/revoked access, bounded downloads, copied-file ingestion,
and secret nonstorage. `config/tests/test_drive_popup_policy.py` checks the SPA
opener and referrer headers on 200 and 304 responses, and the unchanged private
API/admin policies. Synthetic public config and metadata
fixtures live in `contracts/api/fixtures/google-drive-*.json`; React and Django
verify these responses together. Unity consumes neither new parent-only endpoint;
its shared endpoint fixtures remain unchanged.

Frontend SDK/button tests mock Google with synthetic tokens; page tests verify
actual resource/import POST routes and bodies. Run frontend lint, tests, and
build plus the Google/ingestion/project backend suites with test settings.
Live verification requires configured Cloud credentials: select a PDF, cancel
and retry, attach to a project/step, open with an authorized Google account, and
import into a draft without creating a project until confirmed. School-managed
accounts may need the institution to approve Abby's selected-file access.
