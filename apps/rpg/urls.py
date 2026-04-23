from django.urls import path

from . import sprite_admin_views, views

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
    path("cosmetics/catalog/", views.CosmeticCatalogView.as_view(), name="cosmetics-catalog"),
    path("character/equip/", views.EquipCosmeticView.as_view(), name="character-equip"),
    path("character/unequip/", views.UnequipCosmeticView.as_view(), name="character-unequip"),
    path("character/trophy/", views.TrophyBadgeView.as_view(), name="character-trophy"),
    path("sprites/catalog/", views.SpriteCatalogView.as_view(), name="sprite-catalog"),
    path(
        "sprites/admin/",
        sprite_admin_views.SpriteAdminListView.as_view(),
        name="sprite-admin-list",
    ),
    path(
        "sprites/admin/generate/",
        sprite_admin_views.SpriteGenerateView.as_view(),
        name="sprite-admin-generate",
    ),
    path(
        "sprites/admin/<slug:slug>/",
        sprite_admin_views.SpriteAdminDetailView.as_view(),
        name="sprite-admin-detail",
    ),
    path(
        "sprites/admin/<slug:slug>/reroll/",
        sprite_admin_views.SpriteRerollView.as_view(),
        name="sprite-admin-reroll",
    ),
]
