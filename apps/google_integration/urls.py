from django.urls import path

from . import views

urlpatterns = [
    path("auth/google/drive/config/", views.GoogleDriveConfigView.as_view(), name="google-drive-config"),
    path("auth/google/drive/file/", views.GoogleDriveFileView.as_view(), name="google-drive-file"),
    path("auth/google/drive/sources/", views.GoogleDriveSourcesView.as_view(), name="google-drive-sources"),
    path("auth/google/drive/upload/", views.GoogleDriveUploadView.as_view(), name="google-drive-upload"),
    path("auth/google/", views.GoogleAuthInitView.as_view(), name="google-auth-init"),
    path("auth/google/config/", views.GoogleOAuthConfigView.as_view(), name="google-oauth-config"),
    path("auth/google/exchange/", views.GoogleExchangeView.as_view(), name="google-auth-exchange"),
    path("auth/google/login/", views.GoogleLoginView.as_view(), name="google-auth-login"),
    path("auth/google/callback/", views.GoogleCallbackView.as_view(), name="google-auth-callback"),
    path("auth/google/account/", views.GoogleAccountView.as_view(), name="google-account"),
    path("auth/google/calendar/", views.CalendarSettingsView.as_view(), name="google-calendar-settings"),
    path("auth/google/calendar/sync/", views.CalendarSyncView.as_view(), name="google-calendar-sync"),
]
