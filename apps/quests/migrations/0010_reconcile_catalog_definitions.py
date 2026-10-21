"""Reconcile only after PostgreSQL has committed the new FK and its index."""
from importlib import import_module

from django.db import migrations


reconcile_definitions = import_module(
    "apps.quests.migrations.0010_catalog_supersession",
).reconcile_definitions


class Migration(migrations.Migration):
    dependencies = [("quests", "0010_catalog_supersession")]

    operations = [
        migrations.RunPython(reconcile_definitions, migrations.RunPython.noop),
    ]
