"""State-only migration: ``Creation`` now inherits its audit fields from
``config.base_models.ApprovalWorkflowModel`` instead of declaring them inline.

The resulting field set on ``Creation`` is identical (``decided_at`` +
``decided_by`` with the same column types, nullability, on_delete, and
related_name as before), so this migration is a no-op at the schema level —
no ``AlterField`` is needed. We leave it as a documented checkpoint so the
inheritance switch shows up in the migration graph.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('creations', '0002_alter_creationdailycounter_user'),
    ]

    operations = []
