"""Adopt User from apps.projects via state-only migration.

Part of the AUTH_USER_MODEL move from ``projects.User`` to
``accounts.User``. The physical table (``projects_user``) was created
by ``projects/0001_initial``; this migration teaches Django's model
state that the table now belongs to ``apps.accounts``. No SQL is
emitted.

Paired with ``projects/0016_move_user_out`` which state-deletes the
model from the projects app.

Dependency strategy: we depend on ``projects/0015_move_skillcategory_out``
so this runs AFTER projects has built its full state (including the
historical CreateModel for User in projects/0001_initial). We then add
the accounts.User entry pointing at the same db_table.

Fresh DB order is identical — every migration with
``swappable_dependency(settings.AUTH_USER_MODEL)`` now resolves to
``("accounts", "0001_initial")`` via the new AUTH_USER_MODEL setting,
but we explicitly depend on projects/0015 so the historical
projects.User state is fully built (via projects/0001_initial) before
we try to register accounts.User against the same db_table.
"""

import django.contrib.auth.models
import django.contrib.auth.validators
import django.utils.timezone
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="User",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("password", models.CharField(max_length=128, verbose_name="password")),
                        ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                        ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                        ("username", models.CharField(error_messages={"unique": "A user with that username already exists."}, help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.", max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
                        ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                        ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                        ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                        ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                        ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                        ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                        ("role", models.CharField(choices=[("parent", "Parent"), ("child", "Child")], default="child", max_length=10)),
                        ("hourly_rate", models.DecimalField(decimal_places=2, default=Decimal("8.00"), max_digits=5)),
                        ("display_name", models.CharField(blank=True, max_length=100)),
                        ("avatar", models.ImageField(blank=True, null=True, upload_to="avatars/")),
                        ("theme", models.CharField(choices=[("summer", "Summer"), ("winter", "Winter Break"), ("spring", "Spring Break"), ("autumn", "Autumn")], default="summer", max_length=20)),
                        ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                        ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
                    ],
                    options={
                        "db_table": "projects_user",
                        "verbose_name": "user",
                        "verbose_name_plural": "users",
                        "abstract": False,
                    },
                    managers=[
                        ("objects", django.contrib.auth.models.UserManager()),
                    ],
                ),
            ],
        ),
    ]
