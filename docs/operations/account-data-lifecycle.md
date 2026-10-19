# Account departure, family closure and file cleanup

Verified on October 17, 2026. The explicit Settings flows build on PR #262's
transactional file-cleanup queue. They preserve the documented, separate
parent-managed removal contract rather than disabling its self-removal guard.

## Settings: departure and family closure

Every signed-in member can review their own deletion options in Settings →
Account deletion and family handoff. Each action verifies the current Abby
password against a freshly locked account and credential. Google sign-in alone
is not confirmation: an account with no usable Abby password must first obtain
a password reset from a family parent or deployment operator. Passwords and
destructive confirmations are not persisted by these forms. Children can
delete only their own account here, with their password and exact username.
Existing parent-managed child removal is still available.

A parent can leave only by choosing another active parent in the same family.
Shared authored projects, project templates, homework assignments/templates,
chores and habits pass to that parent. Only their `created_by` ownership changes;
assignment, saved progress, reward receipts and rewards do not change. Projects
and homework assigned to the departing account, personal habits, private journals
and other personal data are deleted instead of transferred. If the departing
parent is the family contact, the selected successor becomes the contact.

Children can also author chores, habits and homework that a parent later
publishes or assigns to another member. On child self-deletion, this shared
work automatically passes to the active same-family contact, or otherwise
the oldest active same-family parent by `date_joined`, then primary key. The
child cannot select the recipient or change the family contact. Shared work
requires an active parent; without one, the preview disables deletion and the
operation refuses safely until a parent is active again. The final check runs
after affected records are locked, so a just-finished approval cannot escape
handoff. Only creator pointers change: other members' assignments, progress,
proof files, completions and rewards survive without replay. The child's own
submissions, logs, pending personal proposals and private journals still delete.

The separate **Transfer family contact** action changes `Family.primary_parent`
without deleting anything or transferring shared work. The field is a display
pointer: every active parent retains equal permissions. It confers no extra
authority, and any active parent may change it with password confirmation.

Only the sole active parent may close the family. The preview counts all parents
and children, including inactive members. Closure requires the password, exact
family slug and a fingerprint of the reviewed membership. New members, activation
changes or a contact change invalidate that review with HTTP 409; refresh and
confirm again. Closure removes every family member, their personal and shared
data, family AI credentials, printer configuration/jobs and other family settings.
Global catalogs and other families remain. File cleanup jobs survive the closure.

The new self-deletion/closure flows remove activity structurally linked to the
departing accounts or deleted target objects. A mixed-family activity record
retains the other family's actor/subject pointer but loses its text, context,
deltas, correlation and target. Unattributed historical text without a structural
link and copies in other members' surviving notes/notifications cannot be found
reliably by matching names; these flows do not promise comprehensive anonymization.

All membership decisions serialize on the family, then ordered member rows and
the current credential. Existing member creation, edits, reset, activation and
removal use the same boundary and recheck the actor after waiting. Existing
`is_active` PATCH remains supported with the same safeguards/token revocation;
password PATCH is rejected in favor of the existing reset-password action.
Password login revalidates under these locks, preserving its shared-token rotation
contract. A stale authenticated lifecycle request cannot finish after logout,
password rotation, deactivation or deletion. Other already-running application
requests are not universally cancelled by this change.

Lifecycle mutations lock member gates and dependent records without waiting
on PostgreSQL. An approval or completion already saving affected work makes
deletion return a safe 409; let that save finish, refresh the review and retry.
This avoids waiting on in-flight reward transactions while the family is fenced.
The failed attempt rolls
back any handoff, activity cleanup and file jobs together.

Before collecting the cascade, deletion takes stronger locks on the departing
account; family closure also fences the family and every member. These locks
prevent a newly committed foreign-key save from appearing after the ownership
handoff. Pending reference checks and affected nullable updates, including global
catalog author pointers, also use the busy/retry boundary. An already-running
save that cannot commit after its account is deleted has not confirmed a 201
save; the app does not treat that failed request as saved work.

Malformed historical cross-family relationships cause a safe 409 before deletion
or transfer, with no private record identifiers. They require operator repair;
the deletion service does not guess which family's data to discard. The UI
preserves failed forms for explicit retry and fences late responses by account,
family and credential. A membership-conflict closure requires a new impact review.
Database deletion and cleanup scheduling commit together. A lost HTTP response
does not prove whether the transaction committed: no automatic write retry occurs.
If the credential no longer works, sign in again or ask the operator to confirm.

| Endpoint | Contract |
| --- | --- |
| `GET /api/account/lifecycle/` | Self-scoped impact preview, eligible active successors, member counts and membership fingerprint; no private contents or credentials |
| `POST /api/account/lifecycle/transfer/` | `{password, successor_id}`; parent changes display contact |
| `POST /api/account/lifecycle/delete/` | `{password, confirm_username, successor_id?}`; parent must supply successor; child uses automatic shared-work handoff and cannot select a successor (an optional valid numeric ID is ignored) |
| `POST /api/account/lifecycle/close-family/` | `{password, confirm_family_slug, family_version}`; sole active parent only |

Mutation success is HTTP 204. Password/confirmation/successor failures are 400;
child access to parent-only actions is 403; changed review or inconsistent family
links are 409; stale credentials/accounts are 401. Password confirmations are
throttled to ten per minute per signed-in account. Shared synthetic response
fixtures cover parent, child and sole-active-parent previews.

## Current member deletion contract

A parent can delete another member of their own family from Manage → Family.
Children cannot manage other accounts. A parent cannot delete themselves through
the legacy member endpoint or remove
the last active parent. `Family.primary_parent` is a founder display pointer,
not an additional authorization role. Removing that parent selects the oldest
remaining active parent. The handoff, database deletion and file-cleanup work
commit together or roll back together. Existing DELETE responses remain 204;
that confirms database deletion and scheduling, not completed storage erasure.

Deletion follows the existing model cascades. In particular, projects and
homework authored by a deleted parent can disappear even when assigned to a
remaining child. Reassignment alone does not preserve an authored project.
The confirmation explains that consequence before the destructive request.
Private journal contents are never included in deletion confirmations or
cleanup jobs.

| Data | What deletion does |
| --- | --- |
| Account, private journal, progression, personal ledgers and related cascading rows | Removed from the active database according to the existing FK relationships |
| DRF tokens, MCP access/refresh tokens, linked Google credentials, Calendar mappings and push subscriptions belonging to the member | Cascading database deletion removes the member's stored connection/authorization records; an already-running request may still finish |
| Avatar, project covers/receipts/photos, homework proofs, creation photos/audio, imported PDFs and print files on deleted rows | Storage keys enter a durable cleanup queue in the deletion transaction; a bounded worker retries failures |
| Files referenced by surviving records | Retained while referenced; cleanup is deferred and recorded |
| Activity events and other surviving members' records | Legacy parent-managed removal retains existing SET_NULL behavior; the explicit self-deletion/closure flows above remove/redact structurally linked activity. Surviving notes/notifications can still identify the member. This is not comprehensive anonymization |
| Family-owned content and configuration | Remain with the family when the corresponding records survive, including family AI/provider and printer credentials |
| Google grants, existing Calendar events and exported Drive files | Remain at Google; revoke/delete through Google separately |
| Device drafts, downloaded/exported copies and browser caches | Not remotely erased by member deletion; use the device's controls to clear retained copies |
| Backups, diagnostics and storage object versions | Not purged by this operation; no fixed retention or erasure deadline is established by this change |

## Storage reliability and operator recovery

The allowlist covers every private FileField/ImageField currently attached to
family/member content. Global RPG sprite assets are excluded. Django deletion
signals cover ORM cascades and queryset deletion as well as the member API;
raw SQL bypasses these signals. A database failure that prevents recording a
cleanup job also prevents that deletion. No broker availability is needed in
the request. The existing Celery worker and Beat process service the queue.

Storage deletion is idempotent and separate from database deletion. Failures
keep the storage key, attempts, next retry time and a bounded failure category
in the database. Keys are private operational data: they are not returned by
the API or written to ordinary logs. Cleanup jobs have no member foreign key,
so deleting the member cannot cascade away their outstanding work. A worker
crash after deleting bytes but before acknowledging the job repeats the delete.
Deployment operators must monitor overdue/failed jobs and keep the default
storage backend and bucket configuration unchanged until outstanding jobs drain;
the queue's keys are bound to that store. Scheduling does not promise a deadline.
The existing Beat schedule checks every five minutes, processing at most 25
due jobs per call. Failures back off from five minutes to at most one day and
remain queued without an attempt limit. Storage failures produce count-only
warning logs.

From the deployment's approved Django runtime, the operator can inspect or
retry a bounded due batch through these commands:

```bash
python manage.py cleanup_deleted_files --status   # counts/oldest time; no storage calls
python manage.py cleanup_deleted_files --limit 25
```

The retry command respects backoff and accepts at most 100 jobs. Neither
command prints storage keys or exception messages. These commands do not
authorize a task session to access production.

The worker never scans a bucket or guesses ownership from a filename. It
cannot reconstruct historical orphaned files whose database pointers were
already lost, clean files from failed uploads that never acquired a row, or
purge object versions/backups. Existing immediate file replacement/removal
paths retain their current behavior. A separate inventory/reconciliation
project is needed for those cases.

## Prioritized follow-up backlog

1. **Google return exchange and sessions.** Replace the current reusable token
   in the Google navigation URL with a short-lived, atomic single-use exchange
   bound to the initiating browser. Preserve linking, sign-in, Calendar and
   separate Drive permissions. Revalidate active user/family/credential state
   on completion. Then introduce independent device sessions deliberately:
   legacy password login intentionally rotates one shared DRF token. Specify
   logout, reset, deactivation, deletion, switching and delayed-response rules
   across DRF, MCP and Django sessions before adding another credential type.
2. **Scope existing recovery before extending it.** Journal and PDF import
   already have local recovery and stable server retry identities, but their
   local keys use numeric user ID without backend/family/session identity.
   Bind recovery to the agreed session model and define explicit logout and
   deletion cleanup. Add server idempotency/receipts before durable retries for
   homework proof, new-project and media forms, which currently lose memory
   on reload/process death. Prevent duplicate rewards and stale overwrites.
   First fix the existing homework PATCH response contract: reassignment can
   persist before `skill_tags` serialization returns a `RelatedManager` TypeError.
3. **Retention reconciliation.** Establish operator-owned backup, diagnostics,
   storage-version and provider-copy policies and a monitored support destination.
   Inventory historical orphans and interrupted uploads before claiming complete
   erasure. Decide further child consent/account-recovery policy separately from
   the password-confirmed self-service behavior implemented here.
4. **Packaged-client integrations.** Use a configured public application origin
   for Calendar event links and public About/Privacy links. Add bounded native
   download/share adapters while preserving private attachment permissions and
   expiring URLs. Distinguish cancellation from permission/upload failures;
   do not turn private media URLs into public share links.
5. **Privacy, support and AI reporting.** Reconcile with open PR #255's AI/MCP
   and ingestion disclosures first. Describe actual diagnostics (including
   user identifiers), processors, consent and retention; add problematic-output
   reporting. A real monitored support destination requires the operator's
   contact choice. Do not invent an address or guarantee an unconfigured
   retention period.

Keep these proposals bounded in this document for the next capped review;
they are not newly created tracker issues. Store enrollment, signing,
distribution, gameplay and artwork are outside this work.
