from django.db import migrations, models


def backfill_default_family(apps, schema_editor):
    Family = apps.get_model("families", "Family")
    Reward = apps.get_model("rewards", "Reward")
    if not Reward.objects.filter(family__isnull=True).exists():
        return
    family, _ = Family.objects.get_or_create(
        slug="default-family",
        defaults={"name": "Default Family"},
    )
    Reward.objects.filter(family__isnull=True).update(family=family)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0007_pr3_remove_homework_reward"),
        ("families", "0001_initial"),
    ]

    operations = [
        # 1. Drop the global unique on name first so backfilling cross-family
        #    duplicates doesn't trip the legacy constraint.
        migrations.AlterField(
            model_name="reward",
            name="name",
            field=models.CharField(max_length=100),
        ),
        # 2. Add the FK as nullable so existing rows survive.
        migrations.AddField(
            model_name="reward",
            name="family",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=models.deletion.CASCADE,
                related_name="rewards",
                to="families.family",
            ),
        ),
        # 3. Backfill into the default family.
        migrations.RunPython(backfill_default_family, noop_reverse),
        # 4. Tighten to non-null.
        migrations.AlterField(
            model_name="reward",
            name="family",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="rewards",
                to="families.family",
            ),
        ),
        # 5. Add the per-family unique-name constraint.
        migrations.AddConstraint(
            model_name="reward",
            constraint=models.UniqueConstraint(
                fields=["family", "name"],
                name="reward_unique_name_per_family",
            ),
        ),
    ]
