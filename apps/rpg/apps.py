from django.apps import AppConfig


class RpgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rpg"
    verbose_name = "RPG"

    def ready(self):
        import apps.rpg.signals  # noqa: F401
