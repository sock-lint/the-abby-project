"""State-only deletion of Notification — now lives in apps.notifications.

Paired with ``notifications/0001_initial`` which state-creates the same
model under the ``notifications`` app label, preserving the underlying
Postgres table (``projects_notification``). Zero SQL emitted.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0012_alter_notification_notification_type"),
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Notification"),
            ],
        ),
    ]
