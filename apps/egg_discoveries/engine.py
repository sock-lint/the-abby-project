"""Pure activity allocation, independent of catalog, persistence and randomness."""
CATEGORIES = ("reading", "movement", "practice")


def ordinary_complete(minutes, requirements):
    return (
        sum(minutes.get(category, 0) for category in CATEGORIES) >= requirements["total_minutes"]
        and sum(minutes.get(category, 0) >= requirements["min_minutes_per_type"] for category in CATEGORIES)
        >= requirements["activity_types_required"]
    )


def rare_search_capacity(minutes, requirements):
    """Number of balanced 60-minute searches supported by cumulative effort.

    Keep cumulative totals rather than consuming a greedy pair: A30+B30,
    followed by C60, supports two searches just like A30+C60+B30. Earlier
    search results stay saved; only the allocation of their activity changes.
    """
    totals = [minutes.get(category, 0) for category in CATEGORIES]
    total = sum(totals)
    # A search can combine all three categories, with at most half its effort
    # from any one category. Count all minutes; rounding each category to
    # 30-minute blocks would unfairly strand a varied 100/100/100 routine.
    search_minutes = requirements["minutes_per_search"]
    minority_minutes = search_minutes - requirements["max_minutes_per_type_per_search"]
    return min(total // search_minutes, (total - max(totals)) // minority_minutes)
