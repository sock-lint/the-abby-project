"""Add a server-owned promise without awarding or rewriting saved quests."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("quests", "0007_catalog_goal_retirement")]

    operations = [
        migrations.AddField(
            model_name="quest", name="reward_items_snapshot",
            field=models.JSONField(
                blank=True, editable=False, null=True,
                help_text="Server-owned accepted item IDs/quantities; null retains pre-cutover definition links.",
            ),
        ),
    ]
