"""Read-only presentation of an account's saved, equipped identity."""

from .serializers import CharacterProfileSerializer


IDENTITY_RELATED_FIELDS = ("active_frame", "active_title", "active_trophy_badge")


def earned_identity(user, profile, *, request=None):
    """Project existing selections without initializing a character or rewards.

    Callers own access checks. Refuse mismatched profiles as defense in depth;
    this compact shape contains no progression, private notes or family data.
    """
    if profile is None or profile.user_id != user.pk:
        return None

    def cosmetic(item):
        compact = CharacterProfileSerializer._compact_item(item)
        return {**compact, "slug": item.slug} if compact else None

    avatar = user.avatar.url if user.avatar else None
    if avatar and request is not None:
        avatar = request.build_absolute_uri(avatar)

    return {
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_label,
        "avatar": avatar,
        "active_frame": cosmetic(profile.active_frame),
        "active_title": cosmetic(profile.active_title),
        "active_trophy_badge": CharacterProfileSerializer().get_active_trophy_badge(profile),
    }
