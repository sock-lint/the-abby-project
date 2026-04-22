from datetime import date
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
    date_of_birth = models.DateField(null=True, blank=True)
    grade_entry_year = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Calendar year of August she entered 9th grade (e.g. 2025).",
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

    # ------------------------------------------------------------------
    # Age / grade / chapter derivations
    # ------------------------------------------------------------------

    @property
    def age_years(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def _chapter_year(self, today: date | None = None) -> int | None:
        """The August-starting year covering `today`. 2025 = Aug 2025–Jul 2026."""
        today = today or date.today()
        return today.year if today.month >= 8 else today.year - 1

    @property
    def current_grade(self) -> int | None:
        if self.grade_entry_year is None:
            return None
        chapter_year = self._chapter_year()
        if chapter_year is None:
            return None
        return 9 + (chapter_year - self.grade_entry_year)

    @property
    def school_year_label(self) -> str | None:
        grade = self.current_grade
        if grade is None:
            return None
        if 9 <= grade <= 12:
            return {9: "Freshman", 10: "Sophomore", 11: "Junior", 12: "Senior"}[grade]
        if grade < 9:
            return f"Grade {grade}"
        # Post-HS: "Age {n} · {yyyy}-{yy}"
        age = self.age_years
        cy = self._chapter_year()
        if age is None or cy is None:
            return None
        return f"Age {age} · {cy}-{str(cy + 1)[-2:]}"

    @property
    def days_until_adult(self) -> int | None:
        if not self.date_of_birth:
            return None
        try:
            eighteenth = self.date_of_birth.replace(year=self.date_of_birth.year + 18)
        except ValueError:
            # Feb 29 → Mar 1 on non-leap 18th year
            eighteenth = date(self.date_of_birth.year + 18, 3, 1)
        return (eighteenth - date.today()).days
