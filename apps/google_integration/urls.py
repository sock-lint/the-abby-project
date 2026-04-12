from django.urls import path

from . import views

urlpatterns = [
    path("auth/google/", views.GoogleAuthInitView.as_view(), name="google-auth-init"),
    path("auth/google/login/", views.GoogleLoginView.as_view(), name="google-auth-login"),
    path("auth/google/callback/", views.GoogleCallbackView.as_view(), name="google-auth-callback"),
    path("auth/google/account/", views.GoogleAccountView.as_view(), name="google-account"),
    path("auth/google/calendar/", views.CalendarSettingsView.as_view(), name="google-calendar-settings"),
    path("auth/google/calendar/sync/", views.CalendarSyncView.as_view(), name="google-calendar-sync"),
]
