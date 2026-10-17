# Reading

`ReadingBook` is a child's shelf entry; `ReadingSession` records reading or
listening against one of that child's books. Reading is self-reported and has
no XP, Coins, payments, approvals, journal mirroring, or game-loop hooks.

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
change the summary's counts directly; there are no persistent reward counters.

Recommendations use the bounded, local catalog in `catalog.py` and the pure
ranking service in `recommendations.py`. They do not use an external API,
credentials, or reflections to personalize suggestions. See those modules for
their source links and ranking policy.

Run `python manage.py test apps.reading --settings=config.settings_test` with
a disposable database. PostgreSQL executes the concurrent create/retry tests;
SQLite explicitly skips those three row-lock tests.
