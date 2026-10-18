# Google Drive file picker and uploads

Parents can choose Drive files in **Add Resource** on a project or its step.
Django verifies the selected file and fills the resource title, type, and link.
The parent can edit these fields before choosing **Add Resource**. A resource
link retains Google's sharing permissions; Abby does not make the file public
or grant family members access to it.

The resource picker also has an **Upload** tab. Parents can upload PDFs, photos,
and other files from their device directly to Google Drive and choose a
destination folder. Google handles the upload; Abby verifies the resulting
file's metadata and fills the resource form. The parent must still choose
**Add Resource** to save its link in Abby. Resource uploads do not copy file
contents into Abby or send them to the AI import provider. Access to the file
follows the Google account's Drive and destination folder permissions.

A completed upload can remain in Google Drive if the picker or resource form
is cancelled, the Abby account changes, or metadata verification fails. These
actions do not undo the Google upload. Remove unwanted uploaded files in Drive.

## Save files already stored in Abby

Parents can choose **Save a file from Abby** in **Memories → Gallery** or
in a project's **Add Resource** form. Choose an
imported PDF, project photo, approved homework proof photo, or creation photo,
then choose **Save to Google Drive** and confirm the destination Google account.
Abby sends a copy of that stored file directly to **My Drive**. No download to
the device is needed. The original remains in Abby, and this export does not
send the file to an AI provider or create a project plan PDF.

Imported PDFs are visible only to the parent who imported them; discarded
imports are excluded. Photos use their existing project and family access
rules. Resources that are only external links, videos, audio, and private
journal entries are not export sources. Each completed save creates a new
Drive copy under the chosen account's existing permissions. Abby does not
change sharing. In Add Resource, review the returned title/link and choose
**Add Resource** separately to attach it to the project.

Files must be valid PDFs or readable raster photos of at most 25 MB, including
JPEG, PNG, WebP, GIF, BMP, and TIFF. If the account
changes or a network error makes the result uncertain, a copy may already
exist in My Drive. Check Drive before saving again; Abby does not automatically
retry or remove a completed copy.

In **Auto-fill from Source → PDF**, **Import PDF from Google Drive** copies a
selected PDF into the existing import workflow. The parent reviews its plan
before creating a project. School worksheets use this same project review flow;
this version does not create homework assignments automatically. PDF title and
up to 12,000 characters of extracted text may be sent to Anthropic when
deployment AI import is enabled, as disclosed before selection and in
`/privacy/#drive` and `/privacy/#ai`. Processing runs during import, before the
review screen; choosing whether to apply suggestions does not prevent the
earlier transfer. Files must be genuine, downloadable PDFs of at most 25 MB.
Google Docs exports, folders, and shortcuts are not supported for PDF import.
This separate PDF-only picker selects existing files and has no Upload tab.

## Google review and AI disclosure

The [AI inventory and verification record](google-ai-disclosure.md) describes
recipients, all other AI features, downstream reuse, official sources and open
evidence. Google's current [Drive scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
classifies `drive.file` as non-sensitive. This avoids broad Drive access; it
does not by itself approve an application's use cases or downstream transfers.

The source form provides a shared notice for URL, local PDF and Drive import
before the explicit user action. It names Anthropic (Claude), the source title
and up to 12,000 extracted-text characters. It has no per-request AI opt-out or persisted provider-specific
consent record. Confirm that the actual disclosure and flow meet the review's
requirements before representing consent as verified. Imported project text
can later appear in idea/planning prompts or authorized MCP results; deleting
a Google connection does not retract those earlier disclosures.

The current [Workspace policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)
excludes backing up app/project content to Drive. The existing export feature
copies an individually chosen file in an educational workflow; ask Google to
confirm its eligibility rather than describing it as an approved backup
integration or assuming a narrower scope resolves that use-case question.
No Google approval, provider contract, retention period or completed security
assessment is established by these documents.

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
Uploads use the same `drive.file` grant, which allows creating files; existing
Drive picker deployments need no additional scopes or Cloud setup for uploads.

The journal SPA sends `Cross-Origin-Opener-Policy: same-origin-allow-popups` so
Google's authorization popup can communicate with its opener. It also sends
`Referrer-Policy: strict-origin-when-cross-origin` so website-restricted Picker
keys can verify the journal's public origin. Cross-site referrers omit private
SPA paths and query strings. Reverse proxies must preserve both headers,
including on 304 responses. API and admin responses keep their existing policies.
The HTML app shell declares the same referrer policy. Its content revision changes
with the policy so an existing PWA receives it through the normal app update.
Users must allow popups; an unavailable configuration or blocked SDK leaves
manual links and uploads available.

See Google's [Picker setup](https://developers.google.com/workspace/drive/picker/guides/web-picker-sample),
[upload view](https://developers.google.com/workspace/drive/picker/reference/picker.docsuploadview),
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
- `GET /api/auth/google/drive/sources/?source_type=...` lists authorized stored
  files in pages of 20. Types are `ingestion_pdf`, `project_photo`,
  `homework_proof`, and `creation_photo`. Rows contain `source_type`, string
  `source_id`, `title`, `mime_type`, and `context`; no storage paths or media
  URLs are exposed by this list.
- `POST /api/auth/google/drive/upload/` accepts exactly
  `{source_type, source_id, access_token}`. Django resolves the scoped record,
  reads and validates its stored file within the 25 MB limit, and creates a
  copy in My Drive through Google's fixed API host. It returns the existing
  verified resource metadata shape without storing the access token.
- `POST /api/projects/ingest/google-drive/` accepts the same parent-only selection.
  It verifies the remote MIME type, download permission, size, and PDF header,
  streams at most 25 MB from Google's fixed API host without following redirects,
  and saves a copied PDF plus its canonical source URL. Its response and
  review/commit behavior match normal PDF ingestion. Only the owning parent can
  access the staged job; normal family-scoped resource/project rules still apply.

The picker temporarily owns focus and Escape above an open resource form. The
underlying sheet's fields are retained and its dismiss actions are disabled
until the external interaction finishes. Returning restores the sheet's focus.

Unlinking Google does not remove files uploaded to Drive, copied PDFs, or saved
links. Uploaded files are managed in Google Drive. Discarding an import
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
upload a local file to a chosen Drive folder before explicitly saving its
resource link. Verify that cancelling the resource form leaves no Abby resource
and that a completed upload remains in Drive. Check that PDF-only import has no
Upload tab and imports into a draft without creating a project until confirmed.
School-managed accounts may need the institution to approve Abby's selected-file
access.
