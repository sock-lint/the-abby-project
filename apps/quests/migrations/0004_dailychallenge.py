# Generated for the 2026-04-23 daily-challenge feature.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('quests', '0003_quest_skill_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyChallenge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('challenge_type', models.CharField(
                    max_length=20,
                    choices=[
                        ('clock_hour', 'Clock an hour today'),
                        ('chores', 'Finish N chores today'),
                        ('habits', 'Log N habits today'),
                        ('homework', 'Finish N homework today'),
                        ('milestone', 'Clear a milestone today'),
                    ],
                )),
                ('target_value', models.PositiveIntegerField(default=1)),
                ('current_progress', models.PositiveIntegerField(default=0)),
                ('date', models.DateField(db_index=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('coin_reward', models.PositiveIntegerField(default=10)),
                ('xp_reward', models.PositiveIntegerField(default=20)),
                ('user', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='daily_challenges',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-date'],
                'unique_together': {('user', 'date')},
            },
        ),
    ]
