from django.urls import path

from . import views

urlpatterns = [
    path("character/", views.CharacterView.as_view(), name="character"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("inventory/", views.InventoryView.as_view(), name="inventory"),
    path(
        "inventory/<int:item_id>/use/",
        views.UseConsumableView.as_view(),
        name="use-consumable",
    ),
    path("items/catalog/", views.ItemCatalogView.as_view(), name="item-catalog"),
    path("drops/recent/", views.RecentDropsView.as_view(), name="recent-drops"),
    path("cosmetics/", views.CosmeticsView.as_view(), name="cosmetics"),
    path("character/equip/", views.EquipCosmeticView.as_view(), name="character-equip"),
    path("character/unequip/", views.UnequipCosmeticView.as_view(), name="character-unequip"),
]
