from django.apps import AppConfig


class QuestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.quests"

    def ready(self):
        from .signals import connect_source_deletions
        connect_source_deletions()
