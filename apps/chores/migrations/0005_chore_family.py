"""Audit C1: add per-family scoping to Chore.

3-step migration mirrors apps.rewards.migrations.0008_reward_family:

  1. Add ``family`` FK as nullable so existing rows survive.
  2. Backfill into the ``default-family`` Family row (created if missing).
  3. Tighten to non-null.

Production rollout safety: between step 1 and step 3, ``Chore.save()``'s
defense-in-depth auto-attach (added in the same PR) catches any concurrent
writes that missed the family stamp. Same pattern that protected
``Reward`` and ``ProjectTemplate`` rollouts.
"""
from django.db import migrations, models


def backfill_default_family(apps, schema_editor):
    Family = apps.get_model("families", "Family")
    Chore = apps.get_model("chores", "Chore")
    if not Chore.objects.filter(family__isnull=True).exists():
        return
    family, _ = Family.objects.get_or_create(
        slug="default-family",
        defaults={"name": "Default Family"},
    )
    Chore.objects.filter(family__isnull=True).update(family=family)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("chores", "0004_chore_pending_parent_review"),
        ("families", "0001_initial"),
    ]

    operations = [
        # 1. Add the FK as nullable so existing rows survive.
        migrations.AddField(
            model_name="chore",
            name="family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="chores",
                to="families.family",
            ),
        ),
        # 2. Backfill into the default family.
        migrations.RunPython(backfill_default_family, noop_reverse),
        # 3. Tighten to non-null.
        migrations.AlterField(
            model_name="chore",
            name="family",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="chores",
                to="families.family",
            ),
        ),
    ]
