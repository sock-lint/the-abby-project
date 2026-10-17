"""Explainable local discovery from a reader's shelf, reactions and choices."""

from collections import Counter
from collections.abc import Mapping

from .catalog import BOOK_CATALOG
from .constants import INTERESTS


def _normalized_title(value):
    return " ".join(value.casefold().split())


def _label(value):
    return value.replace("_", " ")


def _public_entry(entry):
    """Copy mutable metadata so consumers cannot modify the shared catalog."""
    result = dict(entry)
    for field in ("interests", "formats", "moods", "styles", "themes", "source_urls"):
        result[field] = list(entry.get(field, ()))
    result["series"] = dict(entry["series"]) if entry.get("series") else None
    return result


def catalog_entry_for_book(book):
    """Recognize saved and legacy books without inventing an identity.

    A missing author is accepted only for a unique title. An explicit different
    author never acquires another book's metadata or series position.
    """
    title = book.get("title", "") if isinstance(book, Mapping) else book.title
    author = book.get("author", "") if isinstance(book, Mapping) else book.author
    matches = [entry for entry in BOOK_CATALOG if _normalized_title(entry["title"]) == _normalized_title(title)]
    if author.strip():
        matches = [entry for entry in matches if _normalized_title(entry["author"]) == _normalized_title(author)]
    return _public_entry(matches[0]) if len(matches) == 1 else None


def _matches_filters(book, *, interest, mood, style, format, length, theme, q):
    for field, selected in (("interests", interest), ("moods", mood), ("styles", style), ("formats", format), ("themes", theme)):
        if selected and selected not in book.get(field, ()):
            return False
    if length:
        pages = book.get("page_count")
        if pages is None:
            return False
        if length == "short" and pages > 200:
            return False
        if length == "medium" and not 201 <= pages <= 349:
            return False
        if length == "long" and pages < 350:
            return False
    if q:
        terms = [book["title"], book["author"]]
        for field in ("interests", "moods", "styles", "themes"):
            terms.extend(_label(value) for value in book.get(field, ()))
        if book.get("series"):
            terms.append(book["series"]["title"])
        text = _normalized_title(" ".join(terms))
        if not all(word in text for word in _normalized_title(q).split()):
            return False
    return True


def _similarity(book, anchor):
    return sum(
        weight * len(set(book.get(field, ())) & set(anchor.get(field, ())))
        for field, weight in (("themes", 5), ("styles", 2), ("moods", 1), ("interests", 1))
    )


def _series_prerequisites(book, series_entries, finished_ids):
    series = book.get("series")
    if not series or series["position"] == 1:
        return True
    earlier = [entry for entry in series_entries[series["id"]] if entry["series"]["position"] < series["position"]]
    return (
        {entry["series"]["position"] for entry in earlier} == set(range(1, series["position"]))
        and all(entry["id"] in finished_ids for entry in earlier)
    )


def recommend_books(user, interest=None, *, mood=None, style=None, format=None,
                    length=None, theme=None, q="", similar_to=None, rotation=0):
    """Return six eligible, explainable picks; never read reflection prose.

    The caller resolves access. All three queries still scope ownership here,
    including the book owner on reaction rows. The latest reaction per book in
    the recent 100 rated sessions wins. Rotation walks the complete ranked list
    in windows of six and wraps, without altering saved reading state.
    """
    from .models import ReadingBook, ReadingDiscoveryFeedback, ReadingSession

    books = list(ReadingBook.objects.filter(user=user).values("id", "title", "author", "status", "interests"))
    owned_titles = {_normalized_title(book["title"]) for book in books}
    book_topics = {
        book["id"]: tuple(topic for topic in book["interests"] if topic in INTERESTS)
        for book in books
    }
    scores = Counter(topic for topics in book_topics.values() for topic in topics)
    liked_topics = {}
    rated_books = set()
    recent_reactions = (
        ReadingSession.objects.filter(user=user, book__user=user)
        .exclude(reaction="")
        .order_by("-occurred_on", "-created_at", "-id")
        .values("book_id", "reaction")[:100]
    )
    for session in recent_reactions:
        book_id = session["book_id"]
        if book_id in rated_books:
            continue
        rated_books.add(book_id)
        reaction = session["reaction"]
        weight = {"loved": 4, "liked": 2, "not_for_me": -1}.get(reaction, 0)
        for topic in book_topics.get(book_id, ()):
            scores[topic] += weight
            if reaction in {"loved", "liked"}:
                liked_topics.setdefault(topic, reaction)

    excluded_ids = set(ReadingDiscoveryFeedback.objects.filter(user=user).values_list("catalog_id", flat=True))
    recognized = [(book, catalog_entry_for_book(book)) for book in books]
    finished_ids = {entry["id"] for book, entry in recognized if entry and book["status"] == ReadingBook.Status.FINISHED}
    series_entries = {}
    for entry in BOOK_CATALOG:
        if entry.get("series"):
            series_entries.setdefault(entry["series"]["id"], []).append(entry)
    anchor = next((entry for entry in BOOK_CATALOG if entry["id"] == similar_to), None) if similar_to else None
    explicit = any((interest, mood, style, format, length, theme, q, similar_to))
    next_series_ids = set()
    if not explicit:
        for _book, entry in recognized:
            if not entry or entry["id"] not in finished_ids or not entry.get("series"):
                continue
            series = entry["series"]
            next_series_ids.update(
                candidate["id"] for candidate in series_entries[series["id"]]
                if candidate["series"]["position"] == series["position"] + 1
            )

    age = user.age_years
    candidates = [
        book for book in BOOK_CATALOG
        if _normalized_title(book["title"]) not in owned_titles
        and book["id"] not in excluded_ids
        and (
            book["age_min"] <= 8 if age is None
            else book["age_min"] <= age and (book["age_max"] is None or age <= book["age_max"])
        )
        and _matches_filters(book, interest=interest, mood=mood, style=style, format=format, length=length, theme=theme, q=q)
        and _series_prerequisites(book, series_entries, finished_ids)
        and (not similar_to or (anchor is not None and book["id"] != anchor["id"] and _similarity(book, anchor) > 0))
    ]
    ranked = []
    covered_topics = set()
    while candidates:
        selected = max(candidates, key=lambda book: (
            book["id"] in next_series_ids,
            _similarity(book, anchor) if anchor else sum(scores[topic] for topic in book["interests"]),
            len(set(book["interests"]) - covered_topics),
        ))
        candidates.remove(selected)
        covered_topics.update(selected["interests"])
        ranked.append(selected)

    surprise_id = None
    if not explicit and any(score > 0 for score in scores.values()) and len(ranked) >= 6:
        surprise = next((book for book in ranked if book["id"] not in next_series_ids and not any(scores[topic] > 0 for topic in book["interests"])), None)
        if surprise:
            ranked.remove(surprise)
            ranked.insert(5, surprise)
            surprise_id = surprise["id"]

    total = len(ranked)
    offset = rotation * 6 % total if total else 0
    ordered = ranked[offset:] + ranked[:offset]
    results = []
    for selected in ordered[:6]:
        matching_likes = [topic for topic in selected["interests"] if topic in liked_topics]
        matching_shelf = [topic for topic in selected["interests"] if scores[topic] > 0]
        if selected["id"] in next_series_ids:
            series = selected["series"]
            reason, kind = f"Continue {series['title']} with book {series['position']}.", "series"
        elif anchor:
            shared = next(((_label(value), field) for field in ("themes", "styles", "moods", "interests") for value in selected.get(field, ()) if value in anchor.get(field, ())), None)
            reason, kind = f"Like {anchor['title']}: more {shared[0]}.", "similar"
        elif interest:
            reason, kind = f"Because you chose {interest}.", "interest"
        elif any((mood, style, format, length, theme, q)):
            choices = [_label(value) for value in (mood, style, format, theme) if value]
            if length:
                choices.append({"short": "200 pages or fewer", "medium": "201–349 pages", "long": "350 pages or more"}[length])
            if q:
                choices.append(f'“{q}”')
            reason, kind = f"Matches your choices: {', '.join(choices)}.", "filter"
        elif selected["id"] == surprise_id:
            reason, kind = f"Try something different: explore {selected['interests'][0]}.", "surprise"
        elif matching_likes:
            topic = max(matching_likes, key=lambda item: scores[item])
            reason, kind = f"More {topic} after a book you {liked_topics[topic]}.", "reaction"
        elif matching_shelf:
            topic = max(matching_shelf, key=lambda item: scores[item])
            reason, kind = f"More {topic}, a topic on your shelf.", "shelf"
        else:
            reason, kind = f"Explore {selected['interests'][0]} in this starter pick.", "starter"
        results.append({**_public_entry(selected), "reason": reason, "reason_kind": kind})

    if anchor:
        basis = f"Read-alikes for {anchor['title']}, using shared themes, style, mood and topics."
    elif interest:
        basis = f"Exploring {interest} from our curated shelf."
    elif explicit:
        basis = "Books matching your discovery choices from our curated shelf."
    elif liked_topics:
        basis = "Inspired by topics in books you liked or loved, with more ideas to explore."
    elif books:
        basis = "Inspired by topics on your shelf, with more ideas to explore."
    else:
        basis = "A varied starter shelf. Choose a topic to find something that interests you."
    if age is None:
        basis += " Starter picks; check publisher age guidance together."
    basis += " Publisher ages are broad guidance, not reading levels. Reflections are never used for suggestions."
    return {"results": results, "basis": basis, "total": total, "has_more": total > 6, "rotation": rotation}
