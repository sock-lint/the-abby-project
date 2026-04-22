from rest_framework.routers import DefaultRouter

from apps.chronicle.views import ChronicleViewSet

router = DefaultRouter(trailing_slash=True)
router.register("chronicle", ChronicleViewSet, basename="chronicle")

urlpatterns = router.urls
