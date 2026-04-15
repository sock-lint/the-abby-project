from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        PARENT = "parent", "Parent"
        CHILD = "child", "Child"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CHILD)
    hourly_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("8.00")
    )
    display_name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    theme = models.CharField(
        max_length=20, default="summer",
        choices=[
            ("summer", "Summer"),
            ("winter", "Winter Break"),
            ("spring", "Spring Break"),
            ("autumn", "Autumn"),
        ],
    )

    objects = CustomUserManager()

    class Meta:
        # Preserve original table name so the move is a state-only migration.
        db_table = "projects_user"

    @property
    def display_label(self) -> str:
        """Human-facing name: display_name when set, otherwise username.

        Single source of truth — imported by serializers (as a CharField
        source) and any code that formats user names (emails, CSV exports,
        MCP payloads).
        """
        return self.display_name or self.username

    def __str__(self):
        return self.display_label
