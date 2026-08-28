from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("", include(router.urls)),
    path("push/config/", views.PushConfigView.as_view(), name="push-config"),
    path("push/subscribe/", views.PushSubscribeView.as_view(), name="push-subscribe"),
    path(
        "push/unsubscribe/",
        views.PushUnsubscribeView.as_view(),
        name="push-unsubscribe",
    ),
]
