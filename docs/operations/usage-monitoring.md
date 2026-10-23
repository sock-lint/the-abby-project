# Usage monitoring

Manage → Admin → Usage is a first-party, read-only report. It measures selected
saved actions and foreground visits without collecting the content of family
work. Sentry remains the separate error and performance diagnostic system.

## Access and collection

The report requires an active staff parent. Its default scope is that parent's
own family. Only a deployment superuser may request deployment-wide aggregates;
global catalog editing privileges alone do not grant that access. Responses
contain counts and dates, not family names, member names or source records.

`POST /api/usage/visit/` accepts an empty object from the signed-in foreground
app. The server derives the account, family and role, and records at most one
visit per account per UTC day across devices. A visit establishes that the app
was opened, not attention, session duration or completion. Background polling
does not call this endpoint. An uncertain visit POST is not retried automatically.

Selected REST save paths record a fixed feature/action and the corresponding
saved record's internal identity. Each source/action is counted at most once
while its usage event is retained, preventing retries of the same surviving
record and reward fan-out from adding actions. Deleting a reading session and
creating another saved session counts as another activity, including when the
underlying endpoint accepts a reused request UUID after deletion. Background
jobs, MCP calls and automatic
approvals do not opt into these human action measurements. The provisioned
`LiveTestFamily` ownership records exclude the observer's synthetic households;
matching a household name is not sufficient to exclude a real family.

| Feature | Recorded action |
| --- | --- |
| Homework | Submission and explicit parent approval |
| Chores | Completion submission and explicit parent approval |
| Projects | Submission, positive work-session clock-out, explicit project or timecard approval |
| Reading | Newly saved reading session |
| Movement | Newly saved movement session |
| Habits | Positive or negative check-in |
| Rewards | Redemption request and explicit parent approval |

The actor is the person who performed the action. A parent logging movement for
a child counts as parent activity. Private writing, journal presence and content,
notes, titles, files, raw URLs, credentials, IP addresses and screen recordings
are excluded from this telemetry. It does not affect reward eligibility or pay
XP, Coins or money.

## Reading the report

`GET /api/admin/usage/` accepts bounded `days` (7, 28 or 90), `role` and `feature`
filters and the authorized `scope`. Periods use UTC dates; the current day is
partial. Successful selected actions establish engagement. Foreground visits
are a separate measure. Submitted work and newly logged activities count as
activities recorded; a parent approval is a separate action and does not count
the child's work twice. Negative habit check-ins and reward requests establish
engagement without asserting a completed activity.

The report shows current and previous totals, a daily trend, unique actors per
feature, new-family milestones, mature one- and four-week returns, pending
reviews, decision turnaround and a seven-day summary. Each section states its
coverage. Retention percentages require a fully observed return window; an
unavailable denominator is not a zero-percent result. A family's first observed
action is not evidence of its first-ever use before measurement began. Returning
families means families active in the week one or four weeks before the latest
fully completed UTC Monday–Sunday week, and active again in that latest week.
Existing households qualify; these are not signup-only cohorts. Both the cohort
week and return week require complete observed history.

Onboarding, returning-family cohorts and the review queue have distinct
denominators from the feature/role-filtered activity totals. Read their coverage
labels before comparing them. Pending-review and decision-time coverage is
limited to saved homework and chore submissions. There is no inferred workflow
abandonment, save-failure rate, sign-in failure rate or request latency from
these usage events; use the existing Sentry diagnostics for technical failures.

Historical audit events, Coin rows and `last_seen_at` are not backfilled as
visits or human actions. `last_seen_at` records only the latest dashboard fetch.
The collection start and retained-history bounds remain visible. Comparisons
outside those bounds are incomplete, including a 90-day period's predecessor.

## Retention and operation

Raw usage events retain 90 UTC calendar dates, including today. The existing application
Celery Beat schedule invokes `apps.usage.tasks.prune_usage_events` daily; it
does not add a host cron job or independent station timer. Reports disregard
expired events even before the next cleanup. The management command
`python manage.py prune_usage_data` performs the same bounded cleanup. The
read-only `python manage.py usage_summary --username <staff-parent>` command
prints the weekly JSON summary for that parent's household; `--scope deployment`
also requires that account to be a superuser.

Account and family deletion cascade to linked usage records. The public privacy
page discloses collection, access and cleanup; operational logs and backups
remain subject to their separate policies. The weekly summary is available in
the report and does not send email or create a new notification schedule.

Shared synthetic Django response fixtures and React consumers run in the
required API fixtures check. Endpoint permissions, cross-family isolation,
save/replay behavior, return-window maturity and frontend account changes have
separate behavioral checks. Validation uses disposable databases and synthetic
identities, without production access.
