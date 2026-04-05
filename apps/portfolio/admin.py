from django.contrib import admin

from .models import ProjectPhoto


@admin.register(ProjectPhoto)
class ProjectPhotoAdmin(admin.ModelAdmin):
    list_display = ["project", "user", "caption", "uploaded_at"]
    list_filter = ["project"]
    search_fields = ["caption"]
