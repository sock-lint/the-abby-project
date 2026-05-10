# Adds the MountExpedition model — Finch-inspired offline mount adventures.
# A mount is sent on a 2/4/8h run, returns with pre-rolled loot. The partial
# unique constraint on (mount, status='active') prevents double-runs while
# leaving claimed/expired rows free for the audit trail.
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0007_userpet_consumable_growth_daily_cap'),
    ]

    operations = [
        migrations.CreateModel(
            name='MountExpedition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tier', models.CharField(choices=[('short', 'Short (2h)'), ('standard', 'Standard (4h)'), ('long', 'Long (8h)')], max_length=10)),
                ('status', models.CharField(choices=[('active', 'Active'), ('claimed', 'Claimed'), ('expired', 'Expired')], default='active', max_length=10)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('returns_at', models.DateTimeField()),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('loot', models.JSONField(blank=True, default=dict)),
                ('mount', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expeditions', to='pets.usermount')),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='mountexpedition',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'active')),
                fields=('mount',),
                name='unique_active_expedition_per_mount',
            ),
        ),
    ]
