"""Explainable book discovery using only a reader's shelf and reaction choices."""

from collections import Counter

from .catalog import BOOK_CATALOG
from .constants import INTERESTS


def _normalized_title(title):
    return " ".join(title.casefold().split())


def recommend_books(user, interest=None):
    """Return up to six sourced picks without loading or transmitting reflections.

    The caller resolves permission to view this user's reading area. Both book
    and session ownership are still scoped here; malformed cross-user sessions
    cannot influence a recommendation. The latest reaction for each book in the
    recent 100 rated sessions wins, so repeated logging does not inflate a topic.
    """
    from .models import ReadingBook, ReadingSession

    books = list(ReadingBook.objects.filter(user=user).values("id", "title", "interests"))
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

    age = user.age_years
    candidates = [
        book for book in BOOK_CATALOG
        if _normalized_title(book["title"]) not in owned_titles
        and (
            book["age_min"] <= 8 if age is None
            else book["age_min"] <= age and (book["age_max"] is None or age <= book["age_max"])
        )
        and (interest is None or interest in book["interests"])
    ]
    # Interest scores take priority; topic variety breaks ties deterministically.
    results = []
    covered_topics = set()
    while candidates and len(results) < 6:
        selected = max(candidates, key=lambda book: (
            sum(scores[topic] for topic in book["interests"]),
            len(set(book["interests"]) - covered_topics),
        ))
        candidates.remove(selected)
        covered_topics.update(selected["interests"])
        matching_likes = [topic for topic in selected["interests"] if topic in liked_topics]
        matching_shelf = [topic for topic in selected["interests"] if scores[topic] > 0]
        if interest:
            reason = f"Because you chose {interest}."
        elif matching_likes:
            topic = max(matching_likes, key=lambda item: scores[item])
            reason = f"More {topic} after a book you {liked_topics[topic]}."
        elif matching_shelf:
            topic = max(matching_shelf, key=lambda item: scores[item])
            reason = f"More {topic}, a topic on your shelf."
        else:
            reason = f"Explore {selected['interests'][0]} in this starter pick."
        results.append({**selected, "interests": list(selected["interests"]), "reason": reason})

    if interest:
        basis = f"Exploring {interest} from our small curated shelf."
    elif liked_topics:
        basis = "Inspired by topics in books you liked or loved, with more ideas to explore."
    elif books:
        basis = "Inspired by topics on your shelf, with more ideas to explore."
    else:
        basis = "A varied starter shelf. Choose a topic to find something that interests you."
    if age is None:
        basis += " Starter picks; check publisher age guidance together."
    basis += " Publisher ages are broad guidance, not reading levels. Reflections are never used for suggestions."
    return {"results": results, "basis": basis}
