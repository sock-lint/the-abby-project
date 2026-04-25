from django.urls import path

from .views import LorebookView


urlpatterns = [
    path("lorebook/", LorebookView.as_view(), name="lorebook"),
]
