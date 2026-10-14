"""Corrections remove unpaid contributions while preserving awarded receipts."""
from django.db.models.signals import post_delete

SOURCES = {
    "movement.MovementSession": "movement_session",
    "timecards.TimeEntry": "clock_out",
    "chores.ChoreCompletion": "chore_complete",
    "homework.HomeworkSubmission": "homework_complete",
    "homework.HomeworkAssignment": "homework_created",
    "habits.HabitLog": "habit_log",
    "creations.Creation": "creation_logged",
    "chronicle.ChronicleEntry": "journal_entry",
    "projects.Project": "project_complete",
    "projects.ProjectMilestone": "milestone_complete",
    "projects.SavingsGoal": "savings_goal_complete",
    "pets.MountExpedition": "expedition_returned",
}


def source_deleted(sender, instance, **kwargs):
    from .models import ChallengeActivity
    from .goals import void_activity
    source_type = SOURCES[sender._meta.label]
    facts = ChallengeActivity.objects.filter(source_type=source_type, source_id=str(instance.pk), voided=False)
    for fact in facts.select_related("user"):
        void_activity(fact.user, source_type, instance.pk)


def connect_source_deletions():
    for model in SOURCES:
        post_delete.connect(source_deleted, sender=model, dispatch_uid=f"challenges.source_deleted.{model}")
