import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Reward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("icon", models.CharField(blank=True, max_length=50)),
                ("image", models.ImageField(blank=True, null=True, upload_to="rewards/")),
                ("cost_coins", models.PositiveIntegerField()),
                (
                    "rarity",
                    models.CharField(
                        choices=[
                            ("common", "Common"),
                            ("uncommon", "Uncommon"),
                            ("rare", "Rare"),
                            ("epic", "Epic"),
                            ("legendary", "Legendary"),
                        ],
                        default="common",
                        max_length=10,
                    ),
                ),
                (
                    "stock",
                    models.PositiveIntegerField(
                        blank=True, null=True,
                        help_text="Null = unlimited; otherwise remaining inventory.",
                    ),
                ),
                ("requires_parent_approval", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["order", "cost_coins", "name"]},
        ),
        migrations.CreateModel(
            name="RewardRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("denied", "Denied"),
                            ("fulfilled", "Fulfilled"),
                            ("canceled", "Canceled"),
                        ],
                        default="pending",
                        max_length=15,
                    ),
                ),
                (
                    "coin_cost_snapshot",
                    models.PositiveIntegerField(
                        help_text="Cost at time of request — authoritative for refunds.",
                    ),
                ),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("parent_notes", models.TextField(blank=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="decided_redemptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="redemptions",
                        to="rewards.reward",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="redemptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="CoinLedger",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.IntegerField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("hourly", "Hourly"),
                            ("project_bonus", "Project Bonus"),
                            ("bounty_bonus", "Bounty Bonus"),
                            ("milestone_bonus", "Milestone Bonus"),
                            ("badge_bonus", "Badge Bonus"),
                            ("redemption", "Redemption"),
                            ("refund", "Refund"),
                            ("adjustment", "Adjustment"),
                        ],
                        max_length=20,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_coin_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "redemption",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="coin_entries",
                        to="rewards.rewardredemption",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coin_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
