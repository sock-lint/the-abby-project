from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="projects.User")
def create_character_profile(sender, instance, created, **kwargs):
    """Auto-create a CharacterProfile when a new User is created."""
    if created:
        from apps.rpg.models import CharacterProfile

        CharacterProfile.objects.get_or_create(user=instance)
