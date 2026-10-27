"""Match category restrictions against accepted, source-owned evidence only."""


def matches_category(context, category_id):
    """Retain old scalar facts and categories frozen with new source tags.

    Skill IDs alone cannot recover a historical category after reparenting.
    Deliberately leave those old facts unchanged instead of reinterpreting them
    through today's taxonomy or granting previously unearned progress.
    """
    if type(category_id) is not int or category_id < 1:
        return False
    scalar = context.get("skill_category_id")
    if type(scalar) is int and scalar == category_id:
        return True
    tags = context.get("skill_tags")
    return isinstance(tags, list) and any(
        isinstance(tag, dict) and type(tag.get("category_id")) is int
        and tag["category_id"] == category_id for tag in tags
    )
