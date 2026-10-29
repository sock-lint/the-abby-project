from django.urls import path

from . import views


urlpatterns = [
    path("", views.DiscoveriesView.as_view(), name="egg-discoveries"),
    path("select/", views.SelectView.as_view(), name="select-egg-discovery"),
    path("<int:pk>/pause/", views.PauseView.as_view(), name="pause-egg-discovery"),
    path("practice/", views.PracticeView.as_view(), name="egg-discovery-practice"),
]
