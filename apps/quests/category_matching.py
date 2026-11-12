"""Match category restrictions against accepted, source-owned evidence only."""


def matches_category(context, category_id):
    """Retain old scalar facts and categories frozen with new source tags.

    Skill IDs alone cannot recover a historical category after reparenting.
    Deliberately leave those old facts unchanged instead of reinterpreting them
    through today's taxonomy or granting previously unearned progress.
    A source's explicit category snapshot takes precedence over older scalar
    or bonus-XP tags, including an empty or malformed snapshot failing closed.
    """
    if type(category_id) is not int or category_id < 1:
        return False
    if "category_skill_tags" not in context:
        scalar = context.get("skill_category_id")
        if type(scalar) is int and scalar == category_id:
            return True
    tags = context.get("category_skill_tags", context.get("skill_tags"))
    return isinstance(tags, list) and any(
        isinstance(tag, dict) and type(tag.get("category_id")) is int
        and tag["category_id"] == category_id for tag in tags
    )
