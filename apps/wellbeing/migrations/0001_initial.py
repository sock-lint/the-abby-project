from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyWellbeingEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date', models.DateField(db_index=True)),
                ('affirmation_slug', models.CharField(max_length=80)),
                ('gratitude_lines', models.JSONField(blank=True, default=list)),
                ('coin_paid_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wellbeing_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'daily wellbeing entries',
                'ordering': ['-date'],
                'unique_together': {('user', 'date')},
            },
        ),
    ]
