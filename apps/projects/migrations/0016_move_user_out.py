"""State-only removal of User — now in apps.accounts.

Paired with ``accounts/0001_initial`` which state-creates the model
under the ``accounts`` app label, preserving the underlying Postgres
table (``projects_user``). Zero SQL emitted.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0015_move_skillcategory_out"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="User"),
            ],
        ),
    ]
