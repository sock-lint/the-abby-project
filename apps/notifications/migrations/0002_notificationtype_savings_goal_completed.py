"""Add ``SAVINGS_GOAL_COMPLETED`` to ``NotificationType``.

Fired by ``SavingsGoalService._fire_completion_pipeline`` when a child
crosses a savings goal's target.
"""

from django.db import migrations, models


NOTIFICATION_TYPE_CHOICES = [
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
    ("savings_goal_completed", "Savings Goal Completed"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=NOTIFICATION_TYPE_CHOICES,
                max_length=25,
            ),
        ),
    ]
