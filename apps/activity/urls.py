from rest_framework.routers import DefaultRouter

from .views import ActivityEventViewSet

router = DefaultRouter()
router.register(r"activity", ActivityEventViewSet, basename="activity")

urlpatterns = router.urls
