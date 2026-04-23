"""Child-proposed rituals gated by parent review.

Adds ``Habit.pending_parent_review`` so children can propose rituals
(name/icon/habit_type/max_taps_per_day only) that stay hidden from
their tap surface until a parent sets ``xp_reward`` + skill tags and
publishes via ``POST /api/habits/{id}/approve/``. Those reward fields
are stripped server-side on child create regardless of payload.

Indexed because ``HabitViewSet.get_queryset`` (child branch) and
``HabitService.log_tap`` filter on it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0004_habit_skill_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="habit",
            name="pending_parent_review",
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
