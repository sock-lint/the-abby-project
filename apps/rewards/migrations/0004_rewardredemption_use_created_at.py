# Generated 2026-04-14
#
# RewardRedemption now inherits from ``config.base_models.CreatedAtModel``
# alongside ``ApprovalWorkflowModel``. Rename the existing ``requested_at``
# column to ``created_at`` so the row's creation timestamp matches the
# convention used by every other approval model (ChoreCompletion,
# HomeworkSubmission, ExchangeRequest).
#
# The API continues to expose ``requested_at`` via a serializer alias, so
# no frontend change is required.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rewards', '0003_alter_decided_by_related_names'),
    ]

    operations = [
        migrations.RenameField(
            model_name='rewardredemption',
            old_name='requested_at',
            new_name='created_at',
        ),
        migrations.AlterModelOptions(
            name='rewardredemption',
            options={'ordering': ['-created_at']},
        ),
    ]
