"""Give existing children the same twice-daily routine as new children."""
from django.db import migrations, models


def install_starter_habits(apps, schema_editor):
    # Keep this snapshot independent of future runtime catalog changes.
    User = apps.get_model("accounts", "User")
    Family = apps.get_model("families", "Family")
    Habit = apps.get_model("habits", "Habit")
    alias = schema_editor.connection.alias
    users = User.objects.using(alias)
    habits = Habit.objects.using(alias)
    for family in Family.objects.using(alias).all().iterator():
        author = users.filter(
            family_id=family.pk, role="parent", is_active=True,
        ).order_by("pk").first()
        for child in users.filter(family_id=family.pk, role="child").iterator():
            if habits.filter(user_id=child.pk, starter_key="brush_teeth").exists():
                continue
            legacy = habits.filter(
                models.Q(name__iexact="Brush teeth") | models.Q(name__iexact="Brush your teeth"),
                user_id=child.pk, starter_key__isnull=True, habit_type="positive",
                max_taps_per_day=2, pending_parent_review=False,
            ).order_by("pk").first()
            if legacy is not None:
                habits.filter(pk=legacy.pk).update(starter_key="brush_teeth")
                continue
            habits.create(
                user_id=child.pk, created_by_id=author.pk if author else child.pk,
                starter_key="brush_teeth", name="Brush your teeth", icon="🪥",
                habit_type="positive", max_taps_per_day=2, xp_reward=5,
                strength=0, is_active=True, pending_parent_review=False,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("habits", "0006_habit_last_decay_date"),
        ("accounts", "0007_user_family_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="habit",
            name="starter_key",
            field=models.CharField(
                blank=True, editable=False, max_length=50, null=True,
                help_text="Stable identity for a child's installed starter routine.",
            ),
        ),
        migrations.AddConstraint(
            model_name="habit",
            constraint=models.UniqueConstraint(
                fields=("user", "starter_key"),
                condition=models.Q(starter_key__isnull=False),
                name="habit_user_starter_key_unique",
            ),
        ),
        # Removing these records would delete a child's real completion history.
        migrations.RunPython(install_starter_habits, migrations.RunPython.noop),
    ]
