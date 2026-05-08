from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0006_proposal_notification_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
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
                    ("chore_rejected", "Chore Rejected"),
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
                    ("birthday", "Birthday"),
                    ("chronicle_first_ever", "Chronicle — first ever"),
                    ("comeback_suggested", "Comeback Quest Suggested"),
                    ("creation_submitted", "Creation Submitted"),
                    ("creation_approved", "Creation Approved"),
                    ("creation_rejected", "Creation Rejected"),
                    ("chore_proposed", "Duty Proposed"),
                    ("habit_proposed", "Ritual Proposed"),
                    ("chore_proposal_approved", "Duty Proposal Approved"),
                    ("habit_proposal_approved", "Ritual Proposal Approved"),
                    ("chore_proposal_rejected", "Duty Proposal Rejected"),
                    ("habit_proposal_rejected", "Ritual Proposal Rejected"),
                ],
                max_length=25,
            ),
        ),
    ]
