import os

from django.db import migrations


DEFAULT_SLUG = "default-family"


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Family = apps.get_model("families", "Family")
    if not User.objects.exists():
        return

    name = os.environ.get("DEFAULT_FAMILY_NAME", "Default Family")
    family, _created = Family.objects.get_or_create(
        slug=DEFAULT_SLUG,
        defaults={"name": name},
    )
    if family.primary_parent_id is None:
        first_parent = (
            User.objects.filter(role="parent", is_active=True)
            .order_by("id")
            .first()
        )
        if first_parent:
            family.primary_parent_id = first_parent.id
            family.save(update_fields=["primary_parent"])
    User.objects.filter(family__isnull=True).update(family=family)


def backwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.update(family=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_user_family_nullable"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
