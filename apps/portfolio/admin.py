from django.contrib import admin

from .models import ProjectPhoto


@admin.register(ProjectPhoto)
class ProjectPhotoAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "caption", "is_timelapse", "uploaded_at")
    list_filter = ("user", "is_timelapse", "uploaded_at")
    search_fields = ("project__title", "user__username", "caption")
    readonly_fields = ("uploaded_at",)
    date_hierarchy = "uploaded_at"
    autocomplete_fields = ("project", "user")
