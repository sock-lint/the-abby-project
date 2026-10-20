# Reading

`ReadingBook` is a child's shelf entry; `ReadingSession` records reading or
listening against one of that child's books. Reading is self-reported. The
daily Reading Adventure rewards ten cumulative minutes of newly logged reading
today with 15 base Reading Comprehension XP and 5 base Coins, once per child per
family-local day. Print, ebook and audiobook minutes count equally; pages,
chapters and reflections remain optional and do not determine reward value.
Reading has no payments, approval flow or journal mirroring.

The web endpoints are `/api/reading-books/`, `/api/reading-sessions/`,
`/api/reading/summary/`, `/api/reading/recommendations/`,
`/api/reading/discovery-feedback/`, and `/api/reading-family-suggestions/`. Shelf,
session and family-suggestion lists use standard DRF pagination. Parents can
view their family's records, select a
child using `user_id`, and create or correct entries for that child. Parents
must explicitly select a same-family child for creates, summaries, and
recommendations. Children only access their own shelf and log. Session lists
also accept a `book` ID filter.

Books use `want_to_read`, `reading`, `finished`, or `paused` status. Session
formats are `print`, `ebook`, or `audiobook`; optional reactions are `loved`,
`liked`, `okay`, and `not_for_me`. At least one of minutes, pages, section, or
reflection must be present. Minutes are bounded to 600 and pages to 2000.
Session dates default to the family's local day and cannot be future dates.

Creating a new session automatically moves its book from `want_to_read` or
`paused` to `reading`, including backdated, listening and notes-only logs.
`finished` books stay finished. The change uses the same owner lock and
transaction as the log and rewards; a failed save rolls everything back.
Replays, corrections and deletion do not change shelf status, and existing
history is not backfilled. Book creation retry payloads retain their original
status even after this automatic change.

Every create requires a UUID `client_request_id`. Reading writes and MCP reads
hold family, then sorted actor/owner member locks while checking the current
actor's role, staff status, activity and family membership after waiting. Create
and replay responses materialize their book and reward fields before releasing
those locks. Parents can still maintain an inactive child's saved history.
Each model uniquely binds
the owner and UUID. `create_payload` retains
the normalized original request so an
identical retry returns the current record even after a correction. Conflicting
reuse returns 400. An omitted session date stays omitted from that payload,
allowing retries across midnight without changing the original entry date.
Ownership, session book, and request identity cannot change through PATCH.

Deleting a book with entries returns 409. The session's `RESTRICT` foreign key
keeps book history intact while permitting account deletion to cascade through
that account's books and entries together. Session correction and deletion
change the summary's history counts directly. Reward credit stays separate:
`ReadingDailyReward` retains capped progress, its original award time and actual
XP/Coins after boosts; its source session uses `SET_NULL` on deletion. A
`ReadingRewardCredit` keeps every new session's UUID, original day and credited
minutes (including zero), so deleting and retrying a historical, notes-only or
over-cap entry cannot create a fresh reward opportunity tomorrow. Neither
corrections, date changes, book status nor retries advance or revoke rewards.
Existing and backdated logs are not rewarded retrospectively.

The new daily reward also calls `freeze_milestone_eligibility` before the game
loop, under the same account/source transaction. This is the trusted acceptance
hook for authored reading milestone gates: it freezes a new goal/occurrence
before that fact can complete its predecessor. Generic source replay, scans and
pending repairs cannot create a milestone window. With no authored gates this
hook leaves the previous activity pipeline unchanged. See
[`reading-voyager-milestones.md`](../../docs/operations/reading-voyager-milestones.md).
Migration `0003` preserves existing live session UUIDs as zero-credit identities;
it reads only owner, UUID and date, without creating progress or awards. Requests
deleted before that migration have no surviving identity evidence to preserve.

MCP reading maintenance uses these same shared correction and deletion services.
Parents explicitly choose a same-family child; children select only themselves.
Book and session detail reads and signed, paginated session history are saved-state
reads. Confirmed edits preserve omitted fields and the original create identity;
confirmed removal of a book with sessions returns a history conflict. Deleting a
session retains its daily receipt and UUID reward credit, including on later retries.

`ReadingRewardService.credit_new_session` runs only after a new session insert,
under the same account lock as every reading write. The inserted log, request
identity, daily credit, XP, Coins and strict game-loop call share a transaction;
a failure rolls them back together. The game loop runs only at the threshold,
giving streak/check-in credit, one supported drop opportunity and compatible
legacy quest progress. It also records one automatic challenge fact from the
awarded `ReadingDailyReward` ID, with its saved day and award timestamp and no
book, reflection or session prose. Only challenges explicitly filtered to
`reading_logged` count these daily Adventures; unfiltered goals retain their
existing activity rules. The bundled `reading-adventures` pack offers supported
Chick hatch ingredients after three Adventures, repeatable Birdseed care after
five in seven days, and a Bookworm title after twenty. These new goals have no
authored Coin payouts. Any push notifications from the direct award and game
loop are deferred until that transaction commits; a rollback discards them.
Reading does not count toward the existing project/movement daily challenge
bonus. Corrections, deletion and source replay cannot change the daily fact;
explicit current-week parent count goals can include saved awarded receipts
even after their source session was deleted. Missing or locked reading
skills award no invented XP; the saved receipt reports actual credit.

Session responses include a nullable `reading_reward` on the original awarding
session. Summary responses include today's `reading_adventure` progress and
reward receipt. Reads create no progress, consume no opportunity and award
nothing. Session queries select the reverse reward relation to avoid a query
per history row; reflection prose never enters reward context or activity logs.

Recommendations use 64 publisher-sourced books in `catalog.py` and
`catalog_data.py`, ranked locally by `recommendations.py`. Edition metadata
includes ISBN, nullable page count, verified formats, original descriptions,
editorial mood/style/theme tags and nullable ordered series. Saved book responses
include `catalog_entry` or null: matching normalizes title/author case and
whitespace; a legacy blank author matches only a unique title. No external
metadata requests, credentials, reflections or family suggestion messages enter
ranking. The browser loads Open Library covers with `no-referrer` and a missing
image fallback. WorldCat links search by title/author and do not establish local
library availability.

`GET /api/reading/recommendations/` accepts optional `interest`, `mood`, `style`,
`book_format`, `length`, `theme`, `q`, `similar_to` and `rotation`. Use
`book_format`, not DRF's renderer-selection `format` query. The enums live in
`constants.py`; search is bounded to 160 characters and rotation to 0–1000.
Filters intersect publisher age bounds and exclude owned/hidden titles. Length
means short ≤200 pages, medium 201–349, long ≥350; unknown counts do not match a
length filter. Search uses catalog titles, authors, tags and series names.
Read-alikes compare catalog themes/styles/moods/topics. Unfiltered picks can
include a new topic and prioritize the next series volume only after every
earlier catalog volume is on this reader's finished shelf. Rotation wraps
through eligible picks six at a time. Responses include `basis`, `total`,
`has_more`, `rotation`, and per-book `reason`/`reason_kind`.

Discovery feedback GET returns this reader's `{catalog_id, choice}` rows. POST
with `not_interested` or `already_read` upserts the unique user/catalog preference
and hides that title; an empty `choice` clears it for Undo. These are idempotent
preferences, with no shelf insertion, session or reward. Parents must select a
same-family child with `user_id`; children can act only for themselves.

Only parents create family suggestions, supplying a same-family child
`user_id`, catalog ID, optional message of at most 500 characters and UUID
`client_request_id`. The normalized retry identity includes the sender; identical
retries return the saved invitation and conflicting payloads fail. An immutable
author display-name snapshot preserves attribution if the parent is deleted.
Reads remain within the recipient's family and hide suggestions whose surviving
sender has moved families or is no longer a parent. The paginated list returns
only `pending` invitations, including `suggested_by`, `catalog_entry` and
`on_shelf`. PATCH accepts only `status: dismissed`. The child explicitly saves a
chosen book through the normal shelf create; this changes `on_shelf`, not the
invitation's status, and awards nothing. Neither sending nor dismissing an
invitation creates a book or reading log.

The existing producer `config.tests.test_reading_api_contract_fixtures` and React
consumer `frontend/src/api/readingContractFixtures.test.js` cover enriched picks,
feedback, attributed invitations, explicit shelf saving and dismissal with
synthetic fixtures under `contracts/api/fixtures/`.

Run `python manage.py test apps.reading --settings=config.settings_test` with
a disposable database. PostgreSQL executes concurrent create/retry and reward
threshold tests; SQLite explicitly skips row-lock tests.
