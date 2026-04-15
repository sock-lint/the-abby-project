"""Adopt Notification from apps.projects via state-only migration.

The physical table (``projects_notification``) was created by
``projects/0002_notification`` and subsequently altered by
``projects/0006``, ``0009``, ``0010``, ``0011``, and ``0012``. This
migration teaches Django's model state that the table now belongs to
``apps.notifications`` with the final field shape after all prior
alters applied. No SQL is emitted.

Paired with ``projects/0013_move_notification_out`` which state-deletes
the same model from the ``projects`` app.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0012_alter_notification_notification_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Notification",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("title", models.CharField(max_length=200)),
                        ("message", models.TextField(blank=True)),
                        ("notification_type", models.CharField(
                            choices=[
                                ("timecard_ready", "Timecard Ready"),
                                ("timecard_approved", "Timecard Approved"),
                                ("badge_earned", "Badge Earned"),
                                ("project_approved", "Project Approved"),
                                ("project_changes", "Changes Requested"),
                                ("payout_recorded", "Payout Recorded"),
                                ("skill_unlocked", "Skill Unlocked"),
                                ("milestone_completed", "Milestone Completed"),
                                ("redemption_requested", "Redemption Requested"),
                                ("chore_submitted", "Chore Submitted"),
                                ("chore_approved", "Chore Approved"),
                                ("exchange_requested", "Exchange Requested"),
                                ("exchange_approved", "Exchange Approved"),
                                ("exchange_denied", "Exchange Denied"),
                                ("project_due_soon", "Project Due Soon"),
                                ("chore_reminder", "Chore Reminder"),
                                ("approval_reminder", "Approval Reminder"),
                                ("homework_created", "Homework Created"),
                                ("homework_submitted", "Homework Submitted"),
                                ("homework_approved", "Homework Approved"),
                                ("homework_rejected", "Homework Rejected"),
                                ("homework_due_soon", "Homework Due Soon"),
                                ("streak_milestone", "Streak Milestone"),
                                ("perfect_day", "Perfect Day"),
                                ("daily_check_in", "Daily Check-In"),
                            ],
                            max_length=25,
                        )),
                        ("is_read", models.BooleanField(default=False)),
                        ("link", models.CharField(blank=True, default="", max_length=255)),
                        ("user", models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="notifications",
                            to=settings.AUTH_USER_MODEL,
                        )),
                    ],
                    options={
                        "db_table": "projects_notification",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
        ),
    ]
