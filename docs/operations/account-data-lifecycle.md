# Account deletion and remaining lifecycle work

Verified against `d35847791598501c474b09da0be0fa8518586e6a` on October 17, 2026.
This first slice makes the existing parent-managed member deletion reliable.
Self-deletion and family closure remain unavailable; the existing safeguards
are intentional and must not simply be removed.

## Current member deletion contract

A parent can delete another member of their own family from Manage → Family.
Children cannot delete accounts. A parent cannot delete themselves or remove
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
| Activity events and other surviving members' records | Existing SET_NULL relationships remain; summaries, context, notifications or notes may still identify the deleted member. This is not comprehensive anonymization |
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

1. **Self-deletion and family closure.** Build on the durable cleanup queue.
   Require recent authentication and an explicit impact review. Allow an adult
   to leave only with a verified active co-parent; require an explicit successor
   for the founder pointer and decide how to preserve shared authored work.
   The last parent's separate closure action must explicitly cover all family
   members, family-owned credentials/content and retained activity. Decide
   child deletion consent, legal retention, backup handling and support
   escalation before claiming complete erasure. Do not infer ownership powers
   from the current cosmetic founder field. Reconcile all account-removal and
   active-status write paths (including existing PATCH), with fresh locked
   permission checks for competing co-parent removals; current guards alone
   are not proof of safety under every concurrent administration request.
2. **Google return exchange and sessions.** Replace the current reusable token
   in the Google navigation URL with a short-lived, atomic single-use exchange
   bound to the initiating browser. Preserve linking, sign-in, Calendar and
   separate Drive permissions. Revalidate active user/family/credential state
   on completion. Then introduce independent device sessions deliberately:
   legacy password login intentionally rotates one shared DRF token. Specify
   logout, reset, deactivation, deletion, switching and delayed-response rules
   across DRF, MCP and Django sessions before adding another credential type.
3. **Scope existing recovery before extending it.** Journal and PDF import
   already have local recovery and stable server retry identities, but their
   local keys use numeric user ID without backend/family/session identity.
   Bind recovery to the agreed session model and define explicit logout and
   deletion cleanup. Add server idempotency/receipts before durable retries for
   homework proof, new-project and media forms, which currently lose memory
   on reload/process death. Prevent duplicate rewards and stale overwrites.
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
