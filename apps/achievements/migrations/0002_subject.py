import django.db.models.deletion
from django.db import migrations, models


def create_default_subjects(apps, schema_editor):
    """Create one 'General' Subject per SkillCategory and assign all skills."""
    Subject = apps.get_model("achievements", "Subject")
    Skill = apps.get_model("achievements", "Skill")
    SkillCategory = apps.get_model("projects", "SkillCategory")

    for category in SkillCategory.objects.all():
        subject, _ = Subject.objects.get_or_create(
            category=category,
            name="General",
            defaults={"description": "Default subject group", "order": 0},
        )
        Skill.objects.filter(category=category, subject__isnull=True).update(
            subject=subject
        )


def drop_default_subjects(apps, schema_editor):
    Subject = apps.get_model("achievements", "Subject")
    Skill = apps.get_model("achievements", "Skill")
    Skill.objects.update(subject=None)
    Subject.objects.filter(name="General").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0001_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
                ("icon", models.CharField(blank=True, max_length=50)),
                ("order", models.IntegerField(default=0)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subjects",
                        to="projects.skillcategory",
                    ),
                ),
            ],
            options={
                "ordering": ["category", "order", "name"],
                "unique_together": {("category", "name")},
            },
        ),
        migrations.AddField(
            model_name="skill",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="skills",
                to="achievements.subject",
            ),
        ),
        migrations.AddField(
            model_name="badge",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="badges",
                to="achievements.subject",
            ),
        ),
        migrations.AlterField(
            model_name="badge",
            name="criteria_type",
            field=models.CharField(
                choices=[
                    ("projects_completed", "Projects Completed"),
                    ("hours_worked", "Hours Worked"),
                    ("category_projects", "Category Projects"),
                    ("streak_days", "Streak Days"),
                    ("first_project", "First Project"),
                    ("first_clock_in", "First Clock In"),
                    ("materials_under_budget", "Materials Under Budget"),
                    ("perfect_timecard", "Perfect Timecard"),
                    ("skill_level_reached", "Skill Level Reached"),
                    ("skills_unlocked", "Skills Unlocked"),
                    ("skill_categories_breadth", "Skill Categories Breadth"),
                    ("subjects_completed", "Subjects Completed"),
                    ("hours_in_day", "Hours in a Day"),
                    ("photos_uploaded", "Photos Uploaded"),
                    ("total_earned", "Total Earned"),
                    ("days_worked", "Days Worked"),
                    ("cross_category_unlock", "Cross-Category Unlock"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterModelOptions(
            name="skill",
            options={"ordering": ["category", "subject", "order"]},
        ),
        migrations.RunPython(create_default_subjects, drop_default_subjects),
    ]
