"""State-only deletion of ProjectIngestionJob — now in apps.ingestion.

Paired with ``ingestion/0001_initial`` which state-creates the model
under the ``ingestion`` app label, preserving the underlying Postgres
table (``projects_projectingestionjob``). Zero SQL emitted.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0013_move_notification_out"),
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="ProjectIngestionJob"),
            ],
        ),
    ]
