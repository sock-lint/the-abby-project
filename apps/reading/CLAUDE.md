# Reading

`ReadingBook` is a child's shelf entry; `ReadingSession` records reading or
listening against one of that child's books. Reading is self-reported. The
daily Reading Adventure rewards ten cumulative minutes of newly logged reading
today with 15 base Reading Comprehension XP and 5 base Coins, once per child per
family-local day. Print, ebook and audiobook minutes count equally; pages,
chapters and reflections remain optional and do not determine reward value.
Reading has no payments, approval flow or journal mirroring.

The web endpoints are `/api/reading-books/`, `/api/reading-sessions/`,
`/api/reading/summary/`, and `/api/reading/recommendations/`. Lists use the
standard DRF pagination. Parents can view their family's records, select a
child using `user_id`, and create or correct entries for that child. Parents
must explicitly select a same-family child for creates, summaries, and
recommendations. Children only access their own shelf and log. Session lists
also accept a `book` ID filter.

Books use `want_to_read`, `reading`, `finished`, or `paused` status. Session
formats are `print`, `ebook`, or `audiobook`; optional reactions are `loved`,
`liked`, `okay`, and `not_for_me`. At least one of minutes, pages, section, or
reflection must be present. Minutes are bounded to 600 and pages to 2000.
Session dates default to the family's local day and cannot be future dates.

Every create requires a UUID `client_request_id`. All reading writes lock the
owner user row, then recheck family membership. Each model uniquely binds the
owner and UUID. `create_payload` retains the normalized original request so an
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
Migration `0003` preserves existing live session UUIDs as zero-credit identities;
it reads only owner, UUID and date, without creating progress or awards. Requests
deleted before that migration have no surviving identity evidence to preserve.

`ReadingRewardService.credit_new_session` runs only after a new session insert,
under the same account lock as every reading write. The inserted log, request
identity, daily credit, XP, Coins and strict game-loop call share a transaction;
a failure rolls them back together. The game loop runs only at the threshold,
giving streak/check-in credit, one supported drop opportunity and compatible
legacy quest progress. Any push notifications from the direct award and game
loop are deferred until that transaction commits; a rollback discards them.
Reading does not add automatic goal facts or count toward
the existing project/movement daily challenge bonus. Missing or locked reading
skills award no invented XP; the saved receipt reports actual credit.

Session responses include a nullable `reading_reward` on the original awarding
session. Summary responses include today's `reading_adventure` progress and
reward receipt. Reads create no progress, consume no opportunity and award
nothing. Session queries select the reverse reward relation to avoid a query
per history row; reflection prose never enters reward context or activity logs.

Recommendations use the bounded, local catalog in `catalog.py` and the pure
ranking service in `recommendations.py`. They do not use an external API,
credentials, or reflections to personalize suggestions. See those modules for
their source links and ranking policy.

Run `python manage.py test apps.reading --settings=config.settings_test` with
a disposable database. PostgreSQL executes concurrent create/retry and reward
threshold tests; SQLite explicitly skips row-lock tests.
