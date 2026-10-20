"""Keep explicit category IDs valid through private definition insertion."""
from django.db import connection

from apps.achievements.models import SkillCategory


def lock_filter_category(trigger_filter):
    """Call after inserting the definition, in that same atomic transaction.

    The definition INSERT obtains ROW EXCLUSIVE before the category KEY SHARE.
    Taking the category first would invert publication/deletion's catalog-table
    then target-row order. A missing category rejects and rolls back the insert.
    """
    category_id = trigger_filter.get("skill_category_id") if isinstance(trigger_filter, dict) else None
    if not category_id:
        return
    if type(category_id) is not int or category_id < 1:
        raise ValueError("Choose an existing skill category.")
    if connection.vendor == "postgresql":
        table = connection.ops.quote_name(SkillCategory._meta.db_table)
        column = connection.ops.quote_name(SkillCategory._meta.pk.column)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {column} FROM {table} WHERE {column} = %s ORDER BY {column} FOR KEY SHARE", [category_id])
            found = cursor.fetchone() is not None
    else:
        found = SkillCategory.objects.filter(pk=category_id).exists()
    if not found:
        raise ValueError("Choose an existing skill category.")
