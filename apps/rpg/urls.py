from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"habits", views.HabitViewSet, basename="habit")

urlpatterns = [
    path("character/", views.CharacterView.as_view(), name="character"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("inventory/", views.InventoryView.as_view(), name="inventory"),
    path("drops/recent/", views.RecentDropsView.as_view(), name="recent-drops"),
    path("cosmetics/", views.CosmeticsView.as_view(), name="cosmetics"),
    path("character/equip/", views.EquipCosmeticView.as_view(), name="character-equip"),
    path("character/unequip/", views.UnequipCosmeticView.as_view(), name="character-unequip"),
    path("", include(router.urls)),
]
