from django.conf import settings
from django.db import models
from django.utils.text import slugify

from config.base_models import TimestampedModel


class Family(TimestampedModel):
    """A household — the scope unit for parents + children + per-family content.

    Parents and children belong to exactly one Family via ``User.family``.
    Per-family content (Reward, ProjectTemplate) carries its own ``family`` FK
    so the same name can exist across households without collisions. Global
    content (skills, badges, RPG items, lorebook) is family-agnostic.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, db_index=True)
    timezone = models.CharField(max_length=64, default="America/Phoenix")
    default_theme = models.CharField(
        max_length=20, default="hyrule",
        help_text="Cover applied for new members until they pick their own.",
    )
    primary_parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="founded_families",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "families"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "family"
            slug, n = base, 2
            while Family.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def parents(self):
        return self.members.filter(role="parent")

    @property
    def children(self):
        return self.members.filter(role="child")
