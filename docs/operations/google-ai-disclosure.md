# AI inventory and Google verification evidence

Reviewed October 17, 2026 against the application source and the official Google
sources linked below. This is a preparation record, not a finding of compliance
or Google approval. The applicable review has not been confirmed. This record
starts with the existing Google OAuth, Calendar and Drive integration. Confirm
the actual request in Google Auth Platform → Verification Center before
submitting. Google Play, Workspace Marketplace and Gemini API reviews are
different processes; this record does not establish that any of them applies.

## Which Google review applies

| Review | Relevance to Abby | Evidence to obtain |
| --- | --- | --- |
| OAuth branding | App identity, public home/privacy pages and domain ownership | Published Branding status, approved domain and matching production client |
| Sensitive-scope verification | Calendar event access; confirm the exact classification in Data Access | Scope justification and a demonstration of each requested permission |
| Selected-file Drive access | `drive.file` is non-sensitive; it supports user-selected files and new files without broad Drive access | Actual requested scopes, Picker selection and operations demonstrated |
| Restricted-scope verification/security assessment | Broad Drive scopes such as `drive` and `drive.readonly` would change this requirement; they are not requested by this code | Exact deployed scope list and Google's determination, rather than assuming AI processing itself triggers an assessment |
| AI/third-party data-use questions | The selected-Drive-PDF import can send document text to Anthropic; saved data can subsequently reach other AI paths | Data-flow inventory, timely consent, provider agreements, retention/deletion evidence and restricted downstream use |
| Workspace agent/API policy audit | Google's 2026 agent-tools guidance reserves policy-verification/audit requests separately from its usage quotas | Check the actual notice; Abby's own MCP server is not Google's Workspace MCP service |

Google separates [branding review](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
from [sensitive-scope review](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification).
Its [Drive scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
classifies `drive.file` as non-sensitive and broader Drive scopes as restricted.
[Restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
can require an independent security assessment when restricted data passes
through servers, subject to applicable exceptions. Non-sensitive access does
not remove privacy, consent or appropriate-use obligations.
Google's [agent tools and API safety guidance](https://developers.google.com/workspace/tools-safety)
also describes possible user-data-policy audits and separate quota changes. Its
existence does not establish that Abby has received such a request or needs a
paid quota increase.

## Complete application AI inventory

These are the direct model calls and assistant interfaces found in the reviewed
source. Whether a provider is enabled in production must be confirmed by the
operator without exposing credentials. The application does not itself train or
fine-tune models. That observation does not prove how external providers handle
requests under the actual account's agreements and settings.

| Feature and trigger | Recipient and data sent | Result, persistence and controls | Code evidence |
| --- | --- | --- | --- |
| Project ideas: Projects requests suggestions when the page loads | Deployment-configured Anthropic model; completed project titles, categories and difficulty, skill names/categories/levels, available categories | Suggestions are returned to the browser; curated suggestions are the fallback. No separate AI opt-in on each page load | `apps/projects/suggestions.py`, `apps/projects/views.py::ProjectSuggestionsView`, `frontend/src/pages/Projects.jsx` |
| URL/PDF import enrichment: parent starts an import | Deployment-configured Anthropic model; source title, available categories and up to 12,000 characters of extracted Markdown. This includes a selected Google Drive PDF's text when AI import is enabled | Suggestions saved in the parent's staged import alongside source/extracted content; parent reviews before project creation. Applying suggestions is optional, but processing is attempted before that review | `apps/ingestion/views.py`, `apps/ingestion/pipeline/enrich.py`, `apps/ingestion/pipeline/pdf.py`, `frontend/src/pages/ingest/SourceStep.jsx` |
| Homework planning: parent or an eligible child chooses to plan an assignment; an authorized MCP client can invoke the same service | Family-selected OpenAI or Anthropic model; homework title, subject, effort level, due date and up to 4,000 description characters | Creates a linked schoolwork project, milestones, steps and materials. This flow saves the plan directly; it does not use the separate project-draft review | `apps/homework/services.py::plan_assignment`, `apps/homework/ai_settings.py`, `apps/mcp_server/tools/homework.py` |
| Project plan assistant: parent requests a new plan or additional items | Family-selected OpenAI or Anthropic model; title (200 characters), description (10,000 characters), difficulty, guidance and optional existing plan. Context is bounded to 10 milestones, 40 steps and 40 materials, including text and task completion flags | Returns a validated draft. Parent reviews and explicitly saves; a request alone does not append items. Saved prices, payment state and reward authority are not included in the model context | `apps/projects/planning.py`, `apps/projects/planning_serializers.py`, `apps/projects/views.py` |
| MCP: external assistant's authorized tool requests | The chosen external client receives the tools' authorized arguments/results. This can include project/homework text, resources, family progress, photos and permitted journal/reflection content; role, family and private-entry restrictions still apply | Reads export data to that client; writes execute application services. Abby's own model API key is not required for ordinary MCP tools. The external client chooses its model, downstream storage and conversation controls | `apps/mcp_server/server.py`, `apps/mcp_server/auth.py`, `apps/mcp_server/context.py`, `apps/mcp_server/tools/`, `apps/mcp_server/CLAUDE.md` |
| Journal voice dictation: author starts the microphone | Browser's Web Speech recognition implementation; microphone audio for transcription. The code does not force on-device processing or select a named speech provider | Final transcript is placed in the journal draft and saved as text only when submitted; Abby has no audio-upload/storage path in this hook. Browser/service processing and retention must be assessed separately | `frontend/src/hooks/useSpeechDictation.js`, `frontend/src/pages/yearbook/JournalEntryFormModal.jsx` |
| Prepared artwork and existing sprites | No runtime image-model call; app displays supplied assets, imported artwork and existing catalog files | AI sprite/image generation and rerolling have been removed. Existing stored artwork is retained; an asset's historical provenance is a separate record | `apps/rpg/content/sprites.py`, `content/rpg/react-three-fiber-assets.md` |

PDF extraction (`pdfplumber`), HTML-to-Markdown conversion, predefined project
fallbacks, rule-based recommendations, reward/XP calculations and R3F rendering
are ordinary parsing, rules or rendering in this implementation. No LLM judges
homework proof images, grants rewards, or replaces Django's authorization checks.
External development assistants and the station's code-review tooling are not
user-facing runtime model calls; their use is not evidence that they receive
production Google or family data.

MCP content authoring now separates global catalog reads (`mcp:catalog`),
private drafts/asset briefs (`mcp:author`), runtime publication (`mcp:publish`)
and household reads/writes. Database content drafts, paired progression simulations and textual editorial drafts use these same independent grants. Catalog-only access excludes household records. Reading corrections and RPG management return only authorized household records; their services recheck current membership under locks. These deterministic tools call no new model provider.
Challenge, reward-audit and scenario tools execute deterministic application
code; the connected external assistant may receive their permitted results.
Asset proposals can be exported as reviewed JSON for an external creation
pipeline. Abby records a brief or delivery reference without making a new
LLM/image-provider call, uploading artwork or asserting publication approval.
See [the MCP authoring/data workflow](mcp-authoring.md). These permissions do not
establish consent for subsequent use of Google-derived content in an external
conversation or asset pipeline.

## Provider configuration and request behavior

All four direct text-generation paths use `config/llm.py::complete_json`:

- Deployment suggestions/enrichment use `LLM_BACKEND=auto|anthropic|none`,
  `ANTHROPIC_API_KEY` and `CLAUDE_MODEL`. With a key and an allowed backend,
  the default model is `claude-haiku-4-5-20251001`. `LLM_BACKEND=none` disables
  these two paths. This deployment setting does not disable family planning or
  external MCP clients.
- Family planning requires the family's saved provider, explicit model ID and
  encrypted API key. There is no deployment-key fallback. Parents can remove
  the connection in Settings → Planning AI; this stops new family planning
  calls but does not delete existing plans or disable deployment features.
- OpenAI uses `https://api.openai.com/v1/responses`, with `store: false`, no
  application-maintained conversation, a 120-second timeout and no redirect
  following. `store: false` is not a promise of zero provider retention.
- Family Anthropic requests use the Messages API at the fixed
  `https://api.anthropic.com` base with a 120-second timeout and no SDK retries.
  Deployment Anthropic uses SDK defaults, which can honor the deployment's
  proxy/base-URL configuration. Record that actual recipient before submission;
  do not assume the deployment necessarily uses the family endpoint.
- Output budgets are 1,024 tokens for ideas, 2,048 for enrichment and 8,192 for
  each family planner. No image-generation provider or Gemini key is needed.

Google credentials are not included by these prompt builders. User-written
content may nevertheless contain names, school information or other personal
information. No automatic personal-data redaction is implemented here.

## Google scopes and data flows

The exact sign-in/Calendar request in `apps/google_integration/services.py` is
`openid`, `https://www.googleapis.com/auth/userinfo.email`,
`https://www.googleapis.com/auth/userinfo.profile` and
`https://www.googleapis.com/auth/calendar.events.owned`. The separate browser
Picker grant requests `https://www.googleapis.com/auth/drive.file`; no Gmail,
broad Drive or generative-AI scope is requested. Compare these to both the
deployed requests and Console declarations, including legacy grants.

| Google-related path | Storage and sharing | AI relevance |
| --- | --- | --- |
| Sign-in/linking | Verified Google subject and email; encrypted access/refresh credentials, expiry/scopes in `GoogleAccount` | No direct LLM input from this integration |
| Calendar sync | Abby writes project/chore/work-session details; stores created-event mappings; sync off by default | Does not import unrelated Calendar events into prompts. Linking/sign-in currently requests Calendar permission even when sync is off |
| Choose/upload a Drive resource | Reads selected-file metadata and saves title/type/canonical link only after Add Resource. Local Picker upload goes directly to Google | Resource selection/upload does not invoke enrichment or send the file bytes to an LLM. Saved titles/links can be returned by authorized MCP tools |
| Import a selected Drive PDF | Parent-only `POST /api/projects/ingest/google-drive/`; reads selected metadata and at most 25 MB of PDF bytes; stores copied PDF, canonical source URL, extracted text and staged result | When deployment AI is enabled, title and bounded extracted text go to Anthropic before review. The token is not sent to the model |
| Save a stored Abby file to Drive | Parent-only `POST /api/auth/google/drive/upload/`; copies an authorized PDF/photo to My Drive; original stays in Abby | No model call. Existing feature's eligibility still needs operator/Google review below |
| Reuse imported/saved content | Committed projects retain reviewed text; suggestions and planners can later include that text; MCP can return accessible project/resource data | Google-derived content and AI-derived content must remain in the disclosure/downstream-use assessment. Current saved project fields have no comprehensive Google-data provenance or downstream-transfer consent ledger |

Drive access tokens are held temporarily in browser memory and sent to Abby
only for the selected operation; code does not persist them to browser storage,
database, import jobs or Celery payloads. Files are read from Google's fixed API
host without redirects. Sign-in/Calendar tokens follow their separate encrypted
server-storage lifecycle. See [Google OAuth](google-oauth.md) and
[Drive operations](google-drive-picker.md) for detailed endpoints and limits.

## Google policy implications

Google requires truthful, accessible disclosure of collection, storage, sharing
and changed uses, least necessary permissions, and consent before new uses.
Its policy also distinguishes primarily child-directed applications from mixed
audience applications. The owner must confirm Abby's classification; optional
password login alone does not determine it.
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy).

The Workspace policy requires contextual disclosure immediately before
affirmative consent, including for agentic behavior. User-facing AI processing
is distinct from generalized model training: transfers must support the disclosed
feature with consent, and data cannot be used to improve a model beyond the
specific user's permitted personalized use. Derived data is relevant too. A
privacy page and API setting alone do not establish a provider's compliance.
The same policy excludes backing up app/project content to Drive; ask Google
whether Abby's explicit, individual file exports fit its educational workflow,
rather than assume they are approved backups or conclusively prohibited. Until
resolved, do not represent that feature as verified.
[Google Workspace user data and developer policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

Google's [generative-AI policy explanation](https://workspace.google.com/blog/ai-and-machine-learning/api-policy-protections)
specifically calls for a privacy-policy commitment against retaining Workspace
API data to develop, improve or train non-personalized AI/ML models. The public
policy records Abby's own purpose limitation; the operator still needs evidence
that downstream recipients honor the applicable restrictions.

## Submission evidence and unresolved operator actions

The following are evidence to collect or decisions to resolve, not completed
verification steps:

1. **Identify the request and deployment.** Save the actual Google message or
   Verification Center questions, production client/project identity, active
   scopes/audience and the deployed commit. The existing setup record names
   `abby-project-493200`; reconcile it against the console rather than creating
   replacement clients or rotating secrets. Confirm separate testing and
   production configuration under Google's [production-readiness guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance).
2. **Approve truthful public copy and demonstrate consent.** Publish the
   reviewed `/privacy/` AI inventory and show actual import notices, the user's
   action and provider receipt. The shared source notice covers URL, local PDF
   and Drive import before the explicit processing action and names Anthropic
   (Claude), the title and the extracted-text limit. There is no per-request AI
   opt-out or durable recipient-specific consent record. Applying a suggestion
   later is not consent obtained before sending the source. Confirm this flow
   satisfies the reviewer's requirements; otherwise implement the required
   consent gate before enabling that transfer.
3. **Bind recipients and provider terms.** Record the actual deployment model,
   endpoint/proxy and provider account; obtain evidence for permitted inference,
   model-training restrictions, human access, subprocessors, geography,
   retention and deletion. Do the same for family-selected providers and MCP
   clients that may receive Google-derived content. Do not claim contractual
   no-training, zero-retention or completed consent from this repository.
4. **Review downstream transfers.** Demonstrate MCP permission grants, current
   parent/staff/family/private-entry checks and external-client confirmations
   for the workflows actually submitted. Determine whether imported content's
   later use in idea prompts, family planning or MCP needs additional consent
   or restrictions; no provenance-based enforcement currently proves that it
   is excluded. Keep Google credentials outside assistant tool responses.
5. **Resolve audience and Drive export eligibility.** Ask Google about the
   actual family/education audience and user-selected individual-file export.
   The source is not evidence that either use case is accepted. Do not add
   broad Drive scopes to resolve an eligibility question.
6. **Document operational access, retention and deletion.** Name the responsible
   operator/support contact privately, the hosting/logging/backup recipients,
   access limits and real retention periods. Soft-discarding an import retains
   its PDF/extracted data; unlinking Google removes stored connection data but
   not copied PDFs, plans, Drive files or Calendar events. Account deletion
   cascades database rows, but does not prove file/blob, log, backup or provider
   deletion. Record a tested removal procedure for each data class and request
   channel; do not promise a time limit unsupported by deployment practice.
7. **Record a synthetic demonstration.** Show public home/privacy pages without
   login; Google consent with app/client identity; first-time linking and
   later sign-in; Calendar opt-in and created event; selected-file resource
   linking; PDF import notice, provider processing and review/commit; controls
   and deletion limitations. Add an MCP example if it is part of Google's
   request. Use synthetic family/school data and reviewer accounts, keeping
   credentials/tokens out of the video and repository.

## Factual response draft for the reviewer

Use only after checking the deployed build and completing the evidence above;
answer additional Google questions directly rather than submitting this as a
blanket compliance attestation:

> The Abby Project provides family project and schoolwork planning. Its AI
> features suggest project ideas, suggest import details from URL/PDF text, and
> create homework/project plans. Deployment suggestions/import enrichment use
> Anthropic; optional family planning uses the parent's configured OpenAI or
> Anthropic account/model. Selected Google Drive PDF text can be transferred to
> Anthropic for the import feature. Saved imported text can also be reused by
> later planning and authorized external assistants. MCP exposes authorized
> application tools to an external assistant, whose provider and conversation
> controls are separate from Abby's own provider connections. Browser voice
> dictation transcribes journal input using the browser's speech service.
> Runtime AI sprite/image generation has been removed. Abby has no application
> training or fine-tuning pipeline. Provider training/retention obligations,
> consent evidence and deletion practices must be supported by the attached
> deployment records, rather than inferred from that implementation fact.

The public disclosure is `https://abby.bos.lol/privacy/#ai` after this reviewed
change is deployed. Record the deployment and console outcome separately; this
document does not claim either has happened.
