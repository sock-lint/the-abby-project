from django.apps import AppConfig


class TimecardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.timecards"

    def ready(self):
        import apps.timecards.signals  # noqa: F401
