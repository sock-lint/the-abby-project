"""Child-proposed duties gated by parent review.

Adds ``Chore.pending_parent_review`` so children can propose duties
(title/icon/recurrence only) that stay hidden from every child's tap
surface until a parent opens the proposal, sets rewards + skill tags,
and publishes via ``POST /api/chores/{id}/approve/``. Reward fields
(``reward_amount``, ``coin_reward``, ``xp_reward``) and skill tags are
stripped server-side on child create regardless of payload.

Indexed because every child-facing chore queryset now filters on it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chores", "0003_chore_skill_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="chore",
            name="pending_parent_review",
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
