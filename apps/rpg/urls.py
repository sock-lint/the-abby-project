from django.urls import path

from . import progression_views, sprite_admin_views, views

urlpatterns = [
    path("rpg/progression-lab/", progression_views.ProgressionLabView.as_view(), name="progression-lab"),
    path(
        "rpg/progression-lab/simulate/",
        progression_views.ProgressionSimulationView.as_view(),
        name="progression-lab-simulate",
    ),
    path("character/", views.CharacterView.as_view(), name="character"),
    path("character/avatar/", views.AvatarPreferencesView.as_view(), name="character-avatar"),
    path("character/avatar/catalog/", views.AvatarCatalogView.as_view(), name="avatar-catalog"),
    path("character/avatar/configuration/", views.AvatarConfigurationView.as_view(), name="avatar-configuration"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("inventory/", views.InventoryView.as_view(), name="inventory"),
    path(
        "inventory/<int:item_id>/use/",
        views.UseConsumableView.as_view(),
        name="use-consumable",
    ),
    path(
        "inventory/<int:item_id>/open/",
        views.OpenCoinPouchView.as_view(),
        name="open-coin-pouch",
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
    # Tombstones prevent old clients receiving a misleading SPA HTML response.
    path(
        "sprites/admin/generate/",
        sprite_admin_views.SpriteGenerationRetiredView.as_view(),
        name="sprite-admin-generate-retired",
    ),
    path(
        "sprites/admin/<slug:slug>/reroll/",
        sprite_admin_views.SpriteGenerationRetiredView.as_view(),
        name="sprite-admin-reroll-retired",
    ),
    path(
        "sprites/admin/<slug:slug>/",
        sprite_admin_views.SpriteAdminDetailView.as_view(),
        name="sprite-admin-detail",
    ),
]
