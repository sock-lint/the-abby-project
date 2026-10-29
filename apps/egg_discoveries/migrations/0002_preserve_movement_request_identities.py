"""Retain known movement UUIDs without replaying any activity or rewards."""
from django.db import migrations


def preserve_existing_request_identities(apps, schema_editor):
    session_model = apps.get_model("movement", "MovementSession")
    credit_model = apps.get_model("egg_discoveries", "DiscoveryActivityCredit")
    alias = schema_editor.connection.alias
    pending = []
    for user_id, request_id, day, minutes in session_model.objects.using(alias).filter(
        client_request_id__isnull=False,
    ).values_list("user_id", "client_request_id", "occurred_on", "duration_minutes").iterator(chunk_size=1000):
        pending.append(credit_model(
            user_id=user_id, source_kind="movement_session", source_key=str(request_id),
            category="movement", occurred_on=day, minutes=minutes, credited_minutes=0,
        ))
        if len(pending) == 1000:
            credit_model.objects.using(alias).bulk_create(pending, batch_size=1000, ignore_conflicts=True)
            pending = []
    if pending:
        credit_model.objects.using(alias).bulk_create(pending, batch_size=1000, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("egg_discoveries", "0001_initial"),
        ("movement", "0004_session_distance_and_request_id"),
    ]

    operations = [migrations.RunPython(preserve_existing_request_identities, migrations.RunPython.noop)]
