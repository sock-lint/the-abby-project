from django.contrib import admin

from .models import Family


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "primary_parent", "created_at")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("primary_parent",)
    prepopulated_fields = {"slug": ("name",)}
