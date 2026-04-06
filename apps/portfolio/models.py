from django.conf import settings
from django.db import models


class ProjectPhoto(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="photos",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="portfolio/", blank=True, null=True)
    video_url = models.URLField(blank=True, null=True, help_text="YouTube/external video link or time-lapse URL")
    caption = models.CharField(max_length=255, blank=True)
    is_timelapse = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.project.title} — {self.caption or 'Photo'}"
