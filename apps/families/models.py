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


class FamilyInvite(TimestampedModel):
    """Single-use, expiring co-parent invite link.

    A parent mints one from Manage → Family; the invitee opens
    ``/join/<token>``, picks their own credentials, and lands in the
    inviter's family as a parent. Tokens are unguessable
    (``secrets.token_urlsafe(32)``), single-use (``used_at`` stamped
    under ``select_for_update`` in the redeem service), and expire after
    ``INVITE_TTL_HOURS``. The redeemed role is hard-coded to parent in
    ``FamilyService.create_parent_from_invite`` — children can never
    arrive through an invite link.
    """

    INVITE_TTL_HOURS = 24

    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, related_name="invites",
    )
    token = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_family_invites",
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="redeemed_family_invite",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "used" if self.used_at else "open"
        return f"Invite to {self.family.name} ({state})"

    @classmethod
    def mint(cls, *, family, created_by) -> "FamilyInvite":
        import secrets
        from datetime import timedelta

        from django.utils import timezone

        return cls.objects.create(
            family=family,
            created_by=created_by,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(hours=cls.INVITE_TTL_HOURS),
        )

    @property
    def is_open(self) -> bool:
        from django.utils import timezone
        return self.used_at is None and self.expires_at > timezone.now()
